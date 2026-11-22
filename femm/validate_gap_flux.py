"""무부하 공극 자속밀도 대조: FEA 대 ORNL/TM-2004/137 그림 13 (data/benchmarks/prius2004_gap_flux_density.csv).

FEA로 무부하(전류 0) 공극 중앙 반지름의 법선 자속밀도 B_n(θ)를 0.75° 간격으로 읽는다. 측정은 슬롯 번호 1~13(7.5° 간격)의 13점이고
회전자 위치·측정 반지름이 보고서에 없어, 회전자 대 측정 시작점의 각도 차이 δ 하나만 자유롭게 두고 맞춘다.
  - 크기를 고정(scale = 1)하고 δ만 맞추면 'FEA가 측정과 같은 자석 세기를 가정했는가'를 본다.
  - 크기도 자유롭게 두면 파형 모양(극 폭·평탄도)이 맞는지, 크기가 몇 배 어긋나는지를 분리해 본다.
실행: FEMMCLI=<femmcli> PRIUS_GEOMETRY=<형상.json> [PRIUS_BR_T=<Br>] python femm/validate_gap_flux.py [출력.csv]
"""
import cmath
import os
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

sys.path.insert(0, str(Path(__file__).parent))
import prius_full as pf  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MEAS = ROOT / "data" / "benchmarks" / "prius2004_gap_flux_density.csv"
BR = float(os.environ["PRIUS_BR_T"]) if os.environ.get("PRIUS_BR_T") else None


def fea_profile() -> tuple[np.ndarray, np.ndarray, float]:
    g = pf.load_geometry()
    rm = 0.5 * (g["stator"]["Rint_m"] + g["rotor"]["Rext_m"])        # 공극 중앙 반지름
    th = np.radians(np.arange(0.0, 90.0 + 1e-9, 0.75))
    r = pf.solve_one((0, 0, 0), 0.0, probes=[rm * cmath.exp(1j * t) for t in th], br_T=BR)
    B = r["B_xy_T"]
    return np.degrees(th), B[:, 0] * np.cos(th) + B[:, 1] * np.sin(th), float(rm)


def fit(theta_deg, Bn, meas_T, free_scale: bool):
    """측정 k번째 점 = s · B_n(7.5°·k + δ). B_n은 45°마다 부호가 바뀌는 반대칭 함수라 90°로 접는다."""
    k = np.arange(len(meas_T))
    fold = lambda t: np.interp(np.asarray(t) % 90.0, theta_deg, Bn)

    def resid(p, sign):
        return (p[1] if free_scale else sign) * fold(7.5 * k + p[0]) - meas_T

    best = None
    for d0 in np.arange(-5, 5.01, 0.25):
        for sign in (1.0, -1.0):          # 측정 파형의 부호(극성)는 회전자 위치 기준에 따라 뒤집힐 수 있다
            r = least_squares(resid, [d0, sign], args=(sign,))
            if best is None or r.cost < best[0].cost:
                best = (r, sign)
    r, sign = best
    return r.x[0], abs(r.x[1]) if free_scale else 1.0, float(np.sqrt((resid(r.x, sign) ** 2).mean()))


def main(out: Path | None) -> None:
    lines = [l for l in MEAS.read_text().splitlines() if l and not l.startswith("#")][1:]
    meas = np.array([float(l.split(",")[1]) for l in lines]) / 1e4              # G -> T
    theta, Bn, rm = fea_profile()
    d1, s1, rms1 = fit(theta, Bn, meas, free_scale=False)
    d2, s2, rms2 = fit(theta, Bn, meas, free_scale=True)
    print(f"공극 중앙 반지름 {rm * 1e3:.3f} mm, FEA 최대 |B_n| = {np.abs(Bn).max():.3f} T (슬롯 맥동 포함), 측정 최대 {np.abs(meas).max():.3f} T")
    print(f"크기 고정(1.00): δ = {d1:+.2f}°, RMS = {rms1:.3f} T")
    print(f"크기 자유  : δ = {d2:+.2f}°, 측정/FEA 크기 = {s2:.3f}, RMS = {rms2:.3f} T (최대값의 {rms2 / np.abs(meas).max() * 100:.1f}%)")
    if out:
        k = np.arange(len(meas))
        fea_at = np.interp((7.5 * k + d2) % 90.0, theta, Bn) * (1 if np.dot(np.interp((7.5 * k + d2) % 90.0, theta, Bn), meas) > 0 else -1)
        out.write_text("# 출처: femm/validate_gap_flux.py (FEA 대 ORNL/TM-2004/137 그림 13). 단위 T. FEA 열은 크기를 맞추기 전 값, 부호만 측정과 맞춤.\n"
                       f"# 맞춤: δ = {d2:+.2f}°, 측정/FEA 크기 = {s2:.3f}, RMS = {rms2:.3f} T\n"
                       "slot,meas_T,fea_T\n" + "\n".join(f"{i + 1},{m:.4f},{f:.4f}" for i, (m, f) in enumerate(zip(meas, fea_at))) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
