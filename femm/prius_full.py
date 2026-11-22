"""Prius 전체 모터(360°, 48슬롯, 8극) FEMM 모델: 공극까지 메시를 만들고 AGE·대칭 경계를 쓰지 않는다.

xfemm의 AGE 회전이 큰 각도에서 부정확해서(docs/FEA_OPTIONS.md 3-2절) 만든 대체 경로다. 회전자는 기하학적으로 돌리고(점마다 모델을
새로 만든다) 토크는 회전자 블록(철심·자석·공기 포켓·공극 안쪽 층)에 대한 Henrotte 응력 적분(mo_blockintegral(22))으로 구한다.
쇄교자속은 회로(직렬 상)에서 바로 읽는다(섹터 배율이 필요 없다). 점마다 독립 프로세스라 병렬로 돌린다.

각도 규약: 회전자 각도 θr[기계 °]은 d축(N극 중심)이 22.5°인 기준 위치에서 반시계로 돌린 양이다.
d축의 A상 축에 대한 전기각은 θe = 150° + 4·θr (prius_run.py의 유도와 같다).
"""
from __future__ import annotations

import math
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from prius_sector import (Edge, Label, Sector, _arc_chain, load_geometry, lua_model, rot, rotor_hole_points,
                          stator_slot_points)

THETA0_ELEC_DEG = 150.0
POLES = 8


def cmath_phase(z: complex) -> float:
    return math.atan2(z.imag, z.real)


def build_full(g: dict, mesh: dict | None = None, rotor_deg: float = 0.0) -> Sector:
    m = {"stator": 3.0e-3, "rotor": 2.0e-3, "magnet": 2.0e-3, "slot": 5.0e-3, "gap": 0.4e-3, "arc_deg": 0.5} | (mesh or {})
    st, ro, wd, sl = g["stator"], g["rotor"], g["winding"], g["stator"]["slot_SlotW11"]
    Zs, Zh = st["Zs"], ro["Zh"]
    pitch, pole_pitch = 2 * math.pi / Zs, 2 * math.pi / Zh
    Rint_s, Rext_s, Rint_r, Rext_r = st["Rint_m"], st["Rext_m"], ro["Rint_m"], ro["Rext_m"]
    r0 = math.radians(rotor_deg)
    quarter = [k * math.pi / 2 for k in range(5)]
    sec = Sector(antiperiodic=False, poles=Zh)

    # ---- 고정자: 보어 원(슬롯 입구 포함), 슬롯, 바깥 원 ----
    sp = stator_slot_points(g)
    bore = []
    for k in range(Zs):
        p = (k + 0.5) * pitch
        bore += [p - sp["alpha"], p + sp["alpha"]]
    sec.edges += _arc_chain(Rint_s, bore + [bore[0] + 2 * math.pi], None, m["arc_deg"])
    for k in range(Zs):
        p = (k + 0.5) * pitch
        z = {n: rot(v, p) for n, v in sp.items() if n.startswith("Z")}
        sec.edges += [Edge("seg", z["Z1"], z["Z2"]), Edge("seg", z["Z2"], z["Z3"]), Edge("seg", z["Z3"], z["Z4"]),
                      Edge("arc", z["Z4"], z["Z7"], 180.0, None, 2.0),
                      Edge("seg", z["Z7"], z["Z8"]), Edge("seg", z["Z8"], z["Z9"]), Edge("seg", z["Z9"], z["Z10"])]
        lay = wd["slot_layout_first_12_slots"][k % 12]
        phase, sign = lay[0], (+1 if lay[1] == "+" else -1)
        sec.labels.append(Label((Rint_s + sl["H0"] + 0.5 * sl["H2"]) * complex(math.cos(p), math.sin(p)), "Cu", m["slot"],
                                phase, sign * wd["Ntcoil_turns_per_slot"], 0.0, f"slot{k}"))
    sec.edges += _arc_chain(Rext_s, quarter, "A0", 2.0)
    sec.labels.append(Label(rot(Rext_s - 5e-3, math.radians(20)), "Steel", m["stator"], name="stator_iron"))

    # ---- 공극: 가운데 원으로 안쪽(회전자 그룹)·바깥쪽 층으로 나눈다 ----
    r_mid = 0.5 * (Rext_r + Rint_s)
    sec.edges += _arc_chain(r_mid, quarter, None, 0.5)
    sec.labels.append(Label(rot(0.5 * (Rext_r + r_mid), math.radians(1.0)), "Air", m["gap"], name="gap_inner", group=1))
    sec.labels.append(Label(rot(0.5 * (r_mid + Rint_s), math.radians(1.0)), "Air", m["gap"], name="gap_outer", group=0))

    # ---- 회전자: 극마다 (j + 0.5)·극피치 + θr, 홀수 번째 극은 자화 반대 ----
    sec.edges += _arc_chain(Rext_r, [r0 + a for a in quarter], None, m["arc_deg"])
    sec.edges += _arc_chain(Rint_r, [r0 + a for a in quarter], "A0", 2.0)
    lower = rotor_hole_points(g)
    upper = {k: v.conjugate() for k, v in lower.items() if k != "e"}
    seg_pairs = [("Z1", "Z2"), ("Z2", "Z3"), ("Z3", "Z8c"), ("Z8c", "Z9"), ("Z8", "Z8c"), ("Z3", "Z4"), ("Z4", "Z5"),
                 ("Z5", "Z6"), ("Z6", "Z8"), ("Z6", "Z7")]
    mag_dir = math.degrees(cmath_phase(1j * lower["e"]))
    for j in range(Zh):
        off = (j + 0.5) * pole_pitch + r0
        flip = 180.0 if j % 2 else 0.0

        def P(z: complex, off: float = off) -> complex:
            return rot(z, off)

        for h in (lower, upper):
            sec.edges += [Edge("seg", P(h[a]), P(h[b])) for a, b in seg_pairs]
            lo, hi = sorted((h["Z1"], h["Z9"]), key=cmath_phase)
            sec.edges.append(Edge("arc", P(lo), P(hi), math.degrees(cmath_phase(hi) - cmath_phase(lo))))
        for h, d, nm in ((lower, mag_dir, "magnet_lower"), (upper, -mag_dir, "magnet_upper")):
            cen = sum(h[k] for k in ("Z8", "Z8c", "Z3", "Z4", "Z5", "Z6")) / 6
            sec.labels.append(Label(P(cen), "Magnet", m["magnet"], magdir_deg=d + math.degrees(off) + flip,
                                    name=f"{nm}{j}", group=1))
            sec.labels.append(Label(P(sum(h[k] for k in ("Z1", "Z2", "Z3", "Z8c", "Z9")) / 5), "Air", m["rotor"],
                                    name=f"pocket{j}", group=1))
        sec.labels.append(Label(P((lower["Z8"] + lower["Z6"] + lower["Z7"] + upper["Z6"]) / 4), "Air", m["rotor"],
                                name=f"kite{j}", group=1))
    sec.labels.append(Label(rot(0.060, math.radians(20) + 0.5 * pole_pitch + r0), "Steel", m["rotor"], name="rotor_iron", group=1))
    sec.labels.append(Label(0j, "<No Mesh>", 1.0, name="shaft"))        # 회전자 안쪽 원 안쪽(축)은 해석하지 않는다
    return sec


