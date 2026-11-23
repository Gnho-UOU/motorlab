"""M7 열 모델: 집중정수 열회로(LPTN). 권선과 고정자 철심의 두 노드와 외부(기름·케이스) 경계.

기획서 4장 M7("집중정수 열회로로 권선·자석 온도 추정, 온도를 저항에 되먹임"), 기획서 5장의 동손 식 `P_cu = 1.5·Rs·(id² + iq²)`, `Rs(T) = R20·(1 + α_cu·(T − 20))`.

수식. 노드 i의 온도 T_i, 열용량 C_i, 노드 사이 열전도도 G_ij(대칭), 경계(온도 T_b 고정)로 가는 열전도도 Gb_i, 입력 열 P_i에 대해
    C_i dT_i/dt = P_i − Σ_j G_ij (T_i − T_j) − Gb_i (T_i − T_b)
행렬로 쓰면 C dT/dt = −L T + P + Gb T_b (L = diag(Σ_j G_ij + Gb_i) − G 는 열 라플라시안, 대칭 양의 정부호).
P, T_b가 구간에서 일정하면 정확해가 있다: T(dt) = e^{A·dt} T + A⁻¹ (e^{A·dt} − I) b, A = −C⁻¹ L, b = C⁻¹ (P + Gb T_b).
정상상태는 L T_ss = P + Gb T_b. 시간 걸음이 크거나 작아도 정확하고(행렬 지수함수), 안정성 제한이 없다.

동손 되먹임: 전류가 정해진 구간에서 동손은 권선 온도에 따라 P_cu(T_w) = 1.5·R21·(1 + α·(T_w − 21))·I_peak² (R21은 ORNL이 21 °C에서 잰 값)이므로
짧은 하위 구간(기본 1 s)마다 현재 T_w로 P_cu를 다시 계산한다. 같은 동작점(전류)에서 저항만 달라지므로 MTPA 전류는 그대로다(전류 최소 운전점이 R에 따라 변하는 효과는 무시).

한계: (1) 권선+고정자 철심 두 노드와 외부 경계만 있다. 자석(회전자) 온도는 이 모델에 없다(ORNL에 자석 온도 측정이 없어 검증 불가). (2) 외부 경계(기름·케이스) 온도 T_b는 호출자가 준다(시나리오 값, ORNL 연속 시험의 기름은 114~130 °C).
(3) 보정은 900 rpm 시험(권선 65~170 °C) 범위다. 그 밖의 속도·냉각 조건은 검증하지 못했다. 근거와 오차는 docs/validation_report.md M7 절.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.linalg import expm

ROOT = Path(__file__).resolve().parents[1]


class ThermalNetwork:
    """노드 이름, 열용량 C [J/K], 노드 사이 열전도도 G [W/K] (대칭, 대각 0), 경계 열전도도 Gb [W/K]."""

    def __init__(self, names, C, G, Gb):
        self.names = list(names)
        self.C = np.asarray(C, dtype=float)
        self.G = np.asarray(G, dtype=float)
        self.Gb = np.asarray(Gb, dtype=float)
        n = len(self.names)
        if self.C.shape != (n,) or self.G.shape != (n, n) or self.Gb.shape != (n,):
            raise ValueError("노드 수와 C, G, Gb의 크기가 맞지 않는다")
        if np.any(self.C <= 0):
            raise ValueError("열용량은 양수여야 한다")
        if np.any(self.G < 0) or np.any(self.Gb < 0) or not np.allclose(self.G, self.G.T) or np.any(np.diag(self.G) != 0):
            raise ValueError("G는 대각이 0인 대칭 음이 아닌 행렬, Gb는 음이 아닌 값이어야 한다")
        if self.Gb.sum() <= 0:
            raise ValueError("경계로 가는 열 경로가 없으면 정상상태가 없다")
        self.L = np.diag(self.G.sum(axis=1) + self.Gb) - self.G
        self._A = -self.L / self.C[:, None]
        self._cache: dict[float, np.ndarray] = {}

    def steady_state(self, P, T_boundary):
        """L T = P + Gb·T_b 의 해."""
        return np.linalg.solve(self.L, np.asarray(P, dtype=float) + self.Gb * float(T_boundary))

    def step(self, T, P, T_boundary, dt):
        """P, T_b가 dt 동안 일정할 때의 정확한 한 걸음."""
        key = float(dt)
        E = self._cache.get(key)
        if E is None:
            E = expm(self._A * dt)
            self._cache[key] = E
        b = (np.asarray(P, dtype=float) + self.Gb * float(T_boundary)) / self.C
        Tinf = np.linalg.solve(self._A, -b)          # 정상상태 (dT/dt = 0): A·T∞ + b = 0
        return Tinf + E @ (np.asarray(T, dtype=float) - Tinf)


@dataclass(frozen=True)
class LPTNParams:
    """보정한 매개변수. 값마다 근거는 JSON의 provenance에 있다(data/thermal/prius2004_lptn.json)."""

    name: str
    C_winding_J_per_K: float
    C_stator_J_per_K: float
    G_winding_stator_W_per_K: float
    G_stator_boundary_W_per_K: float
    R21_ohm: float
    alpha_cu_per_K: float
    boundary_fit_C: float
    fit_initial_stator_C: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)

    def network(self) -> ThermalNetwork:
        G = np.array([[0.0, self.G_winding_stator_W_per_K], [self.G_winding_stator_W_per_K, 0.0]])
        return ThermalNetwork(["winding", "stator"], [self.C_winding_J_per_K, self.C_stator_J_per_K], G, [0.0, self.G_stator_boundary_W_per_K])

    def R_winding(self, T_C):
        return self.R21_ohm * (1.0 + self.alpha_cu_per_K * (np.asarray(T_C, dtype=float) - 21.0))


def load_lptn(name: str) -> LPTNParams:
    d = json.loads((ROOT / "data" / "thermal" / f"{name}_lptn.json").read_text(encoding="utf-8"))
    p = d["parameters"]
    return LPTNParams(name=name, C_winding_J_per_K=p["C_winding_J_per_K"]["value"], C_stator_J_per_K=p["C_stator_J_per_K"]["value"],
                      G_winding_stator_W_per_K=p["G_winding_stator_W_per_K"]["value"],
                      G_stator_boundary_W_per_K=p["G_stator_boundary_W_per_K"]["value"], R21_ohm=p["R21_ohm"]["value"],
                      alpha_cu_per_K=p["alpha_cu_per_K"]["value"], boundary_fit_C=p["boundary_fit_C"]["value"],
                      fit_initial_stator_C=d.get("fit_initial_stator_C", {}), provenance=d.get("provenance", {}))


def simulate_cycle_copper(params: LPTNParams, t_s, current_A, P_other_stator_W, T_boundary_C, T_winding0_C, T_stator0_C,
                          current_is_rms: bool = False, max_substep_s: float = 1.0) -> dict:
    """전류 시계열로 권선·철심 온도를 적분한다. t_s: 시각 [s] (n점), current_A: 점마다 상전류(첨두값, current_is_rms면 실효값), 구간 [t_k, t_k+1]에서 점 k의 값을 쓴다.
    P_other_stator_W: 동손 외 손실(철손, 기계손 중 철심으로 가는 몫)을 구간마다 철심 노드에 넣는 열 [W]. T_boundary_C: 스칼라 또는 점마다.
    동손은 하위 구간마다 현재 권선 온도의 저항으로 다시 계산한다. 돌려주는 값: T_winding_C, T_stator_C (n점), P_copper_W (n점, 구간 시작 시각의 값, 마지막은 직전 값),
    E_copper_J (동손 에너지 합)."""
    t = np.asarray(t_s, dtype=float)
    I = np.asarray(current_A, dtype=float)
    Po = np.asarray(P_other_stator_W, dtype=float)
    Tb = np.broadcast_to(np.asarray(T_boundary_C, dtype=float), t.shape)
    if t.ndim != 1 or len(t) < 2 or np.any(np.diff(t) <= 0) or I.shape != t.shape or Po.shape != t.shape:
        raise ValueError("t는 증가하는 1차원 시각이고 전류와 손실은 같은 길이여야 한다")
    k_phase = 3.0 if current_is_rms else 1.5            # 3·I_rms²·R = 1.5·I_peak²·R
    net = params.network()
    T = np.array([T_winding0_C, T_stator0_C], dtype=float)
    Tw, Ts, Pcu = np.empty(len(t)), np.empty(len(t)), np.empty(len(t))
    Tw[0], Ts[0] = T
    E = 0.0
    for k in range(len(t) - 1):
        n = max(1, int(np.ceil((t[k + 1] - t[k]) / max_substep_s)))
        h = (t[k + 1] - t[k]) / n
        for j in range(n):
            p_cu = k_phase * float(params.R_winding(T[0])) * I[k] ** 2
            if j == 0:
                Pcu[k] = p_cu
            T = net.step(T, [p_cu, Po[k]], Tb[k], h)
            E += p_cu * h
        Tw[k + 1], Ts[k + 1] = T
    Pcu[-1] = Pcu[-2]
    return {"T_winding_C": Tw, "T_stator_C": Ts, "P_copper_W": Pcu, "E_copper_J": E}


def cycle_thermal(result, params: LPTNParams, T_boundary_C: float, T_start_C: float, R_map_ohm: float, T_map_C: float,
                  max_substep_s: float = 1.0) -> dict:
    """주행 사이클 결과(engine.vehicle.CycleResult)의 구간별 전류와 손실로 권선·철심 온도를 구하고 온도에 따른 동손 변화를 전비에 되먹임한다.

    효율맵은 권선 온도 T_map_C의 저항 R_map_ohm으로 만들어져 있다. 구간 k의 동손은 맵에서 P_ref = 1.5·R_map·I_k²이고 실제는 1.5·R(T_w)·I_k²이다.
    동손을 뺀 나머지 손실(철손·기계손·기어 잔여)은 맵 값 그대로 철심 노드로 들어간다고 가정한다(가정: 이 몫의 분배는 측정으로 검증되지 않았다).
    전류가 같은 점에서 저항만 달라진다고 보아 ΔP_cu = 1.5·(R(T_w) − R_map)·I_k²를 전기 입력에 더한다(구동), 회생에서는 회수 전력이 같은 양만큼 줄므로 순 에너지는 두 경우 모두 ΔP_cu만큼 는다.
    시작 온도에서 권선과 철심이 같다고 둔다(T_start_C). 돌려주는 값: T_winding_C, T_stator_C (구간 끝), delta_E_J, E_net_J (보정 후), km_per_kWh (보정 후).
    """
    t = np.asarray(result.t_s, dtype=float)
    n = len(t)
    if n < 2:
        raise ValueError("사이클 구간이 둘 이상이어야 한다")
    mid = 0.5 * (t[:-1] + t[1:])
    edges = np.r_[t[0] - 0.5 * (t[1] - t[0]), mid, t[-1] + 0.5 * (t[-1] - t[-2])]       # 구간 경계 (구간 k = [edges[k], edges[k+1]])
    I = np.asarray(result.current_peak_A, dtype=float)
    p_ref = 1.5 * R_map_ohm * I ** 2
    p_other = np.clip(np.asarray(result.loss_power_W, dtype=float) - p_ref, 0.0, None)
    r = simulate_cycle_copper(params, edges, np.r_[I, I[-1]], np.r_[p_other, p_other[-1]], T_boundary_C, T_start_C, T_start_C,
                              current_is_rms=False, max_substep_s=max_substep_s)
    dt = np.diff(edges)
    p_cu = r["P_copper_W"][:-1]
    delta = float(np.sum((p_cu - p_ref) * dt))
    E_net = float(result.E_net_J) + delta
    return {"T_winding_C": r["T_winding_C"][1:], "T_stator_C": r["T_stator_C"][1:], "P_copper_W": p_cu, "delta_E_J": delta,
            "E_net_J": E_net, "km_per_kWh": float(result.distance_m / 1000.0 / (E_net / 3.6e6))}
