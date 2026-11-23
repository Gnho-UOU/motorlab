"""P4 (M4): 차량 모델, 주행 사이클, 전비 (docs/ENGINE_SPEC.md 5-1절, 기획서 5.5절).

차량·손실 값은 **테스트 전용 합성 값**이다(실제 차량 값은 data/vehicles/prius2004.json). 사이클 데이터는 출처가 있는 실제 파일이다.
"""
import math

import numpy as np
import pytest

from engine.losses import IronParams, MechParams, efficiency_map
from engine.vehicle import Cycle, Vehicle, load_cycle, load_vehicle, road_load_force, run_cycle

KMH = 1 / 3.6


# --- 사이클 데이터 -------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name, n, dist_km, vmax_kmh", [("WLTP", 1801, 23.27, 131.3), ("UDDS", 1370, 11.99, 91.2), ("HWFET", 766, 16.51, 96.4)])
def test_cycle_files_match_published_totals(name, n, dist_km, vmax_kmh):
    """WLTC 클래스 3b 23.26 km(규정 값), UDDS 7.45 mi, HWFET 10.26 mi (EPA)."""
    c = load_cycle(name)
    assert len(c.t_s) == n and c.t_s[0] == 0 and np.all(np.diff(c.t_s) == 1)
    assert np.trapezoid(c.v_ms, c.t_s) / 1000 == pytest.approx(dist_km, abs=0.02)
    assert c.v_ms.max() * 3.6 == pytest.approx(vmax_kmh, abs=0.1)
    assert c.v_ms[0] == 0
    assert "UNECE" in c.source or "EPA" in c.source


def test_cycle_unknown_name_raises():
    with pytest.raises(ValueError):
        load_cycle("NEDC")


# --- 도로 부하와 기어 ----------------------------------------------------------------------------------------------------------------
def make_vehicle(mass=300.0, a=0.0, b=0.0, c=0.0, gain=10.0, gear_loss=None) -> Vehicle:
    sp = np.array([0.0, 1000.0])
    return Vehicle(mass_kg=mass, road_a_N=a, road_b_Ns_m=b, road_c_Ns2_m2=c, motor_speed_gain=gain,
                   gear_speed_rad=sp, gear_loss_W=np.zeros(2) if gear_loss is None else np.asarray(gear_loss, float))


def test_road_load_force_polynomial():
    veh = make_vehicle(a=80.0, b=1.5, c=0.35)
    v = 27.78
    assert road_load_force(veh, v) == pytest.approx(80.0 + 1.5 * v + 0.35 * v**2)
    assert road_load_force(veh, 0.0) == pytest.approx(80.0)


def test_prius_preset_matches_sources():
    """EPA 2004 Prius 시험 차량(04-NHW2): 등가 시험 중량 3250 lb, 도로 부하 계수 A 19.917 lbf, B 0.13911 lbf/mph, C 0.016365 lbf/mph².
    ORNL TM-2006/423: 모터 회전수 [rpm] = 60.66 × 차속 [mph]."""
    veh = load_vehicle("prius2004")
    assert veh.mass_kg == pytest.approx(3250 * 0.45359237)
    lbf, mph = 4.4482216, 0.44704
    assert veh.road_a_N == pytest.approx(19.917 * lbf, rel=1e-6)
    assert veh.road_b_Ns_m == pytest.approx(0.13911 * lbf / mph, rel=1e-6)
    assert veh.road_c_Ns2_m2 == pytest.approx(0.016365 * lbf / mph**2, rel=1e-6)
    rpm_per_mph = veh.motor_speed_gain * mph * 30 / math.pi
    assert rpm_per_mph == pytest.approx(60.66, rel=1e-6)
    assert 380 < road_load_force(veh, 100 * KMH) < 430           # 100 km/h에서 약 400 N (약 11 kW)
    assert veh.gear_loss_W.size >= 10 and np.all(np.diff(veh.gear_speed_rad) > 0)


# --- 에너지 수지 ---------------------------------------------------------------------------------------------------------------------
@pytest.fixture
def lossless(model0, limits):
    T = np.linspace(1.0, 140.0, 70)
    w = np.linspace(2.0, 420.0, 90)
    return efficiency_map(model0, limits, T, w, None, None)


def triangle(peak=20.0, ramp=20):
    t = np.arange(0, 2 * ramp + 1, 1.0)
    v = np.concatenate([np.linspace(0, peak, ramp + 1), np.linspace(peak, 0, ramp + 1)[1:]])
    return Cycle("TRI", t, v, "테스트용")


