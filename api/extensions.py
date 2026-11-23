"""P5 확장 API: 자석(M5), 열(M7), 권선 전환(M8), 최적화 파레토(M6). 서버에는 계산식이 없고 engine/의 결과를 돌려준다.

모든 응답에 모델의 한계를 싣는다(CLAUDE.md: 화면의 숫자는 엔진이 계산한 값, 한계는 숨기지 않는다). 입력 범위는 pydantic이 검사한다.
"""
from __future__ import annotations

import csv
import dataclasses
import math
from functools import lru_cache
from typing import Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engine.magnet import load_grade
from engine.operating import Limits
from engine.optimize import hypervolume_2d, pareto_mask
from engine.thermal import cycle_thermal, load_lptn
from engine.vehicle import load_cycle, load_vehicle, run_cycle
from engine.winding import compare_windings

router = APIRouter()

G1_CAVEAT = ("G1 미달 주의: 이 모터 모델은 고속 약계자 영역에서 필요한 전류를 측정보다 적게 예측했다(엔진/측정 약 0.72, docs/validation_report.md). "
             "고속 출력과 효율은 낙관적일 수 있고, 방향(고속 출력 증가, 저속 토크 감소)만 모델 구조에서 나온다.")


def _api():
    import api.main as m          # 순환 import를 피하려고 늦게 가져온다
    return m


def _clean(a):
    a = np.asarray(a, dtype=float)
    return [None if not math.isfinite(x) else float(x) for x in a] if a.ndim == 1 else [_clean(r) for r in a]


# ---------------------------------------------------------------- M5 자석
_GRADES = ("N45SH", "N38UH", "F33", "Y30H-1")
_STATES = {"noload": "무부하", "mtpa250": "MTPA 250 A", "d_axis_250": "순수 −d축 250 A"}


@router.get("/api/magnets")
def magnets():
    out = []
    for name in _GRADES:
        g = load_grade(name)
        p = g.props
        row = {"id": name, "family": p["family"], "maker": p["maker"], "has_demag_curves": g.temps_C is not None,
               "Tmax_C": p["Tmax_C"]["value"], "curve_note": p.get("curve_note"), "by_temperature": []}
        if g.temps_C is not None:
            for T in g.temps_C:
                row["by_temperature"].append({"T_C": float(T), "Br_T": g.br(float(T)), "HcJ_kApm": g.hcj(float(T)), "Hk_kApm": g.hk(float(T)),
                                              "HcB_kApm": g.hcb(float(T)), "mu_r": g.mu_r(float(T))})
        out.append(row)
    return {"grades": out, "notes": {
        "no_curve": "Y30H-1은 감자 곡선 자료를 찾지 못했다(온도계수만 있음). 같은 사양 범위의 F33(제조사 추정 곡선)으로 판정한다.",
        "estimated": "F33의 곡선은 Goudsmit이 낸 추정 곡선(−40, 20, 225 °C)이다. NdFeB 곡선은 Arnold 데이터시트 곡선을 읽은 값이다.",
        "scope": "감자 여유 = 1 − H/Hk (Hk: J = 0.9·Br인 자계). Prius 형상에 소재를 가정해 넣은 FEA 결과(회전자 0° 한 점)다."}}


@lru_cache(maxsize=1)
def _demag_rows():
    from engine.magnet import ROOT
    return list(csv.DictReader(open(ROOT / "data" / "fea" / "prius2004_demag_check.csv")))


@router.get("/api/magnet_demag")
def magnet_demag(grade: str, temperature_C: float = Query(..., ge=-60, le=300), state: str = "mtpa250"):
    if state not in _STATES:
        raise HTTPException(422, f"state는 {sorted(_STATES)} 중 하나")
    try:
        g = load_grade(grade)
    except KeyError as e:
        raise HTTPException(422, str(e))
    rows = [r for r in _demag_rows() if r["grade"] == grade]
    if not rows or g.temps_C is None:
        raise HTTPException(404, f"{grade}: 감자 판정 자료가 없다 (곡선 없음)")
    hit = [r for r in rows if r["state"] == state and abs(float(r["T_C"]) - temperature_C) < 1e-6]
    if not hit:
        temps = sorted({float(r["T_C"]) for r in rows})
        raise HTTPException(404, f"{grade}: FEA를 푼 온도는 {temps} °C뿐이다")
    r = hit[0]
    H = float(r["H_demag_max_kApm"])
    margin = g.demag_margin(H, temperature_C)
    return {"grade": grade, "temperature_C": temperature_C, "state": state, "state_label": _STATES[state], "id_A": float(r["id_A"]), "iq_A": float(r["iq_A"]),
            "Br_T": float(r["Br_T"]), "H_demag_max_kApm": H, "Hk_kApm": g.hk(temperature_C), "margin": margin, "irreversible": bool(margin < 0),
            "caveat": "Prius 형상에 소재를 가정해 넣은 xfemm 결과, 회전자 0° 한 점, 자석 안 74점의 최대 H. 메시가 모서리 첨두를 최대 2.5% 낮게 볼 수 있다."}


