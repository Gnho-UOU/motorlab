"""ORNL/TM-2004/137 그림 13(공극 자속밀도)·그림 14(자석 B-H)를 PDF에서 숫자로 읽는다.

입력: data/benchmarks/raw/ORNL_TM-2004-137_design_assessment.pdf (저장소에 없음, prius2004_ornl.md 1절의 URL·해시)
의존성: pymupdf, numpy (엔진 의존성이 아니라 이 일회성 도구에만 필요)
실행: python data/benchmarks/digitize_tm137.py
출력: 표준 출력. 결과는 prius2004_gap_flux_density.csv, prius2004_magnet_bh.md에 옮겨 적었다.
축 보정에 쓴 픽셀 좌표(130 dpi 기준)는 그림의 격자선을 직접 찾아 확인한 값이다.
"""
from collections import deque
from pathlib import Path

import fitz
import numpy as np

PDF = Path(__file__).parent / "raw" / "ORNL_TM-2004-137_design_assessment.pdf"
DPI, REF = 300, 130
S = DPI / REF


def render(page_1based: int) -> np.ndarray:
    pix = fitz.open(PDF)[page_1based - 1].get_pixmap(dpi=DPI)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3].astype(int)


def fig13() -> None:
    """magenta 표시점(2004년 곡선)의 중심. 세로축: 8000 G = 310.5 px, 0 G = 458.9 px (130 dpi 좌표)."""
    a = render(12)
    mag = (a[:, :, 0] > 200) & (a[:, :, 1] < 80) & (a[:, :, 2] > 200)
    box = np.zeros_like(mag)
    y0, y1, x0, x1 = int(290 * S), int(630 * S), int(335 * S), int(645 * S)
    box[y0:y1, x0:x1] = mag[y0:y1, x0:x1]
    k = 7                                                   # 7x7 침식: 선은 지우고 정사각형 표시점만 남긴다
    er = np.ones(box.shape, np.uint8)
    for dy in range(-(k // 2), k // 2 + 1):
        for dx in range(-(k // 2), k // 2 + 1):
            er &= np.roll(np.roll(box.astype(np.uint8), dy, 0), dx, 1)
    ys, xs = np.nonzero(er)
    clusters: list[list[tuple[float, float]]] = []
    for x, y in sorted(zip(xs / S, ys / S)):
        if clusters and abs(clusters[-1][0][0] - x) < 6:
            clusters[-1].append((x, y))
        else:
            clusters.append([(x, y)])
    for i, c in enumerate(clusters, 1):
        y = np.mean([p[1] for p in c])
        print(f"slot {i:2d}: B = {(458.9 - y) / (458.9 - 310.5) * 8000:7.0f} G")


def fig14() -> None:
    """Toyota/Prius 직선. 가로축: H = 0 -> 850.2 px, 46.2 px/kOe. 세로축: B = 0 -> 1179.5 px, 22.7 px/kG."""
    a = render(12)
    dark = a.sum(axis=2) < 250
    y0, x0 = int(838 * S), int(290 * S)
    ys, xs = np.nonzero(dark[y0:int(1190 * S), x0:int(860 * S)])
    x, y = (xs + x0) / S, (ys + y0) / S
    H, B = (x - 850.2) / 46.2, (1179.5 - y) / 22.7
    bad = np.zeros(len(x), bool)
    for yy in (838.9, 952.0, 1066.0, 1179.5):
        bad |= np.abs(y - yy) < 1.5
    for xx in (296.0, 388.3, 480.6, 572.7, 664.7, 757.0, 850.2):
        bad |= np.abs(x - xx) < 1.5
    H, B = H[~bad], B[~bad]
    best = max(((np.abs(B - (br + mu * H)) < 0.12).sum(), mu, br)
               for mu in np.arange(0.9, 1.5, 0.005) for br in np.arange(11.0, 13.5, 0.02))
    sel = np.abs(B - (best[2] + best[1] * H)) < 0.12
    c = np.linalg.lstsq(np.c_[np.ones(sel.sum()), H[sel]], B[sel], rcond=None)[0]
    print(f"Br = {c[0] / 10:.3f} T, mu_r = {c[1]:.3f}, Hcb = {-c[0] / c[1]:.2f} kOe ({sel.sum()} 픽셀)")


if __name__ == "__main__":
    fig13()
    fig14()