def test_constant_speed_energy_equals_road_load_work(lossless):
    """손실이 없고 기어 손실이 0이면 등속 주행의 전기 에너지 = 도로 부하 일 (순수 항등식)."""
    veh = make_vehicle(a=50.0, b=0.0, c=0.2)
    t = np.arange(0, 101, 1.0)
    cyc = Cycle("CONST", t, np.full_like(t, 20.0), "테스트용")
    r = run_cycle(veh, lossless, cyc, regen_ratio=0.0)
    work = (50.0 + 0.2 * 20.0**2) * 20.0 * 100            # F · v · T [J]
    assert r.E_in_J == pytest.approx(work, rel=2e-3)
    assert r.distance_m == pytest.approx(2000.0)
    assert r.km_per_kWh == pytest.approx(2.0 / (work / 3.6e6), rel=2e-3)


def test_accelerate_then_brake_returns_kinetic_energy_when_lossless(lossless):
    """도로 부하 0, 모든 손실 0, 회생 비율 1이면 가속에 쓴 에너지를 감속에서 전부 되찾는다 (순 에너지 ≈ 0)."""
    veh = make_vehicle()
    r = run_cycle(veh, lossless, triangle(), regen_ratio=1.0)
    ke = 0.5 * 300.0 * 20.0**2
    assert r.E_in_J == pytest.approx(ke, rel=0.03)
    assert r.E_regen_J == pytest.approx(ke, rel=0.03)
    assert abs(r.E_net_J) < 0.03 * ke


def test_regen_ratio_scales_recovery_and_zero_means_friction_brakes(lossless):
    veh = make_vehicle()
    r0 = run_cycle(veh, lossless, triangle(), regen_ratio=0.0)
    r5 = run_cycle(veh, lossless, triangle(), regen_ratio=0.5)
    r1 = run_cycle(veh, lossless, triangle(), regen_ratio=1.0)
    assert r0.E_regen_J == 0.0
    assert r5.E_regen_J == pytest.approx(0.5 * r1.E_regen_J, rel=1e-9)
    assert r0.E_net_J > r5.E_net_J > r1.E_net_J
    assert r0.E_friction_brake_J > r5.E_friction_brake_J > r1.E_friction_brake_J >= 0
    with pytest.raises(ValueError):
        run_cycle(veh, lossless, triangle(), regen_ratio=1.5)


def test_gear_loss_adds_to_traction_and_reduces_regen(lossless):
    """기어 손실 L[W]: 구동에서는 모터가 P_w + L을 내고, 회생에서는 모터가 |P_w| − L만 받는다."""
    loss = 200.0
    veh0, veh1 = make_vehicle(), make_vehicle(gear_loss=[loss, loss])
    a, b = run_cycle(veh0, lossless, triangle(), 1.0), run_cycle(veh1, lossless, triangle(), 1.0)
    assert b.E_in_J > a.E_in_J and b.E_regen_J < a.E_regen_J
    assert (b.E_in_J - a.E_in_J) == pytest.approx(loss * 20.0, rel=0.2)             # 구동 약 20 s 동안 L·t
    assert (a.E_regen_J - b.E_regen_J) == pytest.approx(loss * 20.0, rel=0.2)


def test_losses_make_motor_energy_higher_and_regen_lower(model_rs, limits):
    iron = IronParams(k_h=0.02, k_e=5e-5, beta=2.0, m_tooth=3.0, m_yoke=6.0, c_tooth=20.0, c_yoke=10.0)
    mech = MechParams(a=0.01, b=2e-8)
    lossy = efficiency_map(model_rs, limits, np.linspace(1.0, 140.0, 70), np.linspace(2.0, 420.0, 90), iron, mech)
    r = run_cycle(make_vehicle(), lossy, triangle(), regen_ratio=1.0)
    ke = 0.5 * 300.0 * 20.0**2
    assert r.E_in_J > ke and r.E_regen_J < ke
    assert r.E_net_J > 0                                          # 왕복 손실
    assert r.E_motor_loss_J > 0


def test_undeliverable_torque_is_reported_not_hidden(lossless):
    """모터가 낼 수 없는 가속(토크 한계 초과)은 shortfall로 기록하고, 전기 에너지는 낼 수 있는 최대 토크로 센다."""
    veh = make_vehicle(mass=3000.0)                              # 20 s에 20 m/s를 만들려면 모터가 낼 수 없는 토크
    r = run_cycle(veh, lossless, triangle(), regen_ratio=1.0)
    assert r.shortfall_time_s > 0 and r.shortfall_wheel_energy_J > 0
    assert np.isfinite(r.E_net_J)


