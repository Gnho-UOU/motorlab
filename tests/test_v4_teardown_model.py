"""V4: 해체 치수 형상(data/benchmarks/prius2004_geometry_teardown.json)과 교정 Br 1.06 T의 FEA 맵을 ORNL 실측과 비교한다.

이 형상의 자석(18.9 × 6.5 mm)·슬롯 개구·공극·적층 길이는 ORNL TM-2010/253(해체 측정)과 TM-2004/217 값이다. 자석 Br은 시료 곡선
(TM-2004/137 그림 14, 1.243 T)이 아니라 **무부하 역기전력에 맞춘 교정값**이다. 같은 값을 공극 자속밀도(그림 13)와 잠금 토크 PM 성분이
독립적으로 확인한다. 통과 기준은 실측의 불확실성(그림에서 읽은 값 약 1%, 시험 온도 불명)에 맞춘 범위다. 계산 방법은 docs/FEA_OPTIONS.md 3-6절.
"""
import json
import math
from pathlib import Path

import numpy as np
import pytest
from scipy.interpolate import CubicSpline

from engine.model import FluxMapModel
from engine.operating import Limits, mtpa_point, optimal_current

ROOT = Path(__file__).resolve().parents[1]
GEOM = ROOT / "data" / "benchmarks" / "prius2004_geometry_teardown.json"
MAP = ROOT / "data" / "flux_maps" / "prius2004_fullmodel_teardown_25A.csv"
LOCKED = ROOT / "data" / "fea" / "prius2004_full_locked_torque_teardown.csv"
LOCKED_MEAS = ROOT / "data" / "benchmarks" / "prius2004_locked_torque.csv"
GAP_MEAS = ROOT / "data" / "benchmarks" / "prius2004_gap_flux_density.csv"
GAP_CMP = ROOT / "data" / "fea" / "prius2004_gap_flux_comparison_teardown_Br106.csv"
VARIANTS = ROOT / "data" / "fea" / "prius2004_efficiency_variants.csv"
EXCESS = ROOT / "data" / "fea" / "prius2004_excess_loss_fit.json"
PERF = ROOT / "data" / "benchmarks" / "prius2004_perf_map.csv"
SINE = ROOT / "data" / "benchmarks" / "prius2004_sine900.csv"


def _csv(path: Path):
    lines = [l for l in path.read_text().splitlines() if l.strip() and not l.startswith("#")]
    return lines[0].split(","), np.array([[float(x) if x else np.nan for x in l.split(",")] for l in lines[1:]])


def test_geometry_values_come_from_ornl_teardown():
    """TM-2010/253: 자석 18.9 × 6.5 mm, 슬롯 개구 1.93 mm, 공극 0.73025 mm, 회전자 적층 83.6 mm. 회전자 반지름은 TM-217 표 5.3의 80.19 mm."""
    g = json.loads(GEOM.read_text())
    h, sl = g["rotor"]["hole_HoleM50"], g["stator"]["slot_SlotW11"]
    assert h["W4"] == pytest.approx(0.0189) and h["H3"] == pytest.approx(0.0065)
    assert sl["W0"] == pytest.approx(0.00193)
    assert g["stator"]["Rint_m"] - g["rotor"]["Rext_m"] == pytest.approx(0.00073, abs=2e-6)
    assert g["stator"]["L1_m"] == pytest.approx(0.0836) and g["rotor"]["Rext_m"] == pytest.approx(0.08019)
    assert g["magnet"]["mur"] == pytest.approx(1.129)
    assert not h.get("air_strip_below_magnet")                       # 자석이 6.5 mm 두께 전체이다 (포켓 가설은 기각)
    assert "슬롯" in g["__source__"]["overrides"]["stator.slot_SlotW11.W1, W2, R1, H2"]      # 슬롯 면적 불일치를 기록했다


def test_map_header_states_br_is_calibrated():
    m = FluxMapModel.from_csv(MAP, p=4, Rs=0.0)
    assert "Br20 = 1.06" in m.source and "보정값" in m.source


