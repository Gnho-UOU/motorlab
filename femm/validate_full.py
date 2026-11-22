"""전체 모터 모델(공극 메시, prius_full.py)로 하는 두 가지 작업.

  crosscheck : AGE 섹터로 만든 dq 자속 맵(회전자 δ = 0)이 전체 모델과 같은 값을 주는지 12점을 비교한다.
  fluxmap    : 전체 모델로 dq 자속 맵을 다시 만든다(25 A 간격 121점). 회전자 0°와 3.75°(슬롯 피치 7.5°의 절반) 두 위치를 평균해
               슬롯 맥동의 기본 성분을 상쇄한다. 약 40~50분, 이어 쓰기.
  locked     : ORNL 잠금 회전자 시험(TM-423 Table 3.2, Fig. 3.10)을 모사한다. 상전류 (Ia, -Ia/2, -Ia/2) 직류를 고정하고
               회전자 각도를 한 극 피치(45°)에 걸쳐 돌려 토크-각도 곡선과 전류별 최대 토크를 구한다.

사용법:  FEMMCLI=/경로/femmcli python femm/validate_full.py crosscheck|fluxmap|locked [출력.csv]
결과는 이어 쓰기라 끊겨도 같은 출력으로 다시 실행하면 이어서 한다. 점마다 약 76초, 8개 병렬.
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import prius_full as pf  # noqa: E402
import prius_sector as ps  # noqa: E402
import prius_run as pr   # noqa: E402  (park, inverse_park)

ROOT = Path(__file__).resolve().parents[1]
import os  # noqa: E402
BR_OVERRIDE = float(os.environ["PRIUS_BR_T"]) if os.environ.get("PRIUS_BR_T") else None   # 자석 Br20 덮어쓰기[T]
AGE_MAP = ROOT / "data" / "flux_maps" / "prius2004_xfemm_delta0_25A.csv"
OUT_DIR = ROOT / "data" / "fea"
CROSS_POINTS = [(0, 50), (0, 150), (0, 250), (-50, 100), (-100, 150), (-100, 250), (-150, 100), (-150, 200),
                (-200, 150), (-250, 100), (-250, 250), (-100, 0)]
LOCKED_CURRENTS = [int(x) for x in os.environ.get("PRIUS_LOCKED_CURRENTS", "50,75,100,125,150,200,250").split(",")]
LOCKED_ANGLES_DEG = [k * 3.75 for k in range(16)]      # 0 ~ 56.25° (ORNL 측정 창 44°를 거울 방향까지 덮는다)


def read_age_map() -> dict[tuple[float, float], tuple[float, float, float]]:
    out = {}
    for line in AGE_MAP.read_text().splitlines():
        if line and not line.startswith("#") and not line.startswith("id_A"):
            a = [float(x) for x in line.split(",")]
            out[(a[0], a[1])] = (a[2], a[3], a[4])
    return out


def crosscheck(out: Path) -> None:
    age = read_age_map()
    th = math.radians(pr.THETA0_ELEC_DEG)
    idv = np.array([p[0] for p in CROSS_POINTS], float)
    iqv = np.array([p[1] for p in CROSS_POINTS], float)
    abc = pr.inverse_park(idv, iqv, np.full(len(idv), th))
    t0 = time.time()
    r = pf.solve_points([(a, b, c, 0.0) for a, b, c in abc], jobs=8)
    psid, psiq = pr.park(r["lambda_abc_Wb"], np.full(len(idv), th))
    lines = ["id_A,iq_A,full_psi_d,full_psi_q,age_psi_d,age_psi_q,full_torque_Nm,flux_torque_Nm,age_torque_Nm"]
    for (i, q), d, qq, T in zip(CROSS_POINTS, psid, psiq, r["torque_Nm"]):
        ad, aq, at = age[(float(i), float(q))]
        lines.append(f"{i},{q},{d:.6f},{qq:.6f},{ad:.6f},{aq:.6f},{T:.3f},{1.5 * 4 * (d * q - qq * i):.3f},{at:.3f}")
    out.write_text("\n".join(lines) + "\n")
    print(f"교차 검증 {len(CROSS_POINTS)}점, {time.time() - t0:.0f}s -> {out}")


MAP_HEADER = """# 출처: FEA 계산 결과. 형상·재료는 data/benchmarks/{geom}  ({what})
# 솔버: xfemm femmcli (커밋 132515c, macOS 이식성 패치 3종, femm/build_xfemm_macos.sh). 2D 정자장, 비선형 BH(철심 M400-50A, 출처 미확인), 자석 {magnet}.
# 방법: 전체 모터(360°, 48슬롯, 8극), 공극까지 메시(AGE 안 씀), 쇄교자속은 상 회로에서 직접 읽음. 회전자 0°와 3.75°(슬롯 피치 7.5°의 절반) 두 위치의 평균(슬롯 맥동 기본 성분 상쇄).
# dq: 크기 불변 Park 변환, d축 = 자석 N극 축, A상 축 대비 전기각 150° + 4·(회전자 각도). 전류는 상 첨두값.
# 한계: 엔드턴 누설 인덕턴스 없음(2D). 자석 온도 20 °C 가정. torque_Nm은 두 위치 Henrotte 토크의 평균(비교용, 위치 평균이라 자속 기반 토크와 가깝다).
# 단위: id_A, iq_A [A], psi_d_Wb, psi_q_Wb [Wb], torque_Nm [N·m]
"""


def map_header() -> str:
    """CSV 머리 주석. 형상 파일과 자석 값은 실제로 쓴 값에서 읽는다(손으로 적지 않는다)."""
    g = pf.load_geometry()
    mag = g["magnet"]
    br = BR_OVERRIDE if BR_OVERRIDE is not None else mag["Br20_T"]
    note = f"Br20 = {br} T, mur = {mag['mur']}"
    if BR_OVERRIDE is not None:
        note += f" (Br은 보정값: ORNL 무부하 역기전력 상수 환산 |ψ| = 0.174 Wb에 맞춤. 형상 파일의 {mag['Br20_T']} T가 아니다)"
    return MAP_HEADER.format(geom=ps.GEOMETRY_JSON.name, what=g["__source__"]["what"], magnet=note)


MAP_POSITIONS_DEG = (0.0, 3.75)


def fluxmap(out: Path) -> None:
    step = 25.0
    ids, iqs = np.arange(-250.0, 1e-9, step), np.arange(0.0, 250.0 + 1e-9, step)
    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            if line and not line.startswith("#") and not line.startswith("id_A"):
                a = line.split(",")
                done.add((round(float(a[0]), 6), round(float(a[1]), 6)))
    else:
        hdr = map_header()
        out.write_text(hdr + "id_A,iq_A,psi_d_Wb,psi_q_Wb,torque_Nm\n")
    t0 = time.time()
    for i in ids:
        todo = [q for q in iqs if (round(float(i), 6), round(float(q), 6)) not in done]
        if not todo:
            continue
        pts, ths = [], []
        for q in todo:
            for d in MAP_POSITIONS_DEG:
                th = math.radians(pr.THETA0_ELEC_DEG + 4 * d)
                a = pr.inverse_park(np.array([i]), np.array([q]), np.array([th]))[0]
                pts.append((*a, d)); ths.append(th)
        r = pf.solve_points(pts, jobs=8, br_T=BR_OVERRIDE)
        psid, psiq = pr.park(r["lambda_abc_Wb"], np.array(ths))
        n = len(MAP_POSITIONS_DEG)
        with out.open("a") as f:
            for k, q in enumerate(todo):
                sl = slice(k * n, (k + 1) * n)
                f.write(f"{i:g},{q:g},{psid[sl].mean():.6f},{psiq[sl].mean():.6f},{r['torque_Nm'][sl].mean():.3f}\n")
        print(f"id = {i:6.1f} A 완료 ({len(todo)}점 x {n}위치), 경과 {time.time() - t0:.0f}s", flush=True)
    print("끝:", out)


def locked(out: Path) -> None:
    done = set()
    if out.exists():
        for line in out.read_text().splitlines()[1:]:
            a = line.split(",")
            done.add((float(a[0]), round(float(a[1]), 4)))
    else:
        out.write_text("Ia_A,theta_deg,torque_Nm,lambda_A_Wb,lambda_B_Wb,lambda_C_Wb\n")
    t0 = time.time()
    for Ia in LOCKED_CURRENTS:
        todo = [a for a in LOCKED_ANGLES_DEG if (float(Ia), round(a, 4)) not in done]
        if not todo:
            continue
        r = pf.solve_points([(Ia, -Ia / 2, -Ia / 2, a) for a in todo], jobs=8, br_T=BR_OVERRIDE)
        with out.open("a") as f:
            for a, T, l in zip(todo, r["torque_Nm"], r["lambda_abc_Wb"]):
                f.write(f"{Ia},{a:g},{T:.3f},{l[0]:.6f},{l[1]:.6f},{l[2]:.6f}\n")
        print(f"Ia = {Ia} A 완료 ({len(todo)}점), 경과 {time.time() - t0:.0f}s", flush=True)
    print("끝:", out)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    OUT_DIR.mkdir(exist_ok=True)
    if mode == "crosscheck":
        crosscheck(Path(sys.argv[2] if len(sys.argv) > 2 else OUT_DIR / "prius2004_crosscheck_age_vs_full.csv"))
    elif mode == "fluxmap":
        fluxmap(Path(sys.argv[2] if len(sys.argv) > 2 else ROOT / "data" / "flux_maps" / "prius2004_fullmodel_25A.csv"))
    elif mode == "locked":
        locked(Path(sys.argv[2] if len(sys.argv) > 2 else OUT_DIR / "prius2004_full_locked_torque.csv"))
    else:
        sys.exit(__doc__)
