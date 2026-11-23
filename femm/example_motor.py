"""연구실 강의 예제 IPMSM(8극 48슬롯, 160 kW급)의 xfemm 전체 모터 모델.

형상은 연구실 강의 자료의 MATLAB 코드(param.m)의 좌표 수식을 그대로 옮긴 것이다(자료 파일은 저장소에 없다, 수치 인용은 허용).
단위 mm로 적고 모델은 SI(m)로 만든다. 한 극은 d축(x축)에 대해 대칭인 "반극"(0°~22.5°)으로 정의되고 거울 복사로 한 극을 만든다.

반극 점 정의 (param.m의 rx/ry 번호 그대로):
  자석 1(비스듬한 V자 한 장): 점 2·3·6·7이 자석 직사각형. 길이 22.9 mm가 m_theta_1 = 49.9° 방향, 두께 2.6 mm.
  자석 2(극 중심의 납작한 자석): 점 11·10·13·12, 두께 3.2 mm(반경 방향), 길이 14 mm(반쪽, 거울로 28 mm).
  공극 구멍(자석 양끝의 공기 구멍): 구멍 1 = 점 1·2·3·4·5·17·6·7·8, 구멍 2 = 점 12·13·14·15·9·10·11.
  브리지 1.5 mm: 구멍은 반지름 R−1.5 mm의 원까지만 뻗는다. 센터포스트: 구멍 1은 y = 1 mm 선에서 끝난다(거울과 합쳐 2 mm).
고정자: 슬롯은 평행 치(폭 2·2.9 mm), 바닥은 반지름 3.05 mm의 원호, 슬롯 입구 1.4 mm, 슈 두께 1.18 mm. 점 번호도 param.m 그대로.
권선: 단층, 상당 직렬 32턴 병렬 2회로. 한 슬롯에 한 변이 있고 8회로 길이가 슬롯당 도체 8가닥(회로 전류 = 상전류/2).
  같은 값으로 슬롯당 4가닥에 상전류를 흘리는 것으로 둔다(슬롯 기자력 8 × 165 A = 4 × 330 A, 쇄교자속은 직렬 32턴).
  12슬롯 주기 배치: U+ U+ W− W− V+ V+ U− U− W+ W+ V− V− (강의 자료 슬라이드). 고정자 슬롯 k의 중심각 = (k + 0.5)·7.5°.
  회전 양의 방향(반시계)에서 상 순서는 A = U, B = V, C = W (+측 변의 위치가 U 7.5°, V 37.5°, W 67.5°이고 코일 중심이 +22.5°).
회전자 위치 r0: 극 j의 d축 각 = j·45° + r0. 홀수 극은 자화가 반대.

강판: 'jfe'는 JFE 35JN230 대표값(B10 1.47, B25 1.57, B50 1.66, B100 1.78 T @ 1000/2500/5000/10000 A/m, data/materials/steel_35JN230.json)을
쓰고 그 아래·위의 곡선 모양은 Prius 모델의 M400-50A 모양을 따른다(JFE가 이 구간 값을 주지 않는다). 'm400'은 Prius 곡선 그대로.
"""
from __future__ import annotations

import cmath
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import prius_full as pf  # noqa: E402
from prius_sector import Edge, Label, Sector, _arc_chain, arc_mid, load_geometry, lua_model, rot  # noqa: E402

MM = 1e-3
P = dict(poles=8, slots=48, stack_mm=153.0, lam_fill=0.97, bridge=1.5, alpha1=0.84, b2_l1=3.7, b_l1=4.9, b_l2=2.0, b_l3=-1.5,
         m_thick1=2.6, m_thick2=3.2, m_length_1=22.9, m_length_2=14.0, m_theta_1=49.9, air_gap=0.8, rotor_outer=66.0,
         rotor_inner=25.0, centerpost_1=1.0, stator_outer=100.0, slot_horizontal_1=12.5, slot_vertical_1=2.9, slot_edge=3.05,
         slot_open=0.7, shoe_thick=1.18, turns_per_slot=4)