def test_prius_wltp_runs_and_balances():
    """실제 모터 맵(동손만, 철손·기계손 없음 = 모터 손실의 하한)으로 WLTP를 돌려 에너지 수지를 확인한다.
    도로 부하 일(바퀴 구동 에너지)보다 전기 소비가 크고, 구동 효율(바퀴 에너지 / 전기 소비)이 0.70~0.98이며 shortfall이 작다."""
    from pathlib import Path

    from engine.model import FluxMapModel
    from engine.operating import Limits

    root = Path(__file__).resolve().parents[1]
    Rs = 0.069 / 1.00393 * (1 + 0.00393 * 80)                    # 권선 80 °C 가정
    model = FluxMapModel.from_csv(root / "data" / "flux_maps" / "prius2004_fullmodel_teardown_25A.csv", p=4, Rs=Rs)
    lim = Limits(Imax=250.0, Vdc=500.0, k_mod=2 / math.pi)
    em = efficiency_map(model, lim, np.linspace(1.0, 250.0, 125), np.linspace(2.0, 640.0, 160), None, None)
    r = run_cycle(load_vehicle("prius2004"), em, load_cycle("WLTP"), regen_ratio=1.0)
    assert r.shortfall_wheel_energy_J < 0.02 * r.E_wheel_traction_J
    assert r.E_net_J == pytest.approx(r.E_in_J - r.E_regen_J)
    assert 0.70 < r.E_wheel_traction_J / r.E_in_J < 0.98
    assert r.E_net_J > r.E_wheel_traction_J - r.E_wheel_brake_J > 0         # 순 기계 일보다 전기 소비가 크다(손실)
    assert r.distance_m / 1000 == pytest.approx(23.27, abs=0.02)


def test_loss_power_series_matches_energy_totals(model_rs, limits):
    """시계열 손실 동력 [W]은 구동 구간의 적분이 E_motor_loss_J와 같고 음수가 아니며, 효율 시계열은 0~1이다. 손실 0이면 손실 시계열도 0이다."""
    iron = IronParams(k_h=0.02, k_e=5e-5, beta=2.0, m_tooth=3.0, m_yoke=6.0, c_tooth=20.0, c_yoke=10.0)
    lossy = efficiency_map(model_rs, limits, np.linspace(1.0, 140.0, 70), np.linspace(2.0, 420.0, 90), iron, MechParams(a=0.01, b=2e-8))
    r = run_cycle(make_vehicle(), lossy, triangle(), regen_ratio=1.0)
    dt = np.diff(triangle().t_s)
    drive = r.em_torque_Nm > 0
    assert np.all(r.loss_power_W >= -1e-9)
    assert float(np.sum(r.loss_power_W[drive] * dt[drive])) == pytest.approx(r.E_motor_loss_J, rel=1e-9)
    e = r.efficiency[np.isfinite(r.efficiency)]
    assert e.size > 0 and np.all((e >= 0) & (e <= 1))   # 아주 작은 회생 동력은 손실에 먹혀 효율 0이 될 수 있다
    assert np.all(np.isnan(r.efficiency[r.em_torque_Nm == 0]))


def test_current_series_is_bounded_and_zero_when_idle(model_rs, limits):
    """구간별 상전류 첨두값은 전류 한계 이하이고, 모터가 동작하지 않는 구간은 0이다. 같은 (T, ω)에서 맵의 값과 같다."""
    lossy = efficiency_map(model_rs, limits, np.linspace(1.0, 140.0, 70), np.linspace(2.0, 420.0, 90), None, None)
    r = run_cycle(make_vehicle(), lossy, triangle(), regen_ratio=1.0)
    assert np.all(r.current_peak_A >= 0) and r.current_peak_A.max() <= limits.Imax * (1 + 1e-6)
    assert np.all(r.current_peak_A[r.em_torque_Nm == 0] == 0)
    k = int(np.argmax(r.em_torque_Nm))
    j = int(np.argmin(np.abs(lossy.speed_grid - r.motor_speed_rad[k])))
    i = int(np.argmin(np.abs(lossy.T_grid - r.em_torque_Nm[k])))
    assert r.current_peak_A[k] == pytest.approx(np.hypot(lossy.id[i, j], lossy.iq[i, j]), rel=0.15)
