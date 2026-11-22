"""Prius 1극 섹터 모델을 xfemm `femmcli`(또는 FEMM Lua)로 풀고 결과를 파싱한다.

환경변수 FEMMCLI = femmcli 경로 (femm/build_xfemm_macos.sh가 만든 것). 한 번 메시를 만든 뒤 점마다 상전류와 회전자 각도(AGE 안쪽
각도)만 바꿔 푼다. 회로 쇄교자속·토크는 섹터 값이므로 전체 = (8극 / 섹터 극 수)배.

dq 변환은 크기 불변이다: [ψd, ψq] = (2/3)·[[cosθ, cos(θ-120°), cos(θ+120°)], [-sinθ, -sin(θ-120°), -sin(θ+120°)]]·[λA, λB, λC].
θ는 d축의 A상 축에 대한 전기각이다. A상의 자기축은 코일 중심이다: 전절 코일(+변 7.5°, -변 52.5°)의 중심은 30°이고
부호가 반대인 쪽이 양의 축이라 -15°다. 따라서 기준 위치에서 θ0 = 4·(22.5° - (-15°)) = 150° (극쌍 4).
(처음에 벨트 중심 7.5°를 축으로 가정해 60°로 두었다가 무부하 해석과 맞지 않아 바로잡았다.)
"""
from __future__ import annotations

import math
import os
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from prius_sector import build_sector, load_geometry, lua_model

POLE_PAIRS = 4
N_POLES = 8
POLES_IN_SECTOR = 2   # 섹터가 포함하는 극 수 (prius_sector.build_sector 기본값과 같다)
THETA0_ELEC_DEG = 150.0
# xfemm AGE 주의(docs/FEA_OPTIONS.md 3-2절): 안쪽·바깥쪽 각도를 둘 다 0으로 두면 거울 대칭이 요구하는 값(무부하 코깅 0)이
# 나오지 않는다. 바깥쪽에 기준각을 주고 안쪽에 기준각 + θr을 주면 θr = 0에서 정확한 대칭 값(θ = 150.000°)이 나온다.
# 상대 회전 |θr|가 약 10°를 넘으면 위상 오차가 커져(22.5°에서 약 -27°) 믿을 수 없다. 그래서 자속 맵은 θr = 0에서만 만든다.
AGE_BASE_DEG = 22.5


def park(lam_abc: np.ndarray, theta_e: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """크기 불변 Park 변환. lam_abc 모양 (n, 3), theta_e [rad] 모양 (n,)."""
    t = np.asarray(theta_e)[:, None] + np.array([0.0, -2 * math.pi / 3, 2 * math.pi / 3])[None, :]
    d = (2 / 3) * np.sum(np.cos(t) * lam_abc, axis=1)
    q = -(2 / 3) * np.sum(np.sin(t) * lam_abc, axis=1)
    return d, q


def inverse_park(i_d: np.ndarray, i_q: np.ndarray, theta_e: np.ndarray) -> np.ndarray:
    """dq -> abc (크기 불변). 반환 모양 (n, 3)."""
    t = np.asarray(theta_e)[:, None] + np.array([0.0, -2 * math.pi / 3, 2 * math.pi / 3])[None, :]
    return np.asarray(i_d)[:, None] * np.cos(t) - np.asarray(i_q)[:, None] * np.sin(t)


def _driver_lua(points: list[tuple[float, float, float, float]], fem: str) -> str:
    L = ["mi_createmesh()", f"npts = {len(points)}"]
    for k, (a, b, c, th) in enumerate(points, 1):
        L.append(f"pa[{k}] = {a:.12g} pb[{k}] = {b:.12g} pc[{k}] = {c:.12g} pth[{k}] = {th:.12g}")
    L.insert(1, "pa = {} pb = {} pc = {} pth = {}")
    L += ["for i = 1, npts do",
          '  mi_modifycircprop("A", 1, pa[i]) mi_modifycircprop("B", 1, pb[i]) mi_modifycircprop("C", 1, pc[i])',
          f'  mi_modifyboundprop("AGE", 11, {AGE_BASE_DEG})',
          f'  mi_modifyboundprop("AGE", 10, {AGE_BASE_DEG} + pth[i])',
          f'  mi_saveas("{fem}")',
          "  mi_analyze(1)", "  mi_loadsolution()",
          '  tq = mo_gapintegral("AGE", 0)',
          '  ia, va, fa = mo_getcircuitproperties("A")',
          '  ib, vb, fb = mo_getcircuitproperties("B")',
          '  ic, vc, fc = mo_getcircuitproperties("C")',
          '  print(format("PT %d %.12g %.12g %.12g %.12g %d %d", i, tq, fa, fb, fc, mo_numnodes(), mo_numelements()))',
          "  mo_close()", "end"]
    return "\n".join(L) + "\n"


def solve_points(points: list[tuple[float, float, float, float]], mesh: dict | None = None, femmcli: str | None = None,
                 timeout: int = 7200) -> dict[str, np.ndarray]:
    """points: [(iA, iB, iC [A, 첨두], 회전자 각도 θr [기계 도, AGE 안쪽 각도])]. 반환: 전체(8극) 토크·쇄교자속 배열."""
    femmcli = femmcli or os.environ.get("FEMMCLI", "femmcli")
    g = load_geometry()
    script = lua_model(g, build_sector(g, mesh, POLES_IN_SECTOR), "prius.fem") + _driver_lua(points, "prius.fem")
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "run.lua").write_text(script)
        out = subprocess.run([femmcli, "-q", "--lua-script=run.lua"], cwd=d, capture_output=True, text=True, timeout=timeout)
    rows = [l.split() for l in out.stdout.splitlines() if l.startswith("PT ")]
    if len(rows) != len(points):
        raise RuntimeError(f"{len(rows)}/{len(points)}점만 풀렸다\n{out.stdout[-1500:]}\n{out.stderr[-800:]}")
    a = np.array([[float(x) for x in r[1:]] for r in rows])
    k = N_POLES / POLES_IN_SECTOR          # 쇄교자속은 섹터 값이므로 전체 = k배
    # mo_gapintegral(AGE, 0)은 이미 전체 360° 토크다 (섹터 값이 아니다). 자속 기반 토크 1.5p(ψd iq - ψq id)와 0.1% 이내로
    # 일치하는 것으로 확인했다 (무맥동 점, id=0 iq=50). 처음에 k를 곱해 8배가 되었다가 바로잡았다.
    return {"torque_Nm": a[:, 1], "lambda_abc_Wb": a[:, 2:5] * k, "nodes": a[:, 5], "elements": a[:, 6]}