SLOT_PATTERN = [("A", +1), ("A", +1), ("C", -1), ("C", -1), ("B", +1), ("B", +1), ("A", -1), ("A", -1),
                ("C", +1), ("C", +1), ("B", -1), ("B", -1)]    # 슬라이드의 U+ U+ W− W− V+ V+ U− U− W+ W+ V− V− 를 A=U, B=V, C=W로 옮긴 것


def rotor_points(p: dict = P) -> dict[str, complex]:
    """반극(d축 = +x)의 점 좌표 [mm]. param.m의 rx/ry 번호."""
    d = lambda deg: cmath.exp(1j * math.radians(deg))
    Rb = p["rotor_outer"] - p["bridge"]
    r_theta = 180.0 / p["poles"]
    z = {}
    z[1] = Rb * d(r_theta * p["alpha1"])
    z[2] = z[1] + p["b_l1"] * d(r_theta + 180)
    z[3] = z[2] + p["m_length_1"] * d(p["m_theta_1"] + 180)
    z[6] = z[3] + p["m_thick1"] * d(p["m_theta_1"] + 90)
    z[17] = z[6] + p["b_l2"] * d(p["m_theta_1"] + 180)
    z[4] = complex(z[3].real, p["centerpost_1"])
    z[5] = complex(z[17].real, p["centerpost_1"])
    z[7] = z[2] + p["m_thick1"] * d(p["m_theta_1"] + 90)
    slope = math.tan(math.radians(r_theta))
    off = z[7].imag - slope * z[7].real
    disc = (2 * slope * off) ** 2 - 4 * (1 + slope ** 2) * (off ** 2 - Rb ** 2)
    x8 = (-2 * slope * off + math.sqrt(disc)) / (2 * (1 + slope ** 2))
    z[8] = complex(x8, slope * x8 + off)
    h2 = p["m_length_2"] + p["b2_l1"]
    z[9] = complex(math.sqrt(Rb ** 2 - h2 ** 2), h2)
    z[11] = complex(z[9].real, 0.0)
    z[10] = complex(z[11].real, p["m_length_2"])
    z[12] = complex(z[11].real - p["m_thick2"], 0.0)
    z[13] = complex(z[12].real, z[10].imag)
    z[14] = z[13] + 0.3
    z[15] = complex(z[14].real, z[14].imag + (h2 - p["m_length_2"] + p["b_l3"]))
    return {f"Z{k}": v for k, v in z.items()}


def stator_points(p: dict = P) -> dict[str, complex]:
    """슬롯 0(중심각 3.75°)의 시계쪽 반 슬롯 점 [mm]. param.m의 sx/sy 번호와 c1(바닥 원호 중심)."""
    s_theta = 180.0 / p["slots"]
    Rsi = p["rotor_outer"] + p["air_gap"]
    d = lambda deg: cmath.exp(1j * math.radians(deg))
    z = {}
    z["S3"] = p["stator_outer"] * d(s_theta)
    z["S4"] = z["S3"] + p["slot_horizontal_1"] * d(s_theta + 180)
    z["C1"] = z["S4"] + p["slot_edge"] * d(s_theta + 180)
    sy5 = p["slot_vertical_1"]
    z["S5"] = complex(math.sqrt(p["slot_edge"] ** 2 - (sy5 - z["C1"].imag) ** 2) + z["C1"].real, sy5)
    opening = math.degrees(math.atan(p["slot_open"] / Rsi))
    z["S6"] = Rsi * d(s_theta - opening)
    z["S7"] = z["S6"] + p["shoe_thick"] * d(s_theta)
    dist = abs(z["S7"])
    z["S8"] = complex(math.sqrt(dist ** 2 - sy5 ** 2), sy5)
    return z


def steel_bh(variant: str) -> list[list[float]]:
    g = load_geometry()
    base = np.array(g["steel"]["BH_H_Apm_B_T"])
    if variant == "m400":
        return base.tolist()
    jfe = {1000.0: 1.47, 2500.0: 1.57, 5000.0: 1.66, 10000.0: 1.78}       # JFE 35JN230 대표값 (data/materials/steel_35JN230.json)
    f = jfe[1000.0] / float(np.interp(1000.0, base[:, 0], base[:, 1]))
    pts = [[0.0, 0.0]]
    for H, B in base[1:]:
        if H < 1000.0:
            pts.append([float(H), float(B) * f])
    pts += [[h, b] for h, b in jfe.items()]
    b10k = float(np.interp(10000.0, base[:, 0], base[:, 1]))
    pts += [[float(H), jfe[10000.0] + float(B) - b10k] for H, B in base[:, :] if H > 10000.0]
    return pts


