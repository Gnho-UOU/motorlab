"""P5 API 확장(api/extensions.py): 자석(M5), 열(M7), 권선 전환(M8), 최적화 파레토(M6). 서버에는 계산식이 없고 엔진 결과를 돌려준다.

각 응답은 엔진을 직접 부른 값과 같아야 하고, 모델의 한계를 응답에 싣고, 잘못된 입력을 거절해야 한다.
"""
import csv
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402
from engine.magnet import load_grade  # noqa: E402

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_magnets_lists_grades_and_curve_availability():
    j = client.get("/api/magnets").json()
    g = {x["id"]: x for x in j["grades"]}
    assert {"N45SH", "N38UH", "F33", "Y30H-1"} <= set(g)
    assert g["N45SH"]["has_demag_curves"] and not g["Y30H-1"]["has_demag_curves"]
    n = load_grade("N45SH")
    row = next(r for r in g["N45SH"]["by_temperature"] if r["T_C"] == 150.0)
    assert row["Br_T"] == pytest.approx(n.br(150.0)) and row["Hk_kApm"] == pytest.approx(n.hk(150.0))
    assert "Y30H-1" in j["notes"]["no_curve"] or "곡선" in j["notes"]["no_curve"]


def test_magnet_demag_margin_matches_engine_and_fea_table():
    r = client.get("/api/magnet_demag", params={"grade": "N45SH", "temperature_C": 150.0, "state": "mtpa250"}).json()
    rows = list(csv.DictReader(open(ROOT / "data/fea/prius2004_demag_check.csv")))
    h = float(next(x for x in rows if x["grade"] == "N45SH" and float(x["T_C"]) == 150.0 and x["state"] == "mtpa250")["H_demag_max_kApm"])
    assert r["H_demag_max_kApm"] == pytest.approx(h)
    assert r["margin"] == pytest.approx(load_grade("N45SH").demag_margin(h, 150.0))
    assert r["margin"] < 0 and r["irreversible"] is True          # 150 °C N45SH는 최대 토크 전류에서 무릎점을 넘는다 (M5)
    assert client.get("/api/magnet_demag", params={"grade": "Y30H-1", "temperature_C": 20, "state": "mtpa250"}).status_code in (200, 404, 422)
    assert client.get("/api/magnet_demag", params={"grade": "N45SH", "temperature_C": 150.0, "state": "nope"}).status_code == 422
    assert client.get("/api/magnet_demag", params={"grade": "NOPE", "temperature_C": 20.0, "state": "noload"}).status_code == 422


def test_thermal_cycle_runs_engine_and_reports_limits():
    r = client.post("/api/thermal_cycle", json={"cycle": "UDDS", "boundary_C": 90.0}).json()
    assert r["cycle"] == "UDDS" and r["boundary_C"] == 90.0
    assert max(r["series"]["winding_C"]) > 90.0 and len(r["series"]["t_s"]) == len(r["series"]["winding_C"])
    assert abs(r["km_per_kWh_feedback"] / r["km_per_kWh_map"] - 1) < 0.05
    assert "자석" in r["limits"] and "경계" in r["limits"]
    assert client.post("/api/thermal_cycle", json={"cycle": "UDDS", "boundary_C": 400.0}).status_code == 422


def test_winding_comparison_uses_the_engine_and_states_the_g1_caveat():
    r = client.post("/api/winding", json={"a": 0.5, "n_torque": 20, "n_speed": 30}).json()
    assert r["a"] == 0.5 and len(r["speed_rpm"]) == 30
    tb, to = np.array(r["max_torque_base_Nm"], dtype=float), np.array(r["max_torque_other_Nm"], dtype=float)
    assert to[0] < tb[0] and to[-1] > tb[-1]                         # 저속 토크는 줄고 고속 토크는 는다
    assert r["feasible_cells"]["best"] >= max(r["feasible_cells"]["base"], r["feasible_cells"]["other"])
    assert "G1" in r["caveat"]
    assert client.post("/api/winding", json={"a": 0.0}).status_code == 422
    assert client.post("/api/winding", json={"a": 5.0}).status_code == 422


def test_pareto_returns_fea_evaluated_designs_with_engine_flags():
    r = client.get("/api/pareto").json()
    d = r["designs"]
    assert len(d) >= 50 and r["baseline"]["id"] == "baseline"
    feas = [x for x in d if x["feasible"]]
    front = [x for x in d if x["pareto"]]
    assert front and all(x["feasible"] for x in front)
    # 파레토 해끼리는 서로 지배하지 않는다
    for a in front:
        assert not any(b["T_Nm"] >= a["T_Nm"] and b["magnet_area_mm2"] <= a["magnet_area_mm2"] and (b["T_Nm"] > a["T_Nm"] or b["magnet_area_mm2"] < a["magnet_area_mm2"]) for b in feas)
    assert r["constraints"]["V_limit_V"] == pytest.approx(2 / np.pi * 680.0) and r["constraints"]["margin_min"] == 0.05
    assert "FEA" in r["note"]
