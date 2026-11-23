"""M5: 자석 소재·온도에 따른 토크·효율·전비 변화와 감자 판정 (Prius 형상에 가정한 소재).

방법: 기준 맵(Br 1.06 T 보정값)에 소재의 Br(T)를 넣은 새 자속 맵을 만든다(engine.magnet.map_for_magnet: 기준 맵 + 가정 맵 Br 1.00·1.40 T 보간,
FEA 점검에서 ψd 최대 오차 약 mWb 단위, docs/validation_report.md). 전류·전압 한계는 ORNL 시험값(250 A, 500 V, 육각파), 손실은 물리 모델
(동손 R = 0.069 Ω @21 °C 온도 보정 + 기계·무부하 철손 TM-423 피팅)이다. 자석이 바뀌면 무부하 철손도 달라지지만 이 모델은 Prius 자석으로 잰
기계손 곡선을 그대로 쓴다(한계). 감자 판정은 femm/demag_check.py의 FEA 결과(MTPA 250 A와 순수 −d 250 A)와 engine/magnet.py의 무릎점 Hk(T)이다.
모터 입력 기준 전비, 순수 전기 구동 환산이다(notebooks/10과 같은 정의). 권선 온도 100 °C, 회생 비율 1.
실행: python notebooks/13_prius_magnet_compare.py   (효율맵 소재마다 약 2초, 전체 1분 안팎)
"""
import csv
import dataclasses
import importlib.util
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("eff", ROOT / "notebooks" / "03_prius_efficiency_validation.py")
eff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eff)
from engine.losses import efficiency_map  # noqa: E402
from engine.magnet import load_grade, map_for_magnet  # noqa: E402
from engine.model import FluxMapModel  # noqa: E402
from engine.operating import Limits, base_speed, max_torque_curve, mtpa_point  # noqa: E402
from engine.vehicle import load_cycle, load_vehicle, run_cycle  # noqa: E402

FM = ROOT / "data" / "flux_maps"
BASE = FluxMapModel.from_csv(eff.MAP, p=eff.P, Rs=0.0)
LO = FluxMapModel.from_csv(FM / "prius2004_fullmodel_Br100_mur104_50A.csv", p=eff.P, Rs=0.0)
HI = FluxMapModel.from_csv(FM / "prius2004_fullmodel_Br140_mur104_50A.csv", p=eff.P, Rs=0.0)
LIMITS = Limits(Imax=250.0, Vdc=500.0, k_mod=2 / math.pi)
T_GRID, W_GRID = np.linspace(1.0, 260.0, 130), np.linspace(2.0, 640.0, 160)
T_WIND = 100.0
VARIANTS = [("기준(Br 1.06 보정값)", None, None), ("N45SH", 20.0, "N45SH"), ("N45SH", 100.0, "N45SH"), ("N45SH", 150.0, "N45SH"),
            ("N38UH", 20.0, "N38UH"), ("N38UH", 100.0, "N38UH"), ("N38UH", 150.0, "N38UH"), ("N38UH", 180.0, "N38UH")]


def demag_rows():
    rows = list(csv.DictReader(open(ROOT / "data" / "fea" / "prius2004_demag_check.csv")))
    return {(r["grade"], float(r["T_C"]), r["state"]): r for r in rows}


def main() -> None:
    veh = load_vehicle("prius2004")
    cyc = {n: load_cycle(n) for n in ("WLTP", "UDDS", "HWFET")}
    demag = demag_rows()
    print("| 자석 | T [°C] | Br [T] | ψm [Wb] | 250 A MTPA 토크 [N·m] | 기저속도 [rpm] | 6000 rpm 최대 토크 [N·m] | WLTP [km/kWh] | UDDS | HWFET | 감자 여유(MTPA 250 A) | 감자 여유(−d 250 A) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name, T, grade in VARIANTS:
        if grade is None:
            model, br = BASE, 1.06
        else:
            g = load_grade(grade)
            br = g.br(T)
            model = map_for_magnet(BASE, LO, HI, 1.00, 1.40, br)
        model = dataclasses.replace(model, Rs=eff.R20 * (1 + eff.ALPHA_CU * (T_WIND - 20)))
        psi_m = float(model.flux(0.0, 0.0)[0])
        d, q = mtpa_point(model, LIMITS.Imax)
        t250 = float(model.torque(d, q))
        nb = base_speed(model, LIMITS) * 30 / math.pi
        tab = max_torque_curve(model, LIMITS, np.array([6000 * math.pi / 30]))
        t6000 = float(tab.T_max[0])
        em = efficiency_map(model, LIMITS, T_GRID, W_GRID, None, eff.MECH, None)
        km = [run_cycle(veh, em, c, 1.0).km_per_kWh for c in cyc.values()]
        if grade is None:
            m1 = m2 = "-"
        else:
            g = load_grade(grade)
            m1 = f"{g.demag_margin(float(demag[(grade, T, 'mtpa250')]['H_demag_max_kApm']), T):+.2f}"
            m2 = f"{g.demag_margin(float(demag[(grade, T, 'd_axis_250')]['H_demag_max_kApm']), T):+.2f}"
        print(f"| {name} | {'-' if T is None else int(T)} | {br:.3f} | {psi_m:.3f} | {t250:.0f} | {nb:.0f} | {t6000:.0f} | "
              f"{km[0]:.2f} | {km[1]:.2f} | {km[2]:.2f} | {m1} | {m2} |", flush=True)


if __name__ == "__main__":
    main()
