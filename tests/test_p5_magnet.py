"""M5 자석 소재·감자 검토 (engine/magnet.py, PLAN 5.6절).

검증 방식: 감자 곡선(데이터시트 그림)과 데이터시트 표/온도계수는 서로 다른 정보다. 곡선에서 읽은 값이 표 값과 맞는지로
디지타이즈 결과를 독립적으로 점검한다. 곡선 값을 표에 맞추려는 보정은 없다.
"""
import json
import math
from pathlib import Path

import numpy as np
import pytest

from engine.magnet import MU0, demag_coupling, field_after_armature, load_grade

ROOT = Path(__file__).resolve().parents[1]
GRADES = json.loads((ROOT / "data" / "materials" / "magnets.json").read_text())["grades"]


@pytest.fixture(scope="module", params=["N45SH", "N38UH"])
def g(request):
    return load_grade(request.param)


def test_every_number_in_data_has_a_source():
    for name, props in GRADES.items():
        for key, val in props.items():
            if isinstance(val, dict):
                assert val.get("source"), f"{name}.{key}에 출처가 없다"


def test_curve_matches_datasheet_table_at_20C(g):
    t = g.props
    assert g.br(20.0) == pytest.approx(t["Br_T"]["nominal"], abs=0.002)            # 곡선은 공칭 Br
    assert g.hcj(20.0) == pytest.approx(t["HcJ_min_kApm"]["value"], abs=8.0)       # 곡선은 최소 HcJ
    hcb = g.hcb(20.0)                                                               # B=0이 되는 자계, 표의 HcB 범위 안
    assert t["HcB_kApm"]["min"] <= hcb <= t["HcB_kApm"]["max"]


def test_temperature_coefficients_from_curves_match_datasheet(g):
    """곡선 8개에서 구한 온도 변화율이 표의 α(Br), α(HcJ)와 맞는다 (표는 곡선과 별개 정보)."""
    hi = g.props["alpha_Br_pct_per_C"]["range_C"][1]
    dT = hi - 20.0
    a_br = (g.br(hi) / g.br(20.0) - 1.0) * 100.0 / dT
    a_hcj = (g.hcj(hi) / g.hcj(20.0) - 1.0) * 100.0 / dT
    assert a_br == pytest.approx(g.props["alpha_Br_pct_per_C"]["value"], abs=0.01)
    assert a_hcj == pytest.approx(g.props["alpha_HcJ_pct_per_C"]["value"], abs=0.03)


def test_recoil_permeability_is_consistent_with_br_and_hcb(g):
    """μr = Br / (μ0·HcB)는 곡선 직선부 기울기에서 구한 값과 같다 (B = Br − μ0·μr·H)."""
    mu_r = g.mu_r(20.0)
    assert 1.0 < mu_r < 1.15
    assert mu_r == pytest.approx(g.br(20.0) / (MU0 * g.hcb(20.0) * 1e3), rel=0.01)


def test_temperature_monotonic_and_range_checked(g):
    temps = np.linspace(-40, 180, 12)
    br = [g.br(t) for t in temps]
    hk = [g.hk(t) for t in temps]
    assert all(a > b for a, b in zip(br, br[1:]))
    assert all(a > b for a, b in zip(hk, hk[1:]))
    with pytest.raises(ValueError):
        g.br(200.0)
    with pytest.raises(ValueError):
        g.hk(-50.0)


def test_knee_field_is_where_polarization_is_90_percent_of_br(g):
    for T in (20.0, 100.0, 150.0):
        hk = g.hk(T)
        assert g.polarization(hk, T) == pytest.approx(0.9 * g.br(T), rel=2e-3)
        assert hk < g.hcj(T)                      # 무릎점은 HcJ보다 안쪽


def test_flux_density_is_polarization_minus_mu0_h(g):
    assert g.flux_density(0.0, 20.0) == pytest.approx(g.br(20.0), rel=1e-9)
    h = 500.0
    assert g.flux_density(h, 20.0) == pytest.approx(g.polarization(h, 20.0) - MU0 * h * 1e3, rel=1e-12)


def test_demag_margin_signs(g):
    T = 100.0
    assert g.demag_margin(0.0, T) == pytest.approx(1.0)
    assert g.demag_margin(g.hk(T), T) == pytest.approx(0.0, abs=1e-12)
    assert g.demag_margin(1.2 * g.hk(T), T) < 0.0