# ---------------------------------------------------------------- M7 열
class ThermalReq(BaseModel):
    preset: Literal["prius2004"] = "prius2004"
    cycle: Literal["WLTP", "UDDS", "HWFET"] = "WLTP"
    regen_ratio: float = Field(1.0, ge=0.0, le=1.0)
    boundary_C: float = Field(90.0, ge=-40.0, le=200.0)
    start_C: float | None = Field(None, ge=-40.0, le=200.0)
    Vdc: float = Field(500.0, gt=0, le=1000)
    Imax: float = Field(250.0, gt=0, le=1000)
    map_winding_C: float = Field(100.0, ge=-40, le=250)


@router.post("/api/thermal_cycle")
def thermal_cycle(req: ThermalReq):
    m = _api()
    em, _, mdl, _ = m._build(req.preset, req.Vdc, req.Imax, req.map_winding_C, "physical", 90, 120, 6100.0)
    veh = load_vehicle(m._preset(req.preset)["vehicle"])
    r = run_cycle(veh, em, load_cycle(req.cycle), req.regen_ratio)
    p = load_lptn("prius2004")
    th = cycle_thermal(r, p, req.boundary_C, req.start_C if req.start_C is not None else req.boundary_C, mdl.Rs, req.map_winding_C)
    step = max(1, math.ceil(len(r.t_s) / 2000))
    s = slice(None, None, step)
    return {"cycle": req.cycle, "boundary_C": req.boundary_C, "start_C": req.start_C if req.start_C is not None else req.boundary_C,
            "km_per_kWh_map": r.km_per_kWh, "km_per_kWh_feedback": th["km_per_kWh"], "delta_energy_kWh": th["delta_E_J"] / 3.6e6,
            "winding_max_C": float(np.max(th["T_winding_C"])), "winding_mean_C": float(np.mean(th["T_winding_C"])),
            "series": {"t_s": _clean(r.t_s[s]), "winding_C": _clean(th["T_winding_C"][s]), "stator_C": _clean(th["T_stator_C"][s]), "current_A": _clean(r.current_peak_A[s])},
            "limits": ("2노드(권선·고정자 철심) 열회로와 외부 경계(기름·케이스, 시나리오 값). 자석 온도는 없다. ORNL 900 rpm 시험(권선 65~170 °C)으로 보정했고 "
                       "연속 시험 권선 온도 ±5 K, 첨두 곡선 뺀-하나 RMS 2.6 K 이하다(docs/validation_report.md M7). G_ws는 짧은 시험으로 잘 정해지지 않는다.")}


# ---------------------------------------------------------------- M8 권선 전환
class WindingReq(BaseModel):
    preset: Literal["prius2004"] = "prius2004"
    a: float = Field(0.5, gt=0.2, le=3.0, description="턴 수 비 (2병렬 0.5, Y→Δ 0.577)")
    Vdc: float = Field(500.0, gt=0, le=1000)
    Imax: float = Field(250.0, gt=0, le=1000)
    winding_C: float = Field(100.0, ge=-40, le=250)
    n_torque: int = Field(40, ge=10, le=130)
    n_speed: int = Field(60, ge=10, le=160)
    max_speed_rpm: float = Field(9000.0, gt=1000, le=20000)


@lru_cache(maxsize=8)
def _winding(preset, a, Vdc, Imax, winding_C, n_T, n_w, max_rpm):
    m = _api()
    mdl, lim, mech, _ = m._motor(preset, Vdc, Imax, winding_C, "physical")
    speeds = np.linspace(2.0, max_rpm / m.RPM, n_w)
    T_grid = np.linspace(1.0, 400.0, n_T)
    return compare_windings(mdl, lim, a, T_grid, speeds, None, mech)


