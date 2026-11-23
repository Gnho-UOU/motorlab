"""G1 잔여 손실의 가설 점검: 자석(분할 안 된 NdFeB 블록)의 와전류 손실이 잔여 손실의 크기를 낼 수 있는가.

ORNL Prius 자석은 83.1 × 18.9 × 6.5 mm 한 덩어리(TM-2010/253)라 축 방향으로 분할되지 않은 것으로 보인다. 고정자의 공간 고조파(MMF 5·7차, 슬롯)가 회전자에서 보면
기본 전기 주파수의 6, 12, ...배로 변해 자석 안에 와전류를 만든다. 이 손실은 전류²·주파수²로 커져 경험식 항 `k_c·I²·f²`와 같은 모양이다.
방법: 측정 행(속도, 토크, 전류)에서 엔진으로 (id, iq)를 풀고(약계자 쪽 해), 같은 (id, iq)를 동기(전류 위상이 회전자와 같이 돎)로 유지하며 회전자를 한 주기(고정자 슬롯 7.5°와
MMF 6차의 최소공배 = 15° 기계각)동안 N위치 돌려 자석 안 점(회전자에 고정)의 벡터 퍼텐셜 A를 읽는다. 축 방향이 균일한 2D에서 회전자 좌표계의 전계는
E_z = −DA/Dt + C(t)이고 C(t)는 한 블록의 축 방향 전체 전류가 0이 되게 정해진다. 따라서 블록당 단위 길이 손실은 P' = σ·S·⟨(Ȧ − ⟨Ȧ⟩_블록)²⟩_시간.
(점들을 블록 안에서 같은 가중치로 평균한다. 블록 면적 S는 다각형 면적. 무한 길이 가정이라 유한 길이(83 mm, 폭 19 mm)에서는 약 15% 작다.)
전체 = P'·L·(블록 2개 × 극 8개). 와전류가 만드는 반작용 자계는 무시한다(저주파 근사: 침투 깊이 12 mm > 두께 6.5 mm, 2.4 kHz에서도 같은 자릿수).
저항률: N45SH 데이터시트의 1.3~1.5 µΩ·m (Prius 자석 등급은 모른다).
한계: 전류는 정현파이므로 육각파 전압의 시간 고조파가 만드는 효과는 없다(실제 시험은 육각파). 회전자 적층 철심 와전류, 코일 AC 손실은 없다.
실행: FEMMCLI=<femmcli> python femm/prius_magnet_eddy.py select | run   → data/fea/prius2004_magnet_eddy.csv
"""
import csv
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

sys.path.insert(0, str(Path(__file__).parent))
import prius_full as pf  # noqa: E402
import prius_run as pr  # noqa: E402
from demag_check import magnet_probes  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.model import FluxMapModel  # noqa: E402

OUT = ROOT / "data" / "fea" / "prius2004_magnet_eddy.csv"
BR, MUR = 1.06, 1.129                       # 교정된 Prius 모델 (docs/FEA_OPTIONS.md 3-6절)
N_POS, PERIOD_DEG = 20, 15.0
STACK = 0.0836
RHO = (1.3e-6, 1.5e-6)
MECH = (0.44058, 7.7652e-7)
R20, ALPHA = 0.069 / (1 + 0.00393), 0.00393
JOBS = int(os.environ.get("JOBS", "16"))


def load_csv(path):
    lines = [l for l in Path(path).read_text().splitlines() if l.strip() and not l.startswith("#")]
    h = lines[0].split(",")
    A = np.loadtxt(lines[1:], delimiter=",")
    return {k: A[:, i] for i, k in enumerate(h)}


def rows_for_targets(targets=(3000, 4500, 6000)):
    """측정 행 중 목표 속도에 가깝고 전류·토크로 약계자 해가 있는 행을 하나씩 고른다. (id, iq)는 엔진 맵 모델의 해."""
    c = load_csv(ROOT / "data/benchmarks/prius2004_perf_map.csv")
    rl = load_csv(ROOT / "data/benchmarks/prius2004_rotor_loss.csv")
    m = FluxMapModel.from_csv(ROOT / "data/flux_maps/prius2004_fullmodel_teardown_25A.csv", p=4, Rs=0.0)
    out = []
    for tgt in targets:
        best = None
        for i in np.argsort(np.abs(c["speed_rpm"] - tgt)):
            if abs(c["speed_rpm"][i] - tgt) > 250 or c["P_ac_W"][i] < 8000:
                continue
            sp = c["speed_rpm"][i]
            w = sp * math.pi / 30
            Is = c["Iac_rms_A"][i] * math.sqrt(2)
            if Is > 250:
                continue
            Tem = c["torque_Nm"][i] + (MECH[0] * w + MECH[1] * w ** 3) / w
            tq = lambda b: float(m.torque(-Is * math.sin(b), Is * math.cos(b))) - Tem
            bs = np.linspace(0, math.pi / 2, 181)
            ts = np.array([tq(b) for b in bs])
            roots = [brentq(tq, bs[k], bs[k + 1]) for k in range(len(bs) - 1) if ts[k] * ts[k + 1] < 0]
            if not roots:
                continue
            b = roots[-1]
            Rs = R20 * (1 + ALPHA * (c["T_stator_C"][i] - 20))
            ex = c["P_ac_W"][i] - c["P_mech_W"][i] - 3 * Rs * c["Iac_rms_A"][i] ** 2 - float(np.interp(sp, rl["motor_rpm"], rl["motor_rotor_loss_W"]))
            best = dict(speed_rpm=float(sp), torque_Nm=float(c["torque_Nm"][i]), Iac_rms_A=float(c["Iac_rms_A"][i]), id_A=-Is * math.sin(b), iq_A=Is * math.cos(b), residual_W=float(ex))
            break
        if best:
            out.append(best)
    return out


