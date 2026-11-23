"""P4: 2004 Prius 모터(MG2)의 주행 사이클 전비. (docs/validation_report.md "전비")

계산 대상은 **모터 입력(교류) 기준 전기 에너지**다. 실제 Prius는 엔진을 같이 쓰므로 이 값은 "이 모터와 차량 값으로 순수 전기 구동을 가정한 환산 전비"이고
실제 Prius의 연비가 아니다. 인버터·배터리·보조 부하는 포함하지 않는다.

모델 두 가지를 같이 보인다(데이터 검증 결과에 맞춰 편차를 숨기지 않기 위해):
  물리 모델 : 동손(R = 0.069 Ω @21 °C, 온도 보정) + 기계·무부하 철손(TM-423 표 3.7 피팅) + 기어 무부하 손실
  경험식 포함: 위에 같은 벤치마크에 맞춘 잔여 손실 k_f·f + k_c·I²·f²를 더한다(G1 충족으로 세지 않는 보정, data/fea/prius2004_excess_loss_fit.json)
검증에서 물리 모델은 주요 영역(1000~4000 rpm)의 효율을 +3.7%p, 4000 rpm 이상에서 약 +10%p 높게 예측했다.
권선 온도는 시나리오 값이다(ORNL 효율 시험의 권선 온도는 70~190 °C).
실행: python notebooks/10_prius_fuel_economy.py   (약 3분, 그림은 notebooks/figures/)
"""
import dataclasses
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("eff", ROOT / "notebooks" / "03_prius_efficiency_validation.py")
eff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eff)
from engine.losses import ExcessLossParams, efficiency_map  # noqa: E402
from engine.model import FluxMapModel  # noqa: E402
from engine.operating import Limits  # noqa: E402
from engine.vehicle import load_cycle, load_vehicle, run_cycle  # noqa: E402

FIG = ROOT / "notebooks" / "figures"
T_GRID = np.linspace(1.0, 260.0, 130)
W_GRID = np.linspace(2.0, 640.0, 160)
LIMITS = Limits(Imax=250.0, Vdc=500.0, k_mod=2 / math.pi)


def build_map(T_wind_C, with_excess):
    base = FluxMapModel.from_csv(eff.MAP, p=eff.P, Rs=0.0)
    model = dataclasses.replace(base, Rs=eff.R20 * (1 + eff.ALPHA_CU * (T_wind_C - 20)))
    ex = None
    if with_excess:
        j = json.loads((ROOT / "data/fea/prius2004_excess_loss_fit.json").read_text())
        ex = ExcessLossParams(k_f=j["k_f_W_per_Hz"], k_c=j["k_c_W_per_A2Hz2"])
    return efficiency_map(model, LIMITS, T_GRID, W_GRID, None, eff.MECH, ex)


def main() -> None:
    veh = load_vehicle("prius2004")
    cycles = {n: load_cycle(n) for n in ("WLTP", "UDDS", "HWFET")}
    print(f"차량: 등가 질량 {veh.mass_kg:.0f} kg, 도로 부하 {veh.road_a_N:.1f} + {veh.road_b_Ns_m:.3f}·v + {veh.road_c_Ns2_m2:.4f}·v² N")
    print("전비 [km/kWh] (모터 입력 기준, 회생 비율 1 / 0)와 [Wh/km]")
    print(f"{'모델':14s}{'권선 °C':>8s}" + "".join(f"{n:>22s}" for n in cycles))
    results = {}
    for with_excess, label in ((False, "물리 모델"), (True, "경험식 포함")):
        for T in (60, 100, 150):
            em = build_map(T, with_excess)
            row = f"{label:14s}{T:8d}"
            for n, c in cycles.items():
                r1, r0 = run_cycle(veh, em, c, 1.0), run_cycle(veh, em, c, 0.0)
                results[(label, T, n)] = (r1, r0)
                row += f"  {r1.km_per_kWh:5.2f}/{r0.km_per_kWh:5.2f} ({r1.Wh_per_km:3.0f})"
            print(row)
    r, _ = results[("물리 모델", 100, "WLTP")]
    short = r.shortfall_wheel_energy_J / r.E_wheel_traction_J * 100
    print(f"\nWLTP(물리 모델, 100 °C, 회생 1) 에너지 내역 [kWh]: 바퀴 구동 {r.E_wheel_traction_J / 3.6e6:.2f}, 바퀴 제동 {r.E_wheel_brake_J / 3.6e6:.2f}, "
          f"기어 손실(구동) {r.E_gear_loss_traction_J / 3.6e6:.3f}, 모터 손실(구동) {r.E_motor_loss_J / 3.6e6:.3f}, 전기 소비 {r.E_in_J / 3.6e6:.2f}, 회생 {r.E_regen_J / 3.6e6:.2f}, 순 {r.E_net_J / 3.6e6:.2f}")
    print(f"못 낸 구동 에너지 {short:.2f}% ({r.shortfall_time_s:.0f} s)")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams["font.family"] = ["AppleGothic", "Malgun Gothic", "NanumGothic", "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
    except ImportError:
        return
    FIG.mkdir(exist_ok=True)
    em = build_map(100, False)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    cs = ax.contourf(em.speed_grid * 30 / np.pi, em.T_grid, np.where(em.feasible, em.eta * 100, np.nan), levels=np.arange(70, 98, 2), cmap="viridis")
    fig.colorbar(cs, label="모터 효율 [%] (물리 모델, 100 °C)")
    for name, col in (("WLTP", "white"), ("UDDS", "orange"), ("HWFET", "red")):
        rr = results[("물리 모델", 100, name)][0]
        m = rr.em_torque_Nm > 0
        ax.plot(rr.motor_speed_rad[m] * 30 / np.pi, rr.em_torque_Nm[m], ".", ms=2, color=col, label=name)
    ax.set_xlabel("모터 속도 [rpm]")
    ax.set_ylabel("전자기 토크 [N·m]")
    ax.legend(markerscale=4)
    ax.set_title("사이클 구동 동작점과 효율맵")
    fig.tight_layout()
    fig.savefig(FIG / "fuel_economy_operating_points.png", dpi=130)
    print("->", FIG / "fuel_economy_operating_points.png")


if __name__ == "__main__":
    main()
