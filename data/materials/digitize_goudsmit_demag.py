"""Goudsmit Magnetics 페라이트 F33 데이터시트(등급표 PDF 6쪽)의 감자 곡선(J-H)을 벡터 경로에서 읽어 CSV로 만든다.

입력(PDF는 저장소에 두지 않는다): https://www.goudsmitmagnetics.com/uploads/pdf/Ferrite_grades_available_at_Goudsmit_20250822_4120.pdf (6쪽 = 인덱스 5)
실행: python data/materials/digitize_goudsmit_demag.py Ferrite_grades.pdf  > 본문 (magnet_demag_curves.csv의 F33 행)

주의: 시트가 "곡선은 현재 Goudsmit 등급 체계의 데이터에서 얻은 추정치다"라고 밝힌다(실측이 아님). 20 °C, −40 °C, 225 °C 세 곡선.
곡선 색과 온도: 빨강 225 °C, 파랑 −40 °C, 초록 20 °C. 범례 글자는 그림이라 읽을 수 없어서 물리량으로 정했다
  (225 °C는 HcJ가 가장 크고 Br이 가장 작다: 시트의 β(HcJ) +0.40 %/°C, α(Br) −0.18 %/°C로 계산한 값과 맞는다. 스크립트가 검사한다).
축 보정: 세로 격자선으로 H(0 = x 485.97 pt, 20 kA/m 간격 15.86 pt), 가로 격자선으로 J(0 = y 410.39 pt, 0.01 T 간격 4.669 pt).
자체 점검: 20 °C J 곡선의 H=0 값이 표의 Br 0.39 T, 영점이 HcJ 243 kA/m와 같아야 하고 그에 맞는 B 곡선의 영점이 HcB 239 kA/m이다.
출력: grade, T_C, H_kApm(감자 방향 자계 크기), J_T. 점선(J)만 읽는다. B = J − μ0·H.
"""
from __future__ import annotations

import sys

import fitz  # PyMuPDF (이 스크립트에서만 쓴다)

X0, KX = 485.97, (485.97 - 89.52) / 500.0       # H=0 위치 [pt], [pt per kA/m]
Y0, KY = 410.39, (410.39 - 176.92) / 0.5        # J=0 위치 [pt], [pt per T]
COLOR_T = {(1.0, 0.0, 0.0): 225, (0.0, 0.439, 0.753): -40, (0.0, 0.69, 0.314): 20}
GRADE, TABLE = "F33", {"Br": 0.39, "HcJ": 243.0, "HcB": 239.0}


def bezier(p0, p1, p2, p3, n=24):
    out = []
    for i in range(1, n + 1):
        t = i / n
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
        out.append((a * p0.x + b * p1.x + c * p2.x + d * p3.x, a * p0.y + b * p1.y + c * p2.y + d * p3.y))
    return out


def curves(path: str, page: int = 5):
    pg = fitz.open(path)[page]
    res = {}
    for d in pg.get_drawings():
        if d.get("width") != 1.5:
            continue
        key = tuple(round(c, 3) for c in d["color"])
        T = next((v for k, v in COLOR_T.items() if all(abs(a - b) < 0.002 for a, b in zip(k, key))), None)
        if T is None:
            continue
        pts = []
        for it in d["items"]:
            if it[0] == "l":
                if not pts:
                    pts.append((it[1].x, it[1].y))
                pts.append((it[2].x, it[2].y))
            elif it[0] == "c":
                if not pts:
                    pts.append((it[1].x, it[1].y))
                pts += bezier(it[1], it[2], it[3], it[4])
        phys = [((X0 - x) / KX, (Y0 - y) / KY) for x, y in pts]
        res[(T, "J" if "3 3" in str(d["dashes"]) else "B")] = phys
    return res


def main(path: str) -> None:
    c = curves(path)
    j20, b20 = c[(20, "J")], c[(20, "B")]
    assert abs(j20[0][1] - TABLE["Br"]) < 0.003, f"Br {j20[0][1]}"
    assert abs(j20[-1][0] - TABLE["HcJ"]) < 1.5, f"HcJ {j20[-1][0]}"
    assert max(h for h, _ in b20) >= TABLE["HcB"] - 1.5, "HcB"
    # 온도 순서 점검: Br은 −40 > 20 > 225, HcJ는 −40 < 20 < 225
    brs = {T: c[(T, "J")][0][1] for T in (-40, 20, 225)}
    hcjs = {T: c[(T, "J")][-1][0] for T in (-40, 20, 225)}
    assert brs[-40] > brs[20] > brs[225] and hcjs[-40] < hcjs[20] < hcjs[225], (brs, hcjs)
    assert abs(hcjs[225] / hcjs[20] - (1 + 0.0040 * 205)) < 0.03 and abs(brs[225] / brs[20] - (1 - 0.0018 * 205)) < 0.03
    print("grade,T_C,H_kApm,J_T")
    for T in (-40, 20, 225):
        for H, J in c[(T, "J")]:
            print(f"{GRADE},{T},{max(H, 0.0):.2f},{max(J, 0.0):.5f}")


if __name__ == "__main__":
    main(sys.argv[1])
