"""2004 Prius 구동모터의 1극(45°) 섹터 FEMM 모델 생성기. (FEMM 또는 xfemm `femmcli`에서 실행)

형상·재료 값은 data/benchmarks/prius2004_geometry.json (제3자 모델, 미검증)에서 읽는다. 점 좌표 정의는 pyleecan(Apache-2.0)의
SlotW11(고정자 슬롯), HoleM50(회전자 V자 구멍) 정의를 옮겼다. 이 모터는 8극이라 일부 섹터만 모델링한다. poles=2(기본): N·S극 한 쌍(90°, 12슬롯)을 주기(periodic) 경계로 닫는다 — xfemm이
자체 벤치마크로 검증한 경로다. poles=1: 한 극(45°)을 반대칭 경계로 닫는다(xfemm에서 결과가 일관되지 않아 쓰지 않는다). 회전자 위치는 공극 요소(AGE)의 안쪽 각도로 바꾸므로 메시를 다시 만들 필요가 없다.

좌표계: 고정자 섹터는 0°~45°, 슬롯 k의 중심각은 (k + 0.5)·7.5° (가정), 회전자는 d축이 22.5°에 오도록 놓는다(기준 위치).
회전자 d축의 A상 축에 대한 전기각은 θe = 150° + 4·θr (θr = AGE 안쪽 각도, 반시계가 +). prius_run.py 참조.
단위는 SI(m, A, T). FEMM의 자석은 B = μ0·μr·(H + Hc), 따라서 Br = μ0·μr·Hc.
"""
from __future__ import annotations

import cmath
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.optimize import fsolve

GEOMETRY_JSON = Path(__file__).resolve().parents[1] / "data" / "benchmarks" / "prius2004_geometry.json"
MU0 = 4e-7 * math.pi


def load_geometry(path: Path = GEOMETRY_JSON) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def rot(z: complex, ang: float) -> complex:
    return z * cmath.exp(1j * ang)


def stator_slot_points(g: dict) -> dict[str, complex]:
    """pyleecan SlotW11 (바깥쪽으로 열린 고정자 슬롯, 슬롯 중심이 +x축). Z1~Z4(아래쪽 절반)와 켤레 점들."""
    s = g["stator"]; sl = s["slot_SlotW11"]; Rbo = s["Rint_m"]
    H0, H1, H2, R1, W0, W1, W2 = (sl[k] for k in ("H0", "H1", "H2", "R1", "W0", "W1", "W2"))
    assert abs(W2 - 2 * R1) < 1e-12, "바닥이 반원(W2 = 2·R1)인 슬롯만 지원한다"
    alpha = math.asin(W0 / (2 * Rbo))
    Z1 = Rbo * cmath.exp(-1j * alpha)
    Z2 = Z1 + H0
    Z3 = complex(Z2.real + H1, -W1 / 2)
    Z4 = complex(Z3.real + (H2 - R1), -W2 / 2)
    return {"Z1": Z1, "Z2": Z2, "Z3": Z3, "Z4": Z4, "Z7": Z4.conjugate(), "Z8": Z3.conjugate(),
            "Z9": Z2.conjugate(), "Z10": Z1.conjugate(), "alpha": alpha}


