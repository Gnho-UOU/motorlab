"""M8 권선 전환(engine/winding.py): 턴 수 비 a로 다시 감은 모터와 동등함, 손실 불변량, 두 결선의 최선 선택.

규약: reconfigure(model, a)는 인버터 단자에서 본 "턴 수가 a배인 같은 모터"다. 같은 기자력에서 단자 전류 i' = i/a, 쇄교자속 ψ' = a·ψ,
저항 R' = a²·R, 토크는 같다. 단자 전류 한계(인버터)와 직류 링크 전압은 그대로다.
"""
import dataclasses

import numpy as np
import pytest

from engine.losses import IronParams, ExcessLossParams, copper_loss, efficiency_map, excess_loss, iron_loss, MechParams
from engine.model import ConstantParamModel, FluxMapModel
from engine.operating import Limits, base_speed, max_torque_curve
from engine.winding import compare_windings, reconfigure

BASE = ConstantParamModel(p=4, Rs=0.02, Ld=0.9e-3, Lq=2.2e-3, psi_m=0.17)


def test_reconfigure_constant_model_is_the_rewound_machine():
    a = 0.5
    m = reconfigure(BASE, a)
    assert (m.Ld, m.Lq, m.psi_m, m.Rs, m.turns_ratio) == pytest.approx((a * a * BASE.Ld, a * a * BASE.Lq, a * BASE.psi_m, a * a * BASE.Rs, a))
    rng = np.random.default_rng(0)
    i_d, i_q = -rng.uniform(0, 120, 6), rng.uniform(0, 150, 6)
    assert np.allclose(m.torque(i_d, i_q), BASE.torque(a * i_d, a * i_q))              # 같은 기자력이면 같은 토크
    v, vb = m.voltage(i_d, i_q, 900.0), BASE.voltage(a * i_d, a * i_q, 900.0)
    assert np.allclose(v[0], a * vb[0]) and np.allclose(v[1], a * vb[1])                # 전압은 a배
    assert np.allclose(copper_loss(m, i_d, i_q), copper_loss(BASE, a * i_d, a * i_q))   # 동손 불변


def _flux_map(base: ConstantParamModel, imax=300.0, n=25):
    ax = np.linspace(-imax, imax, n)
    G = np.meshgrid(ax, ax, indexing="ij")
    d, q = base.flux(G[0], G[1])
    return FluxMapModel(p=base.p, Rs=base.Rs, id_axis=ax, iq_axis=ax, psi_d_map=d, psi_q_map=q)


def test_reconfigure_flux_map_matches_the_original_at_equivalent_currents_and_composes():
    fm = _flux_map(BASE)
    a = 0.6
    m = reconfigure(fm, a)
    assert m.turns_ratio == a and m.Rs == pytest.approx(a * a * fm.Rs)
    assert np.allclose(m.id_axis, fm.id_axis / a)
    rng = np.random.default_rng(1)
    i_d, i_q = -rng.uniform(0, 150, 8), rng.uniform(0, 200, 8)
    assert np.allclose(m.torque(i_d, i_q), fm.torque(a * i_d, a * i_q))
    b = 0.7
    mm = reconfigure(m, b)
    ref = reconfigure(fm, a * b)
    assert mm.turns_ratio == pytest.approx(a * b) and np.allclose(mm.id_axis, ref.id_axis) and np.allclose(mm.psi_d_map, ref.psi_d_map)


def test_iron_and_excess_losses_are_referred_to_the_original_winding():
    a = 0.5
    m = reconfigure(BASE, a)
    iron = IronParams(m_tooth=3.0, m_yoke=5.0, c_tooth=7.0, c_yoke=6.0, k_h=0.02, k_e=1e-5, beta=2.0)
    i_d, i_q, wm = -50.0, 120.0, 400.0
    assert iron_loss(m, i_d, i_q, wm, iron) == pytest.approx(iron_loss(BASE, a * i_d, a * i_q, wm, iron))     # 같은 자속밀도 → 같은 철손
    ex = ExcessLossParams(k_f=0.5, k_c=1e-4)
    from engine.losses import loss_breakdown
    lb_m = loss_breakdown(m, i_d, i_q, wm, None, None, ex)
    lb_b = loss_breakdown(BASE, a * i_d, a * i_q, wm, None, None, ex)
    assert lb_m.P_excess == pytest.approx(lb_b.P_excess) and lb_m.P_in == pytest.approx(lb_b.P_in)


def test_fewer_turns_give_higher_base_speed_and_lower_low_speed_torque_at_the_same_terminal_current():
    lim = Limits(Imax=250.0, Vdc=500.0, k_mod=2 / np.pi)
    m = reconfigure(BASE, 0.5)
    assert base_speed(m, lim) > base_speed(BASE, lim)
    sp = np.array([20.0, 2000.0])
    ta, tb = max_torque_curve(BASE, lim, sp[:1]).T_max[0], max_torque_curve(m, lim, sp[:1]).T_max[0]
    assert tb < ta                                                      # 기자력 a배
    assert np.isnan(max_torque_curve(BASE, lim, sp[1:]).T_max[0]) or max_torque_curve(m, lim, sp[1:]).T_max[0] >= max_torque_curve(BASE, lim, sp[1:]).T_max[0]


def test_compare_windings_best_of_two_and_current_clamp_for_more_turns():
    lim = Limits(Imax=250.0, Vdc=500.0, k_mod=2 / np.pi)
    T_grid, W_grid = np.linspace(2.0, 150.0, 12), np.linspace(20.0, 900.0, 14)
    mech = MechParams(a=0.4, b=1e-6)
    c = compare_windings(BASE, lim, 0.5, T_grid, W_grid, None, mech)
    both = c.base.feasible & c.other.feasible
    assert np.all(c.best.P_in[both] <= np.minimum(c.base.P_in, c.other.P_in)[both] + 1e-9)
    assert np.array_equal(c.best.feasible, c.base.feasible | c.other.feasible)
    assert c.best.feasible.sum() > c.base.feasible.sum()                  # 적은 턴 결선이 고속 영역을 더 연다
    assert np.all((c.choice[both] == 0) == (c.base.P_in <= c.other.P_in)[both])
    # 맵 모델: 턴을 늘리면(a>1) 단자 전류 한계를 맵이 덮는 범위로 줄인다
    fm = _flux_map(BASE, imax=300.0)
    c2 = compare_windings(fm, lim, 2.0, T_grid, W_grid, None, mech)
    assert c2.limits_other.Imax == pytest.approx(150.0)
    with pytest.raises(ValueError):
        reconfigure(BASE, 0.0)
