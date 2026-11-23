"""P4: 운전점 탐색, 부품 도감, 자속 분포, 3D용 권선·하우징 치수, 사이클 시계열 확장 (api/main.py).

서버는 엔진 결과를 표시 단위로 바꿔 줄 뿐이다. 이 테스트는 엔진 값과 일치하는지, 한계를 응답에 싣는지, 출처 없는 값이 없는지 본다.
"""
import math

import numpy as np
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402

client = TestClient(app)


def op(**kw):
    body = {"speed_rpm": 2000, "torque_Nm": 100}
    body.update(kw)
    return client.post("/api/operating_point", json=body)


def test_operating_point_is_consistent_with_engine_physics():
    r = op().json()
    assert r["feasible"] is True
    # 전류 크기와 dq 성분, 위상각이 서로 맞는다
    assert r["current"]["peak_A"] == pytest.approx(math.hypot(r["id_A"], r["iq_A"]), rel=1e-9)
    assert r["current"]["rms_A"] == pytest.approx(r["current"]["peak_A"] / math.sqrt(2), rel=1e-9)
    assert r["current"]["beta_deg"] == pytest.approx(math.degrees(math.atan2(-r["id_A"], r["iq_A"])), rel=1e-9)
    # 전력 수지: 입력 = 축 출력 + 손실 (기계손은 축 출력에서 이미 빠졌다)
    p = r["power_W"]
    assert p["shaft_out"] == pytest.approx(100 * 2000 * math.pi / 30, rel=1e-6)
    assert p["input"] == pytest.approx(p["shaft_out"] + p["loss_total"], rel=1e-6)
    assert p["loss_total"] == pytest.approx(p["copper"] + p["iron"] + p["mechanical"] + p["excess"], rel=1e-6)
    assert r["efficiency"] == pytest.approx(p["shaft_out"] / p["input"], rel=1e-9)
    assert 0.80 < r["efficiency"] < 0.97
    # 전압 한계와 영역 판정
    assert 0 < r["voltage"]["ratio_to_limit"] <= 1.0001
    assert r["mode"] in ("전류 제한(MTPA)", "전압 제한(약계자)")
    w = r["waveforms"]
    assert len(w["theta_deg"]) == len(w["ia"]) == 120
    assert max(np.abs(w["ia"])) == pytest.approx(r["current"]["peak_A"], rel=1e-3)


def test_operating_point_enters_field_weakening_at_high_speed():
    low, high = op(speed_rpm=1000, torque_Nm=60).json(), op(speed_rpm=5000, torque_Nm=40).json()
    assert low["mode"] == "전류 제한(MTPA)" and high["mode"] == "전압 제한(약계자)"
    assert high["current"]["beta_deg"] > low["current"]["beta_deg"]


def test_operating_point_infeasible_is_reported():
    r = op(speed_rpm=6000, torque_Nm=300).json()
    assert r["feasible"] is False and "reason" in r


def test_operating_point_empirical_loss_is_larger_and_labeled():
    a, b = op(model="physical").json(), op(model="empirical").json()
    assert b["power_W"]["excess"] > 0 == a["power_W"]["excess"] * 0
    assert b["efficiency"] < a["efficiency"]


@pytest.mark.parametrize("body", [{"speed_rpm": -5, "torque_Nm": 10}, {"speed_rpm": 1000, "torque_Nm": 0}, {"speed_rpm": 1000, "torque_Nm": 1000}, {"speed_rpm": 99999, "torque_Nm": 10}])
def test_operating_point_bad_input(body):
    assert client.post("/api/operating_point", json=body).status_code == 422


def test_parts_catalog_has_sources_and_flags_unverified_dimensions():
    p = client.get("/api/parts").json()
    ids = [x["id"] for x in p["parts"]]
    assert {"housing", "stator_core", "windings", "rotor_core", "magnets", "shaft", "terminal", "resolver", "bearings"} <= set(ids)
    for part in p["parts"]:
        assert part["name"] and part["role"] and part["story"]
        for s in part["specs"]:
            assert s["source"]                                    # 출처 없는 숫자는 없다 (CLAUDE.md)
        assert isinstance(part["dimensions_sourced"], bool)
    mg = next(x for x in p["parts"] if x["id"] == "magnets")
    assert any("83.1" in s["value"] for s in mg["specs"]) and mg["dimensions_sourced"] is True
    assert next(x for x in p["parts"] if x["id"] == "terminal")["dimensions_sourced"] is False


def test_geometry_has_winding_and_housing_for_3d():
    g = client.get("/api/geometry/prius2004").json()
    w = g["winding"]
    assert len(w["slot_layout"]) == 48 and set(s[0] for s in w["slot_layout"]) == {"A", "B", "C"}
    assert w["coil_pitch_slots"] == 6 and w["end_winding_extension_mm"] == pytest.approx(38.1)
    # 같은 상의 +와 −가 코일 피치만큼 떨어져 있다
    for k, s in enumerate(w["slot_layout"]):
        t = w["slot_layout"][(k + 6) % 48]
        if k % 12 < 6:
            assert s[0] == t[0] and s[1] != t[1]
    h = g["housing"]
    assert h["diameter_mm"] == pytest.approx(299.0) and h["length_mm"] == pytest.approx(205.0)
    assert "TM-2010/253" in h["source"]


def test_flux_states_and_fields():
    lst = client.get("/api/flux").json()
    assert [s["state"] for s in lst["states"]] == ["noload", "mtpa150", "mtpa250", "fw"]
    f = client.get("/api/flux/mtpa250").json()
    n = f["grid_n"]
    assert len(f["A_Wb_per_m"]) == n and len(f["A_Wb_per_m"][0]) == n
    assert f["torque_Nm"] == pytest.approx(339, abs=8)               # 같은 맵의 잠금 토크와 일치(측정 339 N·m)
    assert "FEA" in f["source"] or "xfemm" in f["source"]
    assert client.get("/api/flux/nothing").status_code == 404


def test_cycle_series_has_loss_and_efficiency():
    r = client.post("/api/cycle", json={"cycle": "UDDS"}).json()
    s = r["series"]
    assert len(s["loss_kW"]) == len(s["efficiency"]) == len(s["t_s"])
    eff = [e for e in s["efficiency"] if e is not None]
    assert eff and all(0 <= e <= 1 for e in eff)
    assert all(x >= -1e-9 for x in s["loss_kW"])
    assert len(s["current_A"]) == len(s["t_s"]) and max(s["current_A"]) <= 250.0001
