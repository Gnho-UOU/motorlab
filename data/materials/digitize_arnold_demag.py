"""Arnold Magnetic Technologies 소결 NdFeB 데이터시트의 감자 곡선(J-H)을 벡터 경로에서 읽어 CSV로 만든다.

왜 이 방법인가: 데이터시트 곡선은 래스터 그림이 아니라 PDF 벡터 경로(get_drawings)이다. 눈금 격자선 좌표로 축을 보정하면
눈으로 읽는 것보다 정확하고 재현된다. 래스터 그림용 digitize_tm137.py(ORNL 보고서)와는 다른 문서에 쓰는 별도 스크립트다.

입력(PDF는 저장소에 두지 않는다, 제조사 공개 자료):
  N45SH: https://www.arnoldmagnetics.com/wp-content/uploads/2017/11/N45SH-151021.pdf   (Rev. 210607, 1쪽)
  N38UH: https://www.arnoldmagnetics.com/wp-content/uploads/2019/06/Arnold-Neo-Catalog.pdf   (Rev. 210607, 41쪽 = 인덱스 40)
실행: python data/materials/digitize_arnold_demag.py N45SH.pdf 0 N45SH  Neo_catalog.pdf 40 N38UH  > magnet_demag_curves.csv (헤더 주석은 손으로 붙인다)

축 보정(두 PDF 같은 서식): 가로 격자선 y=578.47 pt가 B=1 kG, 맨 아래 y=595.35 pt가 B=0, 간격 16.882 pt/kG.
세로 H=0은 x=516.775 pt이고 14.5459 pt/kOe(격자선 한 칸 = 2 kOe). 1 kOe = 79.5775 kA/m, 1 kG = 0.1 T.
자체 점검(스크립트가 검사): 20 °C 곡선의 H=0 값이 표의 Br(N45SH 1.350 T, N38UH 1.260 T)과 같아야 하고,
20 °C J 곡선이 0을 지나는 H가 표의 HcJ(N45SH 1592, N38UH 1990 kA/m)와 같아야 한다.
출력 열: grade, T_C, H_kApm (감자 방향 자계 크기), J_T (자기분극). 자속밀도는 B = J − μ0·H (H는 감자 방향 크기)로 계산한다.
"""
from __future__ import annotations

import sys

import fitz  # PyMuPDF (이 스크립트에서만 쓴다. 엔진 의존성이 아니다)

X0, KX = 516.775, 14.5459      # H=0 위치 [pt], [pt/kOe]
Y0, KY = 595.3518, 16.8820     # B=0 위치 [pt], [pt/kG]
KOE_TO_KAPM = 79.5775
TEMPS_C = [-40, 20, 60, 80, 100, 120, 150, 180]   # 곡선 이름표(그림에 적힌 온도)와 Br 내림차순이 같다
CHECK = {"N45SH": (1.350, 1592.0), "N38UH": (1.260, 1990.0)}   # (Br [T], HcJ [kA/m]) 표 값


def to_physical(p):
    return ((X0 - p.x) / KX * KOE_TO_KAPM, (Y0 - p.y) / KY * 0.1)


def j_curves(path: str, page: int):
    """J-H 곡선 8개를 온도 순서대로 돌려준다. 같은 온도의 B 곡선(J−μ0H)은 건너뛴다."""
    pg = fitz.open(path)[page]
    found = []
    for d in pg.get_drawings():
        if len(d["items"]) < 60 or d.get("color") not in ((0.0, 0.0, 0.0), (0.0, 0.0, 1.0)):
            continue
        pts = []
        for it in d["items"]:
            if it[0] == "l":
                if not pts:
                    pts.append(to_physical(it[1]))
                pts.append(to_physical(it[2]))
            elif it[0] == "c":
                if not pts:
                    pts.append(to_physical(it[1]))
                pts.append(to_physical(it[4]))
        if pts[0][1] > 1.0 and abs(pts[0][0]) < 1.0:       # 시작이 (H≈0, B=Br)인 곡선만
            found.append(pts)
    # 같은 온도의 곡선 두 개 중 끝점 B가 0에 가까운 쪽이 J 곡선이다 (B 곡선은 −μ0·HcJ까지 내려간다)
    j = [c for c in found if c[-1][1] > -0.2]
    j.sort(key=lambda c: -c[0][1])                           # Br 큰 순서 = 온도 낮은 순서
    assert len(j) == 8, f"J 곡선 {len(j)}개 (8개여야 한다)"
    return j


def clip_at_zero(pts):
    """J가 0을 지나는 곳(= HcJ)에서 곡선을 자른다. 선형 보간."""
    out = []
    for a, b in zip(pts, pts[1:]):
        out.append(a)
        if a[1] > 0 >= b[1]:
            f = a[1] / (a[1] - b[1])
            out.append((a[0] + f * (b[0] - a[0]), 0.0))
            return out
    return out + [pts[-1]]


def main(argv):
    print("grade,T_C,H_kApm,J_T")
    for path, page, grade in zip(argv[0::3], argv[1::3], argv[2::3]):
        curves = j_curves(path, int(page))
        br20, hcj20 = CHECK[grade]
        c20 = clip_at_zero(curves[1])
        assert abs(curves[1][0][1] - br20) < 0.003, f"{grade} 20 °C Br {curves[1][0][1]:.4f} != {br20}"
        assert abs(c20[-1][0] - hcj20) < 8.0, f"{grade} 20 °C HcJ {c20[-1][0]:.1f} != {hcj20}"
        for T, c in zip(TEMPS_C, curves):
            for H, J in clip_at_zero(c):
                print(f"{grade},{T},{max(H, 0.0):.2f},{J:.5f}")


if __name__ == "__main__":
    main(sys.argv[1:])
