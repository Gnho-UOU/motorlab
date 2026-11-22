"""V1: 해석해가 있는 경우로 엔진 검증 (docs/ENGINE_SPEC.md 4장, 기획서 6장 V1).

기대값의 근거는 docs/derivations.md 절 번호를 단다.
"""
import numpy as np
import pytest

from engine.model import ConstantParamModel
from engine.operating import (
    Limits,
    base_speed,
    max_torque_curve,
    mtpa_point,
    optimal_current,
)

from conftest import IMAX, LD, LQ, P, PSI_M


def _mtpa_analytic(Ld, Lq, psi_m, Is):
    """derivations.md 4절 해석식."""
    dL = Lq - Ld
    id_ = (psi_m - np.sqrt(psi_m**2 + 8 * dL**2 * Is**2)) / (4 * dL)
    return id_, np.sqrt(Is**2 - id_**2)


# ---------------------------------------------------------------- T1
def test_T1_nonsalient_mtpa_is_id_zero():
    m = ConstantParamModel(p=P, Rs=0.0, Ld=0.3e-3, Lq=0.3e-3, psi_m=PSI_M)
    id_, iq = mtpa_point(m, np.array([10.0, 100.0, 250.0]))
    # 격자 간격 이하(0.1% × Imax = 0.25 A)면 충분하다
    np.testing.assert_allclose(id_, 0.0, atol=1e-3)
    np.testing.assert_allclose(iq, [10.0, 100.0, 250.0], rtol=1e-6)


# ---------------------------------------------------------------- T2
def test_T2_mtpa_matches_analytic(model0):
    Is = np.array([20.0, 50.0, 100.0, 150.0, 200.0, 250.0])
    id_, iq = mtpa_point(model0, Is)
    id_ref, iq_ref = _mtpa_analytic(LD, LQ, PSI_M, Is)
    np.testing.assert_allclose(id_, id_ref, rtol=1e-6)
    np.testing.assert_allclose(iq, iq_ref, rtol=1e-6)


def test_T2_hand_calculation_values(model0):
    """ENGINE_SPEC 4장 손계산값: Imax에서 id = -125.0 A, iq = 216.51 A, T = 146.14 N·m."""
    id_, iq = mtpa_point(model0, IMAX)
    assert float(id_) == pytest.approx(-125.0, rel=1e-6)
    assert float(iq) == pytest.approx(216.51, abs=0.01)
    assert float(model0.torque(id_, iq)) == pytest.approx(146.14, abs=0.01)


# ---------------------------------------------------------------- T3
def test_T3_base_speed_rs0(model0, limits):
    """derivations.md 5절, Rs = 0이면 ωe = Vmax / |ψ|."""
    id_, iq = _mtpa_analytic(LD, LQ, PSI_M, IMAX)
    psi = np.hypot(LD * id_ + PSI_M, LQ * iq)
    wm_ref = limits.Vmax / psi / P
    assert base_speed(model0, limits) == pytest.approx(wm_ref, rel=1e-6)
    assert base_speed(model0, limits) == pytest.approx(449.05, abs=0.01)  # 손계산값


def test_T3_base_speed_with_rs_puts_voltage_on_limit(model_rs, limits):
    wb = base_speed(model_rs, limits)
    id_, iq = mtpa_point(model_rs, IMAX)
    vd, vq = model_rs.voltage(id_, iq, P * wb)
    assert float(np.hypot(vd, vq)) == pytest.approx(limits.Vmax, rel=1e-9)


def test_T3_modes_around_base_speed(model0, limits):
    wb = base_speed(model0, limits)
    tab = max_torque_curve(model0, limits, np.array([0.99 * wb, 1.05 * wb]))
    assert list(tab.mode) == ["MTPA", "FW"]
    assert tab.T_max[0] == pytest.approx(146.14, abs=0.01)
    assert tab.T_max[1] < tab.T_max[0]


