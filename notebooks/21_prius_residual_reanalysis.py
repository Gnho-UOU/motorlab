"""G1 잔여 손실 재해석 (docs/validation_report.md "잔여 손실 재해석" 절): 인버터·고조파·정현파 시험이 실제로 무엇을 배제하는가.

(1) 속도 구간별 인버터 효율(P_ac/P_dc)과 잔여 손실. 고속에서 인버터 효율이 99%에 이르는 것이 측정 오류인지 육각파 운전의 성질인지 본다.
(2) 육각파(고속) 전압 고조파가 만드는 전류 고조파와 그 동손의 크기 추정: v_h = V1/h, i_h = v_h/(h·ωe·L_h), P = 1.5·Rs·Σ i_h². L_h는 모르므로 0.3~3.5 mH 범위(정적 측정 Ld 1.92, Lq 5 mH
    의 평균 3.5 mH가 위, 슬롯 누설 수준 0.3 mH가 아래)에서 본다.
(3) 정현파 900 rpm 시험(60 Hz)이 경험식 잔여 손실 항 k_c·I²·f²에 대해 주는 상한: 60 Hz에서는 그 항이 작아서 시험이 배제하는 정도를 계산한다.
실행: python notebooks/21_prius_residual_reanalysis.py
"""
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "notebooks" / file)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main() -> None:
    n08, n09 = _load("n08", "08_prius_high_speed_current.py"), _load("n09", "09_prius_sine_supply_check.py")
    c = n08.load_csv(ROOT / "data/benchmarks/prius2004_perf_map.csv")
    rl = n08.load_csv(ROOT / "data/benchmarks/prius2004_rotor_loss.csv")
    sp = c["speed_rpm"]
    Rs = n08.R20 * (1 + n08.ALPHA * (c["T_stator_C"] - 20))
    ex = c["P_ac_W"] - c["P_mech_W"] - 3 * Rs * c["Iac_rms_A"] ** 2 - np.interp(sp, rl["motor_rpm"], rl["motor_rotor_loss_W"])
    inv = c["P_dc_W"] - c["P_ac_W"]
    print("## (1) 속도 구간별 (P_ac > 5 kW 행)")
    print("| 속도 [rpm] | 행 | 인버터 효율 중앙값 | 인버터 손실 [W] | 잔여 손실 [W] | 잔여/P_dc |")
    print("|---|---|---|---|---|---|")
    for lo, hi in ((0, 1000), (1000, 3000), (3000, 4500), (4500, 7000)):
        m = (sp >= lo) & (sp < hi) & (c["P_ac_W"] > 5000)
        print(f"| {lo}~{hi} | {m.sum()} | {np.median(c['P_ac_W'][m] / c['P_dc_W'][m]):.3f} | {np.median(inv[m]):.0f} | {np.median(ex[m]):.0f} | {100 * np.median(ex[m] / c['P_dc_W'][m]):.1f} % |")
    print("\n## (2) 육각파 전압 고조파의 전류 고조파 동손 (5·7·11·13차, 상 첨두 기본파 318 V, R = 0.07 Ω)")
    print("| 속도 [rpm] | L_h = 0.3 mH | 1.0 mH | 3.5 mH |")
    print("|---|---|---|---|")
    for rpm in (3000, 4500, 6000):
        we = 4 * rpm * math.pi / 30
        row = []
        for L in (0.3e-3, 1.0e-3, 3.5e-3):
            P = sum(1.5 * 0.07 * (318.0 / h / (h * we * L)) ** 2 for h in (5, 7, 11, 13))
            row.append(f"{P:.1f} W")
        print(f"| {rpm} | " + " | ".join(row) + " |")
    print("\n## (3) 정현파 900 rpm 시험(60 Hz)과 경험식 항 k_c·I²·f²")
    rows = [r for r in n09.load() if r["torque_Nm"] >= 60]
    j = json.loads((ROOT / "data/fea/prius2004_excess_loss_fit.json").read_text())
    kc = j["k_c_W_per_A2Hz2"]
    obs = np.array([r["P_elec_W"] - r["P_mech_W"] - n09.DRAG_W - 3 * n09.R20 * (1 + n09.ALPHA * (r["T_winding_C"] - 20)) * r["I_A"] ** 2 for r in rows])
    pred = np.array([kc * r["I_A"] ** 2 * 60.0 ** 2 for r in rows])
    Imax = max(r["I_A"] for r in rows)
    print(f"60 N·m 이상 {len(rows)}행: 관측 잔여 중앙값 {np.median(obs):.0f} W (범위 {obs.min():.0f}~{obs.max():.0f}), 경험식 k_c 항 예측 중앙값 {np.median(pred):.0f} W (범위 {pred.min():.0f}~{pred.max():.0f})")
    m3 = (sp >= 3000) & (c["P_ac_W"] > 5000)
    f3, I3 = 4 * sp[m3] / 60, c["Iac_rms_A"][m3]
    kc_meas = np.linalg.lstsq(np.c_[f3, I3 ** 2 * f3 ** 2], ex[m3], rcond=None)[0][1]
    pred2 = np.array([kc_meas * r["I_A"] ** 2 * 60.0 ** 2 for r in rows])
    print(f"(참고) 같은 식을 측정 전류(Iac_rms)로 다시 맞추면 k_c = {kc_meas:.2e} (모델 전류 기준 {kc:.1e}), 60 Hz 예측 중앙값 {np.median(pred2):.0f} W, 관측 − 예측 중앙값 {np.median(obs - pred2):.0f} W")
    print(f"관측 − 예측 중앙값 {np.median(obs - pred):.0f} W. 열전대 온도 불확실성 ±100 W를 허용하면 시험이 허용하는 k_c 상한은 약 {(100 + np.median(obs)) / (Imax ** 2 * 3600):.1e} (맞춘 값 {kc:.1e}의 {(100 + np.median(obs)) / (Imax ** 2 * 3600) / kc:.2f}배)")


if __name__ == "__main__":
    main()
