"""P2: 손실·효율맵 (docs/ENGINE_SPEC.md 5장, 기획서 5.4절).

IRON·MECH·ALPHA 값은 **테스트 전용 합성 값**이다. 실제 강판·베어링 데이터가 아니다.
"""
import time

import numpy as np
import pytest

from engine.losses import (
    ExcessLossParams,
    IronParams,
    MechParams,
    copper_loss,
    efficiency_map,
    excess_loss,
    iron_loss,
    loss_breakdown,
    loss_objective,
    mech_loss,
    winding_resistance,
)
from engine.operating import max_torque_curve, optimal_current

from conftest import IMAX, P

IRON = IronParams(k_h=0.02, k_e=5e-5, beta=2.0, m_tooth=3.0, m_yoke=6.0, c_tooth=20.0, c_yoke=10.0)
MECH = MechParams(a=0.01, b=2e-8)
EXCESS = ExcessLossParams(k_f=1.5, k_c=2e-6)      # 테스트 전용 합성 값


def test_winding_resistance():
    assert winding_resistance(0.03, 20.0, 0.004) == pytest.approx(0.03)
    assert winding_resistance(0.03, 120.0, 0.004) == pytest.approx(0.03 * 1.4)


def test_copper_loss(model_rs):
    assert copper_loss(model_rs, -100.0, 200.0) == pytest.approx(1.5 * 0.03 * (100.0**2 + 200.0**2))


def test_mech_loss():
    assert mech_loss(500.0, MECH) == pytest.approx(0.01 * 500 + 2e-8 * 500**3)
    assert mech_loss(0.0, MECH) == 0.0


def test_iron_loss_formula_and_scaling(model0):
    id_, iq, wm = -100.0, 200.0, 500.0
    psi = np.hypot(*model0.flux(id_, iq))
    f = P * wm / (2 * np.pi)
    Bt, By = IRON.c_tooth * psi, IRON.c_yoke * psi
    expected = sum(
        m * (IRON.k_h * f * B**IRON.beta + IRON.k_e * f**2 * B**2)
        for m, B in ((IRON.m_tooth, Bt), (IRON.m_yoke, By))
    )
    assert iron_loss(model0, id_, iq, wm, IRON) == pytest.approx(expected, rel=1e-12)
    assert iron_loss(model0, id_, iq, 0.0, IRON) == 0.0
    # 같은 자속에서 속도 2배: 히스테리시스 ×2, 와전류 ×4
    hyst = IronParams(0.02, 0.0, 2.0, 3.0, 6.0, 20.0, 10.0)
    eddy = IronParams(0.0, 5e-5, 2.0, 3.0, 6.0, 20.0, 10.0)
    assert iron_loss(model0, id_, iq, 2 * wm, hyst) == pytest.approx(2 * iron_loss(model0, id_, iq, wm, hyst))
    assert iron_loss(model0, id_, iq, 2 * wm, eddy) == pytest.approx(4 * iron_loss(model0, id_, iq, wm, eddy))


def test_input_power_equals_electrical_power_without_iron_and_mech(model_rs):
    """철손·기계손이 없으면 P_in = 1.5(vd·id + vq·iq) (T5와 같은 항등식)."""
    rng = np.random.default_rng(2)
    id_, iq = rng.uniform(-250, 0, 100), rng.uniform(0, 250, 100)
    wm = rng.uniform(10, 1500, 100)
    lb = loss_breakdown(model_rs, id_, iq, wm, None, None)
    vd, vq = model_rs.voltage(id_, iq, P * wm)
    np.testing.assert_allclose(lb.P_in, 1.5 * (vd * id_ + vq * iq), rtol=1e-12)


def test_loss_budget_closes(model_rs):
    """P_in − P_out = P_cu + P_fe + P_mech."""
    id_, iq, wm = -120.0, 210.0, 600.0
    lb = loss_breakdown(model_rs, id_, iq, wm, IRON, MECH)
    assert lb.P_in - lb.P_out == pytest.approx(lb.P_cu + lb.P_fe + lb.P_mech, rel=1e-12)
    assert lb.eta == pytest.approx(lb.P_out / lb.P_in, rel=1e-12)
    assert 0 < lb.eta < 1


T_GRID = np.linspace(5.0, 140.0, 28)
SPEEDS = np.array([200.0, 900.0, 1250.0])


def test_efficiency_map_feasible_region_matches_torque_curve(model_rs, limits):
    em = efficiency_map(model_rs, limits, T_GRID, SPEEDS, IRON, MECH)
    assert em.eta.shape == (T_GRID.size, SPEEDS.size)
    t_max = max_torque_curve(model_rs, limits, SPEEDS).T_max
    for j in range(SPEEDS.size):
        assert np.all(em.feasible[T_GRID < 0.98 * t_max[j], j])
        assert not np.any(em.feasible[T_GRID > 1.02 * t_max[j], j])
    assert np.all(np.isnan(em.eta[~em.feasible]))