# ---------------------------------------------------------------- T4
def test_T4_max_speed_rs0(model0, limits):
    """derivations.md 6절. ψm > Ld·Imax일 때 ωe,max = Vmax/(ψm − Ld·Imax)."""
    assert PSI_M > LD * IMAX
    wmax = limits.Vmax / (PSI_M - LD * IMAX) / P
    assert wmax == pytest.approx(1347.2, abs=0.1)  # 손계산값
    tab = max_torque_curve(model0, limits, np.array([0.99 * wmax, 1.01 * wmax]))
    assert list(tab.feasible) == [True, False]
    assert tab.mode[1] == "INFEASIBLE"
    assert np.isnan(tab.T_max[1])


# ---------------------------------------------------------------- T5
def test_T5_power_balance(model_rs):
    """P = 1.5(vd id + vq iq) = Te ωm + 1.5 Rs (id² + iq²)  (derivations.md 2절)."""
    rng = np.random.default_rng(0)
    id_ = rng.uniform(-250, 0, 200)
    iq = rng.uniform(0, 250, 200)
    wm = rng.uniform(0, 1500, 200)
    vd, vq = model_rs.voltage(id_, iq, P * wm)
    lhs = 1.5 * (vd * id_ + vq * iq)
    rhs = model_rs.torque(id_, iq) * wm + 1.5 * model_rs.Rs * (id_**2 + iq**2)
    np.testing.assert_allclose(lhs, rhs, rtol=1e-12, atol=1e-9)


# ---------------------------------------------------------------- T6
@pytest.mark.parametrize("name", ["model0", "model_rs"])
def test_T6_torque_speed_curve(name, limits, request):
    m = request.getfixturevalue(name)
    speeds = np.linspace(0.0, 1300.0, 66)
    tab = max_torque_curve(m, limits, speeds)
    assert tab.feasible.sum() > 50
    T = tab.T_max[tab.feasible]
    # T_max는 속도에 대해 비증가 (수치 잡음 허용 1e-6 상대)
    assert np.all(np.diff(T) <= 1e-6 * T.max())
    # 모든 점이 두 제약을 만족 (SLSQP 제약 허용오차 1e-6 상대)
    f = tab.feasible
    I = np.hypot(tab.id[f], tab.iq[f])
    assert np.all(I <= IMAX * (1 + 1e-6))
    vd, vq = m.voltage(tab.id[f], tab.iq[f], P * tab.speed[f])
    assert np.all(np.hypot(vd, vq) <= limits.Vmax * (1 + 1e-6))
    np.testing.assert_allclose(tab.P_mech[f], tab.T_max[f] * tab.speed[f], rtol=1e-12)


# ---------------------------------------------------------------- T7
def test_T7_two_torque_forms(model0):
    rng = np.random.default_rng(1)
    id_ = rng.uniform(-250, 250, 500)
    iq = rng.uniform(-250, 250, 500)
    psi_d, psi_q = model0.flux(id_, iq)
    t_flux = 1.5 * P * (psi_d * iq - psi_q * id_)
    t_split = 1.5 * P * (PSI_M * iq + (LD - LQ) * id_ * iq)
    np.testing.assert_allclose(model0.torque(id_, iq), t_flux, rtol=1e-12)
    np.testing.assert_allclose(t_flux, t_split, rtol=1e-12, atol=1e-9)


