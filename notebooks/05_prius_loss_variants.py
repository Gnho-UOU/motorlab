"""V4 효율: 손실 모델 변형 세 가지를 같은 동작점에서 ORNL Table B-1 실측 효율과 비교한다. (docs/validation_report.md)

배경: TM-423의 '모터 로터 손실'(표 3.7)은 로터를 낀 구성에서 로터를 뺀 구성을 뺀 값이다. 로터가 있으면 고정자 철심에 자석 자속이 걸리므로
이 값에는 **무부하 철손이 이미 들어 있다**. 03번 노트북은 이 값을 기계손으로 쓰고 철손(강판 데이터 피팅)을 또 더했으므로 무부하 손실을
약 2배(속도 전 구간 1.7~2.5배)로 센다. 여기서는 그 이중 계산을 없앤 변형과, 그래도 남는 부하 손실을 경험식으로 본 변형을 비교한다.

변형:
  V0  이전 모델       : 동손 + 철손(M400-50A 피팅) + 기계손(표 3.7 피팅)         <- 03번 노트북과 같다
  V1  이중 계산 제거  : 동손 + 무부하 실측 손실(표 3.7 피팅 하나로 철손·기계손 포함)
  V2  V1 + 잔여 손실  : V1 + k_f·f + k_c·Is_rms²·f²   (**경험식**: 계수는 이 벤치마크의 행에 맞춘 값, 물리 기구는 미규명)
V2는 보정 모델이다. 과적합을 막으려고 (a) 행을 무작위 반으로 나눠 반으로 맞추고 나머지 반으로 평가(20회 반복),
(b) 3000 rpm 미만 행으로 맞추고 3000 rpm 이상 행으로 평가(외삽)한 오차를 함께 보인다.

출력: data/fea/prius2004_efficiency_variants.csv (행별 동작점과 변형별 효율), data/fea/prius2004_excess_loss_fit.json (V2 계수와 검증 결과)
실행: python notebooks/05_prius_loss_variants.py [자속맵.csv]   (기본: ORNL 형상 자속 맵, 약 1분)
"""
from __future__ import annotations

import dataclasses
import importlib.util
import json
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
from engine.losses import loss_breakdown  # noqa: E402
from engine.model import FluxMapModel  # noqa: E402
from engine.operating import Limits, optimal_current  # noqa: E402

MAP = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "flux_maps" / "prius2004_fullmodel_teardown_25A.csv"
OUT = ROOT / "data" / "fea" / "prius2004_efficiency_variants.csv"
OUT_JSON = ROOT / "data" / "fea" / "prius2004_excess_loss_fit.json"
_model: FluxMapModel | None = None


def _init() -> None:
    global _model
    _model = FluxMapModel.from_csv(MAP, p=eff.P, Rs=0.0)


def solve_row(args):
    sp, T, Tst, Vdc = args
    w = sp * math.pi / 30
    m = dataclasses.replace(_model, Rs=eff.R20 * (1 + eff.ALPHA_CU * (Tst - 20)))
    T_em = T + float(eff.MECH.a * w + eff.MECH.b * w ** 3) / w
    return optimal_current(m, Limits(Imax=250.0, Vdc=Vdc, k_mod=2 / math.pi), T_em, w)


def evaluate(c, rows, d, q, model, iron):
    """행마다 효율. iron=None이면 철손 없음(V1). 반환 열: eta, P_cu, P_fe, P_mech, |Is|_rms."""
    out = []
    for k, i in enumerate(rows):
        m = dataclasses.replace(model, Rs=eff.R20 * (1 + eff.ALPHA_CU * (c["T_stator_C"][i] - 20)))
        w = c["speed_rpm"][i] * math.pi / 30
        lb = loss_breakdown(m, d[k], q[k], w, iron, eff.MECH)
        out.append((float(lb.eta), float(lb.P_cu), float(lb.P_fe), float(lb.P_mech), math.hypot(d[k], q[k]) / math.sqrt(2)))
    return np.array(out)


def report(label, d_eta, sp, T):
    core = (sp >= 1000) & (sp <= 4000) & (T >= 30) & (T <= 200)
    print(f"{label:34s} 전체 {d_eta.mean():+5.2f}%p (RMS {np.sqrt((d_eta ** 2).mean()):4.2f}) | 주요영역 {d_eta[core].mean():+5.2f} "
          f"(|Δ|<=3%p {np.mean(np.abs(d_eta[core]) <= 3) * 100:3.0f}%) | 고속(>=4000) {d_eta[sp >= 4000].mean():+5.2f}")


