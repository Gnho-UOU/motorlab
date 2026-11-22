"""M2 운전 영역: MTPA, 기저속도, 최대 토크-속도 곡선, 최소 전류 운전점.

기획서 5.3절, 규약은 docs/ENGINE_SPEC.md 3장, 유도는 docs/derivations.md 3~8절.
모델 종류(상수/맵)에 관계없이 model.flux/torque/voltage만 호출한다 — 해석식은 쓰지 않는다.
탐색 영역은 전동 사분면 id ∈ [−Imax, 0], iq ∈ [0, Imax], β ∈ [0, 90°]
(id = −Is·sinβ, iq = Is·cosβ).
"""
from __future__ import annotations

from dataclasses import dataclass
from math import pi, sqrt

import numpy as np
from scipy.optimize import minimize, minimize_scalar

_N_BETA = 3601       # 전류각 격자 (0.025° 간격)
_N_GRID = 401        # dq 평면 격자 한 변 (Imax/400 간격)
_ACTIVE_TOL = 1e-4   # 제약이 "활성"이라고 보는 상대 오차 (모드 판정용)
_ACCEPT_TOL = 1e-7   # 국소 보정 결과를 받아들이는 제약 위반 상대 허용치


@dataclass(frozen=True)
class Limits:
    """전류 제한 Imax [A, 첨두], 직류 링크 Vdc [V], 선형 변조 한계 계수 k_mod.

    Vmax = k_mod·Vdc  (기획서 5.3, SVPWM 선형 영역 1/√3). 과변조는 k_mod 설정으로만.
    """

    Imax: float
    Vdc: float
    k_mod: float = 1 / sqrt(3)

    def __post_init__(self):
        if self.Imax <= 0 or self.Vdc <= 0 or self.k_mod <= 0:
            raise ValueError("Imax, Vdc, k_mod는 양수여야 한다")

    @property
    def Vmax(self) -> float:
        return self.k_mod * self.Vdc


@dataclass(frozen=True)
class TorqueSpeedTable:
    """최대 토크-속도 곡선. 모든 배열의 길이가 같다.

    speed: 기계 속도 [rad/s], T_max [N·m], id/iq [A], P_mech = T_max·speed [W],
    mode ∈ {"MTPA","FW","MTPV","INFEASIBLE"}, feasible: 영전류에서도 |v| ≤ Vmax이면 True.
    feasible=False인 행은 T_max·id·iq·P_mech = NaN.
    """

    speed: np.ndarray
    T_max: np.ndarray
    id: np.ndarray
    iq: np.ndarray
    mode: np.ndarray
    P_mech: np.ndarray
    feasible: np.ndarray


def _polar(Is, beta):
    return -Is * np.sin(beta), Is * np.cos(beta)


def _vmag(model, id, iq, we):
    vd, vq = model.voltage(id, iq, we)
    return np.hypot(vd, vq)


def mtpa_point(model, Is):
    """전류 크기 Is에서 토크가 최대인 (id, iq) — MTPA (derivations.md 4절).

    β를 격자(0.025°)로 훑어 최대점을 고른 뒤 그 이웃 구간에서 scipy로 보정한다.
    Is는 스칼라 또는 배열 [A, 첨두]. 반환은 Is와 같은 모양의 (id, iq) [A].
    """
    Is_arr = np.asarray(Is, dtype=float)
    flat = np.atleast_1d(Is_arr).ravel()
    beta = np.linspace(0.0, pi / 2, _N_BETA)
    id_g, iq_g = _polar(flat[:, None], beta[None, :])
    T = model.torque(id_g, iq_g)
    k = np.argmax(T, axis=1)

    best_beta = np.empty_like(flat)
    for j, (I, kj) in enumerate(zip(flat, k)):
        lo, hi = beta[max(kj - 1, 0)], beta[min(kj + 1, _N_BETA - 1)]

        def neg_T(b, I=I):
            return -float(model.torque(*_polar(I, b)))

        res = minimize_scalar(neg_T, bounds=(lo, hi), method="bounded", options={"xatol": 1e-12})
        best_beta[j] = res.x if -res.fun >= T[j, kj] else beta[kj]

    id_, iq = _polar(flat, best_beta)
    return id_.reshape(Is_arr.shape), iq.reshape(Is_arr.shape)