def poly_area(poly):
    x = np.array([p.real for p in poly]); y = np.array([p.imag for p in poly])
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def block_areas(g):
    from prius_sector import rotor_hole_points
    ro = g["rotor"]
    lower = rotor_hole_points(g)
    strip = bool(ro["hole_HoleM50"].get("air_strip_below_magnet"))
    keys = ("Z8", "Z8c", "Z3", "Z6") if strip else ("Z8", "Z8c", "Z3", "Z4", "Z5", "Z6")
    a = poly_area([lower[k] for k in keys])
    return a, a                                                              # 위 블록은 아래 블록의 거울상


def solve_op(op, pos_deg):
    g = pf.load_geometry()
    pts = [p for p, _ in magnet_probes(g)]
    th = math.radians(pr.THETA0_ELEC_DEG + 4 * pos_deg)
    ia, ib, ic = pr.inverse_park(np.array([op["id_A"]]), np.array([op["iq_A"]]), np.array([th]))[0]
    z = [p * complex(math.cos(math.radians(pos_deg)), math.sin(math.radians(pos_deg))) for p in pts]          # 회전자에 고정된 점
    r = pf.solve_one((float(ia), float(ib), float(ic)), pos_deg, br_T=BR, mur=MUR, probes=z)
    return r["A_Wb_per_m"], r["torque_Nm"]


def eddy_loss(A_t, dt_s, areas):
    """A_t: (위치, 점) [Wb/m]. 두 블록의 점은 앞뒤 반. 반환: 총 와전류 손실 [W] (저항률 두 값), 블록 안 편차의 시간 rms."""
    n = A_t.shape[1] // 2
    Adot = (np.roll(A_t, -1, axis=0) - np.roll(A_t, 1, axis=0)) / (2 * dt_s)           # 주기 중심 차분
    total = []
    for rho in RHO:
        P = 0.0
        for blk, S in zip((slice(0, n), slice(n, 2 * n)), areas):
            d = Adot[:, blk] - Adot[:, blk].mean(axis=1, keepdims=True)
            P += (1 / rho) * S * float(np.mean(d ** 2))
        total.append(P * STACK * 8)
    return total


def main(mode):
    ops = rows_for_targets()
    if mode == "select":
        for o in ops:
            print(o)
        return
    g = pf.load_geometry()
    areas = block_areas(g)
    pos = [PERIOD_DEG * k / N_POS for k in range(N_POS)]
    jobs = [(o, p) for o in ops for p in pos]
    with ThreadPoolExecutor(max_workers=JOBS) as ex:
        res = list(ex.map(lambda j: solve_op(*j), jobs))
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["speed_rpm", "torque_meas_Nm", "Iac_rms_A", "id_A", "iq_A", "residual_W", "torque_fea_Nm", "P_eddy_rho1.3_W", "P_eddy_rho1.5_W"])
        for k, o in enumerate(ops):
            A = np.array([r[0] for r in res[k * N_POS:(k + 1) * N_POS]])
            T = float(np.mean([r[1] for r in res[k * N_POS:(k + 1) * N_POS]]))
            dt = math.radians(PERIOD_DEG / N_POS) / (o["speed_rpm"] * math.pi / 30)
            p13, p15 = eddy_loss(A, dt, areas)
            w.writerow([o["speed_rpm"], o["torque_Nm"], o["Iac_rms_A"], f"{o['id_A']:.1f}", f"{o['iq_A']:.1f}", f"{o['residual_W']:.0f}", f"{T:.1f}", f"{p13:.0f}", f"{p15:.0f}"])
            print(o, T, p13, p15, flush=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "run")