# ---------------------------------------------------------------- T8
def test_T8_mtpv_matches_flux_circle_search(model_mtpv, limits):
    """derivations.md 7절. 자속 크기 Ψ = Vmax/ωe를 고정하고 자속각 δ를 1차원 탐색."""
    m = model_mtpv
    assert m.psi_m < m.Ld * IMAX  # MTPV가 생기는 조건
    wm = 4000.0
    big_psi = limits.Vmax / (P * wm)
    delta = np.linspace(0.0, np.pi, 400001)
    psi_d, psi_q = big_psi * np.cos(delta), big_psi * np.sin(delta)
    id_ref = (psi_d - m.psi_m) / m.Ld
    iq_ref = psi_q / m.Lq
    T_ref = 1.5 * P * (psi_d * iq_ref - psi_q * id_ref)
    k = np.argmax(T_ref)
    assert np.hypot(id_ref[k], iq_ref[k]) < IMAX * (1 - 1e-3)  # 전류 제한 비활성

    tab = max_torque_curve(m, limits, np.array([wm]))
    assert tab.mode[0] == "MTPV"
    assert tab.T_max[0] == pytest.approx(T_ref[k], rel=1e-3)
    assert tab.id[0] == pytest.approx(id_ref[k], rel=1e-2)
    assert tab.iq[0] == pytest.approx(iq_ref[k], rel=1e-2)


def test_T8_mode_sequence_mtpa_fw_mtpv(model_mtpv, limits):
    tab = max_torque_curve(model_mtpv, limits, np.linspace(10.0, 6000.0, 120))
    assert tab.feasible.all()  # ψm < Ld·Imax이므로 속도 상한 없음
    modes = [str(x) for x in tab.mode]
    collapsed = [m for i, m in enumerate(modes) if i == 0 or m != modes[i - 1]]
    assert collapsed == ["MTPA", "FW", "MTPV"]


# ---------------------------------------------------------------- optimal_current
def _brute_force_min_current(m, limits, T_target, wm, n=801):
    id_ = np.linspace(-IMAX, 0.0, n)[:, None]
    iq = np.linspace(0.0, IMAX, n)[None, :]
    id_, iq = np.broadcast_arrays(id_, iq)
    Is = np.hypot(id_, iq)
    vd, vq = m.voltage(id_, iq, P * wm)
    ok = (
        (Is <= IMAX)
        & (np.hypot(vd, vq) <= limits.Vmax)
        & (m.torque(id_, iq) >= T_target)
    )
    # 최소 전류에서 토크는 정확히 T_target이므로, T ≥ T_target인 격자점의 최소 전류는 항상 그 이상이다
    return Is[ok].min()


@pytest.mark.parametrize("wm", [200.0, 900.0])  # 기저속도(449) 아래·위
def test_optimal_current_vs_brute_force(model_rs, limits, wm):
    T_target = 0.5 * max_torque_curve(model_rs, limits, np.array([wm])).T_max[0]
    id_, iq, ok = optimal_current(model_rs, limits, T_target, wm)
    assert ok
    assert float(model_rs.torque(id_, iq)) == pytest.approx(T_target, rel=1e-6)
    assert np.hypot(id_, iq) <= IMAX * (1 + 1e-9)
    vd, vq = model_rs.voltage(id_, iq, P * wm)
    assert np.hypot(vd, vq) <= limits.Vmax * (1 + 1e-6)
    brute = _brute_force_min_current(model_rs, limits, T_target, wm)
    # 엔진은 격자 최소보다 나쁘면 안 되고(위), 격자 간격(0.31 A)이 만드는 차이보다 크게 좋아서도 안 된다(아래)
    Is = float(np.hypot(id_, iq))
    assert Is <= brute + 1e-6
    assert brute <= Is + 1.0


def test_optimal_current_infeasible_above_max_torque(model_rs, limits):
    wm = 900.0
    T_max = max_torque_curve(model_rs, limits, np.array([wm])).T_max[0]
    _, _, ok = optimal_current(model_rs, limits, 1.05 * T_max, wm)
    assert not ok


def test_optimal_current_rejects_bad_objective(model_rs, limits):
    with pytest.raises(ValueError):
        optimal_current(model_rs, limits, 50.0, 100.0, objective="efficiency")
    with pytest.raises(ValueError):          # objective='loss'에는 loss_fn이 필요하다
        optimal_current(model_rs, limits, 50.0, 100.0, objective="loss")
