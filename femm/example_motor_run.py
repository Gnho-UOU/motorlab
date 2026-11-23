"""연구실 예제 IPMSM(femm/example_motor.py)을 xfemm으로 풀어 JMAG 결과(연구실 강의 자료의 해석 결과 화면)와 비교한다.

비교 대상(강의 자료 슬라이드의 JMAG 결과, 4300 rpm, 상전류 첨두 330 A):
  무부하: 상 역기전력 첨두 277.96 V·실효 207.76 V, THD 15.10 %, 선간 첨두 521.39 V·실효 357.47 V, THD 9.63 %, 코깅 토크 1.29 N·m (p-p)
  부하  : 평균 토크 350.64 N·m, 토크 리플 8.22 %, 단자 전압 첨두 385.75 V, 상전류 실효 233.35 A, 동손 5397 W, 철손 751 W, 효율 96.25 %
  (역기전력의 두 숫자는 앞 = 파형 첨두, 괄호 = 실효: 슬라이드 그림의 파형 121점으로 확정했다)
  JMAG 설정: 자석 N45SH(Arnold, reversible) 온도 50 °C 고정, 강판 35JN230, 적층률 97 %, 적층 153 mm, 상저항 0.033 Ω @50 °C.

방법: 전체 모터 FEA. 무부하는 회전자 위치 24점(3.75° 간격, 한 전기 주기 = 기계각 90°)의 쇄교자속으로 기본파와 고조파를, 코깅은 한 슬롯 피치(7.5°)를 12점으로 본다.
d축 기준 각 θ0은 무부하 A상 쇄교자속의 기본파 위상으로 정한다(θe = θ0 + 4·θr, 맞춤이 아니라 정의). 부하는 전류각 β(id = −I sinβ, iq = I cosβ)를 훑어 토크·전압을 본다.
JMAG의 전류 위상 정의(41°)는 알 수 없어서 β를 JMAG 토크에 맞추지 않고 표로 둔다. 토크는 자속으로(1.5·p·(ψd·iq − ψq·id), 두 회전자 위치 평균)와 FEA(Henrotte) 두 가지로 구한다.
변형 세 가지: 'nominal' (Br = N45SH 50 °C 공칭, 강판 JFE 혼합 곡선), 'm400' (같은 자석, Prius 강판 곡선), 'brmin' (Br을 최소/공칭 1320/1350으로 낮춤).
실행: FEMMCLI=<femmcli> python femm/example_motor_run.py noload|loaded
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
from engine.magnet import load_grade  # noqa: E402

OUT = ROOT / "data" / "fea"
P_PAIRS, RPM, RS, I_PK = 4, 4300.0, 0.0330, 330.0
JOBS = int(os.environ.get("JOBS", "16"))
G = load_grade("N45SH")
VARIANTS = {"nominal": (G.br(50.0), G.mu_r(50.0), "jfe"), "m400": (G.br(50.0), G.mu_r(50.0), "m400"),
            "brmin": (G.br(50.0) * 1320.0 / 1350.0, G.mu_r(50.0), "jfe")}
NOLOAD_POS = np.concatenate([np.arange(0.0, 90.0, 3.75), np.arange(0.0, 7.5, 0.625)])
BETAS = (30.0, 35.0, 40.0, 45.0, 50.0, 55.0)
LOAD_POS = (0.0, 3.75)


def noload() -> None:
    br, mur, steel = VARIANTS["nominal"]
    pos = sorted(set(round(float(x), 4) for x in NOLOAD_POS))
    with ThreadPoolExecutor(max_workers=JOBS) as ex:
        res = list(ex.map(lambda r: em.solve_one((0.0, 0.0, 0.0), r, br, mur, steel), pos))
    with open(OUT / "example_motor_noload.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rotor_deg", "lambda_A_Wb", "lambda_B_Wb", "lambda_C_Wb", "torque_Nm"])
        for r, x in zip(pos, res):
            w.writerow([r, *(f"{v:.6f}" for v in x["lambda_abc_Wb"]), f"{x['torque_Nm']:.4f}"])
    print("noload done", len(pos))


def theta0_rad() -> float:
    """무부하 A상 쇄교자속의 기본파 위상 (λA ≈ Λ cos(4·θr + φ))."""
    rows = [r for r in csv.DictReader(open(OUT / "example_motor_noload.csv"))]
    pos = np.array([float(r["rotor_deg"]) for r in rows])
    main = np.isclose(pos % 3.75, 0.0) | np.isclose(pos % 3.75, 3.75)
    sel = [i for i, r in enumerate(pos) if r < 90.0 and abs(r / 3.75 - round(r / 3.75)) < 1e-6]
    th = np.radians(4 * pos[sel])
    lam = np.array([[float(rows[i][k]) for k in ("lambda_A_Wb", "lambda_B_Wb", "lambda_C_Wb")] for i in sel])
    phasor = (2.0 / len(sel)) * np.sum(lam * np.exp(-1j * th)[:, None], axis=0)
    phi = np.angle(phasor, deg=True)
    d_b, d_c = (phi[1] - phi[0] + 180) % 360 - 180, (phi[2] - phi[0] + 180) % 360 - 180
    if not (abs(d_b + 120) < 10 and abs(d_c - 120) < 10):
        raise RuntimeError(f"상 순서가 양의 순서(B −120°, C +120°)가 아니다: B {d_b:.1f}°, C {d_c:.1f}° (슬롯 패턴의 B·C를 바꿔야 한다)")
    return float(np.angle(phasor[0]))


def solve_dq(variant: str, rotor_deg: float, id_: float, iq: float, th0: float):
    br, mur, steel = VARIANTS[variant]
    th = th0 + 4 * math.radians(rotor_deg)
    ia, ib, ic = pr.inverse_park(np.array([id_]), np.array([iq]), np.array([th]))[0]
    r = em.solve_one((float(ia), float(ib), float(ic)), rotor_deg, br, mur, steel)
    d, q = pr.park(np.array([r["lambda_abc_Wb"]]), np.array([th]))
    return float(d[0]), float(q[0]), r["torque_Nm"]


def loaded() -> None:
    th0 = theta0_rad()
    jobs = [(v, b, pos) for v in VARIANTS for b in (BETAS if v == "nominal" else (40.0, 45.0)) for pos in LOAD_POS]
    jobs += [("nominal", 0.0, pos) for pos in LOAD_POS]                                         # 순수 q축
    with ThreadPoolExecutor(max_workers=JOBS) as ex:
        res = list(ex.map(lambda j: solve_dq(j[0], j[2], -I_PK * math.sin(math.radians(j[1])), I_PK * math.cos(math.radians(j[1])), th0), jobs))
    with open(OUT / "example_motor_loaded.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["variant", "beta_deg", "rotor_deg", "id_A", "iq_A", "psi_d_Wb", "psi_q_Wb", "torque_flux_Nm", "torque_fea_Nm"])
        for (v, b, pos), (d, q, t) in zip(jobs, res):
            i_d, i_q = -I_PK * math.sin(math.radians(b)), I_PK * math.cos(math.radians(b))
            w.writerow([v, b, pos, f"{i_d:.3f}", f"{i_q:.3f}", f"{d:.6f}", f"{q:.6f}", f"{1.5 * P_PAIRS * (d * i_q - q * i_d):.3f}", f"{t:.3f}"])
    print("loaded done", len(jobs), "theta0 deg", math.degrees(th0))


def ripple() -> None:
    """β = 41° (JMAG 전류 위상과 같다고 둔 값)에서 회전자 15° 범위(전기각 60° = 토크 맥동 한 주기)를 1° 간격으로 푼다."""
    th0 = theta0_rad()
    pos = [float(x) for x in np.arange(0.0, 15.0, 1.0)]
    b = math.radians(41.0)
    with ThreadPoolExecutor(max_workers=JOBS) as ex:
        res = list(ex.map(lambda r: solve_dq("nominal", r, -I_PK * math.sin(b), I_PK * math.cos(b), th0), pos))
    with open(OUT / "example_motor_ripple.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rotor_deg", "psi_d_Wb", "psi_q_Wb", "torque_flux_Nm", "torque_fea_Nm"])
        for r, (d, q, t) in zip(pos, res):
            w.writerow([r, f"{d:.6f}", f"{q:.6f}", f"{1.5 * P_PAIRS * (d * I_PK * math.cos(b) + q * I_PK * math.sin(b)):.3f}", f"{t:.3f}"])
    print("ripple done", len(pos))


def cogging_mesh() -> None:
    """코깅 토크의 메시 민감도: 한 슬롯 피치(7.5°)를 12점으로 보되 요소 크기를 줄인 세 가지(기본, 중간, 세밀)로 푼다."""
    br, mur, steel = VARIANTS["nominal"]
    meshes = {"base": None, "medium": {"stator": 2.0e-3, "rotor": 1.4e-3, "magnet": 1.4e-3, "slot": 3.0e-3, "gap": 0.3e-3},
              "fine": {"stator": 1.4e-3, "rotor": 1.0e-3, "magnet": 1.0e-3, "slot": 2.5e-3, "gap": 0.2e-3, "arc_deg": 0.25}}
    pos = [float(x) for x in np.arange(0.0, 7.5, 0.625)]
    jobs = [(k, r) for k in ("medium", "fine") for r in pos]
    with ThreadPoolExecutor(max_workers=JOBS) as ex:
        res = list(ex.map(lambda j: em.solve_one((0.0, 0.0, 0.0), j[1], br, mur, steel, mesh=meshes[j[0]]), jobs))
    with open(OUT / "example_motor_cogging_mesh.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["mesh", "rotor_deg", "torque_Nm", "lambda_A_Wb", "elements"])
        for (k, r), x in zip(jobs, res):
            w.writerow([k, r, f"{x['torque_Nm']:.4f}", f"{x['lambda_abc_Wb'][0]:.6f}", int(x["elements"])])
    print("cogging mesh done", len(jobs))


def cogging_sens() -> None:
    """코깅 토크의 입력 민감도: 강판 곡선(Prius M400 대 JFE 혼합)과 자석 Br(최소 대 공칭)을 바꿔 한 슬롯 피치를 12점으로 푼다(기본 메시)."""
    pos = [float(x) for x in np.arange(0.0, 7.5, 0.625)]
    names = ("m400", "brmin")
    jobs = [(v, r) for v in names for r in pos]
    with ThreadPoolExecutor(max_workers=JOBS) as ex:
        res = list(ex.map(lambda j: em.solve_one((0.0, 0.0, 0.0), j[1], *VARIANTS[j[0]]), jobs))
    with open(OUT / "example_motor_cogging_sens.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["variant", "rotor_deg", "torque_Nm"])
        for (v, r), x in zip(jobs, res):
            w.writerow([v, r, f"{x['torque_Nm']:.4f}"])
    print("cogging sens done", len(jobs))


if __name__ == "__main__":
    {"noload": noload, "loaded": loaded, "ripple": ripple, "cogging_mesh": cogging_mesh, "cogging_sens": cogging_sens}[sys.argv[1]]()
