"""측정 손실에서 모델이 설명하지 못하는 부분(잔여 손실)의 구조를 본다. (docs/validation_report.md "원인 탐색" 절)

잔여 = (P_ac − P_mech) − 동손(R20 = 68.7 mΩ, 모델 동작점 전류) − 무부하 실측 손실(TM-423 표 3.7)
  1) 잔여를 토크로 환산(잔여 / ω)해 속도·토크 칸마다 중앙값을 본다.
  2) 무부하 손실을 자속 크기로 키우는 변형(V3, (|ψ|/|ψ0|)^β)이 잔여를 줄이는지 본다.
  3) 3000 rpm 미만 행에서 잔여 = ω·(a + b·T) (마찰 토크 + 출력 비례)로 설명되는지, 그 위에서 무엇이 남는지 본다.
입력: data/fea/prius2004_efficiency_variants.csv (05번 노트북 출력, 행마다 모델 동작점), data/flux_maps/prius2004_fullmodel_teardown_25A.csv.
실행: python notebooks/07_prius_excess_loss_structure.py
"""
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.model import FluxMapModel  # noqa: E402


def load_csv(path):
    lines = [l for l in Path(path).read_text().splitlines() if l.strip() and not l.startswith("#")]
    h = lines[0].strip().split(",")
    A = np.loadtxt(lines[1:], delimiter=",")
    return {k: A[:, i] for i, k in enumerate(h)}


def main() -> None:
    perf = load_csv(ROOT / "data/benchmarks/prius2004_perf_map.csv")
    v = load_csv(ROOT / "data/fea/prius2004_efficiency_variants.csv")
    rl = load_csv(ROOT / "data/benchmarks/prius2004_rotor_loss.csv")
    m = FluxMapModel.from_csv(ROOT / "data/flux_maps/prius2004_fullmodel_teardown_25A.csv", p=4, Rs=0.0)
    key = {(round(a, 1), round(b, 1)): i for i, (a, b) in enumerate(zip(perf["speed_rpm"], perf["torque_Nm"]))}
    idx = np.array([key[(round(a, 1), round(b, 1))] for a, b in zip(v["speed_rpm"], v["torque_Nm"])])
    sp, T = v["speed_rpm"], v["torque_Nm"]
    w = sp * math.pi / 30
    Pm, Pac = perf["P_mech_W"][idx], perf["P_ac_W"][idx]
    nl = np.interp(sp, rl["motor_rpm"], rl["motor_rotor_loss_W"])
    Cu = v["P_cu_W"]
    psi = np.hypot(*m.flux(v["id_A"], v["iq_A"]))
    psi0 = float(np.hypot(*m.flux(0.0, 0.0)))
    meas = Pac - Pm
    core = (sp >= 1000) & (sp <= 4000) & (T >= 30) & (T <= 200)

    def report(label, loss):
        d = (Pm / (Pm + loss) - v["eta_meas"]) * 100
        print(f"  {label:32s} 평균 {d.mean():+5.2f}  RMS {np.sqrt((d ** 2).mean()):4.2f} | 주요영역 {d[core].mean():+5.2f} "
              f"(3%p 이내 {np.mean(np.abs(d[core]) <= 3) * 100:3.0f}%) | 고속(>=4000) {d[sp >= 4000].mean():+5.2f}")

    print("1) 잔여 손실의 토크 환산 [N·m], 중앙값 (행 수)")
    ex = (meas - Cu - nl) / w
    sb = [(500, 1000), (1000, 2000), (2000, 3000), (3000, 4000), (4000, 5000), (5000, 6200)]
    print("   토크\\rpm " + "".join(f"{a}-{b}".rjust(12) for a, b in sb))
    for tl, th in [(0, 40), (40, 80), (80, 150), (150, 250), (250, 400)]:
        row = ""
        for sl, sh in sb:
            k = (sp >= sl) & (sp < sh) & (T >= tl) & (T < th)
            row += (f"{np.median(ex[k]):5.2f}({k.sum():3d})" if k.sum() >= 3 else "-").rjust(12)
        print(f"   {tl:3d}-{th:<3d}  " + row)
    print("   (250~400 N·m 칸은 R20을 역산한 구간이라 잔여가 R20에 흡수되어 작다)")

    print("2) 무부하 손실을 자속으로 키우는 변형")
    report("V1 무부하 실측만", Cu + nl)
    for beta in (1.0, 1.74, 2.0):
        report(f"V3 무부하·(ψ/ψ0)^{beta:.2f}", Cu + nl * (psi / psi0) ** beta)
    bins = [(0, 40), (40, 80), (80, 150), (150, 250), (250, 400)]
    print("   |ψ|/|ψ0| 중앙값(토크 0~40, 40~80, 80~150, 150~250, 250~400): "
          f"{[round(float(np.median((psi / psi0)[(T >= a) & (T < b)])), 2) for a, b in bins]}")

    print("3) 3000 rpm 미만 행에서 잔여 = ω·(a + b·T)")
    low = sp < 3000
    X = np.c_[w, w * T]
    wt = 1 / Pm[low]
    a, b = np.linalg.lstsq(X[low] * wt[:, None], (meas - Cu - nl)[low] * wt, rcond=None)[0]
    pred = X @ np.array([a, b])
    d = (Pm / (Pm + Cu + nl + pred) - v["eta_meas"]) * 100
    print(f"   a = {a:.2f} N·m (속도에 무관한 마찰 토크), b = {b * 100:.2f}% (출력 비례). 3000 rpm 미만: 평균 {d[low].mean():+.2f}, "
          f"RMS {np.sqrt((d[low] ** 2).mean()):.2f}%p; 3000 rpm 이상(외삽): 평균 {d[~low].mean():+.2f}, RMS {np.sqrt((d[~low] ** 2).mean()):.2f}%p")
    f_e = 4 * sp / 60
    for lo, hi in [(3000, 4000), (4000, 5000), (5000, 6200)]:
        k = (sp >= lo) & (sp < hi)
        r = (meas - Cu - nl - pred)[k]
        print(f"   {lo}-{hi} rpm 남는 손실 중앙값 {np.median(r):5.0f} W = {np.median(r / f_e[k]):.2f} W/Hz")


if __name__ == "__main__":
    main()