@router.post("/api/winding")
def winding(req: WindingReq):
    m = _api()
    c = _winding(req.preset, req.a, req.Vdc, req.Imax, req.winding_C, req.n_torque, req.n_speed, req.max_speed_rpm)
    both = c.base.feasible & c.other.feasible
    return {"a": req.a, "speed_rpm": _clean(c.base.speed_grid * m.RPM), "torque_Nm": _clean(c.base.T_grid),
            "max_torque_base_Nm": _clean(c.tmax_base), "max_torque_other_Nm": _clean(c.tmax_other),
            "feasible_cells": {"base": int(c.base.feasible.sum()), "other": int(c.other.feasible.sum()), "best": int(c.best.feasible.sum()), "total": int(c.best.feasible.size)},
            "other_better_fraction": float(np.mean(c.choice[both] == 1)) if both.any() else None, "choice": c.choice.tolist(),
            "terminal_current_limit_other_A": float(c.limits_other.Imax),
            "eta_best": _clean(np.where(c.best.feasible, c.best.eta, np.nan)),
            "caveat": G1_CAVEAT,
            "model_note": ("같은 철심·자석에서 턴 수를 a배로 바꾼 모터를 인버터 단자에서 본 모델(docs/derivations.md 16절). 전환 순간의 과도·접점 손실·히스테리시스·"
                           "병렬 경로 순환 전류는 없고, 전환 전략은 셀마다 입력 전력이 작은 결선을 고른 상한이다.")}


# ---------------------------------------------------------------- M6 파레토
V_LIMIT, MARGIN_MIN = (2 / math.pi) * 680.0, 0.05


@lru_cache(maxsize=1)
def _pareto():
    from engine.magnet import ROOT
    rows = list(csv.DictReader(open(ROOT / "data" / "fea" / "design_opt_evals.csv")))
    for r in rows:
        for k in r:
            if k not in ("id", "stage"):
                r[k] = float(r[k])
    for r in rows:
        r["feasible"] = bool(r["V_peak_V"] <= V_LIMIT and r["demag_margin_150C"] >= MARGIN_MIN)
    ok = [r for r in rows if r["feasible"]]
    keep = pareto_mask(np.array([[-r["T_Nm"], r["magnet_area_mm2"]] for r in ok]))
    ids = {r["id"] for r, k in zip(ok, keep) if k}
    base = next(r for r in rows if r["id"] == "baseline")
    ref = (-0.9 * base["T_Nm"], 1.2 * base["magnet_area_mm2"])
    hv = {}
    used = []
    for st in ["init"] + sorted({r["stage"] for r in rows if r["stage"].startswith("iter")}):
        used += [r for r in ok if r["stage"] == st]
        hv[st] = hypervolume_2d(np.array([[-r["T_Nm"], r["magnet_area_mm2"]] for r in used]), ref)
    designs = [{**{k: r[k] for k in ("id", "stage", "m_thick1", "m_length_1", "m_theta_1", "m_thick2", "m_length_2", "T_Nm", "beta_deg", "V_peak_V", "demag_margin_150C", "magnet_area_mm2")},
                "feasible": r["feasible"], "pareto": r["id"] in ids} for r in rows]
    return {"designs": designs, "baseline": next(d for d in designs if d["id"] == "baseline"), "hypervolume_by_round": hv,
            "constraints": {"V_limit_V": V_LIMIT, "margin_min": MARGIN_MIN, "geometry": "회전자 철 웹 ≥ 1.5 mm 등(example_motor.geometry_ok)"},
            "variables": ["m_thick1", "m_length_1", "m_theta_1", "m_thick2", "m_length_2"],
            "note": ("연구실 예제 IPMSM(8극 48슬롯, N45SH)의 자석 5개 치수를 GP 대리모델 + NSGA-II로 탐색하고 FEA로 직접 평가한 설계들이다. 파레토 해는 FEA 값에서만 고른다. "
                     "토크는 4위치 평균이라 약 ±1% 불확실하고 감자는 한 점의 평가다(docs/validation_report.md M6).")}


@router.get("/api/pareto")
def pareto():
    return _pareto()