def model_dict(br_T: float, mur: float, steel: str = "jfe", p: dict = P) -> dict:
    return {"magnet": {"Br20_T": br_T, "mur": mur}, "stator": {"L1_m": p["stack_mm"] * MM},
            "steel": {"BH_H_Apm_B_T": steel_bh(steel), "lam_fill": p["lam_fill"]}}


def build(rotor_deg: float = 0.0, mesh: dict | None = None, p: dict = P) -> Sector:
    m = {"stator": 3.0e-3, "rotor": 2.0e-3, "magnet": 2.0e-3, "slot": 4.0e-3, "gap": 0.4e-3, "arc_deg": 0.5} | (mesh or {})
    Zs, Zh = p["slots"], p["poles"]
    pitch, pole_pitch = 2 * math.pi / Zs, 2 * math.pi / Zh
    Rro, Rri = p["rotor_outer"] * MM, p["rotor_inner"] * MM
    Rsi, Rso = (p["rotor_outer"] + p["air_gap"]) * MM, p["stator_outer"] * MM
    Rb = (p["rotor_outer"] - p["bridge"]) * MM
    r0 = math.radians(rotor_deg)
    sec = Sector(antiperiodic=False, poles=Zh)
    quarter = [k * math.pi / 2 for k in range(5)]
    sz = {k: v * MM for k, v in stator_points(p).items()}
    s_half = math.pi / Zs
    mirror_slot = lambda z: cmath.exp(1j * 2 * s_half) * z.conjugate()          # 슬롯 0 중심선(3.75°)에 대한 거울
    open_ang = cmath.phase(sz["S6"])                                            # 시계쪽 입구 모서리의 각 (3.75° − opening)
    half_open = s_half - open_ang                                               # 입구 반폭 각
    # ---- 고정자 ----
    bore = []
    for k in range(Zs):
        c = (k + 0.5) * pitch
        bore += [c - half_open, c + half_open]
    sec.edges += _arc_chain(Rsi, bore + [bore[0] + 2 * math.pi], None, m["arc_deg"])
    for k in range(Zs):
        c = (k + 0.5) * pitch
        rt = lambda z, c=c: rot(z, c - s_half)                                  # 슬롯 0 좌표를 슬롯 k로 돌린다
        half = [sz["S6"], sz["S7"], sz["S8"], sz["S5"]]
        other = [mirror_slot(z) for z in half]
        S4 = sz["S4"]
        sec.edges += [Edge("seg", rt(half[0]), rt(half[1])), Edge("seg", rt(half[1]), rt(half[2])), Edge("seg", rt(half[2]), rt(half[3]))]
        sec.edges += [Edge("seg", rt(other[0]), rt(other[1])), Edge("seg", rt(other[1]), rt(other[2])), Edge("seg", rt(other[2]), rt(other[3]))]
        sec.edges += [Edge("arc", rt(half[3]), rt(other[3]), 0.0, None, 2.0)]    # 아래에서 각도를 채운다 (바닥 원호, 시계쪽 점 → 반시계쪽 점)
        circ, sign = SLOT_PATTERN[k % 12]
        mid = abs(S4) - 0.5 * (abs(S4) - Rsi - p["shoe_thick"] * MM)
        sec.labels.append(Label(mid * cmath.exp(1j * c), "Cu", m["slot"], circ, sign * p["turns_per_slot"], 0.0, f"slot{k}"))
    # 바닥 원호의 각도: 원호 중심 C1, 반지름 slot_edge. 두 끝점이 슬롯 중심선 양쪽에 대칭이다.
    C1, edge_r = sz["C1"], p["slot_edge"] * MM
    a1 = cmath.phase(sz["S5"] - C1)
    a2 = cmath.phase(mirror_slot(sz["S5"]) - C1)
    sweep = math.degrees((a2 - a1) % (2 * math.pi))                             # half[3] → other[3], 반시계, 중심선(바깥쪽)을 지나는 180° 미만 호
    sec.edges = [Edge(e.kind, e.p1, e.p2, sweep, e.boundary, e.maxseg_deg) if (e.kind == "arc" and e.angle_deg == 0.0) else e for e in sec.edges]
    sec.edges += _arc_chain(Rso, quarter, "A0", 2.0)
    sec.labels.append(Label(rot(Rso - 4e-3, math.radians(20)), "Steel", m["stator"], name="stator_iron"))
    # ---- 공극: 가운데 원으로 안쪽(회전자 그룹)·바깥쪽 층 ----
    r_mid = 0.5 * (Rro + Rsi)
    sec.edges += _arc_chain(r_mid, quarter, None, 0.5)
    sec.labels.append(Label(rot(0.5 * (Rro + r_mid), math.radians(1.0)), "Air", m["gap"], name="gap_inner", group=1))
    sec.labels.append(Label(rot(0.5 * (r_mid + Rsi), math.radians(1.0)), "Air", m["gap"], name="gap_outer", group=0))
    # ---- 회전자 ----
    sec.edges += _arc_chain(Rro, [r0 + a for a in quarter], None, m["arc_deg"])
    sec.edges += _arc_chain(Rri, [r0 + a for a in quarter], "A0", 2.0)
    rp = {k: v * MM for k, v in rotor_points(p).items()}
    for j in range(Zh):
        th = j * pole_pitch + r0
        pol = +1 if j % 2 == 0 else -1
        for half_sign in (+1, -1):                                              # +1 위쪽 반극, −1 거울(아래쪽)
            conj = (lambda z: z) if half_sign > 0 else (lambda z: z.conjugate())
            Pn = lambda k, conj=conj, th=th: rot(conj(rp[f"Z{k}"]), th)
            chain1 = [1, 2, 3, 4, 5, 17, 6, 7, 8]
            sec.edges += [Edge("seg", Pn(a), Pn(b)) for a, b in zip(chain1[:-1], chain1[1:])]
            a1, a8 = cmath.phase(Pn(1)), cmath.phase(Pn(8))
            lo, hi = (Pn(1), Pn(8)) if half_sign > 0 else (Pn(8), Pn(1))
            sec.edges.append(Edge("arc", lo, hi, math.degrees(abs(cmath.phase(rp["Z8"]) - cmath.phase(rp["Z1"]))), None, 0.5))
            sec.edges += [Edge("seg", Pn(3), Pn(6)), Edge("seg", Pn(7), Pn(2))]
        # 구멍 2 (반극 두 개가 y=0에서 이어진다)
        for half_sign in (+1, -1):
            conj = (lambda z: z) if half_sign > 0 else (lambda z: z.conjugate())
            Pn = lambda k, conj=conj, th=th: rot(conj(rp[f"Z{k}"]), th)
            chain2 = [12, 13, 14, 15, 9, 10, 11]
            sec.edges += [Edge("seg", Pn(a), Pn(b)) for a, b in zip(chain2[:-1], chain2[1:])]
            sec.edges.append(Edge("seg", Pn(14), Pn(10)))                       # 자석 2 윗변 중 공기쪽 (14 → 10)
        # 자석 2 윗변 중 철쪽 (13 → 14)는 위 사슬에 있다. 자석 2의 윗변과 아랫변이 만나는 중심선은 도체 없음(자석 하나로 이어진 직사각형)
        # 라벨: 자석, 공기
        n1_up = math.radians(P["m_theta_1"] - 90.0)                              # 자석 1 위쪽 자화 방향(국소각)
        for half_sign in (+1, -1):
            conj = (lambda z: z) if half_sign > 0 else (lambda z: z.conjugate())
            Pn = lambda k, conj=conj, th=th: rot(conj(rp[f"Z{k}"]), th)
            cen = lambda ks, Pn=Pn: sum(Pn(k) for k in ks) / len(ks)
            ang = math.degrees(n1_up * half_sign + th) + (0.0 if pol > 0 else 180.0)
            sec.labels.append(Label(cen((2, 3, 6, 7)), "Magnet", m["magnet"], magdir_deg=ang, name=f"mag1_{j}_{half_sign}", group=1))
            sec.labels.append(Label(cen((3, 4, 5, 17, 6)), "Air", m["rotor"], name=f"air_in_{j}_{half_sign}", group=1))
            sec.labels.append(Label(cen((1, 2, 7, 8)), "Air", m["rotor"], name=f"air_out_{j}_{half_sign}", group=1))
            sec.labels.append(Label(cen((14, 15, 9, 10)), "Air", m["rotor"], name=f"air2_{j}_{half_sign}", group=1))
        mag2 = rot((rp["Z12"] + rp["Z11"]) / 2, th)
        sec.labels.append(Label(mag2, "Magnet", m["magnet"], magdir_deg=math.degrees(th) + (0.0 if pol > 0 else 180.0),
                                name=f"mag2_{j}", group=1))
    sec.labels.append(Label(rot(0.040, math.radians(11.0) + r0), "Steel", m["rotor"], name="rotor_iron", group=1))
    sec.labels.append(Label(0j, "<No Mesh>", 1.0, name="shaft"))
    return sec


