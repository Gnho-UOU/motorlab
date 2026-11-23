"""자속 분포(벡터 퍼텐셜 A와 자속밀도 |B|)를 FEA로 풀어 화면용 JSON으로 내보낸다.

실행 상태(전류, 회전자 위치)마다 xfemm으로 전체 모터를 풀고, 고정자 바깥 반지름을 덮는 정사각 격자에서 A [Wb/m]와 B [T]를 읽는다.
자속선은 A의 등고선이다(2D 정자장). 이 파일은 화면의 "자속 분포" 층에 쓰인다: 시각화이고 계산이 아니라 FEA 결과 그대로다.
회전자 위치는 0°(d축이 극 중심 22.5°). 전류는 상 첨두 (iA, iB, iC) = inverse_park(id, iq, θe), θe = 150° + 4·θr.

실행: FEMMCLI=<femmcli> PRIUS_GEOMETRY=<형상.json> PRIUS_BR_T=1.06 python femm/export_flux_field.py [상태 이름 ...]
상태: noload, mtpa150(MTPA, |Is| 150 A), mtpa250(MTPA, 250 A), fw(id −150 A, iq 100 A 약계자)
출력: data/fea/flux_fields/<상태>.json (격자 N×N, 행 우선, 정사각 [-R, R]², 반지름 밖·축 안쪽은 null)
"""
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import prius_full as pf  # noqa: E402
import prius_run as pr  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "fea" / "flux_fields"
N = 161
BR = float(os.environ["PRIUS_BR_T"]) if os.environ.get("PRIUS_BR_T") else None


def mtpa_state(I: float):
    sys.path.insert(0, str(ROOT))
    from engine.model import FluxMapModel
    from engine.operating import mtpa_point
    m = FluxMapModel.from_csv(ROOT / "data" / "flux_maps" / "prius2004_fullmodel_teardown_25A.csv", p=4, Rs=0.0)
    d, q = mtpa_point(m, I)
    return float(d), float(q)


def states():
    return {
        "noload": (0.0, 0.0, "무부하(전류 0)"),
        "mtpa150": (*mtpa_state(150.0), "MTPA, 전류 150 A"),
        "mtpa250": (*mtpa_state(250.0), "MTPA, 전류 250 A (최대 토크)"),
        "fw": (-150.0, 100.0, "약계자 (id −150 A, iq 100 A)"),
    }


def export(name: str, id_: float, iq: float, label: str) -> None:
    g = pf.load_geometry()
    R = g["stator"]["Rext_m"]
    r_in = g["rotor"]["Rint_m"] + 0.5e-3
    xs = np.linspace(-R, R, N)
    pts, idx = [], []
    for j, y in enumerate(xs):
        for i, x in enumerate(xs):
            r = math.hypot(x, y)
            if r_in <= r <= R - 0.3e-3:
                pts.append(complex(x, y)); idx.append((j, i))
    th = math.radians(pr.THETA0_ELEC_DEG)                   # 회전자 0°
    ia, ib, ic = pr.inverse_park(np.array([id_]), np.array([iq]), np.array([th]))[0]
    r = pf.solve_one((float(ia), float(ib), float(ic)), 0.0, probes=pts, br_T=BR)
    A = np.full((N, N), np.nan); Bm = np.full((N, N), np.nan)
    bmag = np.hypot(r["B_xy_T"][:, 0], r["B_xy_T"][:, 1])
    for k, (j, i) in enumerate(idx):
        A[j, i], Bm[j, i] = r["A_Wb_per_m"][k], bmag[k]
    clean = lambda M, nd: [[None if not np.isfinite(v) else round(float(v), nd) for v in row] for row in M]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps({
        "state": name, "label": label, "id_A": id_, "iq_A": iq, "rotor_deg": 0.0, "grid_n": N, "half_size_mm": R * 1000,
        "torque_Nm": r["torque_Nm"], "A_Wb_per_m": clean(A, 6), "B_T": clean(Bm, 3),
        "source": "femm/export_flux_field.py: xfemm 2D 정자장, 전체 모터, 형상 " + os.environ.get("PRIUS_GEOMETRY", "기본") + f", Br {BR if BR else '파일 값'} T",
        "note": "자속선은 A의 등고선. 회전자 위치 0°의 한 순간 값이고 정상상태에서는 자속 분포가 회전자와 함께 돈다고 보고 화면에서 회전자 좌표계로 돌린다(슬롯 맥동은 무시).",
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{name}: {len(pts)}점, 토크 {r['torque_Nm']:.1f} N·m, A {np.nanmin(A):.4f}~{np.nanmax(A):.4f}, |B| 최대 {np.nanmax(Bm):.2f} T", flush=True)


if __name__ == "__main__":
    st = states()
    for n in (sys.argv[1:] or list(st)):
        export(n, *st[n])