def _driver(i_abc: tuple[float, float, float], fem: str) -> str:
    return "\n".join([
        f'mi_modifycircprop("A", 1, {i_abc[0]:.12g})', f'mi_modifycircprop("B", 1, {i_abc[1]:.12g})',
        f'mi_modifycircprop("C", 1, {i_abc[2]:.12g})', "mi_createmesh()", f'mi_saveas("{fem}")', "mi_analyze(1)", "mi_loadsolution()",
        "mo_groupselectblock(1)", "tq = mo_blockintegral(22)", "mo_clearblock()",
        'i1, v1, fa = mo_getcircuitproperties("A")', 'i2, v2, fb = mo_getcircuitproperties("B")',
        'i3, v3, fc = mo_getcircuitproperties("C")',
        'print(format("PT %.12g %.12g %.12g %.12g %d %d", tq, fa, fb, fc, mo_numnodes(), mo_numelements()))']) + "\n"


def solve_one(i_abc: tuple[float, float, float], rotor_deg: float, mesh: dict | None = None,
              femmcli: str | None = None, timeout: int = 3600, br_T: float | None = None) -> dict:
    """모델을 만들어 저장 -> .fem에 [DoSmartMesh] = 0 삽입 -> 다시 열어 푼다.

    xfemm의 Lua에는 smartmesh 명령이 없고(주석 처리됨) 기본값이 켜짐이다. 스마트 메시는 가까운 꼭짓점 간격에 맞춰 요소를 잘게
    만들어 이 모델에서 요소 수가 약 2배(22.5만 -> 11.2만)가 된다. 저장한 .fem에 줄을 넣으면 끌 수 있다.
    """
    femmcli = femmcli or os.environ.get("FEMMCLI", "femmcli")
    g = load_geometry()
    if br_T is not None:                       # 자석 Br20을 덮어쓴다(민감도·보정용). 기본은 JSON 값 1.24 T
        g["magnet"]["Br20_T"] = br_T
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "build.lua").write_text(lua_model(g, build_full(g, mesh, rotor_deg), "m.fem"))
        subprocess.run([femmcli, "-q", "--lua-script=build.lua"], cwd=d, capture_output=True, text=True, timeout=timeout, check=True)
        lines = (d / "m.fem").read_text().splitlines()
        lines.insert(1, "[DoSmartMesh] = 0")
        (d / "m2.fem").write_text("\n".join(lines) + "\n")
        (d / "run.lua").write_text('open("m2.fem")\n' + _driver(i_abc, "full.fem"))
        out = subprocess.run([femmcli, "-q", "--lua-script=run.lua"], cwd=d, capture_output=True, text=True, timeout=timeout)
    rows = [l.split() for l in out.stdout.splitlines() if l.startswith("PT ")]
    if len(rows) != 1:
        raise RuntimeError(f"풀리지 않았다 (rotor {rotor_deg}°)\n{out.stdout[-1200:]}\n{out.stderr[-600:]}")
    v = [float(x) for x in rows[0][1:]]
    return {"torque_Nm": v[0], "lambda_abc_Wb": np.array(v[1:4]), "nodes": v[4], "elements": v[5]}


def solve_points(points: list[tuple[float, float, float, float]], mesh: dict | None = None, jobs: int = 8,
                 femmcli: str | None = None, br_T: float | None = None) -> dict[str, np.ndarray]:
    """points: [(iA, iB, iC [A 첨두], θr [기계 °])]. 점마다 독립 프로세스를 jobs개씩 병렬 실행."""
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        res = list(ex.map(lambda p: solve_one(p[:3], p[3], mesh, femmcli, br_T=br_T), points))
    return {"torque_Nm": np.array([r["torque_Nm"] for r in res]),
            "lambda_abc_Wb": np.array([r["lambda_abc_Wb"] for r in res]),
            "nodes": np.array([r["nodes"] for r in res]), "elements": np.array([r["elements"] for r in res])}