def test_efficiency_map_energy_balance_and_limits(model_rs, limits):
    em = efficiency_map(model_rs, limits, T_GRID, SPEEDS, IRON, MECH)
    f = em.feasible
    assert f.sum() > 40
    np.testing.assert_allclose((em.P_in - em.P_out)[f], (em.P_cu + em.P_fe + em.P_mech)[f], rtol=1e-12)
    assert np.all((em.eta[f] > 0) & (em.eta[f] < 1))
    assert np.all(np.hypot(em.id, em.iq)[f] <= IMAX * (1 + 1e-6))
    w = np.broadcast_to(SPEEDS, em.id.shape)
    vd, vq = model_rs.voltage(em.id[f], em.iq[f], P * w[f])
    assert np.all(np.hypot(vd, vq) <= limits.Vmax * (1 + 1e-6))
    # 실제 토크는 요청 토크 이상이고, 경계가 아닌 곳에서는 거의 같다
    T_req = np.broadcast_to(T_GRID[:, None], em.id.shape)
    assert np.all(em.T_act[f] >= T_req[f] * (1 - 1e-9))
    assert np.median(np.abs(em.T_act[f] / T_req[f] - 1)) < 1e-6


def test_efficiency_map_current_matches_scalar_optimal_current(model_rs, limits):
    t_max = max_torque_curve(model_rs, limits, SPEEDS).T_max
    em = efficiency_map(model_rs, limits, T_GRID, SPEEDS, IRON, MECH)
    checked = 0
    for i, T in enumerate(T_GRID):
        for j, w in enumerate(SPEEDS):
            if T > 0.95 * t_max[j]:
                continue  # 경계 근처는 두 알고리즘의 격자 처리 차이가 커진다
            d, q, ok = optimal_current(model_rs, limits, T, w)
            assert ok and em.feasible[i, j]
            assert np.hypot(em.id[i, j], em.iq[i, j]) == pytest.approx(np.hypot(d, q), rel=2e-3)
            checked += 1
    assert checked > 40


def test_efficiency_map_speed(model_rs, limits):
    T = np.linspace(5.0, 140.0, 40)
    w = np.linspace(50.0, 1250.0, 60)
    t0 = time.perf_counter()
    efficiency_map(model_rs, limits, T, w, IRON, MECH)
    assert time.perf_counter() - t0 < 2.0  # 기획서 G2: 효율맵 1장 2초 이내


# --- objective="loss": 효율이 가장 높은 동작점 (시험 제어기가 id를 바꿔 효율 최고점을 고르는 것과 같다) -----------------------
# (T [N·m], ωm [rad/s]). 모두 그 속도의 최대 토크(300: 146, 600: 121, 900: 72, 1200: 32 N·m)의 약 50~85% 안쪽이라 실행 가능하다.
OPERATING_POINTS = [(60.0, 300.0), (100.0, 600.0), (50.0, 900.0), (22.0, 1200.0)]


@pytest.mark.parametrize("T, wm", OPERATING_POINTS)
def test_loss_objective_with_copper_only_equals_min_current(model_rs, limits, T, wm):
    """동손만 넣으면 최소 손실점 = 최소 전류점이다 (동손 = 1.5·Rs·Is²가 Is에 단조)."""
    cu_only = loss_objective(model_rs, wm, None)
    d1, q1, ok1 = optimal_current(model_rs, limits, T, wm)
    d2, q2, ok2 = optimal_current(model_rs, limits, T, wm, objective="loss", loss_fn=cu_only)
    assert ok1 and ok2
    assert np.hypot(d2, q2) == pytest.approx(np.hypot(d1, q1), rel=1e-6)


@pytest.mark.parametrize("T, wm", OPERATING_POINTS)
def test_loss_objective_never_loses_to_min_current_and_deepens_field_weakening(model_rs, limits, T, wm):
    """철손이 있으면 최소 손실점의 손실이 최소 전류점의 손실 이하이고, 약계자가 같거나 더 깊다(|ψ|가 같거나 작다)."""
    fn = loss_objective(model_rs, wm, IRON)
    d1, q1, _ = optimal_current(model_rs, limits, T, wm)
    d2, q2, ok = optimal_current(model_rs, limits, T, wm, objective="loss", loss_fn=fn)
    assert ok
    assert float(fn(d2, q2)) <= float(fn(d1, q1)) * (1 + 1e-9)
    assert np.hypot(d2, q2) >= np.hypot(d1, q1) * (1 - 1e-9)           # 전류는 같거나 더 크다
    assert float(model_rs.torque(d2, q2)) == pytest.approx(T, rel=1e-6)  # 토크는 정확히 T
    psi = lambda d, q: float(np.hypot(*model_rs.flux(d, q)))
    assert psi(d2, q2) <= psi(d1, q1) * (1 + 1e-9)


