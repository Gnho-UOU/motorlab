"""Prius 모델 입력의 불확실성이 FEA 결과(쇄교자속, 토크)를 얼마나 바꾸는지: G1 미달(고속 필요 전류, 잠금 토크 불일치)의 원인 탐색.

Prius FEA의 입력 중 근거가 약한 것: 강판 B-H 곡선(pyleecan M400-50A, ORNL은 강판 두께 0.33 mm만 적음), 적층률(1.0으로 둠, 실제 0.95~0.97이 보통),
자석 Br(보정값 1.06 T). 이 스크립트는 자석을 기준(Br 1.06 T, μr 1.129)으로 두고 강판 곡선과 적층률만 바꿔 같은 점들을 풀어 비교한다.
변형: base(M400, 적층 1.0), jfe(JFE 35JN230 대표값 곡선 + M400 모양, 더 단단한 강판의 대용), lam97, lam95, jfe_lam95(둘 다).
점: 무부하 (0, 0), 최대 토크 근처 (−100, 150), (−175, 175), 순수 d축 (−250, 0). 점마다 회전자 0°와 3.75° 평균(기준 맵과 같은 방법).
실행: FEMMCLI=<femmcli> python femm/prius_input_sensitivity.py   → data/fea/prius2004_input_sensitivity.csv
"""
import csv
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import example_motor as em  # noqa: E402
import prius_full as pf  # noqa: E402
import prius_run as pr  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "fea" / "prius2004_input_sensitivity.csv"
BR, MUR = 1.06, 1.129
POINTS = [(0, 0), (-100, 150), (-175, 175), (-250, 0)]
POSITIONS = (0.0, 3.75)
JOBS = int(os.environ.get("JOBS", "16"))
VARIANTS = {"base": (None, None), "jfe": (em.steel_bh("jfe"), None), "lam97": (None, 0.97), "lam95": (None, 0.95), "jfe_lam95": (em.steel_bh("jfe"), 0.95)}


def solve(variant, pt, pos):
    bh, lam = VARIANTS[variant]
    th = math.radians(pr.THETA0_ELEC_DEG + 4 * pos)
    ia, ib, ic = pr.inverse_park(np.array([pt[0]]), np.array([pt[1]]), np.array([th]))[0]
    r = pf.solve_one((float(ia), float(ib), float(ic)), pos, br_T=BR, mur=MUR, steel_bh=bh, lam_fill=lam)
    d, q = pr.park(np.array([r["lambda_abc_Wb"]]), np.array([th]))
    return float(d[0]), float(q[0])


def main() -> None:
    jobs = [(v, pt, pos) for v in VARIANTS for pt in POINTS for pos in POSITIONS]
    with ThreadPoolExecutor(max_workers=JOBS) as ex:
        res = list(ex.map(lambda j: solve(*j), jobs))
    acc = {}
    for (v, pt, pos), (d, q) in zip(jobs, res):
        acc.setdefault((v, pt), []).append((d, q))
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["variant", "id_A", "iq_A", "psi_d_Wb", "psi_q_Wb", "torque_flux_Nm"])
        for (v, pt), vals in acc.items():
            d, q = np.mean(vals, axis=0)
            w.writerow([v, pt[0], pt[1], f"{d:.6f}", f"{q:.6f}", f"{1.5 * 4 * (d * pt[1] - q * pt[0]):.3f}"])
    print("done")


if __name__ == "__main__":
    main()