def solve_one(i_abc: tuple[float, float, float], rotor_deg: float, br_T: float, mur: float, steel: str = "jfe",
              mesh: dict | None = None, femmcli: str | None = None, timeout: int = 3600, probes: list[complex] | None = None,
              p: dict | None = None) -> dict:
    """p: 설계 변수를 덮어쓴 형상 딕셔너리(기본 P). M6 최적화가 쓴다."""
    femmcli = femmcli or os.environ.get("FEMMCLI", "femmcli")
    p = P if p is None else p
    g = model_dict(br_T, mur, steel, p)
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "build.lua").write_text(lua_model(g, build(rotor_deg, mesh, p), "m.fem"))
        subprocess.run([femmcli, "-q", "--lua-script=build.lua"], cwd=d, capture_output=True, text=True, timeout=timeout, check=True)
        lines = (d / "m.fem").read_text().splitlines()
        lines.insert(1, "[DoSmartMesh] = 0")
        (d / "m2.fem").write_text("\n".join(lines) + "\n")
        (d / "run.lua").write_text('open("m2.fem")\n' + pf._driver(i_abc, "full.fem", probes))
        out = subprocess.run([femmcli, "-q", "--lua-script=run.lua"], cwd=d, capture_output=True, text=True, timeout=timeout)
    rows = [l.split() for l in out.stdout.splitlines() if l.startswith("PT ")]
    if len(rows) != 1:
        raise RuntimeError(f"풀리지 않았다 (rotor {rotor_deg}°)\n{out.stdout[-1200:]}\n{out.stderr[-600:]}")
    v = [float(x) for x in rows[0][1:]]
    res = {"torque_Nm": v[0], "lambda_abc_Wb": np.array(v[1:4]), "nodes": v[4], "elements": v[5]}
    if probes:
        bp = np.array([[float(x) for x in l.split()[1:]] for l in out.stdout.splitlines() if l.startswith("BP ")])
        res["B_xy_T"], res["A_Wb_per_m"] = bp[:, :2], bp[:, 2]
    return res


