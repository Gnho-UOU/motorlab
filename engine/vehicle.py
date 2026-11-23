"""M4 차량·주행 사이클·전비: 사이클의 속도 곡선을 모터 동작점으로 바꾸고 효율맵에서 전기 에너지를 적분한다.

기획서 5.5절, 규약은 docs/ENGINE_SPEC.md 5-1절, 유도는 docs/derivations.md 11절.

식 (모두 SI, 힘 N, 속도 m/s):
  바퀴 힘      F = m_eq·dv/dt + (A + B·v + C·v²)          A, B, C: EPA 도로 부하 계수(공기·구름·구동계를 한꺼번에 담은 코스트다운 값)
  바퀴 동력    P_w = F·v
  모터 속도    ω_m = g·v                                  g = G/r_w [rad/s per m/s], 기어비와 바퀴 반지름을 합친 값
  모터 축 동력 P_s = P_w + L_gear(ω_m)                    L_gear: 기어 무부하 손실. 구동에서는 모터가 더 내고, 회생에서는 |P_w| − L만 받는다
  구동(P_s > 0): 전자기 토크 T_e = P_s/ω_m + P_mech(ω_m)/ω_m, 전기 입력 P_in(T_e, ω_m)을 효율맵에서 보간
  회생(P_s < 0): 모터가 받는 축 동력 |P_s|, T_e = |P_s|/ω_m − P_mech/ω_m, 전기 출력 P_el = 2·T_e·ω_m − P_in(T_e, ω_m)
                (P_in = T_e·ω_m + 손실이므로 P_el = T_e·ω_m − 손실). 회생 자기 회로는 구동과 거울 대칭(ψd 짝, ψq 홀)이라 같은 맵을 쓴다.
  전비 = 주행 거리 / (E_in − E_regen)  [km/kWh],  E_regen = 회생 경로로 되찾은 전기 에너지
  이산화: 1 Hz 속도 표의 구간마다 평균 속도·평균 가속도로 동작점을 정하고 Δt를 곱해 더한다(구간 중점 적분).

한계: 모터 입력(교류) 기준이다. 인버터·배터리·보조 부하는 포함하지 않는다. 기어 손실은 무부하 값뿐이다(부하 의존 손실 자료 없음).
모터가 낼 수 없는 토크는 낼 수 있는 최대로 자르고 shortfall로 기록한다(숨기지 않는다). 사이클 데이터와 차량 값의 출처는 data/cycles, data/vehicles.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
LBF = 4.4482216152605        # N
MPH = 0.44704                # m/s
LB = 0.45359237              # kg
_CYCLES = {"WLTP": "wltc_class3b.csv", "UDDS": "udds.csv", "HWFET": "hwfet.csv"}


@dataclass(frozen=True)
class Cycle:
    name: str
    t_s: np.ndarray
    v_ms: np.ndarray
    source: str


@dataclass(frozen=True)
class Vehicle:
    """mass_kg는 관성에 쓰는 등가 질량. 도로 부하 F = a + b·v + c·v² [N, v in m/s]. motor_speed_gain = ω_m/v [rad/s per m/s]."""

    mass_kg: float
    road_a_N: float
    road_b_Ns_m: float
    road_c_Ns2_m2: float
    motor_speed_gain: float
    gear_speed_rad: np.ndarray       # 기어 손실 표의 모터 속도 [rad/s], 오름차순
    gear_loss_W: np.ndarray          # 그 속도의 기어 무부하 손실 [W]

    def gear_loss(self, w):
        """속도가 표의 첫 점보다 낮으면 원점(0, 0)에서 직선으로 이은 값을 쓴다(정지하면 끌림 손실도 0)."""
        sp, L = np.asarray(self.gear_speed_rad, float), np.asarray(self.gear_loss_W, float)
        if sp[0] > 0:
            sp, L = np.r_[0.0, sp], np.r_[0.0, L]
        return np.interp(w, sp, L)


@dataclass(frozen=True)
class CycleResult:
    """에너지는 J. E_in: 구동 전기 소비, E_regen: 회생 전기 회수(비율 적용 후), E_net = E_in − E_regen."""

    cycle: str
    regen_ratio: float
    distance_m: float
    E_in_J: float
    E_regen_J: float
    E_net_J: float
    E_wheel_traction_J: float
    E_wheel_brake_J: float
    E_friction_brake_J: float
    E_gear_loss_traction_J: float
    E_motor_loss_J: float            # 구동 중 모터 손실(동손 + 철손 + 기계손 + 잔여) = E_in − 구동 축 에너지
    shortfall_time_s: float
    shortfall_wheel_energy_J: float
    t_s: np.ndarray
    v_ms: np.ndarray
    wheel_power_W: np.ndarray
    motor_speed_rad: np.ndarray
    shaft_power_W: np.ndarray
    em_torque_Nm: np.ndarray         # 부호 있는 전자기 토크 (구동 +, 회생 −)
    elec_power_W: np.ndarray         # 부호 있는 전기 동력 (소비 +, 회수 −, 회수 비율 적용 후)

    @property
    def km_per_kWh(self) -> float:
        return float(self.distance_m / 1000.0 / (self.E_net_J / 3.6e6))

    @property
    def Wh_per_km(self) -> float:
        return float(self.E_net_J / 3600.0 / (self.distance_m / 1000.0))


def _read_csv(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    comments = [l for l in lines if l.startswith("#")]
    rows = [l for l in lines if l.strip() and not l.startswith("#")]
    header = rows[0].split(",")
    A = np.array([[float(x) for x in r.split(",")] for r in rows[1:]])
    return comments, {h: A[:, i] for i, h in enumerate(header)}


def load_cycle(name: str) -> Cycle:
    """name ∈ {WLTP(클래스 3b), UDDS, HWFET}. 속도는 km/h에서 m/s로 바꾼다."""
    key = name.upper()
    if key not in _CYCLES:
        raise ValueError(f"알 수 없는 사이클 {name!r} (가능: {', '.join(_CYCLES)})")
    comments, c = _read_csv(ROOT / "data" / "cycles" / _CYCLES[key])
    return Cycle(key, c["time_s"], c["speed_kmh"] / 3.6, comments[0].lstrip("# ").strip())


def load_vehicle(name: str) -> Vehicle:
    """data/vehicles/<name>.json: 출처 단위(lb, lbf, mph, rpm/mph)를 SI로 바꾼다."""
    j = json.loads((ROOT / "data" / "vehicles" / f"{name}.json").read_text(encoding="utf-8"))
    r = j["road_load_epa_target"]
    _, g = _read_csv(ROOT / j["gear_loss_csv"])
    gain = j["motor_rpm_per_vehicle_mph"] * (np.pi / 30) / MPH          # rpm/mph -> rad/s per (m/s)
    return Vehicle(
        mass_kg=j["mass_equivalent_test_weight_lb"] * LB,
        road_a_N=r["A_lbf"] * LBF,
        road_b_Ns_m=r["B_lbf_per_mph"] * LBF / MPH,
        road_c_Ns2_m2=r["C_lbf_per_mph2"] * LBF / MPH**2,
        motor_speed_gain=gain,
        gear_speed_rad=g["motor_rpm"] * np.pi / 30,
        gear_loss_W=g["gear_loss_W"],
    )


def road_load_force(vehicle: Vehicle, v):
    """F_road = A + B·v + C·v² [N]."""
    v = np.asarray(v, dtype=float)
    return vehicle.road_a_N + vehicle.road_b_Ns_m * v + vehicle.road_c_Ns2_m2 * v**2


def _bilinear(Tg, Wg, Z, T, W):
    """격자 Z[i, j]를 (T, W)에서 쌍선형 보간. T가 첫 격자보다 낮으면 처음 두 행의 기울기로 외삽하고, 격자 밖(위·속도)이나
    모서리에 NaN(실행 불가)이 있으면 NaN을 돌려준다."""
    if not (Wg[0] <= W <= Wg[-1]) or T > Tg[-1]:
        return np.nan
    j = int(np.clip(np.searchsorted(Wg, W) - 1, 0, len(Wg) - 2))
    i = int(np.clip(np.searchsorted(Tg, T) - 1, 0, len(Tg) - 2))
    u = (T - Tg[i]) / (Tg[i + 1] - Tg[i])
    s = (W - Wg[j]) / (Wg[j + 1] - Wg[j])
    z = 0.0
    for di, wi in ((0, 1 - u), (1, u)):
        for dj, wj in ((0, 1 - s), (1, s)):
            w = wi * wj
            if w != 0.0:
                z += w * Z[i + di, j + dj]
    return z


class _MapLookup:
    """EfficiencyMap에서 (T_e, ω)의 P_in과 손실 성분을 읽는다. 실행 불가 점은 낼 수 있는 최대 토크로 자른다."""

    def __init__(self, em):
        self.em = em
        self.Tg, self.Wg = np.asarray(em.T_grid, float), np.asarray(em.speed_grid, float)
        feas = np.asarray(em.feasible, bool)
        self.tmax = np.array([self.Tg[feas[:, j]].max() if feas[:, j].any() else -np.inf for j in range(len(self.Wg))])
        pm = np.asarray(em.P_mech, float)
        self.pmech = np.array([np.nanmax(pm[:, j]) if np.isfinite(pm[:, j]).any() else 0.0 for j in range(len(self.Wg))])

    def mech(self, w):
        return float(np.interp(w, self.Wg, self.pmech))

    def tmax_at(self, w):
        j = int(np.clip(np.searchsorted(self.Wg, w) - 1, 0, len(self.Wg) - 2))
        return float(min(self.tmax[j], self.tmax[j + 1]))          # 속도 사이에서는 보수적으로 작은 쪽

    def read(self, Te, w):
        """(P_in, deliverable, Te_used). 낼 수 없으면 Te를 tmax로 자르고, 그래도 없으면 P_in = NaN."""
        w = float(np.clip(w, self.Wg[0], self.Wg[-1]))
        p = _bilinear(self.Tg, self.Wg, self.em.P_in, Te, w)
        if np.isfinite(p):
            return max(p, 0.0), True, Te
        tm = self.tmax_at(w)
        if not np.isfinite(tm) or tm <= 0:
            return np.nan, False, 0.0
        Te_used = min(Te, tm)
        p = _bilinear(self.Tg, self.Wg, self.em.P_in, Te_used, w)
        return (max(p, 0.0) if np.isfinite(p) else np.nan), False, Te_used


def run_cycle(vehicle: Vehicle, eff_map, cycle: Cycle, regen_ratio: float) -> CycleResult:
    """사이클 한 번의 전기 에너지와 전비. regen_ratio ∈ [0, 1]: 제동 동력 중 모터가 받는 비율(나머지는 마찰 제동)."""
    if not 0.0 <= regen_ratio <= 1.0:
        raise ValueError("regen_ratio는 0~1")
    lk = _MapLookup(eff_map)
    t0, v0 = np.asarray(cycle.t_s, float), np.asarray(cycle.v_ms, float)
    # 구간(Δt)마다 평균 속도와 평균 가속도로 푼다: 관성 일 m·a·v̄·Δt = ½·m·(v₁² − v₀²)이 정확히 성립해 운동 에너지가 새지 않는다.
    dt = np.diff(t0)
    a = np.diff(v0) / dt
    v = 0.5 * (v0[:-1] + v0[1:])
    t = 0.5 * (t0[:-1] + t0[1:])
    F = vehicle.mass_kg * a + road_load_force(vehicle, v)
    Pw = F * v
    w = vehicle.motor_speed_gain * v
    L = vehicle.gear_loss(w)
    n = len(t)
    p_in = np.zeros(n)              # 구동 전기 입력 [W]
    p_gen = np.zeros(n)             # 회생 경로 전기 출력 [W] (회수 비율 적용 전)
    p_shaft_drive = np.zeros(n)     # 구동에서 실제로 낸 축 동력
    Te_signed = np.zeros(n)
    short_w = np.zeros(n)           # 못 낸 바퀴 동력 [W]
    brake_fric_w = np.zeros(n)
    w_eps = lk.Wg[0] * 0.5
    for k in range(n):
        if w[k] < w_eps:
            continue                                    # 정지 부근: 에너지 기여 없음
        mech = lk.mech(w[k])
        if Pw[k] + L[k] >= 0:                           # 구동
            Ps = Pw[k] + L[k]
            Te = Ps / w[k] + mech / w[k]
            p, ok, Te_used = lk.read(Te, w[k])
            Ps_used = Te_used * w[k] - mech
            if not np.isfinite(p):
                short_w[k] = Ps
                continue
            p_in[k], p_shaft_drive[k], Te_signed[k] = p, min(Ps, Ps_used), Te_used
            if not ok:
                short_w[k] = max(Ps - Ps_used, 0.0)
        else:                                           # 회생(제동)
            brake = -Pw[k]                              # 바퀴가 내놓는 제동 동력 [W]
            to_motor = regen_ratio * brake - L[k]       # 모터 축이 받는 동력
            brake_fric_w[k] = brake - regen_ratio * brake
            if to_motor <= 0:
                continue
            Te = to_motor / w[k] - mech / w[k]
            if Te <= 0:
                continue
            p, ok, Te_used = lk.read(Te, w[k])
            if not np.isfinite(p):
                brake_fric_w[k] += regen_ratio * brake
                continue
            if not ok:                                  # 모터가 받을 수 있는 한계 밖: 나머지는 마찰 제동
                brake_fric_w[k] += (Te - Te_used) * w[k]
            p_gen[k] = max(2.0 * Te_used * w[k] - p, 0.0)
            Te_signed[k] = -Te_used
    E = lambda x: float(np.sum(np.asarray(x) * dt))
    pos, neg = np.clip(Pw, 0, None), np.clip(-Pw, 0, None)
    motoring = (Pw + L >= 0) & (w >= w_eps)
    E_in, E_regen = E(p_in), E(p_gen)
    return CycleResult(
        cycle=cycle.name, regen_ratio=float(regen_ratio), distance_m=E(v),
        E_in_J=E_in, E_regen_J=E_regen, E_net_J=E_in - E_regen,
        E_wheel_traction_J=E(pos), E_wheel_brake_J=E(neg), E_friction_brake_J=E(brake_fric_w),
        E_gear_loss_traction_J=E(np.where(motoring, L, 0.0)),
        E_motor_loss_J=E_in - E(p_shaft_drive),
        shortfall_time_s=float(np.sum(dt[short_w > 0])), shortfall_wheel_energy_J=E(short_w),
        t_s=t, v_ms=v, wheel_power_W=Pw, motor_speed_rad=w,
        shaft_power_W=np.where(motoring, p_shaft_drive, 0.0), em_torque_Nm=Te_signed, elec_power_W=p_in - p_gen,
    )
