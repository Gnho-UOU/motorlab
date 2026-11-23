"""자석을 바꿀 때 자속 맵을 어떻게 조정할지 FEA로 확인한다 (M5: 소재별 토크·효율·전비).

기준 맵(data/flux_maps/prius2004_fullmodel_teardown_25A.csv)은 자석 Br = 1.06 T, μr = 1.129로 풀렸다. 다른 자석(Br', μr')을 넣은 맵을 다시 풀지 않고
  ψd'(id, iq) = ψd(id, iq) + (k − 1)·ψm,   ψq'(id, iq) = ψq(id, iq),   k = Br'/Br,   ψm = ψd(0, 0)
로 조정하려 한다(자석 자속은 Br에 비례하고 전기자 자속은 그대로라는 겹침 가정). 가정이 맞는지 서로 다른 자석 두 가지로 FEA를 풀어 비교한다.
기준 맵과 같은 방법: 전체 모터, 회전자 0°와 3.75° 두 위치의 평균, dq는 150° + 4·θr.
변형: N45SH 20 °C (Br 1.350, μr 1.037) 와 N38UH 180 °C (Br 1.018, μr 1.043), 곡선은 engine/magnet.py. 기준 재현(Br 1.06, μr 1.129)도 한 변형으로 넣어 장치를 점검한다.
실행: FEMMCLI=<femmcli> python femm/magnet_scaling_check.py   → data/fea/prius2004_magnet_scaling_check.csv
"""
import csv
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import prius_full as pf  # noqa: E402
import prius_run as pr  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.magnet import load_grade  # noqa: E402
from engine.model import FluxMapModel  # noqa: E402

OUT = ROOT / "data" / "fea" / "prius2004_magnet_scaling_check.csv"
BASE_BR, BASE_MUR = 1.06, 1.129
POINTS = [(0, 0), (-100, 100), (-175, 175), (-250, 0), (0, 250), (-150, 100), (-100, 225)]     # 기준 맵 격자점
POSITIONS_MECH_DEG = (0.0, 3.75)


def variants():
    out = {"base_repro": (BASE_BR, BASE_MUR)}
    for g, T in (("N45SH", 20.0), ("N38UH", 180.0)):
        m = load_grade(g)
        out[f"{g}_{int(T)}C"] = (m.br(T), m.mu_r(T))
    return out


def solve_dq(br: float, mur: float, id_: float, iq: float, rotor_deg: float):
    th = math.radians(pr.THETA0_ELEC_DEG) + 4 * math.radians(rotor_deg)
    ia, ib, ic = pr.inverse_park(np.array([id_]), np.array([iq]), np.array([th]))[0]
    r = pf.solve_one((float(ia), float(ib), float(ic)), rotor_deg, br_T=br, mur=mur)
    d, q = pr.park(np.array([r["lambda_abc_Wb"]]), np.array([th]))
    return float(d[0]), float(q[0])


def main() -> None:
    base = FluxMapModel.from_csv(ROOT / "data" / "flux_maps" / "prius2004_fullmodel_teardown_25A.csv", p=4, Rs=0.0)
    psi_m = float(base.flux(0.0, 0.0)[0])
    jobs = [(name, br, mur, p, pos) for name, (br, mur) in variants().items() for p in POINTS for pos in POSITIONS_MECH_DEG
            if name != "base_repro" or p in ((-100, 100), (-250, 0))]
    with ThreadPoolExecutor(max_workers=int(os.environ.get("JOBS", "6"))) as ex:
        res = list(ex.map(lambda j: solve_dq(j[1], j[2], j[3][0], j[3][1], j[4]), jobs))
    acc: dict = {}
    for (name, br, mur, p, pos), (d, q) in zip(jobs, res):
        acc.setdefault((name, br, mur, p), []).append((d, q))
    rows = []
    for (name, br, mur, p), v in acc.items():
        d, q = np.mean(v, axis=0)
        bd, bq = (float(x) for x in base.flux(float(p[0]), float(p[1])))
        rows.append({"variant": name, "Br_T": round(br, 5), "mur": round(mur, 5), "id_A": p[0], "iq_A": p[1],
                     "psi_d_fea": round(float(d), 6), "psi_q_fea": round(float(q), 6),
                     "psi_d_scaled": round(bd + (br / BASE_BR - 1.0) * psi_m, 6), "psi_q_scaled": round(bq, 6)})
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
