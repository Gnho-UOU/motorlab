"""자석 감자 검토의 FEA 확인 (PLAN 5.6절 '최악 조건은 FEA로 확인').

자석 소재(등급, 온도)마다 Br(T)와 μr(T)를 engine/magnet.py(제조사 곡선)에서 받아 xfemm 전체 모터 모델의 자석에 넣고,
전류 상태마다 자석 안 여러 점에서 자화 방향 자속밀도 B_n을 읽어 감자 방향 자계를 구한다.
  선형 자석 모델: B = μ0·μr·H + Br·n̂   →   H_n = (B_n − Br)/(μ0·μr),  감자 자계 크기 H_demag = −H_n  [kA/m]
이 값을 그 온도의 무릎점 Hk(T)와 비교하면 감자 여유 1 − H_demag/Hk가 나온다(engine.magnet.MagnetGrade.demag_margin).

한계: 모델 자석은 선형이다(무릎점 이후 비선형 감자는 모사하지 않는다). 자석 안 H는 요소마다 상수라 모서리 첨두는 메시에 민감하다
(메시 크기를 바꿔 본 결과는 docs/validation_report.md). 회전자 위치 0°의 한 지점만 푼다(슬롯 위치에 따른 변동은 무시).
기본 형상은 data/benchmarks/prius2004_geometry_teardown.json(Prius). 이 Prius 형상에 다른 자석 소재를 넣은 가정 계산이다.

실행: FEMMCLI=<femmcli> python femm/demag_check.py [등급:온도 ...]  예) N45SH:20 N45SH:150 N38UH:150
출력: data/fea/prius2004_demag_check.csv 에 추가
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
from prius_full import cmath_phase  # noqa: E402
from prius_sector import rot, rotor_hole_points  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.magnet import MU0, load_grade  # noqa: E402

OUT = ROOT / "data" / "fea" / "prius2004_demag_check.csv"
STATES = {                         # 이름: (id [A], iq [A]) 상 전류 첨두 기준 dq
    "noload": (0.0, 0.0),
    "mtpa250": None,               # 맵에서 MTPA 250 A를 구해 채운다
    "d_axis_250": (-250.0, 0.0),   # 순수 감자 (전류 한계 250 A의 상한)
}
HEADER = ["grade", "T_C", "state", "id_A", "iq_A", "Br_T", "mur", "H_demag_max_kApm", "H_demag_mean_kApm", "Bn_mean_T", "Bn_min_T", "torque_Nm", "psi_d_Wb"]


def mtpa250() -> tuple[float, float]:
    from engine.model import FluxMapModel
    from engine.operating import mtpa_point
    m = FluxMapModel.from_csv(ROOT / "data" / "flux_maps" / "prius2004_fullmodel_teardown_25A.csv", p=4, Rs=0.0)
    d, q = mtpa_point(m, 250.0)
    return float(d), float(q)


def magnet_probes(g: dict, shrink: tuple[float, ...] = (0.5, 0.8, 0.92)) -> list[tuple[complex, complex]]:
    """극 0의 자석 두 장(아래·위) 안에서 점 (좌표, 자화 방향 단위벡터)을 만든다.

    자석 다각형(꼭짓점 Z8, Z8c, Z3 [Z4, Z5] Z6, 볼록)의 무게중심과, 각 꼭짓점·변 중점을 무게중심 쪽으로 shrink 배율만큼 줄인 점이다.
    모서리 바로 위(배율 1)는 자석 경계에 걸려 이웃 재질 값을 읽을 수 있어서 0.92까지만 간다.
    """
    ro = g["rotor"]
    pole_pitch = 2 * math.pi / ro["Zh"]
    off = 0.5 * pole_pitch
    lower = rotor_hole_points(g)
    upper = {k: v.conjugate() for k, v in lower.items() if k != "e"}
    mag_dir = math.degrees(cmath_phase(1j * lower["e"]))
    strip = bool(ro["hole_HoleM50"].get("air_strip_below_magnet"))
    keys = ("Z8", "Z8c", "Z3", "Z6") if strip else ("Z8", "Z8c", "Z3", "Z4", "Z5", "Z6")
    out = []
    for h, d in ((lower, mag_dir), (upper, -mag_dir)):
        poly = [h[k] for k in keys]
        c = sum(poly) / len(poly)
        anchors = poly + [0.5 * (poly[i] + poly[(i + 1) % len(poly)]) for i in range(len(poly))]
        ang = math.radians(d) + off
        n = complex(math.cos(ang), math.sin(ang))
        out.append((rot(c, off), n))
        out += [(rot(c + s * (a - c), off), n) for a in anchors for s in shrink]
    return out


def run_one(grade: str, T: float, state: str, id_iq: tuple[float, float], mesh: dict | None = None) -> dict:
    mg = load_grade(grade)
    br, mur = mg.br(T), mg.mu_r(T)
    g = pf.load_geometry()
    pts = magnet_probes(g)
    th = math.radians(pr.THETA0_ELEC_DEG)
    ia, ib, ic = pr.inverse_park(np.array([id_iq[0]]), np.array([id_iq[1]]), np.array([th]))[0]
    r = pf.solve_one((float(ia), float(ib), float(ic)), 0.0, mesh=mesh, probes=[p for p, _ in pts], br_T=br, mur=mur)
    Bn = np.array([b[0] * n.real + b[1] * n.imag for b, (_, n) in zip(r["B_xy_T"], pts)])
    Hd = (br - Bn) / (MU0 * mur) / 1e3                       # [kA/m], 감자 방향이 양수
    psi_d = float(pr.park(np.array([r["lambda_abc_Wb"]]), np.array([th]))[0][0])       # d축 쇄교자속 (1단계 어림 비교용)
    return {"grade": grade, "T_C": T, "state": state, "id_A": id_iq[0], "iq_A": id_iq[1], "Br_T": round(br, 5), "mur": round(mur, 5),
            "H_demag_max_kApm": round(float(Hd.max()), 2), "H_demag_mean_kApm": round(float(Hd.mean()), 2),
            "Bn_mean_T": round(float(Bn.mean()), 5), "Bn_min_T": round(float(Bn.min()), 5), "torque_Nm": round(r["torque_Nm"], 3), "psi_d_Wb": round(psi_d, 6)}


def main(specs: list[str]) -> None:
    STATES["mtpa250"] = mtpa250()
    jobs = [(s.split(":")[0], float(s.split(":")[1]), st, iq) for s in specs for st, iq in STATES.items()]
    with ThreadPoolExecutor(max_workers=int(os.environ.get("JOBS", "6"))) as ex:
        rows = list(ex.map(lambda j: run_one(*j), jobs))
    new = not OUT.exists()
    with open(OUT, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        if new:
            w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r, flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or ["N45SH:20", "N45SH:150"])
