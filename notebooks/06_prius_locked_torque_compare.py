"""잠금 회전자 토크: 전체 모터 FEA 대 ORNL 측정(TM-423 표 3.2 / 그림 3.10)을 비교한다. (docs/validation_report.md, V4 토크)

FEA 파일 형식: Ia_A,theta_deg,torque_Nm,... (femm/validate_full.py locked). 측정: data/benchmarks/prius2004_locked_torque.csv.
비교 두 가지:
  1) 전류별 최대 토크 (FEA / 그림 3.10 값). 각도 기준과 무관하다.
  2) 토크-각도 곡선 모양. ORNL의 각도 영점·방향이 보고서에 없어서 영점 c 하나(250 A 곡선에서만 정함)와 거울 방향을 가정한다.
실행: python notebooks/06_prius_locked_torque_compare.py [FEA.csv ...]   (여러 파일이면 나란히 보인다)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.interpolate import CubicSpline

ROOT = Path(__file__).resolve().parents[1]
ORNL = ROOT / "data" / "benchmarks" / "prius2004_locked_torque.csv"
CURRENTS = [50, 75, 100, 125, 150, 200, 250]
FIG_3_10_PEAK = {50: 74, 75: 118, 100: 154, 125: 199, 150: 221, 200: 286, 250: 337}   # TM-423 Fig. 3.10


def load(fea_path: Path):
    fea = np.array([[float(x) for x in l.split(",")] for l in fea_path.read_text().splitlines()[1:]])
    lines = [l for l in ORNL.read_text().splitlines() if l.strip() and not l.startswith("#")]
    meas = np.loadtxt(lines[1:], delimiter=",")
    have = [Ia for Ia in CURRENTS if (fea[:, 0] == Ia).any()]          # 파일에 있는 전류만 비교한다(일부 전류만 계산한 파일 허용)
    curves = {Ia: CubicSpline(fea[fea[:, 0] == Ia][:, 1], fea[fea[:, 0] == Ia][:, 2]) for Ia in have}
    return curves, meas


def compare(fea_path: Path) -> None:
    curves, meas = load(fea_path)
    g = np.linspace(0, 56.25, 5626)
    have = sorted(curves)
    peaks = np.array([curves[Ia](g).max() / FIG_3_10_PEAK[Ia] for Ia in have])
    print(f"== {fea_path.name}")
    print("전류별 최대 토크 FEA/측정: " + "  ".join(f"{Ia} A {r:.3f}" for Ia, r in zip(have, peaks))
          + f"   (평균 {peaks.mean():.3f}, 최소 {peaks.min():.3f}, 최대 {peaks.max():.3f})")
    ang = meas[:, 0]
    ref = max(have)          # 영점은 가장 큰 전류 곡선에서 정한다(보통 250 A)
    cs = [(np.sqrt(np.mean((curves[ref](c - ang) - meas[:, 1 + CURRENTS.index(ref)]) ** 2)), c) for c in np.arange(100, 200, 0.05)
          if (c - ang).min() >= 0 and (c - ang).max() <= 56.25]
    c = min(cs)[1]
    row = []
    for Ia in have:
        m, f = meas[:, 1 + CURRENTS.index(Ia)], curves[Ia](c - ang)
        row.append(f"{Ia} A r={np.corrcoef(f, m)[0, 1]:.3f} RMS={np.sqrt(np.mean((f - m) ** 2)) / m.max() * 100:4.1f}%")
    print(f"곡선 모양(영점 c = {c:.2f}, 거울): " + "  ".join(row))


if __name__ == "__main__":
    paths = [Path(a) for a in sys.argv[1:]] or [ROOT / "data" / "fea" / "prius2004_full_locked_torque.csv"]
    for p in paths:
        compare(p)
