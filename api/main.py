"""Motor Lab FastAPI 서버.

서버에는 계산식이 없다. engine/의 결과를 표시 단위(rpm, kWh, km/h)로 바꿔 돌려주고, 입력을 검증하고, 모델의 한계(ORNL 실측 대비 편차)를 응답에 싣는다.
실행: uvicorn api.main:app --port 8000   (web/dist가 있으면 같은 서버가 화면도 낸다)
"""
from __future__ import annotations

import dataclasses
import json
import math
import os
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(os.environ.get("MOTORLAB_ROOT") or Path(__file__).resolve().parents[1])     # 데스크톱 앱은 묶은 자원 폴더를 가리킨다
sys.path.insert(0, str(ROOT / "femm"))
import prius_sector as ps  # noqa: E402  (형상 점 좌표 정의: femm/, FEMM 자체는 부르지 않는다)

from engine.losses import ExcessLossParams, MechParams, efficiency_map, loss_breakdown  # noqa: E402
from engine.model import FluxMapModel  # noqa: E402
from engine.operating import Limits, base_speed, max_torque_curve, optimal_current  # noqa: E402
from engine.waveforms import phase_waveforms  # noqa: E402
from engine.vehicle import load_cycle, load_vehicle, run_cycle  # noqa: E402

RPM = 30 / math.pi
CYCLES = {"WLTP": "WLTP (클래스 3b)", "UDDS": "UDDS (EPA 도심)", "HWFET": "HWFET (EPA 고속도로)"}
SCOPE_NOTE = ("모터 입력(교류) 기준 전기 에너지다. 인버터·배터리·보조 부하는 포함하지 않는다. 실제 Prius는 엔진을 함께 쓰므로 "
              "이 값은 순수 전기 구동을 가정한 환산 전비이고 실제 연비가 아니다.")
NOTE_PHYSICAL = ("물리 모델: 동손 + 무부하 실측 손실(기계·철손) + 기어 무부하 손실. ORNL 실측 대비 효율을 주요 영역에서 약 +3.7%p, "
                 "4000 rpm 이상에서 약 +10%p 높게 예측한다(docs/validation_report.md).")
NOTE_EMPIRICAL = ("경험식 포함: 물리 모델에 같은 ORNL 벤치마크 행에 맞춘 잔여 손실을 더했다. 이것은 물리 기구를 확인하지 않은 보정이고 "
                  "시험 범위(500~6100 rpm) 밖에서는 의미가 없다. G1 검증 충족으로 세지 않는다.")