def test_loss_objective_matches_brute_force_search(model_rs, limits):
    """독립 검증: (id, iq) 격자 전수 탐색에서 토크 T 이상을 내는 점 중 손실이 최소인 값과 비교한다."""
    T, wm = 50.0, 900.0                      # 900 rad/s의 최대 토크는 72 N·m (실행 가능한 점)
    fn = loss_objective(model_rs, wm, IRON)
    d, q, ok = optimal_current(model_rs, limits, T, wm, objective="loss", loss_fn=fn)
    assert ok
    n = 701
    gd, gq = np.meshgrid(np.linspace(-IMAX, 0.0, n), np.linspace(0.0, IMAX, n), indexing="ij")
    vd, vq = model_rs.voltage(gd, gq, P * wm)
    good = (np.hypot(gd, gq) <= IMAX) & (np.hypot(vd, vq) <= limits.Vmax) & (model_rs.torque(gd, gq) >= T)
    assert float(fn(d, q)) <= float(fn(gd, gq)[good].min()) * (1 + 1e-9)             # 엔진이 격자 최소보다 나쁘면 안 된다
    near = good & (model_rs.torque(gd, gq) <= T * 1.01)                                # T에 가까운 격자점의 최소와도 가깝다
    assert float(fn(d, q)) >= float(fn(gd, gq)[near].min()) * 0.97


# --- 경험적 잔여 손실 (ExcessLossParams): P = k_f·f + k_c·Is_rms²·f² ---------------------------------------------------------------
def test_excess_loss_formula_and_scaling():
    id_, iq, wm = -80.0, 120.0, 400.0
    f = P * wm / (2 * np.pi)
    is_rms2 = (id_**2 + iq**2) / 2
    assert excess_loss(id_, iq, wm, P, EXCESS) == pytest.approx(EXCESS.k_f * f + EXCESS.k_c * is_rms2 * f**2, rel=1e-12)
    assert excess_loss(id_, iq, 0.0, P, EXCESS) == 0.0
    only_f, only_c = ExcessLossParams(1.5, 0.0), ExcessLossParams(0.0, 2e-6)
    assert excess_loss(id_, iq, 2 * wm, P, only_f) == pytest.approx(2 * excess_loss(id_, iq, wm, P, only_f))      # f에 비례
    assert excess_loss(id_, iq, 2 * wm, P, only_c) == pytest.approx(4 * excess_loss(id_, iq, wm, P, only_c))      # f²에 비례
    assert excess_loss(2 * id_, 2 * iq, wm, P, only_c) == pytest.approx(4 * excess_loss(id_, iq, wm, P, only_c))  # I²에 비례
    assert excess_loss(id_, iq, wm, P, ExcessLossParams(0.0, 0.0)) == 0.0


def test_loss_budget_closes_with_excess_and_lowers_efficiency(model_rs):
    id_, iq, wm = -120.0, 210.0, 600.0
    base = loss_breakdown(model_rs, id_, iq, wm, IRON, MECH)
    lb = loss_breakdown(model_rs, id_, iq, wm, IRON, MECH, EXCESS)
    assert lb.P_excess == pytest.approx(excess_loss(id_, iq, wm, P, EXCESS))
    assert lb.P_in - lb.P_out == pytest.approx(lb.P_cu + lb.P_fe + lb.P_mech + lb.P_excess, rel=1e-12)
    assert lb.eta < base.eta and base.P_excess == 0.0
    assert lb.P_out == pytest.approx(base.P_out)          # 잔여 손실은 입력 전력에만 더한다(샤프트 출력은 그대로)


def test_efficiency_map_with_excess(model_rs, limits):
    a = efficiency_map(model_rs, limits, T_GRID, SPEEDS, IRON, MECH)
    b = efficiency_map(model_rs, limits, T_GRID, SPEEDS, IRON, MECH, EXCESS)
    f = a.feasible
    np.testing.assert_array_equal(a.feasible, b.feasible)
    np.testing.assert_allclose(b.id[f], a.id[f])                       # 동작점(전류 최소)은 손실과 무관하다
    np.testing.assert_allclose((b.P_in - b.P_out)[f], (b.P_cu + b.P_fe + b.P_mech + b.P_excess)[f], rtol=1e-12)
    assert np.all(b.eta[f] < a.eta[f])
    assert np.all(np.isnan(b.P_excess[~f]))
