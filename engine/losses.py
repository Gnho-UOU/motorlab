"""M3 손실·효율맵: 동손, 철손, 기계손과 (토크, 속도) 효율맵.

기획서 5.4절, 규약은 docs/ENGINE_SPEC.md 5장, 유도는 docs/derivations.md 9절.
철손·기계손·구리 온도계수는 **출처 있는 기본값을 두지 않고** 호출자가 넘긴다 (CLAUDE.md의 근거 없는
계수 금지 규칙). 실제 값은 강판 데이터시트·ORNL 보고서를 읽은 뒤 data/에 출처와 함께 기록한다.
전동(T ≥ 0)만 다룬다. 회생은 M4에서 확장한다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.operating import Limits, optimal_current_map


@dataclass(frozen=True)
class IronParams:
    """치·요크 분리 손실 계수 (히스테리시스 + 와전류, 기획서 5.4).

    k_h [W/(kg·Hz·T^β)], k_e [W/(kg·Hz²·T²)], beta(Steinmetz 지수), m_tooth·m_yoke [kg],
    c_tooth·c_yoke [T/Wb]: 자속밀도 환산계수 B_k = c_k·|ψ| (기하에서 오는 값, P3에서 FEA와 비교).
    """

    k_h: float
    k_e: float
    beta: float
    m_tooth: float
    m_yoke: float
    c_tooth: float
    c_yoke: float


@dataclass(frozen=True)
class MechParams:
    """기계손(베어링·풍손) P_mech = a·ω + b·ω³.  a [W/(rad/s)], b [W/(rad/s)³]."""

    a: float
    b: float


@dataclass(frozen=True)
class ExcessLossParams:
    """경험적 잔여 손실 P = k_f·f + k_c·Is_rms²·f²  (f = p·ωm/2π [Hz], Is_rms = |Is|/√2).

    k_f [W/Hz], k_c [W/(A²·Hz²)]. **물리 기구가 확인되지 않은 보정항**이다: 동손(직류 저항)·철손·기계손 모델로 설명되지 않고
    벤치마크에서 측정된 손실이 있을 때, 그 차이를 속도(첫째 항)와 전류·속도 곱(둘째 항, 자석·표피 효과 같은 I²f² 꼴)으로 맞춘다.
    기본값을 두지 않는다: 호출자가 계수와 출처(맞춘 데이터, 검증 방법)를 data/에 기록해 넘긴다 (CLAUDE.md).
    """

    k_f: float
    k_c: float


@dataclass(frozen=True)
class LossBreakdown:
    """운전점 하나(또는 배열)의 손실 수지. 전부 W, 토크 N·m. eta는 P_in ≤ 0이면 NaN."""

    T: np.ndarray
    P_shaft: np.ndarray   # Te·ωm (전자기 출력)
    P_cu: np.ndarray
    P_fe: np.ndarray
    P_mech: np.ndarray
    P_excess: np.ndarray  # 경험적 잔여 손실 (없으면 0)
    P_in: np.ndarray      # P_shaft + P_cu + P_fe + P_excess
    P_out: np.ndarray     # P_shaft − P_mech (축 출력)
    eta: np.ndarray       # P_out / P_in


@dataclass(frozen=True)
class EfficiencyMap:
    """효율맵. 배열 모양은 (n_T, n_speed), 실행 불가능한 점은 feasible=False이고 나머지 값은 NaN."""

    T_grid: np.ndarray
    speed_grid: np.ndarray
    id: np.ndarray
    iq: np.ndarray
    T_act: np.ndarray     # 실제 토크 (경계에서는 T_grid보다 약간 클 수 있다)
    feasible: np.ndarray
    P_cu: np.ndarray
    P_fe: np.ndarray
    P_mech: np.ndarray
    P_excess: np.ndarray
    P_in: np.ndarray
    P_out: np.ndarray
    eta: np.ndarray


def winding_resistance(R20, T_c, alpha_cu):
    """Rs(T) = R20·(1 + α_cu·(T − 20))  (기획서 5.4). T_c [°C], alpha_cu [1/K]는 호출자가 출처와 함께 제공."""
    return R20 * (1 + alpha_cu * (np.asarray(T_c, dtype=float) - 20.0))


def copper_loss(model, id, iq):
    """P_cu = 1.5·Rs·(id² + iq²) [W]  (기획서 5.4). 교류 저항(표피·근접)은 확장에서."""
    id, iq = np.asarray(id, dtype=float), np.asarray(iq, dtype=float)
    return 1.5 * model.Rs * (id**2 + iq**2)


def iron_loss(model, id, iq, wm, iron: IronParams):
    """P_fe = Σ_k m_k·(k_h·f·B_k^β + k_e·f²·B_k²) [W],  k ∈ {치, 요크}  (기획서 5.4, Bertotti 분리식).

    f = p·ωm/2π [Hz], B_k = c_k·|ψ|, |ψ| = √(ψd² + ψq²).
    근거: G. Bertotti, IEEE Trans. Magn. 24(1), 1988 (히스테리시스·와전류 분리). 이상(excess) 손실은
    기획서 식에 없어 생략한다. 자속밀도를 ψ 크기에 비례한다고 본 것은 근사다.
    """
    f = model.p * np.asarray(wm, dtype=float) / (2 * np.pi)
    psi = np.hypot(*model.flux(id, iq))
    total = 0.0
    for m, c in ((iron.m_tooth, iron.c_tooth), (iron.m_yoke, iron.c_yoke)):
        B = c * psi
        total = total + m * (iron.k_h * f * B**iron.beta + iron.k_e * f**2 * B**2)
    return total


def mech_loss(wm, mech: MechParams):
    """P_mech = a·ω + b·ω³ [W]  (기획서 5.4)."""
    wm = np.asarray(wm, dtype=float)
    return mech.a * wm + mech.b * wm**3


def excess_loss(id, iq, wm, p, excess: ExcessLossParams):
    """P_excess = k_f·f + k_c·Is_rms²·f² [W]. f = p·ωm/2π, Is_rms² = (id² + iq²)/2 (크기 불변 dq의 첨두 전류 -> 상 실효값)."""
    id, iq = np.asarray(id, dtype=float), np.asarray(iq, dtype=float)
    f = p * np.asarray(wm, dtype=float) / (2 * np.pi)
    return excess.k_f * f + excess.k_c * 0.5 * (id**2 + iq**2) * f**2


def loss_breakdown(model, id, iq, wm, iron: IronParams | None, mech: MechParams | None,
                   excess: ExcessLossParams | None = None) -> LossBreakdown:
    """손실 수지와 효율 (기획서 5.4, derivations.md 9절).

    η = (Te·ωm − P_mech) / (Te·ωm + P_cu + P_fe + P_excess). iron/mech/excess가 None이면 그 손실은 0.
    철손·잔여 손실은 토크에 반영하지 않고 입력 전력에만 더한다 (ENGINE_SPEC 5장).
    """
    wm = np.asarray(wm, dtype=float)
    T = model.torque(id, iq)
    P_shaft = T * wm
    P_cu = copper_loss(model, id, iq)
    P_fe = 0.0 * P_shaft if iron is None else iron_loss(model, id, iq, wm, iron)
    P_mech = 0.0 * P_shaft if mech is None else mech_loss(wm, mech)
    P_excess = 0.0 * P_shaft if excess is None else excess_loss(id, iq, wm, model.p, excess) + 0.0 * P_shaft
    P_in, P_out = P_shaft + P_cu + P_fe + P_excess, P_shaft - P_mech
    with np.errstate(divide="ignore", invalid="ignore"):
        eta = np.where(P_in > 0, P_out / P_in, np.nan)
    return LossBreakdown(T, P_shaft, P_cu, P_fe, P_mech, P_excess, P_in, P_out, eta)


def loss_objective(model, wm, iron: IronParams | None):
    """`optimal_current(objective="loss", loss_fn=...)`에 넘길 함수를 만든다: (id, iq) -> P_cu + P_fe [W].

    ORNL 시험 제어기는 같은 토크·속도에서 id를 바꿔 효율이 가장 높은 점을 골랐다. 기계손은 동작점과 무관한 상수라 넣지 않는다.
    입력과 출력은 NumPy 배열(브로드캐스팅). 철손이 있으면 최소 손실점은 최소 전류점보다 약계자가 깊다.
    """
    def loss(id_, iq):
        out = copper_loss(model, id_, iq)
        return out if iron is None else out + iron_loss(model, id_, iq, wm, iron)

    return loss


def efficiency_map(model, limits: Limits, T_grid, speed_grid, iron: IronParams | None = None,
                   mech: MechParams | None = None, excess: ExcessLossParams | None = None) -> EfficiencyMap:
    """(토크, 속도) 격자의 효율·손실 성분 (기획서 5.4, ENGINE_SPEC 5장).

    동작점은 전류 크기 최소(optimal_current_map)로 정한다. 손실 최소 동작점은 이후 확장.
    T_grid [N·m], speed_grid는 기계 속도 [rad/s]. 결과 배열은 [i_T, j_speed] 순서.
    """
    T_grid = np.atleast_1d(np.asarray(T_grid, dtype=float))
    speed_grid = np.atleast_1d(np.asarray(speed_grid, dtype=float))
    id_, iq, feas = optimal_current_map(model, limits, T_grid, speed_grid)
    wm = np.broadcast_to(speed_grid[None, :], id_.shape)
    lb = loss_breakdown(model, np.where(feas, id_, 0.0), np.where(feas, iq, 0.0), wm, iron, mech, excess)

    def masked(a):
        return np.where(feas, a, np.nan)

    return EfficiencyMap(T_grid, speed_grid, id_, iq, masked(lb.T), feas, masked(lb.P_cu), masked(lb.P_fe),
                         masked(lb.P_mech), masked(lb.P_excess), masked(lb.P_in), masked(lb.P_out), masked(lb.eta))
