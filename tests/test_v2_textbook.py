"""V2: 교재 공통 식과의 일치 (기획서 6장 V2).

주 교재를 아직 정하지 못해(교재 수치 예제 없음) 교재마다 같은 모양으로 나오는 **돌극 동기기 전력-부하각식**을
정답지로 쓴다. 근거: ORNL/TM-2004/185 식 (1)~(3) (data/benchmarks/prius2004_ornl.md 5절).
이 식은 단자전압 V와 부하각 δ에서 출발하므로, 엔진의 id·iq 기반 유도(derivations.md 1~2절)와 경로가 다르다.

표기(Rs = 0, 첨두값, 크기 불변 변환): vd = −V sinδ, vq = V cosδ, E = ωe·ψm, Xd = ωe·Ld, Xq = ωe·Lq.
  Id = (V cosδ − E)/Xd,  Iq = V sinδ/Xq
  P = 1.5·[ V·E·sinδ/Xd + 0.5·V²·sin2δ·(1/Xq − 1/Xd) ]
(TM-185의 식 (3)은 인쇄상 V² 항이 빠져 있다.)
"""
import numpy as np
import pytest

from engine.model import ConstantParamModel

from conftest import LD, P, PSI_M

V = 202.07                       # 선형 변조 한계 (Vdc = 350 V) [V, 첨두]
WM = np.array([200.0, 600.0, 1000.0])   # 기계 속도 [rad/s]


def phasor_currents(m, wm, V, delta):
    we = m.p * wm
    E, Xd, Xq = we * m.psi_m, we * m.Ld, we * m.Lq
    return (V * np.cos(delta) - E) / Xd, V * np.sin(delta) / Xq


def textbook_power(m, wm, V, delta):
    we = m.p * wm
    E, Xd, Xq = we * m.psi_m, we * m.Ld, we * m.Lq
    return 1.5 * (V * E * np.sin(delta) / Xd + 0.5 * V**2 * np.sin(2 * delta) * (1 / Xq - 1 / Xd))


@pytest.mark.parametrize("wm", WM)
def test_voltage_equations_reproduce_terminal_voltage(model0, wm):
    """부하각식에서 구한 (id, iq)를 엔진 전압식에 넣으면 (−V sinδ, V cosδ)가 나온다."""
    delta = np.linspace(0.05, 1.2, 25)
    id_, iq = phasor_currents(model0, wm, V, delta)
    vd, vq = model0.voltage(id_, iq, P * wm)
    np.testing.assert_allclose(vd, -V * np.sin(delta), rtol=1e-10, atol=1e-9)
    np.testing.assert_allclose(vq, V * np.cos(delta), rtol=1e-10, atol=1e-9)


@pytest.mark.parametrize("wm", WM)
def test_engine_torque_matches_textbook_power_angle(model0, wm):
    """Te·ωm = P_textbook (Rs = 0이므로 전기 입력이 전부 기계 출력)."""
    delta = np.linspace(0.05, 1.2, 25)
    id_, iq = phasor_currents(model0, wm, V, delta)
    np.testing.assert_allclose(model0.torque(id_, iq) * wm, textbook_power(model0, wm, V, delta),
                               rtol=1e-10, atol=1e-6)


def test_nonsalient_reduces_to_power_angle_curve():
    """Ld = Lq이면 P = 1.5·V·E·sinδ/X (돌극 항이 사라진다)."""
    m = ConstantParamModel(p=P, Rs=0.0, Ld=0.3e-3, Lq=0.3e-3, psi_m=PSI_M)
    wm, delta = 500.0, np.linspace(0.05, 1.2, 25)
    id_, iq = phasor_currents(m, wm, V, delta)
    we = P * wm
    expected = 1.5 * V * (we * PSI_M) * np.sin(delta) / (we * 0.3e-3)
    np.testing.assert_allclose(m.torque(id_, iq) * wm, expected, rtol=1e-10)


def test_salient_machine_peak_power_angle_exceeds_90_degrees(model0):
    """Lq > Ld이면 1/Xq − 1/Xd < 0이라 δ = 90°에서도 dP/dδ > 0, 최대 토크 부하각이 90°보다 커진다.

    교재의 정성적 결과(IPM은 최대 토크점이 90° 너머)와 같은지 격자 탐색으로 확인한다.
    같은 V·E의 비돌극 기계는 정확히 90°에서 최대다.
    """
    wm = 1000.0
    delta = np.linspace(0.0, np.pi, 200001)
    m_ns = ConstantParamModel(p=P, Rs=0.0, Ld=LD, Lq=LD, psi_m=PSI_M)
    assert delta[np.argmax(textbook_power(m_ns, wm, V, delta))] == pytest.approx(np.pi / 2, abs=1e-3)
    assert delta[np.argmax(textbook_power(model0, wm, V, delta))] > np.pi / 2 + 0.01
