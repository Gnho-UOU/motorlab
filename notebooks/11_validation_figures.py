"""검증 그래프 한 장 (컨택용 2쪽 요약과 README에 쓴다): docs/figures/validation_summary.png

(a) 잠금 회전자 토크-각도: FEA 대 ORNL 측정 (250 A, 150 A)
(b) 무부하 공극 자속밀도: FEA 대 ORNL 측정 (Br 교정에 쓴 세 측정 중 하나)
(c) 모터 효율: 엔진(물리 모델) 대 ORNL 측정 (대각선이 일치)
(d) 필요 전류 비(엔진/측정)의 속도 의존: 저속은 맞고 고속은 미해결
입력은 모두 data/에 있는 파일이다. 실행: python notebooks/11_validation_figures.py
"""
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from scipy.interpolate import CubicSpline  # noqa: E402

plt.rcParams["font.family"] = ["AppleGothic", "Malgun Gothic", "NanumGothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def csv(path):
    lines = [l for l in Path(path).read_text().splitlines() if l.strip() and not l.startswith("#")]
    h = lines[0].split(",")
    A = np.array([[float(x) if x else np.nan for x in l.split(",")] for l in lines[1:]])
    return {k: A[:, i] for i, k in enumerate(h)}


def main() -> None:
    fig, ax = plt.subplots(2, 2, figsize=(10.5, 7.6))
    # (a) 잠금 토크
    fea = np.array([[float(x) for x in l.split(",")] for l in (ROOT / "data/fea/prius2004_full_locked_torque_teardown.csv").read_text().splitlines()[1:]])
    meas = csv(ROOT / "data/benchmarks/prius2004_locked_torque.csv")
    ang = meas["shaft_angle_deg"]
    curves = {I: CubicSpline(fea[fea[:, 0] == I][:, 1], fea[fea[:, 0] == I][:, 2]) for I in (75, 150, 250)}
    c = min((np.sqrt(np.mean((curves[250](c - ang) - meas["torque_250A_Nm"]) ** 2)), c) for c in np.arange(100, 200, 0.05) if (c - ang).min() >= 0 and (c - ang).max() <= 56.25)[1]
    a = ax[0, 0]
    for I, col in ((250, "#d98d55"), (150, "#2a9fc9")):
        a.plot(4 * (ang - ang[0]), meas[f"torque_{I}A_Nm"], "o", ms=4, color=col, label=f"ORNL 측정 {I} A")
        a.plot(4 * (ang - ang[0]), curves[I](c - ang), "-", color=col, lw=1.6, label=f"FEA {I} A")
    a.set_xlabel("회전자 위치 [전기각 °] (영점 1개를 맞춤)"); a.set_ylabel("토크 [N·m]"); grid = np.linspace(0, 56.25, 2000)
    r250 = curves[250](grid).max() / 337; r150 = curves[150](grid).max() / 221   # 최대 토크는 TM-423 그림 3.10 값 (notebooks/06과 같은 기준)
    a.set_title(f"(a) 잠금 회전자 토크: 최대값 FEA/측정 = {r250:.2f} (250 A), {r150:.2f} (150 A)", fontsize=10); a.legend(fontsize=8); a.grid(alpha=.25)
    # (b) 공극 자속밀도
    lines = [l for l in (ROOT / "data/fea/prius2004_gap_flux_comparison_teardown_Br106.csv").read_text().splitlines() if l and not l.startswith("#")][1:]
    g = np.array([[float(x) for x in l.split(",")] for l in lines])
    a = ax[0, 1]
    a.plot(g[:, 0], g[:, 1], "o-", color="#d98d55", label="ORNL 측정 (그림 13 디지털화)")
    a.plot(g[:, 0], g[:, 2], "s--", color="#2a9fc9", label="FEA")
    a.set_xlabel("슬롯 번호 (7.5° 간격)"); a.set_ylabel("공극 자속밀도 [T]"); a.set_title("(b) 무부하 공극 자속밀도 (Br 교정에 쓴 측정과의 일치)", fontsize=10); a.legend(fontsize=8); a.grid(alpha=.25)
    # (c) 효율
    v = csv(ROOT / "data/fea/prius2004_efficiency_variants.csv")
    a = ax[1, 0]
    sc = a.scatter(v["eta_meas"] * 100, v["eta_v1"] * 100, c=v["speed_rpm"], s=11, cmap="viridis")
    a.plot([60, 100], [60, 100], "k--", lw=1)
    a.set_xlim(60, 100); a.set_ylim(60, 100); a.set_xlabel("ORNL 측정 모터 효율 [%]"); a.set_ylabel("엔진 모터 효율, 물리 모델 [%]")
    core = (v["speed_rpm"] >= 1000) & (v["speed_rpm"] <= 4000) & (v["torque_Nm"] >= 30) & (v["torque_Nm"] <= 200)
    d = (v["eta_v1"] - v["eta_meas"]) * 100
    a.set_title(f"(c) 효율: 주요 영역 평균 {d[core].mean():+.1f}%p, 4000 rpm 이상 {d[v['speed_rpm'] >= 4000].mean():+.1f}%p (엔진이 높음)", fontsize=10)
    fig.colorbar(sc, ax=a, label="속도 [rpm]"); a.grid(alpha=.25)
    # (d) 필요 전류 비
    perf = csv(ROOT / "data/benchmarks/prius2004_perf_map.csv")
    key = {(round(s, 1), round(t, 1)): i for i, (s, t) in enumerate(zip(perf["speed_rpm"], perf["torque_Nm"]))}
    idx = np.array([key[(round(s, 1), round(t, 1))] for s, t in zip(v["speed_rpm"], v["torque_Nm"])])
    ratio = np.hypot(v["id_A"], v["iq_A"]) / (perf["Iac_rms_A"][idx] * math.sqrt(2))
    a = ax[1, 1]
    a.scatter(v["speed_rpm"], ratio, s=9, color="#d98d55", alpha=.7)
    a.axhline(1, color="k", ls="--", lw=1); a.set_ylim(0.5, 1.3); a.set_xlabel("모터 속도 [rpm]"); a.set_ylabel("필요 전류 엔진/측정")
    a.set_title(f"(d) 필요 전류: 저속 중앙값 {np.median(ratio[v['speed_rpm'] < 2000]):.2f}, 4000 rpm 이상 {np.median(ratio[v['speed_rpm'] >= 4000]):.2f} (미해결)", fontsize=10); a.grid(alpha=.25)
    fig.suptitle("Motor Lab 검증: 2004 Toyota Prius 구동모터, ORNL 실측과 비교 (교정값은 자석 Br 1.06 T 하나)", fontsize=10.5)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    out = ROOT / "docs" / "figures"; out.mkdir(exist_ok=True)
    fig.savefig(out / "validation_summary.png", dpi=170)
    print("->", out / "validation_summary.png")


if __name__ == "__main__":
    main()