def test_load_line_operating_point_satisfies_both_curves(g):
    """무부하 동작점: 자석 곡선 위(B = J − μ0H)이면서 부하선 B = Pc·μ0·H 위."""
    for Pc in (2.0, 5.0, 10.0):
        H, B = g.load_line_point(Pc, 20.0)
        assert B == pytest.approx(Pc * MU0 * H * 1e3, rel=1e-6)
        assert B == pytest.approx(g.flux_density(H, 20.0), rel=1e-6)
        assert 0.0 < B < g.br(20.0)
    h_hi, b_hi = g.load_line_point(10.0, 20.0)
    h_lo, b_lo = g.load_line_point(2.0, 20.0)
    assert h_lo > h_hi and b_lo < b_hi              # 퍼미언스 계수가 작을수록 자계가 세지고 자속은 줄어든다


def test_hotter_magnet_has_lower_flux_and_less_margin(g):
    H20, B20 = g.load_line_point(5.0, 20.0)
    H100, B100 = g.load_line_point(5.0, 100.0)
    assert B100 < B20
    assert g.demag_margin(H100, 100.0) < g.demag_margin(H20, 20.0)


def test_armature_demag_is_linear_in_negative_id():
    """H = H0 + κ·max(−id, 0). κ는 FEA 두 점에서 구하고, 같은 κ가 다른 id에서도 성립한다(선형)."""
    kappa = demag_coupling(100.0, 550.0, -250.0)
    assert kappa == pytest.approx(1.8)
    assert field_after_armature(100.0, kappa, 0.0) == pytest.approx(100.0)
    assert field_after_armature(100.0, kappa, -125.0) == pytest.approx(100.0 + 1.8 * 125.0)
    assert field_after_armature(100.0, kappa, +80.0) == pytest.approx(100.0)       # 자화 보강 쪽은 줄이지 않는다
    with pytest.raises(ValueError):
        demag_coupling(100.0, 200.0, 10.0)


def test_demag_coupling_from_prius_fea_is_temperature_independent_for_ndfeb_but_not_ferrite():
    """femm/demag_check.py 결과(xfemm, Prius 형상): κ는 NdFeB(μr ≈ 1.04) 두 등급·여러 온도에서 ±5% 안에서 같다. 페라이트(μr 1.10, Br 0.4 T)는
    자석 투자율과 철심 포화가 달라서 κ가 약 15% 작다(그래서 NdFeB의 κ를 페라이트에 쓰면 감자를 과대 예측한다)."""
    import csv
    rows = list(csv.DictReader(open(ROOT / "data" / "fea" / "prius2004_demag_check.csv")))
    for r in rows:
        for k in r:
            if k not in ("grade", "state"):
                r[k] = float(r[k])
    by = {(r["grade"], r["T_C"], r["state"]): r for r in rows}
    kap = lambda r: demag_coupling(by[(r["grade"], r["T_C"], "noload")]["H_demag_mean_kApm"], r["H_demag_mean_kApm"], r["id_A"])
    kappas = [kap(r) for r in rows if r["state"] == "d_axis_250" and r["grade"] in ("N45SH", "N38UH")]
    assert len(kappas) >= 6
    assert max(kappas) / min(kappas) < 1.05
    ferrite = [kap(r) for r in rows if r["state"] == "d_axis_250" and r["grade"] == "F33"]
    assert len(ferrite) >= 3 and max(ferrite) < 0.9 * min(kappas)
    # κ를 한 점(N45SH 20 °C, 순수 d축)에서 구해 id와 iq가 함께 있는 MTPA 250 A 점의 평균 자계를 예측하면 5% 안
    k = demag_coupling(by[("N45SH", 20.0, "noload")]["H_demag_mean_kApm"], by[("N45SH", 20.0, "d_axis_250")]["H_demag_mean_kApm"], -250.0)
    m = by[("N45SH", 20.0, "mtpa250")]
    assert field_after_armature(by[("N45SH", 20.0, "noload")]["H_demag_mean_kApm"], k, m["id_A"]) == pytest.approx(m["H_demag_mean_kApm"], rel=0.05)


def test_ferrite_has_properties_but_no_unsourced_demag_check():
    f = load_grade("Y30H-1")
    assert f.props["alpha_Br_pct_per_C"]["value"] == pytest.approx(-0.2)
    assert f.props["alpha_HcJ_pct_per_C"]["value"] is None           # 출처를 못 찾은 값은 비워 둔다
    with pytest.raises(NotImplementedError):
        f.hk(20.0)


def test_unknown_grade_is_an_error():
    with pytest.raises(KeyError):
        load_grade("N99XX")
