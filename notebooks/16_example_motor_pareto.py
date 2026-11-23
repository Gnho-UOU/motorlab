"""M6: 연구실 예제 IPMSM의 자석 설계 최적화 결과 (토크 최대 · 자석 단면적 최소, 전압·감자 제약).

입력: data/fea/design_opt_evals.csv (femm/design_opt_run.py: FEA로 평가한 설계 표). 설계마다 13번의 전체 모터 FEA.
  T_Nm: 상전류 첨두 330 A, 4300 rpm에서 전류각 β를 최적으로 잡은 평균 토크(4위치 평균), V_peak_V: 그때 단자 전압 기본파 첨두,
  demag_margin_150C: N45SH 150 °C에서 최악 점의 1 − H/Hk, magnet_area_mm2: 극당 자석 단면적.
제약: V ≤ 433 V ((2/π)·680 V), 감자 여유 ≥ 0.05. 비교 대상은 같은 평가기로 푼 기준 설계(강의 자료의 원 설계).
출력(화면): 평가 요약, FEA로 평가한 설계 중 제약을 지키는 파레토 해, 기준 설계 대비. 그림: docs/figures/pareto_example_motor.png
참고: 파레토 해는 FEA로 직접 평가한 설계에서만 고른다(대리모델 예측이 아니다). 대리모델 정확도는 LOO RMSE로 보인다.
실행: python notebooks/16_example_motor_pareto.py
"""
import csv
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.optimize import GPSurrogate, hypervolume_2d, pareto_mask  # noqa: E402

VARS = ["m_thick1", "m_length_1", "m_theta_1", "m_thick2", "m_length_2"]
LOWER = np.array([2.0, 18.0, 44.0, 2.4, 10.0])
UPPER = np.array([3.4, 26.0, 56.0, 4.2, 16.0])
V_LIMIT, MARGIN_MIN = (2 / np.pi) * 680.0, 0.05


def main() -> None:
    rows = list(csv.DictReader(open(ROOT / "data" / "fea" / "design_opt_evals.csv")))
    for r in rows:
        for k in r:
            if k not in ("id", "stage"):
                r[k] = float(r[k])
    base = next(r for r in rows if r["id"] == "baseline")
    ok = [r for r in rows if r["V_peak_V"] <= V_LIMIT and r["demag_margin_150C"] >= MARGIN_MIN]
    print(f"평가한 설계 {len(rows)}개 (초기 {sum(r['stage'] == 'init' for r in rows)}, 반복 {sum(r['stage'].startswith('iter') for r in rows)}), 제약을 지키는 설계 {len(ok)}개")
    print(f"기준 설계: T = {base['T_Nm']:.1f} N·m (β* {base['beta_deg']:.1f}°), V = {base['V_peak_V']:.0f} V, 감자 여유 {base['demag_margin_150C']:+.2f}, 자석 {base['magnet_area_mm2']:.1f} mm²/극")
    F = np.array([[-r["T_Nm"], r["magnet_area_mm2"]] for r in ok])
    keep = pareto_mask(F)
    front = sorted([r for r, k in zip(ok, keep) if k], key=lambda r: r["magnet_area_mm2"])
    print("\n## FEA로 평가한 설계 중 제약을 지키는 파레토 해 (자석 면적 오름차순)")
    print("| 설계 | 자석 [mm²/극] | 면적 변화 | T* [N·m] | 토크 변화 | β* [°] | V [V] | 감자 여유 | t1 | L1 | θ1 | t2 | L2 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in front:
        print(f"| {r['id']} | {r['magnet_area_mm2']:.1f} | {100 * (r['magnet_area_mm2'] / base['magnet_area_mm2'] - 1):+.1f} % | {r['T_Nm']:.1f} | "
              f"{100 * (r['T_Nm'] / base['T_Nm'] - 1):+.1f} % | {r['beta_deg']:.1f} | {r['V_peak_V']:.0f} | {r['demag_margin_150C']:+.2f} | "
              + " | ".join(f"{r[v]:.2f}" for v in VARS) + " |")
    dom = [r for r in ok if r["T_Nm"] >= base["T_Nm"] and r["magnet_area_mm2"] <= base["magnet_area_mm2"]
           and (r["T_Nm"] > base["T_Nm"] or r["magnet_area_mm2"] < base["magnet_area_mm2"])]
    print(f"\n기준 설계를 지배하는(토크 ≥, 자석 ≤, 하나는 엄격히) 설계: {len(dom)}개")
    ref = (-0.9 * base["T_Nm"], 1.2 * base["magnet_area_mm2"])
    print("\n초체적(ref: 토크 0.9배, 면적 1.2배)이 반복마다 얼마나 커지는가:")
    stages = ["init"] + sorted({r["stage"] for r in rows if r["stage"].startswith("iter")})
    used = []
    for st in stages:
        used += [r for r in ok if r["stage"] == st]
        Fs = np.array([[-r["T_Nm"], r["magnet_area_mm2"]] for r in used])
        print(f"  {st}: 설계 {len(used)}개, 초체적 {hypervolume_2d(Fs, ref):.1f}")
    X = (np.array([[r[v] for v in VARS] for r in rows]) - LOWER) / (UPPER - LOWER)
    print("\n대리모델(전 표본) LOO RMSE: " + ", ".join(
        f"{name} {GPSurrogate().fit(X, np.array([r[col] for r in rows])).loo_rmse():.3g}" for name, col in
        (("T [N·m]", "T_Nm"), ("V [V]", "V_peak_V"), ("감자 여유", "demag_margin_150C"))))
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams["font.family"] = ["AppleGothic", "Malgun Gothic", "NanumGothic", "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
        fig, ax = plt.subplots(figsize=(7.5, 5))
        bad = [r for r in rows if r not in ok]
        ax.scatter([r["magnet_area_mm2"] for r in bad], [r["T_Nm"] for r in bad], c="#bbbbbb", s=22, label="제약 위반")
        init = [r for r in ok if r["stage"] == "init"]
        it = [r for r in ok if r["stage"].startswith("iter")]
        ax.scatter([r["magnet_area_mm2"] for r in init], [r["T_Nm"] for r in init], c="#2a9fc9", s=26, label="초기 표본(라틴 하이퍼큐브)")
        ax.scatter([r["magnet_area_mm2"] for r in it], [r["T_Nm"] for r in it], c="#d98d55", s=26, label="대리모델 반복으로 고른 설계")
        ax.plot([r["magnet_area_mm2"] for r in front], [r["T_Nm"] for r in front], "k-", lw=1.2, label="파레토 전선(FEA 값)")
        ax.plot(base["magnet_area_mm2"], base["T_Nm"], "r*", ms=14, label="기준 설계")
        ax.set_xlabel("자석 단면적 [mm²/극]")
        ax.set_ylabel("최대 평균 토크 [N·m] (330 A, 4300 rpm)")
        ax.set_title("자석 설계 최적화: FEA로 평가한 설계")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)
        fig.tight_layout()
        out = ROOT / "docs" / "figures" / "pareto_example_motor.png"
        fig.savefig(out, dpi=150)
        print("->", out)
    except ImportError:
        pass


if __name__ == "__main__":
    main()