def base_speed(model, limits: Limits) -> float:
    """기저속도 ωm [rad/s]: Imax의 MTPA점에서 |v| = Vmax가 되는 속도 (derivations.md 5절).

    |v|² = Rs²·I² + 2·ωe·Rs·(ψd·iq − ψq·id) + ωe²·|ψ|² = Vmax²  을 ωe에 대해 푼 양의 근.
    Rs = 0이면 ωe = Vmax/|ψ|.
    """
    id_, iq = mtpa_point(model, limits.Imax)
    psi_d, psi_q = model.flux(id_, iq)
    a = float(psi_d**2 + psi_q**2)
    b = float(2 * model.Rs * (psi_d * iq - psi_q * id_))
    c = float(model.Rs**2 * limits.Imax**2 - limits.Vmax**2)
    if c >= 0:
        raise ValueError("Rs·Imax ≥ Vmax: 저항 전압강하만으로 전압 한계를 넘어 기저속도가 없다")
    we = (-b + sqrt(b * b - 4 * a * c)) / (2 * a)
    return we / model.p


def _refine_max_torque(model, limits, we, x0, T0):
    """격자 최적점 x0=(id, iq)에서 SLSQP로 토크 최대화 (두 제약 포함). 개선·실행 가능할 때만 채택."""
    I, V = limits.Imax, limits.Vmax
    scale = max(T0, 1e-3)

    def neg_T(x):
        return -float(model.torque(x[0] * I, x[1] * I)) / scale

    cons = [
        {"type": "ineq", "fun": lambda x: 1.0 - (x[0] ** 2 + x[1] ** 2)},
        {"type": "ineq", "fun": lambda x: 1.0 - (float(_vmag(model, x[0] * I, x[1] * I, we)) / V) ** 2},
    ]
    res = minimize(neg_T, np.asarray(x0) / I, method="SLSQP", bounds=[(-1, 0), (0, 1)],
                   constraints=cons, options={"maxiter": 200, "ftol": 1e-13})
    id_, iq = res.x[0] * I, res.x[1] * I
    ok = (np.hypot(id_, iq) <= I * (1 + _ACCEPT_TOL)
          and float(_vmag(model, id_, iq, we)) <= V * (1 + _ACCEPT_TOL)
          and float(model.torque(id_, iq)) >= T0)
    return (id_, iq) if ok else (x0[0], x0[1])


def max_torque_curve(model, limits: Limits, speeds) -> TorqueSpeedTable:
    """속도별 최대 토크와 그때의 (id, iq), 운전 모드 (기획서 5.3, derivations.md 6~8절).

    제약: id² + iq² ≤ Imax², vd² + vq² ≤ Vmax² (Rs 전압강하 포함).
    방법: dq 평면 401×401 격자 전수 탐색 → SLSQP 국소 보정.
    한계: 전압 제약을 만족하는 영역이 격자 간격(Imax/400)보다 좁은 최고속도 직전(약 0.3% 이내)에서는
    feasible을 놓칠 수 있다.
    모드: 전압 비활성 → MTPA, 전압·전류 활성 → FW, 전압만 활성 → MTPV.
    speeds: 기계 속도 배열 [rad/s].
    """
    speeds = np.atleast_1d(np.asarray(speeds, dtype=float))
    I, V = limits.Imax, limits.Vmax

    g_id, g_iq = np.meshgrid(np.linspace(-I, 0.0, _N_GRID), np.linspace(0.0, I, _N_GRID), indexing="ij")
    inside = g_id**2 + g_iq**2 <= I**2
    g_id, g_iq = g_id[inside], g_iq[inside]
    g_T = model.torque(g_id, g_iq)

    n = speeds.size
    T_max, id_o, iq_o = (np.full(n, np.nan) for _ in range(3))
    mode = np.full(n, "INFEASIBLE", dtype="<U10")
    feasible = np.zeros(n, dtype=bool)

    for j, w in enumerate(speeds):
        we = model.p * w
        ok = _vmag(model, g_id, g_iq, we) <= V
        if not ok.any():
            continue
        i0 = np.argmax(np.where(ok, g_T, -np.inf))
        id_, iq = _refine_max_torque(model, limits, we, (g_id[i0], g_iq[i0]), float(g_T[i0]))
        T_max[j], id_o[j], iq_o[j], feasible[j] = float(model.torque(id_, iq)), id_, iq, True

        v_act = float(_vmag(model, id_, iq, we)) >= V * (1 - _ACTIVE_TOL)
        i_act = np.hypot(id_, iq) >= I * (1 - _ACTIVE_TOL)
        mode[j] = "MTPA" if not v_act else ("FW" if i_act else "MTPV")

    return TorqueSpeedTable(speeds, T_max, id_o, iq_o, mode, T_max * speeds, feasible)


