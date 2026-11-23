"""G1 고속 불일치의 역추론: 2D FEA에 없는 직렬 누설 인덕턴스 ΔL(엔드턴 누설 등)이 있다면 얼마여야 하는가, 그리고 한 값으로 일관되게 설명되는가.

가설: 측정 모터는 고속에서 육각파 전압 한계(Vmax = (2/π)·Vdc)에 걸려 있다(TM-423 표 B-1 Vac_rms가 239~241 V로 포화, docs/FEA_OPTIONS.md).
엔진/FEA는 측정 전류·토크에서 모델 전압이 한계의 약 0.75배라고 말한다(notebooks/08). 엔드턴 누설은 회전자 자석과 쇄교하지 않아 토크는 바꾸지 않고
전압만 늘린다: ψ' = ψ + ΔL·i (dq 성분별). 행마다 |v(ΔL)| = Vmax가 되는 ΔL을 풀어 분포를 본다.
판정(가설을 지지하려면): (1) 행마다 구한 ΔL이 한 값 근처에 모인다(변동계수 작음), (2) 그 값이 정적 측정 인덕턴스(Ld 1.92 mH, Lq 5 mH)에 비해 작고 엔드턴 누설로 그럴듯한 크기다.
이것은 보정이 아니라 가설 점검이다. 엔진 맵에는 넣지 않는다.
입력: data/benchmarks/prius2004_perf_map.csv, data/flux_maps/prius2004_fullmodel_teardown_25A.csv (notebooks/08과 같은 입력과 같은 행 선택)
실행: python notebooks/18_prius_leakage_inference.py
"""
import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.model import FluxMapModel  # noqa: E402

spec = importlib.util.spec_from_file_location("n08", ROOT / "notebooks" / "08_prius_high_speed_current.py")
n08 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n08)


def main() -> None:
    c = n08.load_csv(ROOT / "data/benchmarks/prius2004_perf_map.csv")
    m = FluxMapModel.from_csv(ROOT / "data/flux_maps/prius2004_fullmodel_teardown_25A.csv", p=4, Rs=0.0)
    out = []
    for i in np.nonzero(c["speed_rpm"] >= 3000)[0]:
        sp = c["speed_rpm"][i]
        w = sp * math.pi / 30
        we = 4 * w
        Is = c["Iac_rms_A"][i] * math.sqrt(2)
        if Is > 250:
            continue
        Tem = c["torque_Nm"][i] + (n08.MECH[0] * w + n08.MECH[1] * w ** 3) / w
        tq = lambda b: float(m.torque(-Is * math.sin(b), Is * math.cos(b))) - Tem
        bs = np.linspace(0, math.pi / 2, 181)
        ts = np.array([tq(b) for b in bs])
        roots = [brentq(tq, bs[k], bs[k + 1]) for k in range(len(bs) - 1) if ts[k] * ts[k + 1] < 0]
        if not roots:
            continue
        b = roots[-1]
        d, q = -Is * math.sin(b), Is * math.cos(b)
        Rs = n08.R20 * (1 + n08.ALPHA * (c["T_stator_C"][i] - 20))
        pd, pq = (float(x) for x in m.flux(d, q))
        Vmax = 2 / math.pi * c["Vdc_V"][i]

        def v(dL):
            return math.hypot(Rs * d - we * (pq + dL * q), Rs * q + we * (pd + dL * d)) - Vmax

        v0 = v(0.0) + Vmax
        if v(0.0) >= 0:
            continue                                     # 이미 한계 이상: 이 가설로는 설명할 부분이 없다
        grid = np.linspace(0, 3e-3, 301)
        vs = np.array([v(x) for x in grid])
        idx = [k for k in range(len(grid) - 1) if vs[k] * vs[k + 1] < 0]
        if not idx:
            out.append((sp, Is, Tem, v0 / Vmax, float("nan")))
            continue
        out.append((sp, Is, Tem, v0 / Vmax, brentq(v, grid[idx[0]], grid[idx[0] + 1])))
    R = np.array(out)
    ok = np.isfinite(R[:, 4])
    dL = R[ok, 4] * 1e3
    print(f"행 {len(R)}개 중 0~3 mH 안에서 ΔL 해가 있는 행 {ok.sum()}개 (해가 없는 행 {len(R) - ok.sum()}개)")
    print(f"ΔL [mH]: 중앙값 {np.median(dL):.2f}, 사분위 {np.percentile(dL, 25):.2f}~{np.percentile(dL, 75):.2f}, 범위 {dL.min():.2f}~{dL.max():.2f}, 변동계수 {dL.std() / dL.mean():.2f}")
    print(f"정적 측정 인덕턴스: Ld 1.92 mH, Lq 5 mH (ORNL TM-423 4.3.1절)")
    for lo, hi in ((3000, 4000), (4000, 5000), (5000, 7000)):
        s = ok & (R[:, 0] >= lo) & (R[:, 0] < hi)
        if s.any():
            print(f"  {lo}~{hi} rpm: 행 {s.sum()}, ΔL 중앙값 {np.median(R[s, 4]) * 1e3:.2f} mH")
    for lo, hi in ((0, 40), (40, 80), (80, 400)):
        s = ok & (R[:, 2] >= lo) & (R[:, 2] < hi)
        if s.any():
            print(f"  토크 {lo}~{hi} N·m: 행 {s.sum()}, ΔL 중앙값 {np.median(R[s, 4]) * 1e3:.2f} mH")


if __name__ == "__main__":
    main()
