"""M7 열 모델(engine/thermal.py): 해석해와의 일치, 에너지 보존, ORNL TM-2005/33 측정과의 비교.

ORNL 비교는 자료 CSV(data/thermal/)로 하고, 보정에 쓴 자료와 쓰지 않은 자료를 나눠 판정한다(docs/validation_report.md M7 절).
"""
import csv
import math
from pathlib import Path

import numpy as np
import pytest

from engine.thermal import ThermalNetwork, load_lptn, simulate_cycle_copper

ROOT = Path(__file__).resolve().parents[1]


def test_single_node_rc_matches_the_exponential_solution():
    """한 노드: C dT/dt = P − G(T − Tb). T(t) = Tb + P/G + (T0 − Tb − P/G)·exp(−G t / C)."""
    C, G, P, Tb, T0 = 5000.0, 20.0, 800.0, 60.0, 30.0
    net = ThermalNetwork(["x"], [C], np.zeros((1, 1)), [G])
    T = np.array([T0])
    for _ in range(10):
        T = net.step(T, [P], Tb, 30.0)
    t = 300.0
    assert T[0] == pytest.approx(Tb + P / G + (T0 - Tb - P / G) * math.exp(-G * t / C), rel=1e-10)


def test_steady_state_balances_heat_flow_and_step_is_a_fixed_point():
    net = ThermalNetwork(["w", "s"], [2600.0, 8800.0], np.array([[0, 150.0], [150.0, 0]]), [0.0, 41.0])
    P = np.array([1000.0, 1000.0])
    Tss = net.steady_state(P, 100.0)
    assert 41.0 * (Tss[1] - 100.0) == pytest.approx(2000.0)                 # 밖으로 나가는 열 = 총 입력
    assert 150.0 * (Tss[0] - Tss[1]) == pytest.approx(1000.0)               # 권선에서 철심으로 흐르는 열 = 권선 손실
    assert np.allclose(net.step(Tss, P, 100.0, 600.0), Tss)


def test_step_composes_exactly():
    """같은 입력이면 dt 두 번 = 2·dt 한 번 (행렬 지수함수의 반군 성질)."""
    net = ThermalNetwork(["w", "s"], [2600.0, 8800.0], np.array([[0, 150.0], [150.0, 0]]), [0.0, 41.0])
    T0 = np.array([140.0, 90.0]); P = np.array([5000.0, 300.0])
    a = net.step(net.step(T0, P, 100.0, 7.0), P, 100.0, 7.0)
    b = net.step(T0, P, 100.0, 14.0)
    assert np.allclose(a, b, atol=1e-9)


def test_invalid_networks_are_rejected():
    with pytest.raises(ValueError):
        ThermalNetwork(["a", "b"], [1.0, 1.0], np.array([[0, 1.0], [2.0, 0]]), [1.0, 0.0])    # 비대칭
    with pytest.raises(ValueError):
        ThermalNetwork(["a"], [0.0], np.zeros((1, 1)), [1.0])                                  # 열용량 0
    with pytest.raises(ValueError):
        ThermalNetwork(["a", "b"], [1.0, 1.0], np.array([[0, 1.0], [1.0, 0]]), [0.0, 0.0])     # 경계로 가는 길이 없음


def _steady_rows():
    lines = [l for l in (ROOT / "data/thermal/prius2004_steady.csv").read_text().splitlines() if l[:1].isdigit()]
    return np.array([[float(x) for x in l.split(",")] for l in lines])


def test_prius_steady_winding_temperature_from_oil_temperature_within_6K():
    """ORNL 표 9·10의 평형 4점: 기름 온도와 손실(동손 → 권선, 철손+잔여 → 철심)에서 권선 온도를 예측한다. 예측에 쓴 G_sb는 같은 4점의 평균이라 독립 검증이 아니다."""
    p = load_lptn("prius2004")
    net = p.network()
    for Tc, Tq, Pt, Pm, Pcu, Pco, Tw, To, dT, fl in _steady_rows():
        T = net.steady_state([Pcu, Pco], To)
        assert abs(T[0] - Tw) < 6.0


def _peak_curves():
    out = {}
    for l in (ROOT / "data/thermal/prius2004_peak_winding_transient.csv").read_text().splitlines():
        if l[:1].isdigit():
            tq, I, t, T = (float(x) for x in l.split(","))
            out.setdefault(int(tq), []).append((t, T, I))
    return {k: np.array(v) for k, v in out.items()}


