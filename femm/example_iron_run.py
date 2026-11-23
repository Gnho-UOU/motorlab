"""연구실 예제 IPMSM의 철손 계산용 자속밀도 파형: 부하(β = 41°, 상전류 첨두 330 A, 4300 rpm)에서 회전자를 한 전기 주기(기계각 90°)
동안 돌리며 고정자 치·요크·슈와 회전자 철심의 점 B(Bx, By)를 읽어 data/fea/example_motor_iron_probes.npz에 쓴다.

점 배치 (영역마다 면적 가중치를 같이 저장한다. 철손은 점마다 구한 W/kg에 가중 질량을 곱해 더한다):
  치(tooth)  첫 90°의 치 12개 × 반지름 6단(68~86 mm, 평행 치폭 5.8 mm를 가로로 3점)
  슈(shoe)   치마다 반지름 67.4 mm에 3점 (슈 면적 8.7 mm²)
  요크       반지름 87.5~100 mm를 3단 × 24각(90° 구간)
  회전자     한 극(45°)을 극 좌표 격자(반지름 8단 × 24각)로 읽고 구멍(자석·공기)에 들어가는 점은 뺀다. 회전자 좌표계에서 고정된 점이다.
고정자 영역은 90° 구간의 값이므로 전체는 ×4, 회전자는 한 극이므로 ×8이다(N·S극과 위치 대칭을 가정).
시간 간격: 한 전기 주기를 60 위치(회전자 1.5° 간격, 전기각 6°)로 나눈다. 슬롯 고조파 23·25차까지 보이는 간격이다.
메시는 중간 크기(요소 약 11만 개). 요소별 값이라 치 안쪽 B에는 요소 크기 만큼의 불확실성이 있다(docs/validation_report.md).
실행: FEMMCLI=<femmcli> python femm/example_iron_run.py
"""
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from matplotlib.path import Path as MPath

sys.path.insert(0, str(Path(__file__).parent))
import example_motor as em  # noqa: E402
import example_motor_run as run  # noqa: E402
import prius_run as pr  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BETA_DEG = 41.0
N_POS = 60
MESHES = {"medium": {"stator": 2.0e-3, "rotor": 1.4e-3, "magnet": 1.4e-3, "slot": 3.0e-3, "gap": 0.3e-3},
          "fine": {"stator": 1.4e-3, "rotor": 1.0e-3, "magnet": 1.0e-3, "slot": 2.5e-3, "gap": 0.2e-3, "arc_deg": 0.25}}
MESH_NAME = os.environ.get("IRON_MESH", "medium")        # 메시 민감도: medium(기본) 또는 fine
DENS = int(os.environ.get("IRON_DENSITY", "1"))           # 점 밀도 배수: 1(기본) 또는 2 (반지름·각도 점 수를 두 배)
MESH = MESHES[MESH_NAME]
OUT = ROOT / "data" / "fea" / ("example_motor_iron_probes.npz" if (MESH_NAME, DENS) == ("medium", 1)
                               else f"example_motor_iron_probes_{MESH_NAME}_d{DENS}.npz")
MM = 1e-3


def stator_points():
    """(좌표 [m], 면적 가중치 [m²], 영역 이름 배열). 영역: 0 치, 1 슈, 2 요크."""
    pts, area, reg = [], [], []
    pitch = math.radians(7.5)
    n_rad, n_w = 6 * DENS, 3 if DENS == 1 else 5
    dr = 18.0 / n_rad
    for j in range(12):
        c = j * pitch
        u, v = complex(math.cos(c), math.sin(c)), complex(-math.sin(c), math.cos(c))
        for k in range(n_rad):
            r = 68.0 + dr * (k + 0.5)
            for i in range(n_w):
                off = -2.9 + 5.8 * (i + 0.5) / n_w
                pts.append((r * u + off * v) * MM)
                area.append((5.8 / n_w) * dr * MM * MM)
                reg.append(0)
        for i in range(n_w):                                                    # 슈: 치 중심선 기준 가로 n_w점
            off = -2.9 + 5.8 * (i + 0.5) / n_w
            pts.append((67.4 * u + off * v) * MM)
            area.append(8.7 / n_w * MM * MM)
            reg.append(1)
    r_edges = np.linspace(87.5, 100.0, 3 * DENS + 1)
    n_phi = 24 * DENS
    dphi = math.radians(90.0 / n_phi)
    for a, b in zip(r_edges[:-1], r_edges[1:]):
        r = 0.5 * (a + b)
        for i in range(n_phi):
            phi = (i + 0.5) * dphi
            pts.append(r * complex(math.cos(phi), math.sin(phi)) * MM)
            area.append(0.5 * (b * b - a * a) * dphi * MM * MM)
            reg.append(2)
    return np.array(pts), np.array(area), np.array(reg)