def rotor_hole_points(g: dict) -> dict[str, complex]:
    """pyleecan HoleM50 (V자 자석 구멍의 아래쪽 팔). d축이 +x축. 위쪽 팔은 켤레복소수. H4 = W1 = W2 = 0인 구멍만 지원."""
    r = g["rotor"]; h = r["hole_HoleM50"]; Rext = r["Rext_m"]; Zh = r["Zh"]
    H0, H1, H2, H3, H4, W0, W1, W2, W3, W4 = (h[k] for k in ("H0", "H1", "H2", "H3", "H4", "W0", "W1", "W2", "W3", "W4"))
    assert H4 == 0 and W1 == 0 and W2 == 0, "H4 = W1 = W2 = 0인 구멍만 지원한다"
    alpham = 2 * math.asin(W0 / (2 * (Rext - H1)))
    Harc = (Rext - H1) * (1 - math.cos(alpham / 2))
    gammam = math.atan((H0 - H1 - Harc) / (W0 / 2.0 - W1 / 2.0))
    hssp = math.pi / Zh
    x78 = (H3 - H2) / math.cos(gammam)
    Z9 = complex(Rext - Harc - H1, -W0 / 2)
    Z8 = complex(Rext - H0, -W1 / 2)
    Z7 = complex(Rext - H0 - x78, -W1 / 2)
    Z1 = (Rext - H1) * cmath.exp(1j * (-hssp + math.asin(W3 / (2 * (Rext - H1)))))
    # 자석: Z8을 원점, 윗변을 x축으로 한 국소 좌표에서 만든 뒤 Z9-Z8 방향으로 회전
    Z8c = complex(W2 + W4, 0)
    Z5 = complex(W2, -H3)
    Z4 = Z8c - 1j * H3
    Z6 = Z5 + 1j * H2
    Z3 = Z4 + 1j * H2
    e = cmath.exp(1j * cmath.phase(Z9 - Z8))
    Z3, Z4, Z5, Z6, Z8c = (z * e + Z8 for z in (Z3, Z4, Z5, Z6, Z8c))
    # Z2: 선분 Z2-Z3이 자석 폭 방향(Z3-Z6)과 평행하도록 하는 점 (pyleecan과 같은 방식)
    Z3r, Z1r, Z6r = rot(Z3, hssp), rot(Z1, hssp), rot(Z6, hssp)
    x = fsolve(lambda x: np.imag((Z3r - (Z1r - x)) / (Z6r - Z3r)), H3 - H2)
    Z2 = rot(Z1r - x[0], -hssp)
    return {"Z1": Z1, "Z2": Z2, "Z3": Z3, "Z4": Z4, "Z5": Z5, "Z6": Z6, "Z7": Z7, "Z8": Z8, "Z8c": Z8c, "Z9": Z9, "e": e}


@dataclass
class Edge:
    kind: str                 # "seg" 또는 "arc"
    p1: complex
    p2: complex
    angle_deg: float = 0.0    # arc일 때 p1에서 p2로 가는 반시계 호의 각도
    boundary: str | None = None
    maxseg_deg: float = 1.0
    meshsize: float | None = None


@dataclass
class Label:
    pos: complex
    material: str
    meshsize: float
    circuit: str | None = None
    turns: int = 0
    magdir_deg: float = 0.0
    name: str = ""
    group: int = 0          # 후처리에서 mo_groupselectblock으로 한 번에 고르기 위한 블록 그룹(회전자 = 1)


@dataclass
class Sector:
    edges: list[Edge] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    antiperiodic: bool = True      # 1극 섹터면 반대칭, 2극 섹터면 주기 경계
    poles: int = 1


def arc_center(e: Edge) -> complex:
    """반시계 호(p1 -> p2, 각도 θ)의 중심: 현 중점에서 진행 방향의 왼쪽으로 r·cos(θ/2). θ = 180°이면 중점."""
    half = math.radians(e.angle_deg) / 2
    d = (e.p2 - e.p1) / 2
    r = abs(d) / math.sin(half)
    return (e.p1 + e.p2) / 2 + 1j * d / abs(d) * r * math.cos(half)


def arc_mid(e: Edge) -> complex:
    c = arc_center(e)
    return c + (e.p1 - c) * cmath.exp(1j * math.radians(e.angle_deg) / 2)


def _arc_chain(r: float, angles: list[float], boundary: str | None, maxseg: float) -> list[Edge]:
    pts = [r * cmath.exp(1j * a) for a in angles]
    return [Edge("arc", pts[i], pts[i + 1], math.degrees(angles[i + 1] - angles[i]), boundary, maxseg)
            for i in range(len(pts) - 1)]


