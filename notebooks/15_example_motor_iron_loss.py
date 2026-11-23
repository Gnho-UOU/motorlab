"""연구실 예제 IPMSM의 철손과 효율: FEA 자속밀도 파형으로 구한 값 대 JMAG 결과.

입력: data/fea/example_motor_iron_probes.npz (femm/example_iron_run.py: 부하 β = 41°, 330 A, 4300 rpm, 한 전기 주기 60위치, 점 B)
      engine/steel.py (JFE 35JN230 카탈로그 값에서 계수를 구한 Bertotti 식: 고전 와전류 + 히스테리시스, 60 Hz 대표값 1% 안에서 예측)
JMAG 결과(연구실 강의 자료의 결과 화면): 평균 토크 350.64 N·m, 동손 5397.15 W, 철손 751.48 W, 출력 157892 W, 입력 164040.6 W, 효율 96.25 %.
방법: 점마다 Bx, By 파형을 푸리에 분해해 고조파별 W/kg을 더하고(직류 성분 제외), 영역별 질량(면적 × 적층 153 mm × 적층률 0.97 × 7600 kg/m³)을 곱한다.
  고정자는 90° 구간 ×4, 회전자는 한 극 ×8. 회전자 점의 B는 회전자 좌표계로 돌려서 본다(자석·전류 파형이 회전자에 대해 정지한 성분은 직류라 손실이 없다).
한계: 점 수가 적다(요소별 B가 아님). 이상(excess) 손실·소형 루프 보정이 없다. 35JN230의 수백 Hz 이상 철손 자료가 없어 고전 와전류 식의 외삽이다.
JMAG는 철손 계산에 JFE 라이브러리 곡선을 쓴다(우리가 가진 정보보다 많다). 자석 와전류 손실은 어느 쪽에도 없다.
실행: python notebooks/15_example_motor_iron_loss.py
"""
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.steel import load_steel  # noqa: E402

STACK, LAM_FILL = 0.153, 0.97
F1 = 4300.0 / 60.0 * 4.0
RPM_W = 4300.0 * 2 * math.pi / 60.0
RS, I_RMS = 0.0330, 330.0 / math.sqrt(2)
JMAG = {"torque": 350.64, "copper": 5397.15, "core": 751.48, "eff": 96.25}


def region_loss(steel, bx, by, weights_m2, mult):
    """bx, by: (위치, 점). 영역 철손 [W]."""
    total = 0.0
    kg_per_m2 = STACK * LAM_FILL * steel.density_kg_m3
    for j in range(bx.shape[1]):
        total += steel.loss_from_waveform(bx[:, j], by[:, j], F1) * weights_m2[j] * kg_per_m2 * mult
    return total


def compute(npz="example_motor_iron_probes.npz"):
    """영역별 철손 [W]의 dict, 합계, 평균 토크, 출력, 동손, 효율 [%], 점 가중 질량(고정자·회전자) 를 돌려준다."""
    d = np.load(ROOT / "data" / "fea" / npz)
    steel = load_steel("35JN230")
    pos = np.radians(d["positions_deg"])
    B = d["B_xy_T"].astype(float)
    n_s = int(d["n_stator"])
    reg, sa, ra = d["stator_region"], d["stator_area_m2"], d["rotor_area_m2"]
    out = {}
    for code, name in ((0, "치"), (1, "슈"), (2, "요크")):
        m = reg == code
        out[name] = region_loss(steel, B[:, :n_s, 0][:, m], B[:, :n_s, 1][:, m], sa[m], 4.0)
    rb = B[:, n_s:, 0] + 1j * B[:, n_s:, 1]
    rb = rb * np.exp(-1j * pos)[:, None]                                       # 회전자 좌표계로
    out["회전자"] = region_loss(steel, rb.real, rb.imag, ra, 8.0)
    core = sum(out.values())
    torque = float(np.mean(d["torque_Nm"]))
    p_out = torque * RPM_W
    copper = 3 * I_RMS ** 2 * RS
    eff = 100 * p_out / (p_out + copper + core)
    mass = (4 * sa.sum() * STACK * LAM_FILL * steel.density_kg_m3, 8 * ra.sum() * STACK * LAM_FILL * steel.density_kg_m3)
    return out, core, torque, p_out, copper, eff, mass


def main() -> None:
    out, core, torque, p_out, copper, eff, mass = compute()
    print("## 철손 (35JN230 카탈로그 기반 Bertotti 식, FEA 파형, 4300 rpm, 330 A, β = 41°)")
    print("| 영역 | 손실 [W] |")
    print("|---|---|")
    for k, v in out.items():
        print(f"| {k} | {v:.0f} |")
    print(f"| **합계** | **{core:.0f}** (JMAG {JMAG['core']:.0f} W, {100 * (core / JMAG['core'] - 1):+.1f} %) |")
    print("\n## 효율")
    print("| 항목 | xfemm | JMAG |")
    print("|---|---|---|")
    print(f"| 평균 토크 (Henrotte, 60위치) [N·m] | {torque:.2f} | {JMAG['torque']} |")
    print(f"| 출력 [W] | {p_out:.0f} | 157892 |")
    print(f"| 동손 3·I²·R [W] (R = 0.033 Ω) | {copper:.0f} | {JMAG['copper']:.0f} |")
    print(f"| 철손 [W] | {core:.0f} | {JMAG['core']:.0f} |")
    print(f"| 효율 [%] | {eff:.2f} | {JMAG['eff']} |")
    print(f"\n질량(점 가중): 고정자 철심 {mass[0]:.1f} kg, 회전자 {mass[1]:.1f} kg")

if __name__ == "__main__":
    main()