def test_no_load_flux_matches_back_emf_by_construction():
    """Br 1.06 T는 무부하 역기전력 환산 0.174 Wb에 맞춘 교정값이다(맵 ψd(0,0) 0.1744 Wb)."""
    m = FluxMapModel.from_csv(MAP, p=4, Rs=0.0)
    assert abs(float(m.flux(0.0, 0.0)[0]) - 0.174) < 0.002


def test_gap_flux_density_matches_fig_13_independently():
    """교정에 쓰지 않은 측정: 그림 13의 공극 자속밀도 13점. 크기를 맞추지 않은 FEA의 크기비(측정/FEA) 1.00±0.04, RMS가 최대값의 5% 이하."""
    _, meas = _csv(GAP_MEAS)
    assert len(meas) == 13 and 0.74 < np.abs(meas[:, 1]).max() / 1e4 < 0.76
    head = [l for l in GAP_CMP.read_text().splitlines() if l.startswith("# 맞춤")][0]
    scale = float(head.split("크기 = ")[1].split(",")[0])
    rms = float(head.split("RMS = ")[1].split(" T")[0])
    assert 0.96 < scale < 1.04 and rms < 0.05 * 0.75


# --- 잠금 회전자 토크 (교정에 쓰지 않음) -------------------------------------------------------------------------------------------
PEAK = {75: 118.0, 150: 221.0, 250: 337.0}     # TM-423 그림 3.10
MEAS_COL = {75: 2, 150: 5, 250: 7}


def _locked():
    fea = np.array([[float(x) for x in l.split(",")] for l in LOCKED.read_text().splitlines()[1:]])
    _, meas = _csv(LOCKED_MEAS)
    return {Ia: CubicSpline(fea[fea[:, 0] == Ia][:, 1], fea[fea[:, 0] == Ia][:, 2]) for Ia in PEAK}, meas


def test_locked_peak_torque_within_7_percent():
    """75·150·250 A 잠금 토크 최대값 FEA/측정이 0.93~1.03 (측정 불확실성: 표 3.2와 그림 3.10의 차이 4% 안팎)."""
    curves, _ = _locked()
    g = np.linspace(0, 56.25, 5626)
    for Ia, peak in PEAK.items():
        assert 0.93 <= curves[Ia](g).max() / peak <= 1.03, Ia


def test_locked_torque_curve_shape_matches_with_one_angle_origin():
    """곡선 모양: 영점 하나(250 A에서 결정)와 거울 방향 가정으로 상관계수 > 0.99, RMS < 7%."""
    curves, meas = _locked()
    ang = meas[:, 0]
    c = min((np.sqrt(np.mean((curves[250](c - ang) - meas[:, 7]) ** 2)), c) for c in np.arange(100, 200, 0.05)
            if (c - ang).min() >= 0 and (c - ang).max() <= 56.25)[1]
    for Ia in PEAK:
        m, f = meas[:, MEAS_COL[Ia]], curves[Ia](c - ang)
        assert np.corrcoef(f, m)[0, 1] > 0.99 and np.sqrt(np.mean((f - m) ** 2)) / m.max() < 0.07


def test_required_current_matches_measurement_at_low_speed():
    """속도 < 1950 rpm, 토크 55~290 N·m에서 엔진 필요 전류 / (측정 상전류 실효값 × √2)가 0.93~1.07."""
    m = FluxMapModel.from_csv(MAP, p=4, Rs=0.0)
    hdr, A = _csv(PERF)
    col = {h: A[:, i] for i, h in enumerate(hdr)}
    sel = np.nonzero((col["torque_Nm"] > 55) & (col["torque_Nm"] < 290) & (col["speed_rpm"] > 500) & (col["speed_rpm"] < 1950))[0]
    lim = Limits(Imax=250.0, Vdc=500.0, k_mod=2 / math.pi)
    ratios = []
    for k in sel[np.linspace(0, len(sel) - 1, 8).astype(int)]:
        d, q, ok = optimal_current(m, lim, float(col["torque_Nm"][k]), col["speed_rpm"][k] * math.pi / 30)
        assert ok
        ratios.append(math.hypot(d, q) / (col["Iac_rms_A"][k] * math.sqrt(2)))
    assert all(0.93 <= r <= 1.07 for r in ratios), np.round(ratios, 2)