def build_sector(g: dict, mesh: dict | None = None, poles: int = 2) -> Sector:
    m = {"stator": 1.5e-3, "rotor": 1.5e-3, "magnet": 1.0e-3, "slot": 2.0e-3, "edge": 1.5e-3} | (mesh or {})
    st, ro, wd = g["stator"], g["rotor"], g["winding"]
    Zs = st["Zs"]
    pole_pitch = 2 * math.pi / ro["Zh"]           # 한 극의 기계각: 극 수 = Zh = 8 -> 45°
    sector = poles * pole_pitch                   # poles=1: 반대칭, poles=2: 주기(N·S극 한 쌍)
    pitch = 2 * math.pi / Zs
    n_slot = round(sector / pitch)
    assert n_slot == 6 * poles and abs(n_slot * pitch - sector) < 1e-12, "한 극에 슬롯 6개를 가정"
    Rint_s, Rext_s = st["Rint_m"], st["Rext_m"]
    Rint_r, Rext_r = ro["Rint_m"], ro["Rext_m"]
    sl = st["slot_SlotW11"]
    sec = Sector(antiperiodic=(poles == 1), poles=poles)

    # ---- 고정자 ----
    sp = stator_slot_points(g)
    phi = [(k + 0.5) * pitch for k in range(n_slot)]
    bore_angles = [0.0]
    for p in phi:
        bore_angles += [p - sp["alpha"], p + sp["alpha"]]
    bore_angles.append(sector)
    sec.edges += _arc_chain(Rint_s, bore_angles, "AGE", 0.25)      # 치 끝과 슬롯 입구 모두 공극 경계
    for k, p in enumerate(phi):
        z = {n: rot(v, p) for n, v in sp.items() if n.startswith("Z")}
        sec.edges += [Edge("seg", z["Z1"], z["Z2"]), Edge("seg", z["Z2"], z["Z3"]), Edge("seg", z["Z3"], z["Z4"]),
                      Edge("arc", z["Z4"], z["Z7"], 180.0, None, 2.0),     # 바닥 반원(바깥쪽으로 볼록)
                      Edge("seg", z["Z7"], z["Z8"]), Edge("seg", z["Z8"], z["Z9"]), Edge("seg", z["Z9"], z["Z10"])]
        phase, sign = wd["slot_layout_first_12_slots"][k % 12][0], (+1 if wd["slot_layout_first_12_slots"][k % 12][1] == "+" else -1)
        sec.labels.append(Label((Rint_s + sl["H0"] + 0.5 * sl["H2"]) * cmath.exp(1j * p), "Cu", m["slot"],
                                phase, sign * wd["Ntcoil_turns_per_slot"], 0.0, f"slot{k}"))
    sec.edges += _arc_chain(Rext_s, [0.0, sector / 2, sector], "A0", 2.0)
    # 반대칭 경계의 짝이 되는 두 변은 메시 노드가 일치해야 하므로 요소 크기를 명시한다(자동 메시 아님)
    sec.edges += [Edge("seg", Rint_s + 0j, Rext_s + 0j, boundary="SPBC", meshsize=m["edge"]),
                  Edge("seg", rot(Rint_s, sector), rot(Rext_s, sector), boundary="SPBC", meshsize=m["edge"])]
    sec.labels.append(Label(rot(Rext_s - 5e-3, math.radians(20)), "Steel", m["stator"], name="stator_iron"))

    # ---- 회전자: 극마다 국소 d축 = +x를 (j + 0.5)·극피치만큼 돌려 놓는다. 홀수 번째 극은 자화 방향이 반대(S극) ----
    half_angles = [k * pole_pitch / 2 for k in range(2 * poles + 1)]
    sec.edges += _arc_chain(Rext_r, half_angles, "AGE", 0.25)
    sec.edges += _arc_chain(Rint_r, half_angles, "A0", 2.0)
    sec.edges += [Edge("seg", Rint_r + 0j, Rext_r + 0j, boundary="RPBC", meshsize=m["edge"]),
                  Edge("seg", rot(Rint_r, sector), rot(Rext_r, sector), boundary="RPBC", meshsize=m["edge"])]
    lower = rotor_hole_points(g)
    upper = {k: v.conjugate() for k, v in lower.items() if k != "e"}
    seg_pairs = [("Z1", "Z2"), ("Z2", "Z3"), ("Z3", "Z8c"), ("Z8c", "Z9"),            # 끝 공극(자석 바깥쪽)
                 ("Z8", "Z8c"), ("Z3", "Z4"), ("Z4", "Z5"), ("Z5", "Z6"), ("Z6", "Z8"),  # 자석 직사각형
                 ("Z6", "Z7")]                                                          # 가운데 공극
    mag_dir = math.degrees(cmath.phase(1j * lower["e"]))      # 자화: 윗변에서 극편 쪽(+i·e). 아래쪽 팔 기준 (N극)
    for j in range(poles):
        off = (j + 0.5) * pole_pitch
        flip = 180.0 if j % 2 else 0.0

        def P(z: complex, off: float = off) -> complex:      # 국소 -> 전역
            return rot(z, off)

        for h in (lower, upper):
            sec.edges += [Edge("seg", P(h[a]), P(h[b])) for a, b in seg_pairs]
            lo, hi = sorted((h["Z1"], h["Z9"]), key=cmath.phase)                   # 구멍 바깥 호(반지름 Rext-H1)
            sec.edges.append(Edge("arc", P(lo), P(hi), math.degrees(cmath.phase(hi) - cmath.phase(lo))))
        for h, d, nm in ((lower, mag_dir, "magnet_lower"), (upper, -mag_dir, "magnet_upper")):
            cen = sum(h[k] for k in ("Z8", "Z8c", "Z3", "Z4", "Z5", "Z6")) / 6
            sec.labels.append(Label(P(cen), "Magnet", m["magnet"], magdir_deg=d + math.degrees(off) + flip,
                                    name=f"{nm}{j}"))
            sec.labels.append(Label(P(sum(h[k] for k in ("Z1", "Z2", "Z3", "Z8c", "Z9")) / 5), "Air", m["rotor"],
                                    name=f"pocket{j}"))
        sec.labels.append(Label(P((lower["Z8"] + lower["Z6"] + lower["Z7"] + upper["Z6"]) / 4), "Air", m["rotor"],
                                name=f"kite{j}"))
    sec.labels.append(Label(rot(0.060, math.radians(20) + 0.5 * pole_pitch), "Steel", m["rotor"], name="rotor_iron"))
    return sec