def plot(path: str, rotor_deg: float = 0.0) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    sec = build(rotor_deg)
    fig, ax = plt.subplots(figsize=(11, 11))
    for e in sec.edges:
        if e.kind == "seg":
            ax.plot([e.p1.real, e.p2.real], [e.p1.imag, e.p2.imag], color="k", lw=0.6)
        else:
            c = cmath.phase(0)  # 호는 현으로 근사해 그린다
            from prius_sector import arc_center
            ctr = arc_center(e)
            a0 = cmath.phase(e.p1 - ctr)
            ts = np.linspace(0, math.radians(e.angle_deg), 24)
            pts = [ctr + (e.p1 - ctr) * cmath.exp(1j * t) for t in ts]
            ax.plot([q.real for q in pts], [q.imag for q in pts], color="k", lw=0.6)
    colors = {"Cu": "tab:orange", "Steel": "tab:blue", "Magnet": "tab:red", "Air": "tab:gray"}
    for lab in sec.labels:
        ax.plot(lab.pos.real, lab.pos.imag, ".", color=colors.get(lab.material, "g"), ms=5)
    ax.set_aspect("equal")
    fig.savefig(path, dpi=110)


# ---- 설계 변수 형상의 타당성 검사 (M6 최적화가 쓴다) ----
def _seg_dist(a: complex, b: complex, c: complex, d: complex) -> float:
    """두 선분 ab, cd 사이의 최소 거리 (교차하면 0)."""
    cross = lambda u, v: u.real * v.imag - u.imag * v.real
    r, s = b - a, d - c
    den = cross(r, s)
    if abs(den) > 1e-12:
        t, u = cross(c - a, s) / den, cross(c - a, r) / den
        if 0 <= t <= 1 and 0 <= u <= 1:
            return 0.0

    def point_seg(p, q1, q2):
        ab = q2 - q1
        if abs(ab) < 1e-12:
            return abs(p - q1)
        t = max(0.0, min(1.0, ((p - q1) * ab.conjugate()).real / abs(ab) ** 2))
        return abs(p - (q1 + t * ab))
    return min(point_seg(a, c, d), point_seg(b, c, d), point_seg(c, a, b), point_seg(d, a, b))


