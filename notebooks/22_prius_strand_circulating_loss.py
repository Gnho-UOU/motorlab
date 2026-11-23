"""G1 잔여 손실의 가설 점검: 병렬 소선의 순환 전류 손실이 `k_c·I²·f²` 항의 크기를 낼 수 있는가. (docs/validation_report.md "병렬 소선 순환 전류" 절)

가설: 한 턴이 13가닥 병렬 소선(0.912 mm)이고 소선 위치가 균일하게 섞이지(전위되지) 않았다면 슬롯 누설 자속이 소선마다 다른 유도 기전력을 만들고,
병렬 소선 끝이 이어진 루프에 순환 전류가 흘러 손실이 `ω²B²`, 즉 `I²f²`로 커진다. 60 Hz 시험에서는 `(60/f)²`만큼만 보인다.
모델(근사, 가정 모두 표시):
  슬롯 누설 자속밀도: 슬롯 폭 w = (W1 + W2)/2 = 6.5 mm(해체 형상), 슬롯 안은 한 상의 9턴뿐(단층)이므로 깊이 방향으로 MMF가 0에서 9·I_pk까지 올라간다.
    소선이 놓인 깊이 전체의 평균 B_avg = 0.5·μ0·9·I_pk/w.  [가정: 슬롯이 도체로 가득 차 있고 자속이 폭 방향]
  소선 i의 깊이 위치 편차 d_i (평균 0, 표준편차 d_rms): 루프 기전력 e_i = κ·2·ω_e·B_avg·L·d_i (슬롯 양쪽 2개, 직렬 턴 N_s = 72턴이 같은 부호로 더해지면 κ = 72, 무작위면 √72 ≈ 8.5)
  순환 전류 손실(소선 n = 13가닥, 소선 한 가닥의 상 전체 길이 저항 R_s = ρ·N_s·l_turn/A_s, 상 3개): P = 3·n·Var(e)/R_s = 3·n·(κ·2·ω_e·B_avg·L·d_rms)²/R_s
  → P = k·I_rms²·f², k = 3·n·(κ·4π·β·L·d_rms)²/R_s·2, β = 0.5·μ0·9/w · √... (I_pk² = 2·I_rms²)
이 노트북은 반대로 풀어, 측정 잔여 손실이 낸 k_c(측정 전류 기준)에서 κ·d_rms를 역산하고 가능한 범위(κ 8.5~72, d_rms 0.3~1.2 mm)와 견준다.
입력: data/benchmarks/prius2004_perf_map.csv, prius2004_rotor_loss.csv, 해체 형상 JSON. 한계: 소선 배치·전위 상태는 자료가 없다. 이 계산은 가능성의 크기 점검이다(판정 아님).
실행: python notebooks/22_prius_strand_circulating_loss.py
"""
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("n08", ROOT / "notebooks" / "08_prius_high_speed_current.py")
n08 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n08)

MU0 = 4e-7 * math.pi
RHO_CU, A_S, N_STRAND, N_TURN_SERIES, L_TURN = 1.73e-8, math.pi / 4 * 0.912e-3 ** 2, 13, 72, 0.41     # pyleecan 소선 정보, 턴당 길이는 ORNL 역검산(prius2004_ornl.md)
G = json.loads((ROOT / "data/benchmarks/prius2004_geometry_teardown.json").read_text())["stator"]
W_SLOT = 0.5 * (G["slot_SlotW11"]["W1"] + G["slot_SlotW11"]["W2"])
STACK = G["L1_m"]


def main() -> None:
    c = n08.load_csv(ROOT / "data/benchmarks/prius2004_perf_map.csv")
    rl = n08.load_csv(ROOT / "data/benchmarks/prius2004_rotor_loss.csv")
    sp = c["speed_rpm"]
    Rs = n08.R20 * (1 + n08.ALPHA * (c["T_stator_C"] - 20))
    ex = c["P_ac_W"] - c["P_mech_W"] - 3 * Rs * c["Iac_rms_A"] ** 2 - np.interp(sp, rl["motor_rpm"], rl["motor_rotor_loss_W"])
    m = (sp >= 3000) & (c["P_ac_W"] > 5000)
    f = 4 * sp[m] / 60
    I = c["Iac_rms_A"][m]
    X = np.c_[f, I ** 2 * f ** 2]
    kf, kc = np.linalg.lstsq(X, ex[m], rcond=None)[0]
    r2 = 1 - ((ex[m] - X @ [kf, kc]) ** 2).sum() / ((ex[m] - ex[m].mean()) ** 2).sum()
    print(f"≥ 3000 rpm {m.sum()}행, 측정 전류(Iac_rms) 기준 잔여 = k_f·f + k_c·I²f²: k_f = {kf:.2f} W/Hz, k_c = {kc:.2e} W/(A²Hz²), R² = {r2:.3f}")
    Rstrand = RHO_CU * N_TURN_SERIES * L_TURN / A_S
    beta = 0.5 * MU0 * 9 / W_SLOT                       # B_avg = beta·I_pk [T/A]
    print(f"슬롯 폭 {W_SLOT * 1e3:.1f} mm, B_avg = {beta * 1e3:.3f} mT/A (I_pk 250 A에서 {beta * 250:.2f} T), 소선 한 가닥 상 전체 저항 R_s = {Rstrand:.2f} Ω")
    # k = 3·n·(κ·4π·β·L·d)²/R_s ·2  (I_pk² = 2 I_rms², ω_e = 2π f)
    need = math.sqrt(kc * Rstrand / (3 * N_STRAND * 2)) / (4 * math.pi * beta * STACK)
    print(f"측정 k_c를 내려면 κ·d_rms = {need * 1e3:.1f} mm")
    print("| 가정 | κ | d_rms [mm] | κ·d_rms [mm] | 그 가정의 k [W/(A²Hz²)] | 측정 k_c 대비 |")
    print("|---|---|---|---|---|---|")
    for label, kappa, d in (("무작위, 번들 1 mm", math.sqrt(72), 0.3e-3), ("무작위, 번들 4 mm", math.sqrt(72), 1.15e-3),
                            ("일관된 편차, 번들 1 mm", 72, 0.3e-3), ("일관된 편차, 번들 4 mm", 72, 1.15e-3)):
        k = 3 * N_STRAND * (kappa * 4 * math.pi * beta * STACK * d) ** 2 / Rstrand * 2
        print(f"| {label} | {kappa:.1f} | {d * 1e3:.2f} | {kappa * d * 1e3:.1f} | {k:.2e} | {k / kc:.2f} |")
    f60 = 60.0
    print(f"\n같은 k_c로 60 Hz, I_rms 60~80 A: {kc * 60 ** 2 * f60 ** 2:.0f}~{kc * 80 ** 2 * f60 ** 2:.0f} W (정현파 시험 허용 오차 ±100 W 안)")


if __name__ == "__main__":
    main()
