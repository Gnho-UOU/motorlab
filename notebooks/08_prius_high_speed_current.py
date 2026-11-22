"""고속(>= 3000 rpm)에서 엔진 필요 전류가 측정보다 작은 이유를 가르는 두 가지 시험. (docs/validation_report.md "원인 탐색" 절)

(1) 측정 전류와 토크에서 모델이 요구하는 전압.
    행마다 측정 상전류 첨두값 |Is|와 전자기 토크 T_em(샤프트 토크 + 기계손/ω)을 고정하고, 전류각 β(id = −|Is|·sinβ, iq = |Is|·cosβ)를
    풀어 모델의 전압 크기를 계산한다. 이 전압이 육각파 한계 Vmax = (2/π)·Vdc에 가까우면 모델과 측정이 같은 말을 하는 것이다.
(2) 잔여 손실이 자속에 비례하는지 전류에 비례하는지.
    같은 동작점(측정 전류, 풀린 β)의 모델 자속 |ψ|와 측정 전류로 잔여 손실 = P_ac − P_mech − 동손(측정 전류) − 무부하 실측 손실을 회귀한다.
    ORNL 제어기는 id를 바꿔 효율이 가장 높은 점을 골랐으므로, 손실이 자속에 의존하면 약계자가 더 깊은 점(전류가 큰 점)이 선택될 수 있다.
입력: data/benchmarks/prius2004_perf_map.csv, prius2004_rotor_loss.csv, data/flux_maps/prius2004_fullmodel_pocket_25A.csv
실행: python notebooks/08_prius_high_speed_current.py
"""
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.model import FluxMapModel  # noqa: E402

MECH = (0.44058, 7.7652e-7)           # TM-423 표 3.7 로터 손실 피팅 (notebooks/03)
R20, ALPHA = 0.065, 0.00393


def load_csv(path):
    lines = [l for l in Path(path).read_text().splitlines() if l.strip() and not l.startswith("#")]
    h = lines[0].strip().split(",")
    A = np.loadtxt(lines[1:], delimiter=",")
    return {k: A[:, i] for i, k in enumerate(h)}


def main() -> None:
    c = load_csv(ROOT / "data/benchmarks/prius2004_perf_map.csv")
    rl = load_csv(ROOT / "data/benchmarks/prius2004_rotor_loss.csv")
    m = FluxMapModel.from_csv(ROOT / "data/flux_maps/prius2004_fullmodel_pocket_25A.csv", p=4, Rs=0.0)
    rows = []
    for i in np.nonzero(c["speed_rpm"] >= 3000)[0]:
        sp = c["speed_rpm"][i]
        w = sp * math.pi / 30
        we = 4 * w
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
        b = roots[-1]                                         # 약계자 쪽 해(전류각이 큰 쪽)
        d, q = -Is * math.sin(b), Is * math.cos(b)
        Rs = R20 * (1 + ALPHA * (c["T_stator_C"][i] - 20))
        pd, pq = (float(x) for x in m.flux(d, q))
        V = math.hypot(Rs * d - we * pq, Rs * q + we * pd)
        Vmax = 2 / math.pi * c["Vdc_V"][i]
        Pcu = 3 * Rs * (Is / math.sqrt(2)) ** 2
        nl = float(np.interp(sp, rl["motor_rpm"], rl["motor_rotor_loss_W"]))
        ex = c["P_ac_W"][i] - c["P_mech_W"][i] - Pcu - nl
        rows.append((sp, 4 * sp / 60, math.hypot(pd, pq), Is, ex, V / Vmax, c["torque_Nm"][i], math.degrees(b)))
    R = np.array(rows)
    sp, f, psi, Is, ex, vr = R[:, 0], R[:, 1], R[:, 2], R[:, 3], R[:, 4], R[:, 5]
    print(f"측정 전류·토크를 만족하는 약계자 쪽 해가 있는 행: {len(R)}")
    print(f"(1) 모델 전압 / 육각파 한계: 중앙값 {np.median(vr):.2f}, 범위 {vr.min():.2f}~{vr.max():.2f} "
          f"(1이면 한계. 4000 rpm 이상 {np.median(vr[sp >= 4000]):.2f}, 토크 40 N·m 미만 {np.median(vr[R[:, 6] < 40]):.2f}, 80 N·m 이상 {np.median(vr[R[:, 6] >= 80]):.2f})")
    print(f"    모델 |ψ| 범위 {psi.min():.3f}~{psi.max():.3f} Wb (무부하 {float(np.hypot(*m.flux(0.0, 0.0))):.3f}), 잔여 손실 {ex.min():.0f}~{ex.max():.0f} W")
    print("(2) 잔여 손실 회귀 (R², 계수)")

    def fit(name, X):
        co = np.linalg.lstsq(X, ex, rcond=None)[0]
        r2 = 1 - ((ex - X @ co) ** 2).sum() / ((ex - ex.mean()) ** 2).sum()
        print(f"    {name:22s} R² = {r2:6.3f}  계수 {np.array2string(co, precision=3)}")

    fit("f", np.c_[f])
    fit("f·ψ²", np.c_[f * psi ** 2])
    fit("f², f²ψ²", np.c_[f ** 2, f ** 2 * psi ** 2])
    fit("f, I²f²", np.c_[f, Is ** 2 * f ** 2])
    fit("f, f²ψ²", np.c_[f, f ** 2 * psi ** 2])
    lg = np.c_[np.ones(len(R)), np.log(f), np.log(psi)]
    y = np.log(np.clip(ex, 10, None))
    co = np.linalg.lstsq(lg, y, rcond=None)[0]
    print(f"    거듭제곱 ex = {math.exp(co[0]):.3g}·f^{co[1]:.2f}·ψ^{co[2]:.2f}  (ψ 지수가 음수면 자속이 낮을수록 손실이 크다)")


if __name__ == "__main__":
    main()