def rotor_points_local():
    """회전자 한 극의 점(극 국부 좌표, d축 = +x) [m], 면적 [m²]. 구멍 안의 점은 제외."""
    z = {k: v for k, v in em.rotor_points().items()}
    hole1 = [z[f"Z{k}"] for k in (1, 2, 3, 4, 5, 17, 6, 7, 8)]
    up = [z[f"Z{k}"] for k in (12, 13, 14, 15, 9, 10, 11)]
    hole2 = up + [p.conjugate() for p in reversed(up)]
    polys = [MPath([(p.real, p.imag) for p in h]) for h in (hole1, [p.conjugate() for p in hole1], hole2)]
    r_edges = np.array([25.0, 31.0, 38.0, 46.0, 54.0, 60.0, 63.0, 64.5, 66.0])
    if DENS > 1:                                                                # 각 구간을 DENS등분
        r_edges = np.concatenate([np.linspace(a, b, DENS, endpoint=False) for a, b in zip(r_edges[:-1], r_edges[1:])] + [[66.0]])
    n_ang = 24 * DENS
    dphi = math.radians(45.0 / n_ang)
    pts, area = [], []
    for a, b in zip(r_edges[:-1], r_edges[1:]):
        r = 0.5 * (a + b)
        for i in range(n_ang):
            phi = -math.radians(22.5) + (i + 0.5) * dphi
            p = r * complex(math.cos(phi), math.sin(phi))
            if any(poly.contains_point((p.real, p.imag)) for poly in polys):
                continue
            pts.append(p * MM)
            area.append(0.5 * (b * b - a * a) * dphi * MM * MM)
    return np.array(pts), np.array(area)


def main() -> None:
    th0 = run.theta0_rad()
    br, mur, steel = run.VARIANTS["nominal"]
    sp, sa, sr = stator_points()
    rp, ra = rotor_points_local()
    b = math.radians(BETA_DEG)
    id_, iq = -run.I_PK * math.sin(b), run.I_PK * math.cos(b)
    positions = [90.0 * k / N_POS for k in range(N_POS)]

    def one(r_deg: float):
        r0 = math.radians(r_deg)
        th = th0 + 4 * r0
        ia, ib, ic = pr.inverse_park(np.array([id_]), np.array([iq]), np.array([th]))[0]
        rglob = rp * np.exp(1j * r0)                                         # 회전자 점은 회전자와 함께 돈다 (극 0, d축 각 = r0)
        probes = list(sp) + list(rglob)
        res = em.solve_one((float(ia), float(ib), float(ic)), r_deg, br, mur, steel, mesh=MESH, probes=probes)
        return res["B_xy_T"], res["torque_Nm"]
    with ThreadPoolExecutor(max_workers=run.JOBS) as ex:
        out = list(ex.map(one, positions))
    B = np.stack([o[0] for o in out])                                          # (위치, 점, 2)
    np.savez_compressed(OUT, positions_deg=np.array(positions), B_xy_T=B.astype(np.float32), torque_Nm=np.array([o[1] for o in out]),
                        stator_area_m2=sa, stator_region=sr, rotor_area_m2=ra, n_stator=len(sp),
                        info="B at probe points; stator region 0 tooth, 1 shoe, 2 yoke; weights are 90-degree stator sector and one rotor pole")
    print("done", B.shape)


if __name__ == "__main__":
    main()