def _current_for_torque(model, T, beta, Imax):
    """전류각 β에서 토크 T를 내는 전류 크기 Is. 이분법(Is에 대해 T 단조증가 가정).

    Imax에서도 T에 못 미치는 β는 NaN. 상수 파라미터 IPMSM(Lq ≥ Ld)에서 β ∈ [0, 90°]이면 성립한다.
    """
    beta = np.asarray(beta, dtype=float)
    lo, hi = np.zeros_like(beta), np.full_like(beta, Imax)
    reachable = model.torque(*_polar(hi, beta)) >= T
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        low = model.torque(*_polar(mid, beta)) < T
        lo, hi = np.where(low, mid, lo), np.where(low, hi, mid)
    return np.where(reachable, hi, np.nan)


def optimal_current(model, limits: Limits, T, speed, objective: str = "current"):
    """토크 T, 기계 속도 speed에서 제약을 지키며 전류 크기를 최소화하는 (id, iq, feasible).

    방법: β 격자마다 T를 내는 Is(β)를 이분법으로 구하고, 전압·전류 제약을 만족하는 것 중 Is 최소를 고른 뒤
    (a) 전압 경계에 걸리면 β를 이분법으로, (b) 내부 최소이면 scipy bounded로 보정한다.
    T ≥ 0(전동)만 다룬다. 실행 불가능하면 (NaN, NaN, False).
    objective: 지금은 "current"만. "loss"는 P2에서.
    """
    if objective != "current":
        raise NotImplementedError("objective='loss'는 P2(losses.py) 이후에 지원한다")
    if T < 0:
        raise ValueError("T < 0(회생)은 M4에서 확장한다")
    I, V, we = limits.Imax, limits.Vmax, model.p * speed

    beta = np.linspace(0.0, pi / 2, _N_BETA)
    Is = _current_for_torque(model, T, beta, I)
    id_, iq = _polar(Is, beta)
    valid = ~np.isnan(Is)
    feas = valid & (_vmag(model, np.nan_to_num(id_), np.nan_to_num(iq), we) <= V)
    if not feas.any():
        return float("nan"), float("nan"), False

    cost = np.where(feas, Is, np.inf)
    k = int(np.argmin(cost))
    b_best = float(beta[k])

    def point(b):
        i_s = float(_current_for_torque(model, T, b, I))
        return i_s, (not np.isnan(i_s)) and float(_vmag(model, *_polar(i_s, b), we)) <= V

    # (a) 이웃 중 전류는 더 작지만 전압 제약에 막힌 쪽이 있으면 그 경계까지 β를 좁힌다
    blocked = [j for j in (k - 1, k + 1) if 0 <= j < _N_BETA and valid[j] and not feas[j] and Is[j] < Is[k]]
    if blocked:
        b_ok, b_bad = b_best, float(beta[blocked[0]])
        for _ in range(60):
            mid = 0.5 * (b_ok + b_bad)
            if point(mid)[1]:
                b_ok = mid
            else:
                b_bad = mid
        b_best = b_ok
    else:
        # (b) 전압이 활성이 아닌 내부 최소: 이웃 구간에서 Is(β) 최소화
        lo = float(beta[k - 1]) if k > 0 and valid[k - 1] else b_best
        hi = float(beta[k + 1]) if k < _N_BETA - 1 and valid[k + 1] else b_best
        if hi > lo:
            res = minimize_scalar(lambda b: point(b)[0], bounds=(lo, hi), method="bounded",
                                  options={"xatol": 1e-12})
            if point(res.x)[1] and point(res.x)[0] <= Is[k]:
                b_best = float(res.x)

    i_s, _ = point(b_best)
    d, q = _polar(i_s, b_best)
    return float(d), float(q), True
