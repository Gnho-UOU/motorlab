"""동작점 선택 방식(전류 최소 대 효율 최적)이 ORNL 실측과의 비교를 얼마나 바꾸는지 본다. (docs/validation_report.md)

ORNL 시험 제어기는 같은 토크·속도에서 id를 바꿔 가며 효율이 가장 높은 점을 골랐다. 엔진의 기본 동작점은 전류 최소다. 철손이 크면
효율 최적점은 약계자가 더 깊어 전류가 커지므로, 고속 필요 전류 과소 예측(엔진/측정 0.77)이 이 차이에서 올 수 있다.

비교하는 경우:
  전류 최소         : optimal_current(objective="current")  (기존)
  효율 최적, 철손 x1: 최적화에 쓰는 철손 = 피팅한 값 그대로
  효율 최적, 철손 xN: 최적화에 쓰는 철손만 N배 (진단용: 모델에 없는 손실이 있다면 제어기는 더 깊은 약계자를 골랐을 것)
효율은 항상 피팅한 철손으로 평가한다(최적화에 쓴 철손과 평가에 쓰는 철손을 섞지 않는다).
실행: python notebooks/04_prius_operating_point_objective.py
"""
from __future__ import annotations

import dataclasses
import importlib.util
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("eff", ROOT / "notebooks" / "03_prius_efficiency_validation.py")
eff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eff)
from engine.losses import loss_objective  # noqa: E402
from engine.model import FluxMapModel  # noqa: E402
from engine.operating import Limits, optimal_current  # noqa: E402

_model: FluxMapModel | None = None


def _init() -> None:
    global _model
    _model = FluxMapModel.from_csv(eff.MAP, p=eff.P, Rs=0.0)


def solve(args):
    sp, T, Tst, Vdc, objective, iron_scale = args
    w = sp * math.pi / 30
    m = dataclasses.replace(_model, Rs=eff.R20 * (1 + eff.ALPHA_CU * (Tst - 20)))
    T_em = T + float(eff.MECH.a * w + eff.MECH.b * w ** 3) / w
    lim = Limits(Imax=250.0, Vdc=Vdc, k_mod=2 / math.pi)
    if objective == "current":
        return optimal_current(m, lim, T_em, w)
    iron = dataclasses.replace(eff.IRON, k_h=eff.IRON.k_h * iron_scale, k_e=eff.IRON.k_e * iron_scale)
    return optimal_current(m, lim, T_em, w, objective="loss", loss_fn=loss_objective(m, w, iron))


def run(c, rows, objective, iron_scale):
    args = [(c["speed_rpm"][k], c["torque_Nm"][k], c["T_stator_C"][k], c["Vdc_V"][k], objective, iron_scale) for k in rows]
    with ProcessPoolExecutor(max_workers=8, initializer=_init) as ex:
        res = list(ex.map(solve, args, chunksize=4))
    return (np.array([r[0] for r in res]), np.array([r[1] for r in res]), np.array([r[2] for r in res], bool))


def summarize(c, label, d, q, ok, rows, model):
    sp, T, Tst = c["speed_rpm"][rows], c["torque_Nm"][rows], c["T_stator_C"][rows]
    r = eff.efficiency(d, q, sp, Tst, iron=eff.IRON, model=model)
    dE = (r[:, 0] - c["eta_motor"][rows]) * 100
    ratio = np.hypot(d, q) / (c["Iac_rms_A"][rows] * math.sqrt(2))
    lo, hi = sp < 1950, sp > 2400
    core = (sp >= 1000) & (sp <= 4000) & (T >= 30) & (T <= 200)
    print(f"{label:30s} {ok.sum():3d}행 | 필요 전류 엔진/측정: 저속 {np.median(ratio[lo]):.2f}, 고속 {np.median(ratio[hi]):.2f} "
          f"({ratio[hi].min():.2f}~{ratio[hi].max():.2f}) | Δη 전체 {dE.mean():+5.2f}, 주요 {dE[core].mean():+5.2f}, "
          f"고속(>=4000) {dE[sp >= 4000].mean():+5.2f} %p", flush=True)
    return dE, ratio


def main() -> None:
    c = eff.load_perf()
    sel = np.nonzero(c["speed_rpm"] >= 500)[0]
    model = FluxMapModel.from_csv(eff.MAP, p=eff.P, Rs=0.0)
    for label, objective, scale in (("전류 최소", "current", 1.0), ("효율 최적, 철손 x1", "loss", 1.0),
                                    ("효율 최적, 최적화 철손 x2", "loss", 2.0), ("효율 최적, 최적화 철손 x3", "loss", 3.0)):
        d, q, ok = run(c, sel, objective, scale)
        summarize(c, label, d[ok], q[ok], ok[ok], sel[ok], model)


if __name__ == "__main__":
    main()
