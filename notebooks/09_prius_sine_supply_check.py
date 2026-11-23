"""정현파 전원(인버터 없음) 900 rpm 시험으로 자속 맵과 손실 모델을 검증한다. (docs/validation_report.md "원인 탐색" 절)

데이터: data/benchmarks/prius2004_sine900.csv (ORNL/TM-2005/33 표 4~6). 60 Hz 정현파 전원에 동기시켜 돌렸으므로 제어기가 동작점을
고르지 않고, PWM 고조파도 없다. 선간 전압 V_LL과 토크가 주어지면 동작점 (id, iq)가 전압 방정식으로 정해진다:
  vd = Rs·id − ωe·ψq,  vq = Rs·iq + ωe·ψd,  |v| = √2·V_LL/√3,  Te = 1.5·p·(ψd·iq − ψq·id)
미지수 (id, iq)를 |v|와 토크 두 식으로 푼다(해가 둘이면 전류가 작은 쪽). 비교:
  (1) 선전류 I와 역률: 맵(자속) 검증. 보정 없음.
  (2) 입력 전력: P_el − [T·ω + 구동계 마찰 160 W + 동손] = 철손 + 잔여 손실. 동손은 모델 전류가 아니라 **측정 전류**로 계산한다(모델 전류가 달라도
      손실 비교가 흐려지지 않게). 이 값이 작으면 인버터 시험의 잔여 손실은 인버터가 만든 것이다.
토크게이지는 기어를 지난 뒤 값이라 같은 보고서의 무부하 회전 시험 160.2 W(1.7 N·m)를 구동계 마찰로 본다(105 °C만 150.8 W, 이 파일에는 없음).
실행: python notebooks/09_prius_sine_supply_check.py [자속맵.csv]   (기본: 최종 채택 맵)
"""
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import fsolve

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.model import FluxMapModel  # noqa: E402

R20, ALPHA = 0.069 / (1 + 0.00393), 0.00393      # R(21 °C) = 0.069 Ω (ORNL/TM-2010/253 표 2.7, 상 저항 = 선간 평균의 절반)
DRAG_W, W_M = 160.2, 900 * math.pi / 30          # 구동계 마찰 [W], 기계 각속도 [rad/s]
WE = 4 * W_M


def load():
    lines = [l for l in (ROOT / "data/benchmarks/prius2004_sine900.csv").read_text().splitlines() if l.strip() and not l.startswith("#")]
    h = lines[0].split(",")
    rows = []
    for l in lines[1:]:
        v = l.split(",")
        rows.append({k: (float(x) if x != "" else float("nan")) for k, x in zip(h, v)})
    return rows


def solve(m, V_LL, T_em, Rs):
    vpk = math.sqrt(2) * V_LL / math.sqrt(3)
    best = None
    for id0 in (-20.0, -60.0, -120.0):
        for iq0 in (10.0, 60.0, 150.0):
            def f(x):
                id_, iq = min(0.0, max(-250.0, x[0])), min(250.0, max(0.0, x[1]))
                pd, pq = (float(a) for a in m.flux(id_, iq))
                vd, vq = Rs * id_ - WE * pq, Rs * iq + WE * pd
                return [math.hypot(vd, vq) - vpk, float(m.torque(id_, iq)) - T_em]
            x, info, ier, _ = fsolve(f, [id0, iq0], full_output=True)
            if ier == 1 and -250 <= x[0] <= 0 and 0 <= x[1] <= 250:
                if best is None or math.hypot(*x) < math.hypot(*best):
                    best = x
    return best


def main() -> None:
    MAP = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/flux_maps/prius2004_fullmodel_teardown_25A.csv"
    m = FluxMapModel.from_csv(MAP, p=4, Rs=0.0)
    print(f"맵: {MAP.name}")
    print("냉각 V_LL  T   |  I 측정  I 모델  비  | 역률 측정 모델 | 손실 측정−(기계+마찰+동손) [W]")
    out = []
    for r in load():
        if r["torque_Nm"] < 10:
            continue
        Rs = R20 * (1 + ALPHA * (r["T_winding_C"] - 20))
        sol = solve(m, r["V_LL"], r["torque_Nm"] + DRAG_W / W_M, Rs)
        if sol is None:
            print(f"{r['coolant_C']:4.0f} {r['V_LL']:5.0f} {r['torque_Nm']:4.0f}  해 없음 (모델이 이 전압·토크를 만들 수 없다)")
            continue
        id_, iq = sol
        pd, pq = (float(a) for a in m.flux(id_, iq))
        vd, vq = Rs * id_ - WE * pq, Rs * iq + WE * pd
        I = math.hypot(id_, iq) / math.sqrt(2)
        P_in = 1.5 * (vd * id_ + vq * iq)
        pf = P_in / (math.sqrt(3) * r["V_LL"] * I)
        cu = 3 * Rs * I ** 2
        cu_meas = 3 * Rs * r["I_A"] ** 2
        resid = r["P_elec_W"] - (r["P_mech_W"] + DRAG_W + cu_meas)
        out.append((r["coolant_C"], r["torque_Nm"], r["I_A"], I, r["pf"], pf, resid, r["P_mech_W"], r["P_elec_W"], cu_meas))
        print(f"{r['coolant_C']:4.0f} {r['V_LL']:5.0f} {r['torque_Nm']:4.0f}  | {r['I_A']:6.1f} {I:6.1f} {I / r['I_A']:5.2f} | {r['pf']:5.2f} {pf:5.2f} | {resid:6.0f}")
    A = np.array(out)
    ok = ~np.isnan(A[:, 4])
    print(f"\n행 {len(A)}개. 전류 모델/측정: 중앙값 {np.median(A[:, 3] / A[:, 2]):.3f}, 범위 {np.min(A[:, 3] / A[:, 2]):.3f}~{np.max(A[:, 3] / A[:, 2]):.3f}")
    print(f"역률 모델−측정: 평균 {np.mean(A[ok, 5] - A[ok, 4]):+.3f}, 범위 {np.min(A[ok, 5] - A[ok, 4]):+.3f}~{np.max(A[ok, 5] - A[ok, 4]):+.3f}")
    hi = A[:, 1] >= 60
    print(f"철손 + 잔여 손실(측정 − 기계 − 마찰 − 동손(측정 전류)): 토크 60 N·m 이상 중앙값 {np.median(A[hi, 6]):.0f} W (입력 전력의 {np.median(A[hi, 6] / A[hi, 8]) * 100:.1f}%), "
          f"전체 범위 {A[:, 6].min():.0f}~{A[:, 6].max():.0f} W")
    eta_meas = A[:, 7] / A[:, 8]
    eta_mod = A[:, 7] / (A[:, 7] + DRAG_W + A[:, 9])
    print(f"효율(측정 전류 동손 + 마찰만): 측정보다 평균 {np.mean(eta_mod - eta_meas) * 100:+.2f}%p 높다 (철손·잔여 손실 몫)")
    lo = A[:, 1] <= 60
    print(f"전류 모델/측정: 토크 60 N·m 이하 중앙값 {np.median(A[lo, 3] / A[lo, 2]):.2f}, 70 N·m 이상 {np.median(A[~lo, 3] / A[~lo, 2]):.2f}, 110 N·m 이상 {np.median(A[A[:, 1] >= 110, 3] / A[A[:, 1] >= 110, 2]):.2f}")


if __name__ == "__main__":
    main()
