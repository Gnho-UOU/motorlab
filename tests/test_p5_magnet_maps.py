"""M5: 자석 소재에 맞춘 자속 맵 (engine.magnet.map_for_magnet).

기준 맵(Br 1.06 T, 25 A 격자)과 가정 자석 맵 두 개(Br 1.00 T와 1.40 T, μr 1.04, 50 A 격자, 같은 FEA 방법)가 있다.
소재의 Br가 두 값 사이일 때 ψ' = ψ_기준 + Δ(Br)로 새 맵을 만든다. Δ = ψ_가정 − ψ_기준은 50 A 격자점에서 구하고 Br에 대해 선형 보간,
격자 사이는 쌍선형 보간한다. 이 방식이 FEA를 다시 푼 값과 얼마나 맞는지는 FEA 점검 파일(data/fea/prius2004_magnet_scaling_check.csv)로 잰다.
"""
import csv
from pathlib import Path

import numpy as np
import pytest

from engine.magnet import map_for_magnet
from engine.model import FluxMapModel

ROOT = Path(__file__).resolve().parents[1]
FM = ROOT / "data" / "flux_maps"
BASE = FluxMapModel.from_csv(FM / "prius2004_fullmodel_teardown_25A.csv", p=4, Rs=0.0)
LO = FluxMapModel.from_csv(FM / "prius2004_fullmodel_Br100_mur104_50A.csv", p=4, Rs=0.0)
HI = FluxMapModel.from_csv(FM / "prius2004_fullmodel_Br140_mur104_50A.csv", p=4, Rs=0.0)


def test_reproduces_the_fea_maps_at_their_own_br_and_coarse_nodes():
    for br, ref in ((1.00, LO), (1.40, HI)):
        m = map_for_magnet(BASE, LO, HI, 1.00, 1.40, br)
        for i in ref.id_axis:
            for q in ref.iq_axis:
                a, b = m.flux(i, q), ref.flux(i, q)
                assert a[0] == pytest.approx(b[0], abs=1e-9) and a[1] == pytest.approx(b[1], abs=1e-9)


def test_grid_and_shape_follow_the_base_map_and_no_extrapolation():
    m = map_for_magnet(BASE, LO, HI, 1.00, 1.40, 1.2)
    assert np.array_equal(m.id_axis, BASE.id_axis) and np.array_equal(m.iq_axis, BASE.iq_axis)
    assert m.torque_fea is None                       # FEA 토크는 기준 맵의 것이라 넘기지 않는다
    for bad in (0.95, 1.45):
        with pytest.raises(ValueError):
            map_for_magnet(BASE, LO, HI, 1.00, 1.40, bad)


def test_no_load_flux_grows_with_br_and_q_axis_is_nearly_unchanged_at_no_current():
    psi_m = [map_for_magnet(BASE, LO, HI, 1.00, 1.40, br).flux(0.0, 0.0) for br in (1.0, 1.1, 1.2, 1.3, 1.4)]
    d = [p[0] for p in psi_m]
    assert all(a < b for a, b in zip(d, d[1:]))
    assert all(abs(p[1]) < 5e-3 for p in psi_m)


def test_matches_independent_fea_points_of_other_magnets():
    """FEA를 따로 푼 점(N45SH 20 °C Br 1.350, N38UH 180 °C Br 1.018)과 비교. 오차 상한은 실측한 값에 여유를 둔 것."""
    rows = list(csv.DictReader(open(ROOT / "data" / "fea" / "prius2004_magnet_scaling_check.csv")))
    rows = [r for r in rows if r["variant"] != "base_repro"]
    assert len(rows) == 14
    worst_d = worst_q = 0.0
    for r in rows:
        m = map_for_magnet(BASE, LO, HI, 1.00, 1.40, float(r["Br_T"]))
        d, q = m.flux(float(r["id_A"]), float(r["iq_A"]))
        worst_d = max(worst_d, abs(d - float(r["psi_d_fea"])))
        worst_q = max(worst_q, abs(q - float(r["psi_q_fea"])))
    assert worst_d < 0.002 and worst_q < 0.002         # [Wb] (실측 최대 1.0 mWb, 단순 겹침은 21 mWb)