def lua_model(g: dict, sec: Sector, filename: str = "prius.fem") -> str:
    mag = g["magnet"]; depth = g["stator"]["L1_m"]
    Hc = mag["Br20_T"] / (MU0 * mag["mur"])
    L = ['newdocument(0)', f'mi_probdef(0, "meters", "planar", 1e-8, {depth:.9g}, 30)',
         'mi_addmaterial("Air", 1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0)',
         'mi_addmaterial("Cu", 1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0)',
         f'mi_addmaterial("Magnet", {mag["mur"]}, {mag["mur"]}, {Hc:.9g}, 0, 0, 0, 0, 1, 0, 0, 0)',
         'mi_addmaterial("Steel", 1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0)', 'mi_addbhpoint("Steel", 0, 0)']
    L += [f'mi_addbhpoint("Steel", {B:.9g}, {H:.9g})' for H, B in g["steel"]["BH_H_Apm_B_T"][1:]]
    L += [f'mi_addcircprop("{c}", 0, 1)' for c in "ABC"]
    bc, age = (5, 7) if sec.antiperiodic else (4, 6)      # BdryFormat: 4 주기, 5 반대칭, 6 주기 AGE, 7 반대칭 AGE
    formats = {"A0": 0, "SPBC": bc, "RPBC": bc, "AGE": age}
    L += [f'mi_addboundprop("{n}", 0, 0, 0, 0, 0, 0, 0, 0, {f})' for n, f in formats.items()
          if any(e.boundary == n for e in sec.edges)]
    seen: set[tuple[int, int]] = set()
    for e in sec.edges:
        for z in (e.p1, e.p2):
            key = (round(z.real * 1e9), round(z.imag * 1e9))
            if key not in seen:
                seen.add(key)
                L.append(f"mi_addnode({z.real:.12g}, {z.imag:.12g})")
    for e in sec.edges:
        if e.kind == "seg":
            L.append(f"mi_addsegment({e.p1.real:.12g}, {e.p1.imag:.12g}, {e.p2.real:.12g}, {e.p2.imag:.12g})")
        else:
            L.append(f"mi_addarc({e.p1.real:.12g}, {e.p1.imag:.12g}, {e.p2.real:.12g}, {e.p2.imag:.12g}, "
                     f"{e.angle_deg:.12g}, {e.maxseg_deg:g})")
    for e in sec.edges:
        if e.boundary is None:
            continue
        if e.kind == "seg":
            mid = (e.p1 + e.p2) / 2
            L.append(f'mi_selectsegment({mid.real:.12g}, {mid.imag:.12g}) '
                     f'mi_setsegmentprop("{e.boundary}", {e.meshsize or 0}, {0 if e.meshsize else 1}, 0, 0) '
                     f"mi_clearselected()")
        else:
            mid = arc_mid(e)
            L.append(f'mi_selectarcsegment({mid.real:.12g}, {mid.imag:.12g}) '
                     f'mi_setarcsegmentprop({e.maxseg_deg:g}, "{e.boundary}", 0, 0) mi_clearselected()')
    for lab in sec.labels:
        circ = f'"{lab.circuit}"' if lab.circuit else '"<None>"'
        L.append(f"mi_addblocklabel({lab.pos.real:.12g}, {lab.pos.imag:.12g}) "
                 f"mi_selectlabel({lab.pos.real:.12g}, {lab.pos.imag:.12g})")
        L.append(f'mi_setblockprop("{lab.material}", 0, {lab.meshsize:g}, {circ}, {lab.magdir_deg:.9g}, {lab.group}, {lab.turns}) '
                 f"mi_clearselected()")
    L.append(f'mi_saveas("{filename}")')
    return "\n".join(L) + "\n"


