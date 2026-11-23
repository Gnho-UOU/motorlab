"""M5: Prius 형상에 소결 NdFeB 등급(N45SH, N38UH)을 넣었을 때의 감자 여유와, 1단계 등가회로 어림의 정확도.

입력: data/fea/prius2004_demag_check.csv (femm/demag_check.py, xfemm 전체 모터, 자석 안 74점에서 읽은 자화 방향 B)
      engine/magnet.py (제조사 감자 곡선: Br(T), μr(T), Hk(T))
출력(화면): 1) FEA 감자 여유 표  2) 1단계 어림(H = H0 + κ·(−id), κ는 FEA 한 점에서)과 FEA의 자석 자계 비교, 기각한 ψd/ψm 가정
주의: 이 Prius 형상 자석에 이 등급을 넣은 가정 계산이다(실제 Prius 자석 등급은 알려져 있지 않다). 모델 자석은 선형이라 무릎점 이후는 모사하지 않는다.
실행: python notebooks/12_prius_magnet_check.py
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.magnet import MU0, demag_coupling, field_after_armature, load_grade  # noqa: E402

rows = list(csv.DictReader(open(ROOT / "data" / "fea" / "prius2004_demag_check.csv")))
for r in rows:
    for k in r:
        if k not in ("grade", "state"):
            r[k] = float(r[k])
by = {(r["grade"], r["T_C"], r["state"]): r for r in rows}

print("## 1) FEA 감자 여유 = 1 − H_demag/Hk (자석 안 74점 중 최악 점, 회전자 0°)")
print("| 등급 | T [°C] | 상태 | id, iq [A] | 토크 [N·m] | H_demag 최대 [kA/m] | Hk [kA/m] | 여유 | 판정 |")
print("|---|---|---|---|---|---|---|---|---|")
for r in rows:
    g = load_grade(r["grade"])
    hk = g.hk(r["T_C"])
    m = g.demag_margin(r["H_demag_max_kApm"], r["T_C"])
    verdict = "안전" if m > 0.2 else ("주의" if m > 0 else "비가역 감자")
    print(f"| {r['grade']} | {r['T_C']:.0f} | {r['state']} | {r['id_A']:.0f}, {r['iq_A']:.0f} | {r['torque_Nm']:.0f} | "
          f"{r['H_demag_max_kApm']:.0f} | {hk:.0f} | {m:+.2f} | {verdict} |")

print("\n## 2) 1단계 어림 대 FEA (자석 평균 자계): H = H0 + κ·(−id)")
print("κ는 N45SH 20 °C의 순수 d축(−250 A) 한 점에서만 구하고, 나머지 모든 점을 그 κ로 예측한다(소재·온도·iq가 섞인 점은 검증용).")
n0 = by[("N45SH", 20.0, "noload")]
kappa = demag_coupling(n0["H_demag_mean_kApm"], by[("N45SH", 20.0, "d_axis_250")]["H_demag_mean_kApm"], -250.0)
print(f"κ = {kappa:.3f} kA/m per A")
print("| 등급 | T [°C] | 상태 | id [A] | 어림 H [kA/m] | FEA H [kA/m] | 오차 |")
print("|---|---|---|---|---|---|---|")
for r in rows:
    if r["state"] == "noload":
        continue
    H0 = by[(r["grade"], r["T_C"], "noload")]["H_demag_mean_kApm"]
    est = field_after_armature(H0, kappa, r["id_A"])        # H0는 그 등급·온도의 FEA 무부하 평균 값(어림에는 무부하 FEA 한 점이 필요하다)
    print(f"| {r['grade']} | {r['T_C']:.0f} | {r['state']} | {r['id_A']:.0f} | {est:.0f} | {r['H_demag_mean_kApm']:.0f} | {est / r['H_demag_mean_kApm'] - 1:+.1%} |")

print("\n(기각된 가정) 자석 자속이 d축 쇄교자속 ψd/ψm에 비례한다고 놓으면 같은 점들에서 평균 자계를 +120~+190% 과대 예측한다.")
print("IPM의 d축 전기자 자속은 대부분 자석이 아니라 회전자 철심을 지나기 때문이다.")
for r in rows:
    if r["state"] != "mtpa250" or r["grade"] != "N45SH" or r["T_C"] != 20.0:
        continue
    n = by[(r["grade"], r["T_C"], "noload")]
    ratio = r["psi_d_Wb"] / n["psi_d_Wb"]
    wrong = n["H_demag_mean_kApm"] + n["Bn_mean_T"] * (1 - ratio) / (load_grade("N45SH").mu_r(20.0) * MU0 * 1e3)
    print(f"예) N45SH 20 °C MTPA 250 A: ψd/ψm = {ratio:.2f} → 기각된 식 {wrong:.0f} kA/m, FEA {r['H_demag_mean_kApm']:.0f} kA/m")
