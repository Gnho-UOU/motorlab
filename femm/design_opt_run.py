"""M6 설계 최적화의 FEA 평가기와 구동기 (연구실 예제 IPMSM, 자석 N45SH).

설계 변수 5개(mm, °): m_thick1(V자 자석 두께), m_length_1(V자 자석 길이), m_theta_1(V자 자석 각), m_thick2(평평한 자석 두께), m_length_2(평평한 자석 반길이).
목적: 평균 토크(4300 rpm, 상전류 첨두 330 A에서 전류각 β를 최적으로 잡았을 때) 최대화, 자석 단면적 [mm²/극] 최소화.
  magnet_area = 2·m_length_1·m_thick1 + 2·m_length_2·m_thick2  (V자 자석 2장 + 평평한 자석 1장(길이 2·m_length_2)).
제약: 단자 전압 기본파 첨두 ≤ 433 V (육각파 한계 (2/π)·680 V, 강의 자료의 DC 링크 680 V), 150 °C(N45SH 최고 사용 온도)에서 감자 여유 ≥ 0.05 (기준 설계가 0.078이라 0.1은 기준 설계도 못 지킨다. 메시가 모서리 첨두를 최대 2.5% 낮게 보는 점을 감안한 여유)
  (자석 안 점 중 최악 점의 H/Hk, engine/magnet.py), 형상 타당성(geometry_ok).
평가 (설계 하나): 전류각 β ∈ {33°, 41°, 49°}마다 회전자 4위치(0, 1.875, 3.75, 5.625°)를 풀어 Henrotte 토크 평균과 dq 쇄교자속 평균을 얻고(12점, N45SH 50 °C 공칭 Br),
  토크를 β에 대한 포물선으로 맞춰 최대 토크 T*와 그 β*를, 전압도 같은 방식으로 β*에서 구한다. 감자는 N45SH 150 °C의 Br·μr로 β = 49°(가장 센 감자 쪽)의 한 점을 풀어
  자석 안 점의 H를 읽는다(1점). 설계마다 13점. 메시는 중간(요소 약 11만 개). 토크 평균은 슬롯 리플(p-p 약 8%)의 4위치 평균이라 약 ±1% 불확실성이 있다.
실행: FEMMCLI=<femmcli> python femm/design_opt_run.py init 24 | iterate 4 8 [시작번호] | report
  init N: 형상이 타당한 라틴 하이퍼큐브 설계 N개와 기준 설계를 평가한다. iterate R K: R번 반복, 매번 GP 대리모델(T*, V, 감자 여유) + NSGA-II로 후보 K개를 골라 FEA로 평가한다.
결과 표: data/fea/design_opt_evals.csv (설계마다 한 줄, 이어 쓰기).
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
import prius_run as pr  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.magnet import MU0, load_grade  # noqa: E402
from engine.optimize import DesignSpace, GPSurrogate, latin_hypercube, pareto_mask, run_nsga2, select_diverse  # noqa: E402

OUT = ROOT / "data" / "fea" / "design_opt_evals.csv"
VARS = ["m_thick1", "m_length_1", "m_theta_1", "m_thick2", "m_length_2"]
SPACE = DesignSpace(VARS, [2.0, 18.0, 44.0, 2.4, 10.0], [3.4, 26.0, 56.0, 4.2, 16.0])
BASE_X = [em.P[v] for v in VARS]
BETAS = (33.0, 41.0, 49.0)
POSITIONS = (0.0, 1.875, 3.75, 5.625)
I_PK, RS, RPM = 330.0, 0.0330, 4300.0
WE = 2 * math.pi * RPM / 60 * 4
V_LIMIT, MARGIN_MIN = (2 / math.pi) * 680.0, 0.05
MESH = {"stator": 2.0e-3, "rotor": 1.4e-3, "magnet": 1.4e-3, "slot": 3.0e-3, "gap": 0.3e-3}
G = load_grade("N45SH")
BR50, MUR50 = G.br(50.0), G.mu_r(50.0)
BR150, MUR150, HK150 = G.br(150.0), G.mu_r(150.0), G.hk(150.0)
HEADER = ["id", "stage", *VARS, "T_Nm", "beta_deg", "V_peak_V", "T33", "T41", "T49", "V33", "V41", "V49",
          "H_demag_max_kApm", "demag_margin_150C", "magnet_area_mm2"]
JOBS = int(os.environ.get("JOBS", "16"))


def design_p(x) -> dict:
    return {**em.P, **{k: float(v) for k, v in zip(VARS, x)}}


def magnet_area(x) -> float:
    p = design_p(x)
    return 2 * p["m_length_1"] * p["m_thick1"] + 2 * p["m_length_2"] * p["m_thick2"]


def quadratic_peak(betas, values):
    """세 점 (β, 값)을 지나는 포물선의 꼭짓점 (β*, 값*). 꼭짓점이 구간 밖이면 가장 가까운 끝점으로 자른다."""
    a, b, c = np.polyfit(betas, values, 2)
    bs = float(np.clip(-b / (2 * a), min(betas), max(betas))) if a < 0 else float(betas[int(np.argmax(values))])
    return bs, float(np.polyval([a, b, c], bs))


def theta0_rad() -> float:
    import example_motor_run as run
    return run.theta0_rad()


def solve_loaded(p, beta_deg, rotor_deg, br, mur, th0, probes=None):
    b = math.radians(beta_deg)
    id_, iq = -I_PK * math.sin(b), I_PK * math.cos(b)
    th = th0 + 4 * math.radians(rotor_deg)
    ia, ib, ic = pr.inverse_park(np.array([id_]), np.array([iq]), np.array([th]))[0]
    r = em.solve_one((float(ia), float(ib), float(ic)), rotor_deg, br, mur, "jfe", mesh=MESH, probes=probes, p=p)
    d, q = pr.park(np.array([r["lambda_abc_Wb"]]), np.array([th]))
    return float(d[0]), float(q[0]), r["torque_Nm"], r.get("B_xy_T"), (id_, iq)


def magnet_probes(p, n=(6, 3)):
    """극 0의 자석 세 장의 점 (좌표 [m], 자화 방향 단위벡터): V자 자석 위·아래 반쪽과 평평한 자석. 모서리에서 8% 안쪽 격자."""
    z = {k: v * em.MM for k, v in em.rotor_points(p).items()}
    out = []
    ang1 = math.radians(p["m_theta_1"] - 90.0)
    for sign in (+1, -1):
        cj = (lambda q: q) if sign > 0 else (lambda q: q.conjugate())
        a, b, c, d = (cj(z[f"Z{k}"]) for k in (2, 3, 6, 7))              # 자석 1 직사각형 꼭짓점 순서 2-3-6-7
        nvec = complex(math.cos(sign * ang1), math.sin(sign * ang1))
        for i in range(n[0]):
            for j in range(n[1]):
                u, v = 0.08 + 0.84 * i / (n[0] - 1), 0.08 + 0.84 * j / (n[1] - 1)
                out.append(((1 - u) * ((1 - v) * a + v * d) + u * ((1 - v) * b + v * c), nvec))
    z12, z11, z13 = z["Z12"], z["Z11"], z["Z13"]
    for i in range(3):
        for j in range(12):
            u, v = 0.08 + 0.84 * i / 2, -0.92 + 1.84 * j / 11
            out.append((complex(z12.real + u * (z11.real - z12.real), v * z13.imag), complex(1.0, 0.0)))
    return out


def evaluate_batch(designs: list, ids: list, stage: str) -> list:
    """설계 목록을 한꺼번에 풀어(작업을 모두 한 풀에 넣어 병렬) 표의 행으로 돌려준다."""
    th0 = theta0_rad()
    jobs = []
    for di, x in enumerate(designs):
        for beta in BETAS:
            for r in POSITIONS:
                jobs.append((di, "load", beta, r))
        jobs.append((di, "demag", BETAS[-1], 0.0))

    def run_job(j):
        di, kind, beta, r = j
        p = design_p(designs[di])
        if kind == "load":
            d, q, t, _, _ = solve_loaded(p, beta, r, BR50, MUR50, th0)
            return d, q, t, None
        probes = magnet_probes(p)
        d, q, t, B, _ = solve_loaded(p, beta, r, BR150, MUR150, th0, probes=[pt for pt, _ in probes])
        Bn = np.array([b[0] * n.real + b[1] * n.imag for b, (_, n) in zip(B, probes)])
        return d, q, t, float(np.max((BR150 - Bn) / (MU0 * MUR150) / 1e3))
    with ThreadPoolExecutor(max_workers=JOBS) as ex:
        res = list(ex.map(run_job, jobs))
    rows = []
    for di, x in enumerate(designs):
        mine = [(j, r) for j, r in zip(jobs, res) if j[0] == di]
        T, V = [], []
        for beta in BETAS:
            rs = [r for j, r in mine if j[1] == "load" and j[2] == beta]
            psi_d, psi_q = np.mean([r[0] for r in rs]), np.mean([r[1] for r in rs])
            b = math.radians(beta)
            id_, iq = -I_PK * math.sin(b), I_PK * math.cos(b)
            V.append(math.hypot(RS * id_ - WE * psi_q, RS * iq + WE * psi_d))
            T.append(float(np.mean([r[2] for r in rs])))
        bstar, tstar = quadratic_peak(BETAS, T)
        vstar = float(np.polyval(np.polyfit(BETAS, V, 2), bstar))
        hmax = next(r[3] for j, r in mine if j[1] == "demag")
        rows.append({"id": ids[di], "stage": stage, **{k: round(float(v), 4) for k, v in zip(VARS, x)}, "T_Nm": round(tstar, 3),
                     "beta_deg": round(bstar, 3), "V_peak_V": round(vstar, 2), "T33": round(T[0], 3), "T41": round(T[1], 3), "T49": round(T[2], 3),
                     "V33": round(V[0], 2), "V41": round(V[1], 2), "V49": round(V[2], 2), "H_demag_max_kApm": round(hmax, 2),
                     "demag_margin_150C": round(1 - hmax / HK150, 4), "magnet_area_mm2": round(magnet_area(x), 3)})
    return rows


def read_table() -> list:
    if not OUT.exists():
        return []
    rows = list(csv.DictReader(open(OUT)))
    for r in rows:
        for k in r:
            if k not in ("id", "stage"):
                r[k] = float(r[k])
    return rows


def append_rows(rows: list) -> None:
    new = not OUT.exists()
    with open(OUT, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        if new:
            w.writeheader()
        w.writerows(rows)


def valid_lhs(n: int, seed: int) -> np.ndarray:
    """형상이 타당한 라틴 하이퍼큐브 설계 n개 (타당하지 않은 점은 건너뛰고 표본을 늘려 채운다)."""
    pts = []
    k = 3
    while len(pts) < n:
        pts = []
        for x in SPACE.scale(latin_hypercube(n * k, SPACE.dim, seed=seed + k)):
            if em.geometry_ok(design_p(x))[0]:
                pts.append(x)
            if len(pts) == n:
                break
        k += 1
    return np.array(pts)


def surrogate_model():
    """표에서 T*, V, 감자 여유의 GP를 만들고 NSGA-II가 부를 model(X) -> (F, G)를 돌려준다. 제약은 예측 평균에 표준편차를 한 번 더 불리하게 더한다."""
    rows = read_table()
    X = SPACE.unscale(np.array([[r[v] for v in VARS] for r in rows]))
    gps = {k: GPSurrogate().fit(X, np.array([r[col] for r in rows])) for k, col in (("T", "T_Nm"), ("V", "V_peak_V"), ("M", "demag_margin_150C"))}

    def model(Xr):
        u = SPACE.unscale(Xr)
        t, _ = gps["T"].predict(u)
        v, sv = gps["V"].predict(u)
        m, sm = gps["M"].predict(u)
        area = np.array([magnet_area(x) for x in Xr])
        ok = np.array([0.0 if em.geometry_ok(design_p(x))[0] else 1.0 for x in Xr])      # 형상 타당성 위반은 큰 양수 제약
        F = np.stack([-t, area], axis=1)
        Gc = np.stack([v + sv - V_LIMIT, MARGIN_MIN - (m - sm), ok], axis=1)
        return F, Gc
    return model, gps, rows


def main(argv) -> None:
    mode = argv[0]
    if mode == "init":
        n = int(argv[1])
        have = {r["id"] for r in read_table()}
        designs, ids = [], []
        if "baseline" not in have:
            designs.append(BASE_X)
            ids.append("baseline")
        for i, x in enumerate(valid_lhs(n, seed=11)):
            if f"i{i:02d}" not in have:
                designs.append(x)
                ids.append(f"i{i:02d}")
        for k in range(0, len(designs), 4):                                  # 4개씩 묶어 저장(중간에 끊겨도 이어 쓴다)
            append_rows(evaluate_batch(designs[k:k + 4], ids[k:k + 4], "init"))
            print("saved", ids[k:k + 4], flush=True)
    elif mode == "iterate":
        rounds, k = int(argv[1]), int(argv[2])
        start = int(argv[3]) if len(argv) > 3 else 0                       # 이어서 돌릴 때 반복 번호 시작값 (표의 stage 이름이 겹치지 않게)
        for rd in range(start, start + rounds):
            model, gps, rows = surrogate_model()
            X, F, Gc = run_nsga2(model, SPACE, pop=120, gens=150, seed=100 + rd)
            if len(X) == 0:
                print("대리모델이 제약을 만족하는 해를 못 찾았다. 제약을 풀거나 표본을 더 늘려야 한다.")
                return
            have_x = SPACE.unscale(np.array([[r[v] for v in VARS] for r in rows]))
            order = select_diverse(F, min(len(F), k * 3))
            cand = []
            for i in order:                                                  # 이미 평가한 설계와 너무 가까우면(정규화 거리 0.05 미만) 건너뛴다
                if np.min(np.linalg.norm(have_x - SPACE.unscale(X[i]), axis=1)) > 0.05:
                    cand.append(X[i])
                if len(cand) == k:
                    break
            n0 = len(rows)
            ids = [f"r{rd}_{i}_{n0}" for i in range(len(cand))]
            print(f"round {rd}: Pareto 후보 {len(X)}개, 평가 {len(cand)}개, GP LOO RMSE T {gps['T'].loo_rmse():.2f}, "
                  f"V {gps['V'].loo_rmse():.2f}, margin {gps['M'].loo_rmse():.3f}", flush=True)
            for i in range(0, len(cand), 4):
                append_rows(evaluate_batch(cand[i:i + 4], ids[i:i + 4], f"iter{rd}"))
                print("saved", ids[i:i + 4], flush=True)
    elif mode == "report":
        print(len(read_table()), "designs")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