def main() -> None:
    c = eff.load_perf()
    sel = np.nonzero(c["speed_rpm"] >= 500)[0]
    args = [(c["speed_rpm"][k], c["torque_Nm"][k], c["T_stator_C"][k], c["Vdc_V"][k]) for k in sel]
    with ProcessPoolExecutor(max_workers=8, initializer=_init) as ex:
        res = list(ex.map(solve_row, args, chunksize=4))
    ok = np.array([r[2] for r in res], bool)
    d, q = np.array([r[0] for r in res])[ok], np.array([r[1] for r in res])[ok]
    rows = sel[ok]
    model = FluxMapModel.from_csv(MAP, p=eff.P, Rs=0.0)
    print(f"맵 {MAP.name}: {len(sel)}행 중 {ok.sum()}행 실행 가능")
    sp, Pm, Pac, Tq = (c[k][rows] for k in ("speed_rpm", "P_mech_W", "P_ac_W", "torque_Nm"))
    eta_meas = c["eta_motor"][rows]
    f = eff.P * sp / 60
    v0 = evaluate(c, rows, d, q, model, eff.IRON)
    v1 = evaluate(c, rows, d, q, model, None)
    report("V0 이전(철손 + 기계손 이중)", (v0[:, 0] - eta_meas) * 100, sp, Tq)
    report("V1 이중 계산 제거", (v1[:, 0] - eta_meas) * 100, sp, Tq)

    # V2: 잔여 손실 = (측정 총손실) - (V1이 말하는 손실). 모델 동작점의 전류를 쓴다(측정 전류가 아니라).
    loss_v1 = Pm / v1[:, 0] - Pm
    resid = (Pac - Pm) - loss_v1
    X = np.c_[f, v1[:, 4] ** 2 * f ** 2]
    sc = np.abs(X).max(axis=0)
    wt = 1.0 / Pm                       # 잔차를 샤프트 출력으로 나눠 맞춘다: 효율 오차(Δη ≈ -η·Δ손실/P_mech)에 가깝게 가중
    fit = lambda m: np.linalg.lstsq((X / sc)[m] * wt[m, None], resid[m] * wt[m], rcond=None)[0] / sc
    coef = fit(np.ones(len(sp), bool))

    def eta_with(cf, idx=slice(None)):
        return Pm[idx] / (Pm[idx] + loss_v1[idx] + X[idx] @ cf)

    report("V2 V1 + k_f·f + k_c·I²f² (전체 행)", (eta_with(coef) - eta_meas) * 100, sp, Tq)
    print(f"   k_f = {coef[0]:.4g} W/Hz, k_c = {coef[1]:.4g} W/(A²·Hz²)  (Is는 모델 동작점의 상 실효 전류)")
    rng = np.random.default_rng(0)
    errs = []
    for _ in range(20):
        m = rng.random(len(sp)) < 0.5
        cf = fit(m)
        errs.append(np.sqrt((((eta_with(cf) - eta_meas) * 100)[~m] ** 2).mean()))
    print(f"   무작위 반으로 맞추고 나머지 반 평가(20회): RMS {np.mean(errs):.2f}%p (범위 {np.min(errs):.2f}~{np.max(errs):.2f})")
    lo = sp < 3000
    cf = fit(lo)
    de = ((eta_with(cf) - eta_meas) * 100)[~lo]
    print(f"   3000 rpm 미만으로 맞추고 이상 행 평가(외삽, {int((~lo).sum())}행): 평균 {de.mean():+.2f}, RMS {np.sqrt((de ** 2).mean()):.2f}%p")
    print(f"   훈련 계수(3000 rpm 미만): k_f = {cf[0]:.4g}, k_c = {cf[1]:.4g}")

    OUT.parent.mkdir(exist_ok=True)
    eta_v2 = eta_with(coef)
    rowsout = ["speed_rpm,torque_Nm,T_stator_C,id_A,iq_A,eta_meas,eta_v0,eta_v1,eta_v2,P_cu_W,P_nl_W,P_excess_W"]
    for k, i in enumerate(rows):
        rowsout.append(f"{c['speed_rpm'][i]:g},{c['torque_Nm'][i]:g},{c['T_stator_C'][i]:g},{d[k]:.3f},{q[k]:.3f},{eta_meas[k]:.4f},"
                       f"{v0[k, 0]:.4f},{v1[k, 0]:.4f},{eta_v2[k]:.4f},{v1[k, 1]:.1f},{v1[k, 3]:.1f},{(X @ coef)[k]:.1f}")
    OUT.write_text("\n".join(rowsout) + "\n")
    core = (sp >= 1000) & (sp <= 4000) & (Tq >= 30) & (Tq <= 200)
    dE = (eta_v2 - eta_meas) * 100
    OUT_JSON.write_text(json.dumps({
        "what": "경험적 잔여 손실 P = k_f·f + k_c·Is_rms²·f² 의 계수 (물리 기구 미규명, ORNL Table B-1 효율 행에 맞춘 값)",
        "k_f_W_per_Hz": float(coef[0]), "k_c_W_per_A2Hz2": float(coef[1]),
        "fit": {"flux_map": MAP.name, "rows": int(len(sp)), "weights": "1/P_mech(측정 샤프트 출력)", "baseline_loss": "동손(R20 = 68.7 mΩ, α = 0.00393) + 무부하 실측 손실(TM-423 표 3.7 피팅)",
                "Is_rms": "모델 동작점(전류 최소)의 |Is|/√2, 측정 전류가 아님"},
        "validation": {"all_rows_mean_delta_eta_pp": float(dE.mean()), "all_rows_rms_pp": float(np.sqrt((dE ** 2).mean())),
                       "core_region_mean_pp": float(dE[core].mean()), "core_region_within_3pp": float(np.mean(np.abs(dE[core]) <= 3)),
                       "random_half_holdout_rms_pp": float(np.mean(errs)), "extrapolate_lt3000_to_ge3000_rms_pp": float(np.sqrt((de ** 2).mean()))},
        "limits": f"ORNL 시험의 속도·전류 범위(500~6100 rpm, 250 A 이하) 안에서만 쓴다. 3000 rpm 미만 행만으로 맞춘 계수는 그 이상 속도에서 평균 {de.mean():+.1f}%p 편향된다(k_c 항을 식별하지 못함).",
        "script": "notebooks/05_prius_loss_variants.py"}, ensure_ascii=False, indent=1) + "\n")
    print("->", OUT, "\n->", OUT_JSON)


if __name__ == "__main__":
    main()
