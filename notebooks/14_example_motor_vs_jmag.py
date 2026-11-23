"""연구실 예제 IPMSM: xfemm 전체 모터 결과 대 JMAG 결과 (4300 rpm, 상전류 첨두 330 A).

입력: data/fea/example_motor_{noload,loaded,ripple}.csv (femm/example_motor_run.py)
JMAG 수치의 출처: 연구실 강의 자료(JMAG 실습 매뉴얼의 해석 결과 화면, 파일은 저장소에 두지 않았다).
  무부하 역기전력 '277.96(207.76) V, THD 15.10 %', 선간 '521.39(357.47) V, THD 9.63 %', 코깅 1.29 N·m,
  부하 토크 350.64 N·m, 토크 리플 8.22 %, 단자 전압 첨두 385.75 V.
  역기전력의 앞 숫자와 괄호 숫자의 뜻은 자료만으로 확정하지 못했다(후처리 코드는 둘 다 'rms'로 적는다). 이 노트북은 우리 값을 여러 정의로 보인다.
이 비교는 해석기끼리의 비교다(실측이 아니다). 형상은 강의 자료 코드의 수식, 자석은 N45SH 50 °C 공칭, 강판은 JFE 35JN230 대표값 + Prius 곡선 모양.
실행: python notebooks/14_example_motor_vs_jmag.py
"""
import csv
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "fea"
WE = 2 * math.pi * 4300 / 60 * 4          # 전기 각속도 [rad/s]
RS = 0.0330                                # 상저항 [Ω] (강의 자료, 50 °C)


def read(name):
    return list(csv.DictReader(open(OUT / name)))


def noload_report():
    rows = read("example_motor_noload.csv")
    pos = np.array([float(r["rotor_deg"]) for r in rows])
    lam = np.array([[float(r[k]) for k in ("lambda_A_Wb", "lambda_B_Wb", "lambda_C_Wb")] for r in rows])
    torque = np.array([float(r["torque_Nm"]) for r in rows])
    sel = [i for i, p in enumerate(pos) if p < 90 and abs(p / 3.75 - round(p / 3.75)) < 1e-6]
    la, n = lam[sel], len(sel)
    a = np.abs(np.fft.rfft(la[:, 0])) * 2 / n
    k = np.arange(1, 12)
    ek = WE * k * a[1:12]                                       # 기전력 고조파 (미분 = k·ω)
    ll = np.abs(np.fft.rfft(la[:, 0] - la[:, 1])) * 2 / n
    ell = WE * k * ll[1:12]
    cog = torque[pos < 7.5]
    print("## 무부하 (자석 N45SH 50 °C 공칭)")
    print("| 항목 | xfemm | JMAG |")
    print("|---|---|---|")
    print(f"| 상 쇄교자속 기본파 ψm [Wb] | {a[1]:.4f} | - |")
    print(f"| 상 역기전력 기본파 첨두 / 실효 [V] | {WE * a[1]:.1f} / {WE * a[1] / math.sqrt(2):.1f} | 277.96 / 207.76 중 하나씩 |")
    print(f"| 상 역기전력 실효(11차까지 전체) [V] | {math.sqrt(np.sum(ek ** 2) / 2):.1f} | 207.76 (괄호) |")
    print(f"| 상 역기전력 THD [%] | {100 * math.sqrt(np.sum(ek[1:] ** 2)) / ek[0]:.2f} | 15.10 |")
    print(f"| 선간 역기전력 기본파 실효 [V] | {WE * ll[1] / math.sqrt(2):.1f} | 357.47 (괄호) |")
    print(f"| 선간 역기전력 THD [%] | {100 * math.sqrt(np.sum(ell[1:] ** 2)) / ell[0]:.2f} | 9.63 |")
    print(f"| 코깅 토크 p-p [N·m] ({len(cog)}점) | {cog.max() - cog.min():.2f} | 1.29 |")
    print("고조파(상 쇄교자속, k = 3, 5, 7, 9, 11) [mWb]: " + ", ".join(f"{a[j] * 1000:.2f}" for j in (3, 5, 7, 9, 11)))


def loaded_report():
    acc = defaultdict(list)
    for r in read("example_motor_loaded.csv"):
        acc[(r["variant"], float(r["beta_deg"]))].append(r)

    def mean(rs, key):
        return float(np.mean([float(x[key]) for x in rs]))
    print("\n## 부하 (상전류 첨두 330 A, 전류각 β: id = −I·sinβ, iq = I·cosβ)")
    print("| 변형 | β [°] | 토크 자속식 [N·m] | 토크 FEA [N·m] | 단자 전압 기본파 첨두 [V] |")
    print("|---|---|---|---|---|")
    table = {}
    for (v, b), rs in sorted(acc.items()):
        d, q, i_d, i_q = mean(rs, "psi_d_Wb"), mean(rs, "psi_q_Wb"), mean(rs, "id_A"), mean(rs, "iq_A")
        volt = math.hypot(RS * i_d - WE * q, RS * i_q + WE * d)
        table[(v, b)] = (mean(rs, "torque_flux_Nm"), mean(rs, "torque_fea_Nm"), volt)
        print(f"| {v} | {b:.0f} | {table[(v, b)][0]:.1f} | {table[(v, b)][1]:.1f} | {volt:.1f} |")
    t40, t45 = table[("nominal", 40.0)], table[("nominal", 45.0)]
    t41 = tuple(a + (b - a) * 0.2 for a, b in zip(t40, t45))      # β = 41° (JMAG 전류 위상과 같다고 둔 값)
    print(f"\nβ = 41°에서 보간: 토크 {t41[0]:.1f} (자속식) / {t41[1]:.1f} (FEA), 전압 {t41[2]:.1f} V   (JMAG: 350.64 N·m, 385.75 V)")
    print(f"  토크 차이 {100 * (t41[0] / 350.64 - 1):+.1f} % / {100 * (t41[1] / 350.64 - 1):+.1f} %, 전압 차이 {100 * (t41[2] / 385.75 - 1):+.1f} %")
    for v in ("m400", "brmin"):
        a, b = table[(v, 40.0)], table[(v, 45.0)]
        print(f"  변형 {v} β = 41°: 토크 {a[0] + (b[0] - a[0]) * 0.2:.1f} / {a[1] + (b[1] - a[1]) * 0.2:.1f}, 전압 {a[2] + (b[2] - a[2]) * 0.2:.1f} V")


def ripple_report():
    rows = read("example_motor_ripple.csv")
    for key, label in (("torque_flux_Nm", "자속식"), ("torque_fea_Nm", "FEA(Henrotte)")):
        t = np.array([float(r[key]) for r in rows])
        print(f"토크 리플({label}, β = 41°, 15점): 평균 {t.mean():.1f} N·m, p-p {t.max() - t.min():.1f} N·m, 리플 {100 * (t.max() - t.min()) / t.mean():.2f} %   (JMAG 8.22 %)")


if __name__ == "__main__":
    noload_report()
    loaded_report()
    if (OUT / "example_motor_ripple.csv").exists():
        print()
        ripple_report()