def test_mtpa_torque_at_250_a_matches_locked_rotor():
    m = FluxMapModel.from_csv(MAP, p=4, Rs=0.0)
    d, q = mtpa_point(m, 250.0)
    assert 315.0 <= float(m.torque(d, q)) <= 350.0          # ORNL 339 N·m (2005년 시험), 400 N·m (2004년)


def test_sine_supply_900_rpm_losses_are_all_copper_and_drag():
    """인버터 없는 60 Hz 정현파 시험(TM-2005/33)에서 측정 전류로 동손(R = 0.069 Ω @21 °C)과 구동계 마찰 160 W를 빼면 남는 손실이
    입력 전력의 ±2% 안이다. 인버터 시험의 잔여 손실(약 2 N·m·ω)이 정현파에서는 없다는 기록이다."""
    hdr, A = _csv(SINE)
    c = {h: A[:, i] for i, h in enumerate(hdr)}
    R20 = 0.069 / (1 + 0.00393)
    cu = 3 * R20 * (1 + 0.00393 * (c["T_winding_C"] - 20)) * c["I_A"] ** 2
    resid = c["P_elec_W"] - c["P_mech_W"] - 160.2 - cu
    hi = c["torque_Nm"] >= 60
    assert np.abs(resid[hi] / c["P_elec_W"][hi]).max() < 0.02


# --- 효율: 물리 모델만 대 경험적 잔여 손실 ------------------------------------------------------------------------------------------
def _variants():
    hdr, A = _csv(VARIANTS)
    c = {h: A[:, i] for i, h in enumerate(hdr)}
    core = (c["speed_rpm"] >= 1000) & (c["speed_rpm"] <= 4000) & (c["torque_Nm"] >= 30) & (c["torque_Nm"] <= 200)
    return c, core


def test_physics_only_efficiency_still_misses_g1():
    """V1(동손 + 무부하 실측 손실, 이중 계산 없음)은 효율을 체계적으로 높게 예측한다: 주요영역 평균 +3~5%p, 3%p 이내 행 < 60%.
    이중 계산을 없애면 V0보다 나빠진다(남은 손실이 드러남). 이 미달을 숨기지 않는 기록이다."""
    c, core = _variants()
    assert len(c["speed_rpm"]) == 380
    d1 = (c["eta_v1"] - c["eta_meas"]) * 100
    assert 3.0 < d1[core].mean() < 5.0 and (np.abs(d1[core]) <= 3).mean() < 0.6
    d0 = (c["eta_v0"] - c["eta_meas"]) * 100
    assert d1[core].mean() > d0[core].mean()


def test_empirical_excess_loss_closes_gap_inside_data_range_only():
    """V2(경험식 k_f·f + k_c·I²f²)는 같은 행에 맞춘 보정이다. 전체 RMS < 2%p, 주요영역 3%p 이내 행 ≥ 95%.
    홀드아웃과 외삽 오차를 JSON에 같이 기록했고, 외삽(3000 rpm 미만으로 맞춰 이상 평가)은 RMS 3%p를 넘는다."""
    c, core = _variants()
    d2 = (c["eta_v2"] - c["eta_meas"]) * 100
    assert np.sqrt((d2 ** 2).mean()) < 2.0 and (np.abs(d2[core]) <= 3).mean() >= 0.95
    j = json.loads(EXCESS.read_text())
    v = j["validation"]
    assert v["random_half_holdout_rms_pp"] < 2.0
    assert v["extrapolate_lt3000_to_ge3000_rms_pp"] > 3.0
    assert j["k_f_W_per_Hz"] == pytest.approx(3.5, abs=0.3) and j["k_c_W_per_A2Hz2"] == pytest.approx(4.9e-6, rel=0.2)
    assert "물리 기구 미규명" in j["what"]