def polygon_distance(A: list, B: list) -> float:
    """두 다각형(꼭짓점 목록, 닫힘 가정)의 변 사이 최소 거리 [단위는 입력과 같다]. 한 다각형이 다른 쪽을 완전히 품는 경우는 따로 보지 않는다."""
    ea = [(A[i], A[(i + 1) % len(A)]) for i in range(len(A))]
    eb = [(B[i], B[(i + 1) % len(B)]) for i in range(len(B))]
    return min(_seg_dist(a, b, c, d) for a, b in ea for c, d in eb)


def rotor_webs_mm(p: dict = P) -> dict:
    """회전자 철 웹(구멍 사이 철의 최소 폭) [mm]: 구멍 1-구멍 2, 구멍 1 위·아래(센터포스트), 이웃 극 구멍 1끼리(q축 철), 구멍 1과 축 구멍."""
    z = rotor_points(p)
    h1 = [z[f"Z{k}"] for k in (1, 2, 3, 4, 5, 17, 6, 7, 8)]
    up = [z[f"Z{k}"] for k in (12, 13, 14, 15, 9, 10, 11)]
    h2 = up + [q.conjugate() for q in reversed(up)]
    cj = lambda poly: [q.conjugate() for q in poly]
    rt = lambda poly, deg: [q * cmath.exp(1j * math.radians(deg)) for q in poly]
    return {"hole1_hole2": polygon_distance(h1, h2), "center_post": polygon_distance(h1, cj(h1)),
            "q_axis": polygon_distance(h1, rt(cj(h1), 360.0 / p["poles"])),
            "hole1_shaft": min(abs(q) for q in h1) - p["rotor_inner"]}


def geometry_ok(p: dict = P, min_web_mm: float = 1.5) -> tuple[bool, str]:
    """설계 변수 형상이 만들 수 있는지: 구멍의 점 순서와 위치가 맞고(자석 끝이 센터포스트 선 위), 철 웹이 min_web_mm 이상이다.
    min_web_mm = 1.5는 설계 가정이다: 기준 설계의 철 웹(센터포스트 2.0, 구멍 사이 3.3, q축 3.5 mm)의 절반 안팎. 기계적 응력은 계산하지 않는다."""
    z = rotor_points(p)
    if z["Z3"].imag < p["centerpost_1"] + 1e-9:
        return False, "자석 1의 안쪽 끝이 센터포스트 선 아래"
    if z["Z17"].imag < p["centerpost_1"] + 1e-9 or z["Z6"].imag < z["Z17"].imag:
        return False, "구멍 1의 안쪽 끝 점 순서가 맞지 않음"
    if z["Z9"].real <= z["Z12"].real or z["Z15"].imag <= z["Z14"].imag:
        return False, "구멍 2 점 순서가 맞지 않음"
    if cmath.phase(z["Z8"]) >= math.radians(180.0 / p["poles"]):
        return False, "구멍 1 바깥 끝이 극 경계를 넘음"
    for name, v in rotor_webs_mm(p).items():
        floor = 3.0 if name == "hole1_shaft" else min_web_mm
        if v < floor:
            return False, f"철 웹 {name} = {v:.2f} mm < {floor} mm"
    return True, "ok"