app = FastAPI(title="Motor Lab API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])


def _preset(name: str) -> dict:
    return json.loads((ROOT / "data" / "motors" / f"{name}.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=4)
def _flux_model(name: str) -> FluxMapModel:
    pr = _preset(name)
    return FluxMapModel.from_csv(ROOT / pr["flux_map"], p=pr["pole_pairs"], Rs=0.0)


def _motor(name, Vdc, Imax, winding_C, model):
    """모델(권선 저항 온도 보정), 한계, 기계손, 잔여 손실 계수."""
    pr = _preset(name)
    w = pr["winding"]
    Rs = w["R_21C_ohm"] / (1 + w["alpha_per_K"] * (21.0 - 20.0)) * (1 + w["alpha_per_K"] * (winding_C - 20.0))
    mdl = dataclasses.replace(_flux_model(name), Rs=Rs)
    lim = Limits(Imax=Imax, Vdc=Vdc, k_mod=pr["limits_default"]["k_mod"])
    mech = MechParams(a=pr["mech_loss"]["a_W_per_rad_s"], b=pr["mech_loss"]["b_W_per_rad_s3"])
    excess = None
    if model == "empirical":
        j = json.loads((ROOT / pr["excess_loss"]).read_text(encoding="utf-8"))
        excess = ExcessLossParams(k_f=j["k_f_W_per_Hz"], k_c=j["k_c_W_per_A2Hz2"])
    return mdl, lim, mech, excess


@lru_cache(maxsize=32)
def _build(name, Vdc, Imax, winding_C, model, n_T, n_w, max_rpm):
    """효율맵과 최대 토크 곡선. 같은 입력은 캐시한다."""
    mdl, lim, mech, excess = _motor(name, Vdc, Imax, winding_C, model)
    speeds = np.linspace(2.0, max_rpm / RPM, n_w)
    coarse = np.linspace(speeds[0], speeds[-1], min(n_w, 30))        # 최대 토크 곡선은 점 30개로 풀고 격자 속도로 다시 샘플링한다(표시용)
    tc = max_torque_curve(mdl, lim, coarse)
    t_max = np.interp(speeds, coarse, tc.T_max)
    T_grid = np.linspace(1.0, float(np.ceil(np.nanmax(t_max))), n_T)
    em = efficiency_map(mdl, lim, T_grid, speeds, None, mech, excess)
    return em, t_max, mdl, lim


def _clean(a):
    """NaN → None (JSON)."""
    a = np.asarray(a, dtype=float)
    return [None if not math.isfinite(x) else float(x) for x in a] if a.ndim == 1 else [_clean(r) for r in a]


@lru_cache(maxsize=1)
def _validation(name: str) -> dict:
    pr = _preset(name)
    lines = [l for l in (ROOT / pr["validation_csv"]).read_text().splitlines() if l.strip() and not l.startswith("#")]
    h = lines[0].split(",")
    A = np.array([[float(x) for x in l.split(",")] for l in lines[1:]])
    c = {k: A[:, i] for i, k in enumerate(h)}
    core = (c["speed_rpm"] >= 1000) & (c["speed_rpm"] <= 4000) & (c["torque_Nm"] >= 30) & (c["torque_Nm"] <= 200)
    hi = c["speed_rpm"] >= 4000
    d1, d2 = (c["eta_v1"] - c["eta_meas"]) * 100, (c["eta_v2"] - c["eta_meas"]) * 100
    return {
        "reference": "ORNL/TM-2006/423 부록 B 표 B-1, 모터 효율 (행 %d개)" % len(d1),
        "physical_core_mean_error_pp": float(d1[core].mean()), "physical_high_speed_mean_error_pp": float(d1[hi].mean()),
        "empirical_core_mean_error_pp": float(d2[core].mean()), "empirical_high_speed_mean_error_pp": float(d2[hi].mean()),
        "empirical_is_calibration": True,
        "g1_status": "물리 모델만으로는 효율 기준 미달 (docs/validation_report.md)",
    }


class EffReq(BaseModel):
    preset: Literal["prius2004"] = "prius2004"
    Vdc: float = Field(500.0, gt=0, le=1000)
    Imax: float = Field(250.0, gt=0, le=1000)
    winding_C: float = Field(100.0, ge=-40, le=250)
    model: Literal["physical", "empirical"] = "physical"
    n_torque: int = Field(50, ge=10, le=200)
    n_speed: int = Field(70, ge=10, le=300)
    max_speed_rpm: float = Field(6100.0, gt=500, le=20000)


class VehicleOverride(BaseModel):
    mass_kg: float | None = Field(None, gt=100, le=10000)
    road_a_N: float | None = Field(None, ge=0, le=1000)
    road_b_Ns_m: float | None = Field(None, ge=0, le=50)
    road_c_Ns2_m2: float | None = Field(None, ge=0, le=5)


class CycleReq(BaseModel):
    preset: Literal["prius2004"] = "prius2004"
    cycle: Literal["WLTP", "UDDS", "HWFET"] = "WLTP"
    regen_ratio: float = Field(1.0, ge=0.0, le=1.0)
    Vdc: float = Field(500.0, gt=0, le=1000)
    Imax: float = Field(250.0, gt=0, le=1000)
    winding_C: float = Field(100.0, ge=-40, le=250)
    model: Literal["physical", "empirical"] = "physical"
    vehicle: VehicleOverride = VehicleOverride()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/presets")
def presets():
    pr = _preset("prius2004")
    cycles = []
    for cid, label in CYCLES.items():
        c = load_cycle(cid)
        cycles.append({"id": cid, "name": label, "distance_km": float(np.trapezoid(c.v_ms, c.t_s) / 1000), "duration_s": float(c.t_s[-1]), "source": c.source})
    veh = load_vehicle(pr["vehicle"])
    return {
        "motors": [{"id": pr["id"], "name": pr["name"], "sources": pr["sources"], "limits": pr["limits_default"],
                    "winding_R_21C_ohm": pr["winding"]["R_21C_ohm"]}],
        "cycles": cycles,
        "vehicle": {"mass_kg": veh.mass_kg, "road_a_N": veh.road_a_N, "road_b_Ns_m": veh.road_b_Ns_m, "road_c_Ns2_m2": veh.road_c_Ns2_m2},
        "validation": _validation("prius2004"),
        "model_notes": {"physical": NOTE_PHYSICAL, "empirical": NOTE_EMPIRICAL},
    }


def _outline(pts_complex):
    return [[round(z.real * 1000, 4), round(z.imag * 1000, 4)] for z in pts_complex]


@app.get("/api/geometry/{preset}")
def geometry(preset: Literal["prius2004"]):
    """3D 화면용 단면 윤곽. 점 좌표 정의는 femm/prius_sector.py(pyleecan SlotW11·HoleM50)이고 서버는 단위만 mm로 바꾼다."""
    pr = _preset(preset)
    g = ps.load_geometry(ROOT / pr["geometry"])
    sp = ps.stator_slot_points(g)
    c, r = (sp["Z4"] + sp["Z7"]) / 2, abs(sp["Z4"] - sp["Z7"]) / 2
    arc = [c + r * complex(math.cos(math.radians(a)), math.sin(math.radians(a))) for a in range(-90, 91, 10)]
    slot = [sp[k] for k in ("Z1", "Z2", "Z3", "Z4")] + arc + [sp[k] for k in ("Z7", "Z8", "Z9", "Z10")]
    low = ps.rotor_hole_points(g)
    up = {k: v.conjugate() for k, v in low.items() if k != "e"}
    mag = lambda h: [h[k] for k in ("Z8", "Z8c", "Z3", "Z4", "Z5", "Z6")]
    return {
        "slots": g["stator"]["Zs"], "poles": g["rotor"]["Zh"], "stack_length_mm": g["stator"]["L1_m"] * 1000,
        "stator": {"bore_radius_mm": g["stator"]["Rint_m"] * 1000, "outer_radius_mm": g["stator"]["Rext_m"] * 1000, "slot_outline_mm": _outline(slot),
                   "slot_angle_offset_deg": 180.0 / g["stator"]["Zs"]},
        "rotor": {"outer_radius_mm": g["rotor"]["Rext_m"] * 1000, "inner_radius_mm": g["rotor"]["Rint_m"] * 1000,
                  "magnets_mm": [_outline(mag(low)), _outline(mag(up))], "pole_angle_offset_deg": 180.0 / g["rotor"]["Zh"]},
        "source": g["__source__"]["what"],
        "winding": {"slot_layout": g["winding"]["slot_layout_first_12_slots"] * (g["stator"]["Zs"] // 12), "coil_pitch_slots": g["winding"]["coil_pitch_slots"],
                    "turns_per_slot": g["winding"]["Ntcoil_turns_per_slot"], "end_winding_extension_mm": pr["end_winding_extension_mm"]["value"],
                    "end_winding_source": pr["end_winding_extension_mm"]["source"]},
        "housing": pr["housing"],
    }


@app.post("/api/efficiency")
def efficiency(req: EffReq):
    t0 = time.perf_counter()
    em, t_max, mdl, lim = _build(req.preset, req.Vdc, req.Imax, req.winding_C, req.model, req.n_torque, req.n_speed, req.max_speed_rpm)
    eta = np.where(em.feasible, em.eta, np.nan)
    return {
        "speed_rpm": _clean(em.speed_grid * RPM), "torque_Nm": _clean(em.T_grid), "eta": _clean(eta),
        "max_torque_Nm": _clean(t_max), "base_speed_rpm": float(base_speed(mdl, lim) * RPM),
        "peak_eta": float(np.nanmax(eta)), "model": req.model,
        "model_note": NOTE_PHYSICAL if req.model == "physical" else NOTE_EMPIRICAL,
        "elapsed_ms": (time.perf_counter() - t0) * 1000,
    }


@app.post("/api/cycle")
def cycle(req: CycleReq):
    t0 = time.perf_counter()
    em, *_ = _build(req.preset, req.Vdc, req.Imax, req.winding_C, req.model, 90, 120, 6100.0)
    veh = load_vehicle(_preset(req.preset)["vehicle"])
    over = {k: v for k, v in req.vehicle.model_dump().items() if v is not None}
    if over:
        veh = dataclasses.replace(veh, mass_kg=over.get("mass_kg", veh.mass_kg), road_a_N=over.get("road_a_N", veh.road_a_N),
                                  road_b_Ns_m=over.get("road_b_Ns_m", veh.road_b_Ns_m), road_c_Ns2_m2=over.get("road_c_Ns2_m2", veh.road_c_Ns2_m2))
    r = run_cycle(veh, em, load_cycle(req.cycle), req.regen_ratio)
    kwh = lambda j: float(j / 3.6e6)
    step = max(1, math.ceil(len(r.t_s) / 2000))                  # 드라이브 모드가 1초 간격 그대로 재생할 수 있게 거의 줄이지 않는다
    s = slice(None, None, step)
    drive = r.em_torque_Nm > 0
    return {
        "cycle": req.cycle, "regen_ratio": req.regen_ratio, "model": req.model, "distance_km": r.distance_m / 1000,
        "km_per_kWh": r.km_per_kWh, "wh_per_km": r.Wh_per_km,
        "energy_kWh": {"wheel_traction": kwh(r.E_wheel_traction_J), "wheel_brake": kwh(r.E_wheel_brake_J), "gear_loss_traction": kwh(r.E_gear_loss_traction_J),
                       "motor_loss_traction": kwh(r.E_motor_loss_J), "motor_in": kwh(r.E_in_J), "regen": kwh(r.E_regen_J), "net": kwh(r.E_net_J),
                       "friction_brake": kwh(r.E_friction_brake_J)},
        "shortfall": {"time_s": r.shortfall_time_s, "wheel_energy_fraction": float(r.shortfall_wheel_energy_J / max(r.E_wheel_traction_J, 1e-9))},
        "series": {"t_s": _clean(r.t_s[s]), "speed_kmh": _clean(r.v_ms[s] * 3.6), "motor_rpm": _clean(r.motor_speed_rad[s] * RPM),
                   "torque_Nm": _clean(r.em_torque_Nm[s]), "elec_power_kW": _clean(r.elec_power_W[s] / 1000),
                   "loss_kW": _clean(r.loss_power_W[s] / 1000), "efficiency": _clean(r.efficiency[s]), "current_A": _clean(r.current_peak_A[s])},
        "operating_points": {"motor_rpm": _clean(r.motor_speed_rad[drive] * RPM), "torque_Nm": _clean(r.em_torque_Nm[drive])},
        "scope_note": SCOPE_NOTE, "model_note": NOTE_PHYSICAL if req.model == "physical" else NOTE_EMPIRICAL,
        "validation": _validation(req.preset), "elapsed_ms": (time.perf_counter() - t0) * 1000,
    }



class OpReq(BaseModel):
    preset: Literal["prius2004"] = "prius2004"
    speed_rpm: float = Field(2000.0, gt=0, le=12000)
    torque_Nm: float = Field(100.0, gt=0, le=600)
    Vdc: float = Field(500.0, gt=0, le=1000)
    Imax: float = Field(250.0, gt=0, le=1000)
    winding_C: float = Field(100.0, ge=-40, le=250)
    model: Literal["physical", "empirical"] = "physical"


@app.post("/api/operating_point")
def operating_point(req: OpReq):
    """(속도, 샤프트 토크)의 전류 최소 운전점과 전압·손실·효율·3상 파형. 모든 값은 엔진이 계산한다."""
    mdl, lim, mech, excess = _motor(req.preset, req.Vdc, req.Imax, req.winding_C, req.model)
    w = req.speed_rpm / RPM
    p_mech = mech.a * w + mech.b * w**3
    d, q, ok = optimal_current(mdl, lim, req.torque_Nm + p_mech / w, w)
    if not ok:
        return {"feasible": False, "reason": "이 속도에서 이 토크는 전류 한계 또는 전압 한계 안에서 낼 수 없다", "speed_rpm": req.speed_rpm, "torque_Nm": req.torque_Nm}
    d, q = float(d), float(q)
    lb = loss_breakdown(mdl, d, q, w, None, mech, excess)
    vd, vq = (float(x) for x in mdl.voltage(d, q, mdl.p * w))
    psi_d, psi_q = (float(x) for x in mdl.flux(d, q))
    v_pk = math.hypot(vd, vq)
    ratio = v_pk / lim.Vmax
    wf = phase_waveforms(d, q, vd, vq, 120)
    return {
        "feasible": True, "speed_rpm": req.speed_rpm, "torque_Nm": req.torque_Nm, "em_torque_Nm": float(lb.T),
        "id_A": d, "iq_A": q,
        "current": {"peak_A": math.hypot(d, q), "rms_A": math.hypot(d, q) / math.sqrt(2), "beta_deg": wf["beta_deg"]},
        "voltage": {"vd_V": vd, "vq_V": vq, "peak_V": v_pk, "ll_rms_V": v_pk * math.sqrt(3) / math.sqrt(2), "limit_peak_V": lim.Vmax, "ratio_to_limit": ratio},
        "flux": {"psi_d_Wb": psi_d, "psi_q_Wb": psi_q, "psi_Wb": math.hypot(psi_d, psi_q)},
        "power_W": {"shaft_out": float(lb.P_out), "input": float(lb.P_in), "loss_total": float(lb.P_in - lb.P_out), "copper": float(lb.P_cu),
                    "iron": float(lb.P_fe), "mechanical": float(lb.P_mech), "excess": float(lb.P_excess)},
        "efficiency": float(lb.eta), "mode": "전압 제한(약계자)" if ratio >= 0.985 else "전류 제한(MTPA)",
        "waveforms": {k: (_clean(v) if isinstance(v, np.ndarray) else v) for k, v in wf.items()},
        "model_note": NOTE_PHYSICAL if req.model == "physical" else NOTE_EMPIRICAL,
    }


@app.get("/api/parts")
def parts():
    """부품 도감. 숫자마다 출처가 있고, 치수 출처가 없는 부품은 dimensions_sourced = false이다."""
    return json.loads((ROOT / "data" / "motors" / "prius2004_parts.json").read_text(encoding="utf-8"))


_FLUX_STATES = ["noload", "mtpa150", "mtpa250", "fw"]


@lru_cache(maxsize=8)
def _flux(state: str) -> dict:
    return json.loads((ROOT / "data" / "fea" / "flux_fields" / f"{state}.json").read_text(encoding="utf-8"))


@app.get("/api/flux")
def flux_list():
    return {"states": [{k: _flux(s)[k] for k in ("state", "label", "id_A", "iq_A", "torque_Nm")} for s in _FLUX_STATES]}


@app.get("/api/flux/{state}")
def flux_field(state: str):
    """FEA로 푼 자속 분포(벡터 퍼텐셜 A와 |B|). 시각화용이고 화면에서 계산하지 않는다."""
    if state not in _FLUX_STATES:
        raise HTTPException(status_code=404, detail=f"알 수 없는 상태 {state!r}")
    return _flux(state)


_dist = ROOT / "web" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
