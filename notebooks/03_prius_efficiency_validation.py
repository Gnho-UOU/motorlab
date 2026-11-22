"""V4: 엔진의 모터 효율을 ORNL Table B-1(428점)의 실측 모터 효율과 비교한다. (기획서 6장 V4, G1)

입력: 자속 맵(data/flux_maps/prius2004_fullmodel_pocket_25A.csv), 철손 계수(M400-50A 손실 데이터 피팅, f <= 400 Hz),
      기계손(TM-423 Table 3.7 모터 로터 손실 피팅), 상저항(저속 고토크 행에서 역산한 R20).
방법: 행마다 (속도, 샤프트 토크)에서 전류 크기를 최소로 하는 동작점(optimal_current)을 풀고 loss_breakdown으로 효율을 구한다.
      전자기 토크는 T_em = T_shaft + P_mech/ω (샤프트 토크에 기계손을 더함). 권선 온도는 행마다 실측 값으로 Rs(T)를 쓴다.
출력: data/fea/prius2004_efficiency_validation_pocket.csv (행별 동작점과 효율), 요약은 표준 출력.

이 노트북은 V0(철손 + 기계손 이중 계산) 모델이다. 이중 계산을 없앤 변형은 05번 노트북. 04번이 여기 상수(MAP, IRON, MECH)를 가져다 쓴다.

모터 효율의 정의(ORNL): η = P_mech / P_ac (샤프트 기계 출력 / 인버터 출력 = 모터 입력 전력). 인버터 손실은 포함하지 않는다.
실행: python notebooks/03_prius_efficiency_validation.py   (약 수 분, 프로세스 병렬)
"""
from __future__ import annotations

import dataclasses
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.losses import IronParams, MechParams, loss_breakdown  # noqa: E402
from engine.model import FluxMapModel  # noqa: E402
from engine.operating import Limits, optimal_current  # noqa: E402

MAP = ROOT / "data" / "flux_maps" / "prius2004_fullmodel_pocket_25A.csv"        # 포켓 가설 형상, Br 보정 없음 (docs/FEA_OPTIONS.md 3-6절)
PERF = ROOT / "data" / "benchmarks" / "prius2004_perf_map.csv"
OUT = ROOT / "data" / "fea" / "prius2004_efficiency_validation_pocket.csv"      # 구형상 결과(prius2004_efficiency_validation.csv)는 덮어쓰지 않는다

ALPHA_CU = 0.00393                       # 구리 저항 온도계수 [1/K] (pyleecan Copper1)
R20 = 0.065                              # [Ω] 저속(< 400 rpm) 고토크 17행에서 역산 (중앙값). 기하 추정은 0.049~0.056
IRON = IronParams(k_h=0.02411, k_e=1.769e-4, beta=1.736, m_tooth=6.52, m_yoke=9.26, c_tooth=6.14, c_yoke=4.62)
MECH = MechParams(a=0.44058, b=7.7652e-7)   # TM-423 Table 3.7 모터 로터 손실 피팅 (윤활유 25 °C)
P = 4

_model: FluxMapModel | None = None


def load_perf() -> dict[str, np.ndarray]:
    lines = [l for l in PERF.read_text().splitlines() if l.strip() and not l.startswith("#")]
    A = np.loadtxt(lines[1:], delimiter=",")
    return {h: A[:, i] for i, h in enumerate(lines[0].strip().split(","))}


def _init() -> None:
    global _model
    _model = FluxMapModel.from_csv(MAP, p=P, Rs=0.0)


def solve_row(args: tuple[float, float, float, float]) -> tuple[float, float, bool]:
    speed_rpm, T_shaft, T_st, Vdc = args
    w = speed_rpm * math.pi / 30
    Rs = R20 * (1 + ALPHA_CU * (T_st - 20))
    m = dataclasses.replace(_model, Rs=Rs)
    T_em = T_shaft + float(MECH.a * w + MECH.b * w ** 3) / w
    d, q, ok = optimal_current(m, Limits(Imax=250.0, Vdc=Vdc, k_mod=2 / math.pi), T_em, w)
    return d, q, bool(ok)


def efficiency(d, q, speed_rpm, T_st, iron=IRON, mech=MECH, r20=R20, model=None):
    model = model or FluxMapModel.from_csv(MAP, p=P, Rs=0.0)
    w = np.asarray(speed_rpm) * math.pi / 30
    out = []
    for i in range(len(w)):
        m = dataclasses.replace(model, Rs=r20 * (1 + ALPHA_CU * (T_st[i] - 20)))
        lb = loss_breakdown(m, d[i], q[i], w[i], iron, mech)
        out.append((float(lb.eta), float(lb.P_cu), float(lb.P_fe), float(lb.P_mech)))
    return np.array(out)


def main() -> None:
    c = load_perf()
    sel = np.nonzero(c["speed_rpm"] >= 500)[0]               # 저속(< 500 rpm)은 R20 역산에 썼으므로 검증에서 제외
    args = [(c["speed_rpm"][k], c["torque_Nm"][k], c["T_stator_C"][k], c["Vdc_V"][k]) for k in sel]
    with ProcessPoolExecutor(max_workers=8, initializer=_init) as ex:
        res = list(ex.map(solve_row, args, chunksize=4))
    d = np.array([r[0] for r in res]); q = np.array([r[1] for r in res]); ok = np.array([r[2] for r in res])
    print(f"{len(sel)}행 중 엔진이 풀 수 있는 행 {ok.sum()}개 (나머지는 전류 250 A 또는 전압 한계 밖)")
    model = FluxMapModel.from_csv(MAP, p=P, Rs=0.0)
    s = sel[ok]
    r = efficiency(d[ok], q[ok], c["speed_rpm"][s], c["T_stator_C"][s], model=model)
    eta_meas = c["eta_motor"][s]
    lines = ["speed_rpm,torque_Nm,T_stator_C,id_A,iq_A,eta_meas,eta_model,P_cu_W,P_fe_W,P_mech_W"]
    for k, i in enumerate(s):
        lines.append(f"{c['speed_rpm'][i]:g},{c['torque_Nm'][i]:g},{c['T_stator_C'][i]:g},{d[ok][k]:.3f},{q[ok][k]:.3f},"
                     f"{eta_meas[k]:.4f},{r[k,0]:.4f},{r[k,1]:.1f},{r[k,2]:.1f},{r[k,3]:.1f}")
    OUT.write_text("\n".join(lines) + "\n")
    print("->", OUT)


if __name__ == "__main__":
    main()