def test_prius_peak_winding_heating_curves_within_3K_given_the_initial_iron_temperature():
    """ORNL 그림 19의 다섯 곡선(900 rpm 첨두 시험). 철심 초기 온도는 측정되지 않아 곡선마다 맞춘 값(data/thermal/prius2004_lptn.json)을 쓴다."""
    p = load_lptn("prius2004")
    for tq, v in _peak_curves().items():
        Ts0 = p.fit_initial_stator_C[str(tq)]
        T = simulate_cycle_copper(p, v[:, 0], np.full(len(v), v[0, 2]), np.zeros(len(v)), T_boundary_C=p.boundary_fit_C,
                                  T_winding0_C=v[0, 1], T_stator0_C=Ts0, current_is_rms=True)["T_winding_C"]
        assert np.sqrt(np.mean((T - v[:, 1]) ** 2)) < 3.0


def test_cycle_copper_loss_energy_balance_and_temperature_feedback():
    """구간 입력(전류·기타 손실)을 주면 Σ(입력 열) = 저장된 열 + 경계로 나간 열이고, 같은 전류에서 온도가 오를수록 동손이 커진다."""
    p = load_lptn("prius2004")
    t = np.arange(0.0, 601.0, 1.0)
    I = np.full(len(t), 250.0)
    r = simulate_cycle_copper(p, t, I, np.full(len(t), 300.0), T_boundary_C=70.0, T_winding0_C=70.0, T_stator0_C=70.0)
    assert r["T_winding_C"][-1] > r["T_winding_C"][0] + 20
    assert np.all(np.diff(r["P_copper_W"]) >= -1e-9)                 # 같은 전류에서 온도 상승 → 동손 증가
    C = p.network().C
    stored = C[0] * (r["T_winding_C"][-1] - 70.0) + C[1] * (r["T_stator_C"][-1] - 70.0)
    dt = np.diff(t)
    heat_in = float(np.sum((r["P_copper_W"][:-1] + 300.0) * dt))
    lost = float(np.sum(p.G_stator_boundary_W_per_K * (r["T_stator_C"][:-1] - 70.0) * dt))
    assert heat_in - stored - lost == pytest.approx(0.0, abs=0.02 * heat_in)     # 구간 안의 온도 변화가 있어 2% 허용(구간 시작 값으로 적분)


def test_cycle_thermal_has_no_correction_when_temperature_equals_the_map_temperature_and_grows_with_heating():
    from types import SimpleNamespace

    from engine.thermal import cycle_thermal

    p = load_lptn("prius2004")
    t = np.arange(0.5, 300.0, 1.0)                                    # 구간 중점 시각 (1 s 간격)
    I = np.where(t < 150, 200.0, 0.0)
    R_map = 0.069
    res = SimpleNamespace(t_s=t, current_peak_A=I, loss_power_W=1.5 * R_map * I ** 2 + 400.0, E_net_J=1.0e6, distance_m=2000.0)
    # 권선이 맵 온도(=21 °C에서의 R21)와 같고 경계도 같은 온도에서 시작하며 전류가 0이면 보정이 0이다
    zero = SimpleNamespace(**{**res.__dict__, "current_peak_A": np.zeros_like(t), "loss_power_W": np.zeros_like(t)})
    r0 = cycle_thermal(zero, p, T_boundary_C=21.0, T_start_C=21.0, R_map_ohm=p.R21_ohm, T_map_C=21.0)
    assert r0["delta_E_J"] == pytest.approx(0.0, abs=1e-6) and np.allclose(r0["T_winding_C"], 21.0)
    # 맵 온도(21 °C)보다 뜨거워지면 동손이 늘어 에너지가 늘고 전비가 줄어든다
    r1 = cycle_thermal(res, p, T_boundary_C=21.0, T_start_C=21.0, R_map_ohm=p.R21_ohm, T_map_C=21.0)
    assert r1["delta_E_J"] > 0 and r1["E_net_J"] > res.E_net_J and r1["km_per_kWh"] < 2000.0 / 1000.0 / (res.E_net_J / 3.6e6)
    assert r1["T_winding_C"].max() > 40.0