def plot(sec: Sector, path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 11))
    for e in sec.edges:
        col = {"AGE": "tab:red", "A0": "tab:green", "SPBC": "tab:purple", "RPBC": "tab:purple"}.get(e.boundary, "k")
        if e.kind == "seg":
            ax.plot([e.p1.real, e.p2.real], [e.p1.imag, e.p2.imag], color=col, lw=0.9)
        else:
            c = arc_center(e)
            a0 = cmath.phase(e.p1 - c)
            t = np.linspace(a0, a0 + math.radians(e.angle_deg), 40)
            r = abs(e.p1 - c)
            ax.plot(c.real + r * np.cos(t), c.imag + r * np.sin(t), color=col, lw=0.9)
    colors = {"Cu": "tab:orange", "Steel": "tab:blue", "Magnet": "tab:red", "Air": "tab:gray"}
    for lab in sec.labels:
        ax.plot(lab.pos.real, lab.pos.imag, "o", color=colors[lab.material], ms=5)
        tag = f" {lab.circuit}{'+' if lab.turns > 0 else '-'}" if lab.circuit else ""
        ax.annotate(lab.name + tag, (lab.pos.real, lab.pos.imag), fontsize=7)
    ax.set_aspect("equal"); ax.grid(alpha=0.3)
    ax.set_title("Prius 2004 1-pole sector (third-party geometry, unverified)")
    fig.savefig(path, dpi=110, bbox_inches="tight")


if __name__ == "__main__":
    import sys
    s = build_sector(load_geometry())
    out = sys.argv[1] if len(sys.argv) > 1 else "prius_sector.png"
    plot(s, out)
    print(f"{len(s.edges)} edges, {len(s.labels)} labels -> {out}")
