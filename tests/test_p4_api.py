"""P4: FastAPI 서버(api/main.py). 서버에는 계산식이 없고 엔진 결과를 표시 단위(rpm, kWh)로 바꿔 돌려준다 (CLAUDE.md).

모든 숫자는 엔진이 계산한 값이다. 이 테스트는 서버가 엔진 결과를 왜곡하지 않는지, 한계(검증 편차)를 응답에 싣는지, 잘못된 입력을 거절하는지 본다.
"""
import math

import numpy as np
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402

client = TestClient(app)


def poly_area(pts):
    x, y = np.array(pts, float).T
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def test_health_and_presets():
    assert client.get("/api/health").json() == {"status": "ok"}
    p = client.get("/api/presets").json()
    assert [c["id"] for c in p["cycles"]] == ["WLTP", "UDDS", "HWFET"]
    m = p["motors"][0]
    assert m["id"] == "prius2004" and "ORNL" in m["sources"]
    v = p["validation"]
    # 검증 편차가 응답에 있다 (숨기지 않는다): 물리 모델은 효율을 높게 예측한다
    assert 3.0 < v["physical_core_mean_error_pp"] < 5.0 and v["physical_high_speed_mean_error_pp"] > 8.0
    assert v["empirical_is_calibration"] is True


def test_geometry_outlines_come_from_the_geometry_file():
    g = client.get("/api/geometry/prius2004").json()
    assert g["slots"] == 48 and g["poles"] == 8
    assert g["stator"]["bore_radius_mm"] == pytest.approx(80.92, abs=0.01) and g["stator"]["outer_radius_mm"] == pytest.approx(134.62)
    assert g["rotor"]["outer_radius_mm"] == pytest.approx(80.19)
    assert g["stack_length_mm"] == pytest.approx(83.6)
    assert poly_area(g["stator"]["slot_outline_mm"]) == pytest.approx(217.5, abs=3.0)          # 슬롯 면적
    assert len(g["rotor"]["magnets_mm"]) == 2                                                # V자 한 극의 두 자석
    for mg in g["rotor"]["magnets_mm"]:
        assert poly_area(mg) == pytest.approx(18.9 * 6.5, rel=0.02)                          # 자석 18.9 × 6.5 mm


def test_efficiency_map_basic_shape_and_limits():
    r = client.post("/api/efficiency", json={}).json()
    sp, T, eta = np.array(r["speed_rpm"]), np.array(r["torque_Nm"]), np.array(r["eta"], dtype=float)
    assert eta.shape == (len(T), len(sp))
    f = np.isfinite(eta)
    assert f.sum() > 500 and (eta[f] > 0).all() and (eta[f] < 1).all()
    assert 0.90 < np.nanmax(eta) < 0.98
    assert len(r["max_torque_Nm"]) == len(sp) and r["max_torque_Nm"][0] > 250          # 저속 최대 토크 (Imax 250 A)
    assert 800 < r["base_speed_rpm"] < 3000
    assert r["elapsed_ms"] < 15000 and "물리 모델" in r["model_note"]


def test_empirical_model_has_lower_efficiency_and_is_labeled():
    a = client.post("/api/efficiency", json={"model": "physical"}).json()
    b = client.post("/api/efficiency", json={"model": "empirical"}).json()
    ea, eb = np.array(a["eta"], dtype=float), np.array(b["eta"], dtype=float)
    ok = np.isfinite(ea) & np.isfinite(eb)
    assert (eb[ok] <= ea[ok] + 1e-12).all() and (eb[ok] < ea[ok]).any()
    assert "보정" in b["model_note"]


def test_cycle_energy_balance_and_regen():
    r1 = client.post("/api/cycle", json={"cycle": "WLTP", "regen_ratio": 1.0}).json()
    r0 = client.post("/api/cycle", json={"cycle": "WLTP", "regen_ratio": 0.0}).json()
    assert r1["distance_km"] == pytest.approx(23.27, abs=0.02)
    e = r1["energy_kWh"]
    assert e["net"] == pytest.approx(e["motor_in"] - e["regen"], abs=1e-9)
    assert 8.0 < r1["km_per_kWh"] < 12.0 and r0["km_per_kWh"] < r1["km_per_kWh"]
    assert r1["wh_per_km"] == pytest.approx(1000 / r1["km_per_kWh"], rel=1e-9)
    ts = r1["series"]
    assert 100 <= len(ts["t_s"]) <= 700 and len(ts["speed_kmh"]) == len(ts["t_s"]) == len(ts["motor_rpm"]) == len(ts["torque_Nm"])
    assert r1["shortfall"]["wheel_energy_fraction"] < 0.02
    assert "모터 입력" in r1["scope_note"]


def test_vehicle_override_changes_result():
    base = client.post("/api/cycle", json={"cycle": "UDDS", "regen_ratio": 1.0}).json()
    heavy = client.post("/api/cycle", json={"cycle": "UDDS", "regen_ratio": 1.0, "vehicle": {"mass_kg": 2000}}).json()
    assert heavy["km_per_kWh"] < base["km_per_kWh"]


@pytest.mark.parametrize("path, body", [
    ("/api/cycle", {"cycle": "NEDC"}),
    ("/api/cycle", {"cycle": "WLTP", "regen_ratio": 1.5}),
    ("/api/efficiency", {"Vdc": -10}),
    ("/api/efficiency", {"Imax": 0}),
    ("/api/efficiency", {"model": "magic"}),
    ("/api/efficiency", {"winding_C": 1000}),
])
def test_bad_input_is_rejected(path, body):
    assert client.post(path, json=body).status_code == 422


def test_preset_mech_loss_is_the_fit_of_the_ornl_table():
    """프리셋의 기계손 계수는 ORNL 표 3.7 12점의 P = a·ω + b·ω³ 최소제곱 피팅이다(손으로 적은 값이 아니다)."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    pr = json.loads((root / "data" / "motors" / "prius2004.json").read_text())
    rows = [l.split(",") for l in (root / "data" / "benchmarks" / "prius2004_rotor_loss.csv").read_text().splitlines() if l and not l.startswith("#")][1:]
    w = np.array([float(r[1]) for r in rows]) * math.pi / 30
    P = np.array([float(r[3]) for r in rows])
    a, b = np.linalg.lstsq(np.c_[w, w**3], P, rcond=None)[0]
    assert pr["mech_loss"]["a_W_per_rad_s"] == pytest.approx(a, rel=1e-3)
    assert pr["mech_loss"]["b_W_per_rad_s3"] == pytest.approx(b, rel=1e-3)
