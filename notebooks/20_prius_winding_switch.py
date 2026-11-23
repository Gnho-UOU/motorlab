"""M8 권선 전환 가정 계산: 2004 Prius 모터(물리 모델, 같은 자속 맵)에 턴 수 비 a의 결선을 추가했을 때의 효과.

가정이다: 실제 Prius는 결선을 바꾸지 않는다. "이 모터에 직렬/병렬 또는 Y/Δ 전환이 있다면 어디서 이득이고 사이클 전비가 얼마나 달라지나"를 같은 철심·자석, 같은 인버터(Imax 250 A, Vdc 500 V)로 계산한다.
기준 결선 = 실제 Prius(직렬). a = 1/2: 2병렬로 전환(턴 수 절반), a = 1/√3: Y → Δ와 같은 단자 효과. 전환 전략은 셀마다 입력 전력이 작은 결선을 고르는 상한(전환 손실·히스테리시스 없음).
(유도: docs/derivations.md 16절). 효율맵·사이클 입력은 notebooks/10과 같다(권선 100 °C 저항, 물리 모델, 회생 비율 1).
실행: python notebooks/20_prius_winding_switch.py (약 5분)
"""
import dataclasses
import importlib.util
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.model import FluxMapModel  # noqa: E402
from engine.operating import max_torque_curve  # noqa: E402
from engine.vehicle import load_cycle, load_vehicle, run_cycle  # noqa: E402
from engine.winding import compare_windings, reconfigure  # noqa: E402

_spec = importlib.util.spec_from_file_location("fe", ROOT / "notebooks" / "10_prius_fuel_economy.py")
fe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fe)


def main() -> None:
    veh = load_vehicle("prius2004")
    base = FluxMapModel.from_csv(fe.eff.MAP, p=fe.eff.P, Rs=0.0)
    model = dataclasses.replace(base, Rs=fe.eff.R20 * (1 + fe.eff.ALPHA_CU * (100 - 20)))
    cycles = {n: load_cycle(n) for n in ("WLTP", "UDDS", "HWFET")}
    for a, label in ((0.5, "2병렬 (a = 1/2)"), (1 / math.sqrt(3), "Y → Δ (a = 1/√3)"), (0.75, "a = 3/4 (탭 전환)")):
        c = compare_windings(model, fe.LIMITS, a, fe.T_GRID, fe.W_GRID, None, fe.eff.MECH)
        sp_rpm = fe.W_GRID * 30 / math.pi
        ext = np.linspace(20.0, 1000.0, 99)                                            # 최대 속도 비교용 확장 격자 [rad/s]
        tb_ext = max_torque_curve(model, fe.LIMITS, ext).T_max
        to_ext = max_torque_curve(reconfigure(model, a), c.limits_other, ext).T_max
        print(f"\n## {label}")
        e_rpm = ext * 30 / math.pi
        print("최대 토크 [N·m] (Imax 250 A, Vdc 500 V; 이 모터는 ψm < Ld·Imax라 최고 속도 제한이 없고 토크가 속도에 따라 줄어든다)")
        for rpm in (500, 1500, 3000, 5000, 6000, 9000):
            j = int(np.argmin(np.abs(e_rpm - rpm)))
            print(f"  {e_rpm[j]:6.0f} rpm: 기준 {tb_ext[j]:6.1f}, 전환 결선 {to_ext[j]:6.1f}, 최대 출력 기준 {tb_ext[j] * ext[j] / 1000:5.1f} kW, 전환 결선 {to_ext[j] * ext[j] / 1000:5.1f} kW")
        feas_gain = int(c.best.feasible.sum() - c.base.feasible.sum())
        both = c.base.feasible & c.other.feasible
        gain = 100 * (c.base.eta[both] / c.best.eta[both] - 1)
        print(f"실행 가능 셀: 기준 {int(c.base.feasible.sum())}, 전환 결선 {int(c.other.feasible.sum())}, 합집합 {int(c.best.feasible.sum())} (전환으로 {feas_gain}셀 추가)")
        eb, eo = c.base.eta[both], c.best.eta[both]
        print(f"두 결선이 모두 되는 셀 {int(both.sum())}개 중 전환 결선이 더 좋은 셀 {100 * float(np.mean(c.choice[both] == 1)):.0f}%, 그 셀들의 효율 개선 평균 {100 * float(np.mean((eo - eb)[c.choice[both] == 1])) if (c.choice[both] == 1).any() else 0:+.2f}%p")
        print("| 사이클 | 기준 [km/kWh] | 전환 결선만 | 최적 전환 | 개선 | 구동 에너지 중 전환 결선 비율 |")
        print("|---|---|---|---|---|---|")
        for name, cyc in cycles.items():
            rb = run_cycle(veh, c.base, cyc, 1.0)
            ro = run_cycle(veh, c.other, cyc, 1.0)
            rt = run_cycle(veh, c.best, cyc, 1.0)
            w_idx = np.clip(np.searchsorted(c.best.speed_grid, rt.motor_speed_rad), 0, len(c.best.speed_grid) - 1)
            t_idx = np.clip(np.searchsorted(c.best.T_grid, np.abs(rt.em_torque_Nm)), 0, len(c.best.T_grid) - 1)
            ch = c.choice[t_idx, w_idx]
            drv = rt.em_torque_Nm > 0
            frac = float(np.sum(rt.elec_power_W[drv & (ch == 1)] > 0) and np.sum(rt.elec_power_W[drv & (ch == 1)]) / np.sum(rt.elec_power_W[drv]))
            print(f"| {name} | {rb.km_per_kWh:.2f} | {ro.km_per_kWh:.2f} | {rt.km_per_kWh:.2f} | {100 * (rt.km_per_kWh / rb.km_per_kWh - 1):+.2f} % | {100 * frac:.0f} % |")


if __name__ == "__main__":
    main()
