"""M7 열 모델 검증과 주행 사이클 권선 온도. (docs/validation_report.md "M7" 절)

(1) ORNL/TM-2005/33 대비: 연속 시험 4점의 권선 온도(기름 온도를 경계로, 보정에 쓴 자료), 첨두 시험 5곡선(철심 초기 온도만 맞춘 값),
    첨두 곡선 하나를 빼고 나머지로 G_ws를 다시 맞춰 뺀 곡선을 예측(철심 초기 온도 하나만 맞춤)하는 뺀-하나-검증.
(2) 사이클: Prius 효율맵(물리 모델, 권선 100 °C 저항)과 같은 구간별 전류·손실로 권선 온도를 적분하고 온도에 따른 동손 변화를 전비에 되먹임한다.
    경계(기름·케이스) 온도는 시나리오 값이다. 시작은 권선=철심=경계 온도.
입력: data/thermal/*.csv, *.json, 효율맵(notebooks/10과 같은 방법). 실행: python notebooks/19_prius_thermal.py (약 3분)
"""
import importlib.util
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "data" / "thermal"))
from engine.thermal import cycle_thermal, load_lptn, simulate_cycle_copper  # noqa: E402
from engine.vehicle import load_cycle, load_vehicle, run_cycle  # noqa: E402
import fit_lptn as fl  # noqa: E402

_spec = importlib.util.spec_from_file_location("fe", ROOT / "notebooks" / "10_prius_fuel_economy.py")
fe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fe)


def validate_ornl() -> None:
    p = load_lptn("prius2004")
    steady, curves = fl.load_steady(), fl.load_peak()
    net = p.network()
    print(f"매개변수: C_w {p.C_winding_J_per_K:.0f} J/K, C_s {p.C_stator_J_per_K:.0f} J/K, G_ws {p.G_winding_stator_W_per_K:.1f} W/K, G_sb {p.G_stator_boundary_W_per_K:.1f} W/K, T_b {p.boundary_fit_C} °C")
    print("\n## 연속 시험 4점 (기름 온도를 경계로, 동손 → 권선, 철손+잔여 → 철심; G_sb는 같은 4점의 평균)")
    print("| 냉각수 입구 | 측정 권선 | 모델 권선 | 차이 | 모델 철심 | (측정 케이스 평균) |")
    print("|---|---|---|---|---|---|")
    case = (91.2, 97.3, 108.3, 118.4)                     # ORNL 표 16의 케이스 온도 세 점의 평균 (참고, 보정에 안 씀)
    for (Tc, Tq, Pt, Pm, Pcu, Pco, Tw, To, dT, fl_), cs in zip(steady, case):
        T = net.steady_state([Pcu, Pco], To)
        print(f"| {Tc:.1f} | {Tw:.1f} | {T[0]:.1f} | {T[0] - Tw:+.1f} | {T[1]:.1f} | {cs} |")
    print("\n## 첨두 시험 5곡선 (그림 19, 철심 초기 온도는 곡선마다 맞춤)")
    print("| 토크 [N·m] | 전류 [Arms] | 권선 시작→끝 [°C] | 철심 초기(맞춘 값) | RMS [K] | 최대 [K] |")
    print("|---|---|---|---|---|---|")
    for tq, v in curves.items():
        T = simulate_cycle_copper(p, v[:, 0], np.full(len(v), v[0, 2]), np.zeros(len(v)), p.boundary_fit_C, v[0, 1], p.fit_initial_stator_C[str(tq)], current_is_rms=True)["T_winding_C"]
        e = T - v[:, 1]
        print(f"| {tq} | {v[0, 2]:.0f} | {v[0, 1]:.0f} → {v[-1, 1]:.0f} | {p.fit_initial_stator_C[str(tq)]:.0f} | {np.sqrt(np.mean(e ** 2)):.2f} | {np.abs(e).max():.2f} |")
    print("\n## 뺀-하나-검증: 나머지 4곡선으로 G_ws, 각 곡선의 철심 초기 온도를 맞추고, 뺀 곡선은 철심 초기 온도 하나만 맞춰 예측")
    print("| 뺀 곡선 [N·m] | G_ws [W/K] | 철심 초기(맞춘 값) | RMS [K] | 최대 [K] |")
    print("|---|---|---|---|---|")
    from scipy.optimize import least_squares
    T_b = float(np.mean(steady[:, 7]))
    for out in curves:
        rest = {k: v for k, v in curves.items() if k != out}
        G_ws, G_sb, _, _ = fl.fit(T_b, steady, rest)
        v = curves[out]
        g = least_squares(lambda t: fl.simulate_curve(G_ws, G_sb, T_b, v, t[0]) - v[:, 1], [60.0], bounds=([0.0], [170.0]))
        print(f"| {out} | {G_ws:.0f} | {g.x[0]:.0f} | {np.sqrt(np.mean(g.fun ** 2)):.2f} | {np.abs(g.fun).max():.2f} |")


def cycles() -> None:
    p = load_lptn("prius2004")
    veh = load_vehicle("prius2004")
    em = fe.build_map(100, False)
    R_map = fe.eff.R20 * (1 + fe.eff.ALPHA_CU * (100 - 20))
    print("\n## 사이클 권선 온도와 전비 되먹임 (효율맵: 물리 모델, 권선 100 °C 저항; 회생 비율 1)")
    print("| 사이클 | 경계 온도 [°C] | 권선 최고 [°C] | 권선 평균 [°C] | 전비 맵 가정 [km/kWh] | 전비 온도 되먹임 [km/kWh] | 변화 |")
    print("|---|---|---|---|---|---|---|")
    for name in ("WLTP", "UDDS", "HWFET"):
        r = run_cycle(veh, em, load_cycle(name), 1.0)
        for Tb in (60.0, 90.0, 115.0):
            th = cycle_thermal(r, p, Tb, Tb, R_map, 100.0)
            print(f"| {name} | {Tb:.0f} | {th['T_winding_C'].max():.0f} | {th['T_winding_C'].mean():.0f} | {r.km_per_kWh:.2f} | {th['km_per_kWh']:.2f} | {100 * (th['km_per_kWh'] / r.km_per_kWh - 1):+.2f} % |")


if __name__ == "__main__":
    validate_ornl()
    cycles()
