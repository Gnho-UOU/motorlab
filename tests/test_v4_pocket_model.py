"""V4: ORNL 값 + 포켓 가설 형상(data/benchmarks/prius2004_geometry_ornl_pocket.json)의 FEA 맵을 ORNL 실측과 비교한다.

이 형상은 자석 Br을 **보정하지 않았다**(TM-137 그림 14의 측정값 1.243 T). 통과 기준은 실측의 불확실성(그림에서 읽은 값 약 1%,
전류 정의, 시험 온도 불명)에 맞춘 범위이고, 포켓 두께 6.5 mm가 실제로 포켓이라는 것은 ORNL 문서에 없는 가설이다.
경험적 잔여 손실(V2)은 같은 벤치마크 행에 맞춘 보정이라 따로 표시한다. 계산 방법은 docs/FEA_OPTIONS.md 3-6절.
"""
import json
import math
from pathlib import Path

import numpy as np
import pytest
from scipy.interpolate import CubicSpline

from engine.model import FluxMapModel
from engine.operating import Limits, mtpa_point, optimal_current

ROOT = Path(__file__).resolve().parents[1]
GEOM = ROOT / "data" / "benchmarks" / "prius2004_geometry_ornl_pocket.json"
GEOM_ORNL = ROOT / "data" / "benchmarks" / "prius2004_geometry_ornl.json"
MAP = ROOT / "data" / "flux_maps" / "prius2004_fullmodel_pocket_25A.csv"
LOCKED = ROOT / "data" / "fea" / "prius2004_full_locked_torque_pocket.csv"
LOCKED_MEAS = ROOT / "data" / "benchmarks" / "prius2004_locked_torque.csv"
GAP_MEAS = ROOT / "data" / "benchmarks" / "prius2004_gap_flux_density.csv"
GAP_CMP = ROOT / "data" / "fea" / "prius2004_gap_flux_comparison_pocket.csv"
VARIANTS = ROOT / "data" / "fea" / "prius2004_efficiency_variants.csv"
EXCESS = ROOT / "data" / "fea" / "prius2004_excess_loss_fit.json"
PERF = ROOT / "data" / "benchmarks" / "prius2004_perf_map.csv"


def _csv(path: Path):
    lines = [l for l in path.read_text().splitlines() if l.strip() and not l.startswith("#")]
    return lines[0].split(","), np.array([[float(x) for x in l.split(",")] for l in lines[1:]])


def test_geometry_values_come_from_ornl_tables():
    """TM-217 표 5.3: 적층 83.57, 회전자 반지름 80.19, 자석 두께 5.31, 자석 폭 38.48/2, 브리지 1.45 mm. TM-137 그림 14: Br 1.243, μr 1.129."""
    g = json.loads(GEOM.read_text())
    h = g["rotor"]["hole_HoleM50"]
    assert g["stator"]["L1_m"] == pytest.approx(0.08357) and g["rotor"]["Rext_m"] == pytest.approx(0.08019)
    assert h["H3"] - h["H2"] == pytest.approx(0.00531)                 # 자석 두께 = 포켓 두께 − 아래 공기 띠
    assert h["W4"] == pytest.approx(0.03848 / 2) and h["H1"] == pytest.approx(0.00145)
    assert h["air_strip_below_magnet"] is True
    assert g["magnet"]["Br20_T"] == pytest.approx(1.243) and g["magnet"]["mur"] == pytest.approx(1.129)
    assert "가설" in g["__source__"]["pocket_hypothesis"]
    # 포켓 가설 파일은 ORNL 형상 파일에서 포켓 두께·공기 띠만 다르다
    o = json.loads(GEOM_ORNL.read_text())["rotor"]["hole_HoleM50"]
    skip = ("H3", "H2", "air_strip_below_magnet")
    assert {k: v for k, v in h.items() if k not in skip} == {k: v for k, v in o.items() if k not in skip}


def test_map_header_states_no_br_calibration():
    m = FluxMapModel.from_csv(MAP, p=4, Rs=0.0)
    assert "Br20 = 1.243" in m.source and "보정값" not in m.source


def test_no_load_flux_matches_back_emf_without_calibration():
    """무부하 ψd(0,0)이 ORNL 역기전력 환산 0.174 Wb의 3% 안이다 (Br 보정 없음). FEA 기본파 진폭은 0.16985 Wb."""
    m = FluxMapModel.from_csv(MAP, p=4, Rs=0.0)
    assert abs(float(m.flux(0.0, 0.0)[0]) / 0.174 - 1) < 0.03


def test_gap_flux_density_waveform_and_amplitude_match_fig_13():
    """TM-137 그림 13: 13점 측정 파형. 크기를 맞추지 않은 FEA의 크기비(측정/FEA)가 1.00±0.07이고 RMS가 최대값의 5% 이하."""
    _, meas = _csv(GAP_MEAS)
    assert len(meas) == 13 and 0.74 < np.abs(meas[:, 1]).max() / 1e4 < 0.76
    head = [l for l in GAP_CMP.read_text().splitlines() if l.startswith("# 맞춤")][0]
    scale = float(head.split("크기 = ")[1].split(",")[0])
    rms = float(head.split("RMS = ")[1].split(" T")[0])
    assert 0.93 < scale < 1.07 and rms < 0.05 * 0.75


# --- 잠금 회전자 토크 ---------------------------------------------------------------------------------------------------------------
TABLE_3_2_PEAK = {75: 117.7, 150: 229.0, 250: 339.0}      # TM-423 개정판 표 3.2의 열 최대값
MEAS_COL = {75: 2, 150: 5, 250: 7}                         # prius2004_locked_torque.csv의 열 번호


def _locked():
    fea = np.array([[float(x) for x in l.split(",")] for l in LOCKED.read_text().splitlines()[1:]])
    _, meas = _csv(LOCKED_MEAS)
    curves = {Ia: CubicSpline(fea[fea[:, 0] == Ia][:, 1], fea[fea[:, 0] == Ia][:, 2]) for Ia in TABLE_3_2_PEAK}
    return curves, meas


def test_locked_peak_torque_within_10_percent_without_calibration():
    """75·150·250 A 잠금 토크 최대값 FEA/측정이 0.90~1.05 (ORNL 형상 Br 1.065 보정: 0.92~0.95)."""
    curves, _ = _locked()
    g = np.linspace(0, 56.25, 5626)
    for Ia, peak in TABLE_3_2_PEAK.items():
        assert 0.90 <= curves[Ia](g).max() / peak <= 1.05, Ia


def test_locked_torque_curve_shape_matches_with_one_angle_origin():
    """곡선 모양: 영점 하나(250 A에서 결정)와 거울 방향 가정으로 상관계수 > 0.99, RMS < 8%."""
    curves, meas = _locked()
    ang = meas[:, 0]
    c = min((np.sqrt(np.mean((curves[250](c - ang) - meas[:, 7]) ** 2)), c) for c in np.arange(100, 200, 0.05)
            if (c - ang).min() >= 0 and (c - ang).max() <= 56.25)[1]
    for Ia in TABLE_3_2_PEAK:
        m, f = meas[:, MEAS_COL[Ia]], curves[Ia](c - ang)
        assert np.corrcoef(f, m)[0, 1] > 0.99 and np.sqrt(np.mean((f - m) ** 2)) / m.max() < 0.08


def test_required_current_matches_measurement_at_low_speed():
    """속도 < 1950 rpm, 토크 55~290 N·m에서 엔진 필요 전류 / (측정 상전류 실효값 × √2)가 0.93~1.10 (구형상 보정 맵 0.93~1.07)."""
    m = FluxMapModel.from_csv(MAP, p=4, Rs=0.0)
    hdr, A = _csv(PERF)
    col = {h: A[:, i] for i, h in enumerate(hdr)}
    sel = np.nonzero((col["torque_Nm"] > 55) & (col["torque_Nm"] < 290) & (col["speed_rpm"] > 500) & (col["speed_rpm"] < 1950))[0]
    lim = Limits(Imax=250.0, Vdc=500.0, k_mod=2 / math.pi)
    ratios = []
    for k in sel[np.linspace(0, len(sel) - 1, 8).astype(int)]:
        d, q, ok = optimal_current(m, lim, float(col["torque_Nm"][k]), col["speed_rpm"][k] * math.pi / 30)
        assert ok
        ratios.append(math.hypot(d, q) / (col["Iac_rms_A"][k] * math.sqrt(2)))
    assert all(0.93 <= r <= 1.10 for r in ratios), np.round(ratios, 2)


def test_mtpa_torque_at_250_a_matches_locked_rotor():
    m = FluxMapModel.from_csv(MAP, p=4, Rs=0.0)
    d, q = mtpa_point(m, 250.0)
    assert 315.0 <= float(m.torque(d, q)) <= 350.0          # ORNL 339 N·m (2005년 시험), 400 N·m (2004년)


# --- 효율: 물리 모델만 대 경험적 잔여 손실 ------------------------------------------------------------------------------------------
def _variants():
    hdr, A = _csv(VARIANTS)
    c = {h: A[:, i] for i, h in enumerate(hdr)}
    core = (c["speed_rpm"] >= 1000) & (c["speed_rpm"] <= 4000) & (c["torque_Nm"] >= 30) & (c["torque_Nm"] <= 200)
    return c, core


def test_physics_only_efficiency_still_misses_g1():
    """V1(동손 + 무부하 실측 손실, 이중 계산 없음)은 효율을 체계적으로 높게 예측한다: 주요영역 평균 +3~5%p, 3%p 이내 행 < 60%.
    이중 계산을 없애면 V0보다 오히려 나빠진다(남은 부하 손실이 드러남). 이 미달을 숨기지 않는 기록이다."""
    c, core = _variants()
    assert len(c["speed_rpm"]) == 377
    d1 = (c["eta_v1"] - c["eta_meas"]) * 100
    assert 3.0 < d1[core].mean() < 5.0 and (np.abs(d1[core]) <= 3).mean() < 0.6
    d0 = (c["eta_v0"] - c["eta_meas"]) * 100
    assert d1[core].mean() > d0[core].mean()


def test_empirical_excess_loss_closes_gap_inside_data_range_only():
    """V2(경험식 k_f·f + k_c·I²f²)는 같은 행에 맞춘 보정이다. 전체 RMS < 2%p, 주요영역 3%p 이내 행 ≥ 95%.
    홀드아웃과 외삽 오차를 JSON에 같이 기록했고, 외삽(3000 rpm 미만으로 맞춰 이상 평가)은 RMS 3%p를 넘는다."""
    c, core = _variants()
    d2 = (c["eta_v2"] - c["eta_meas"]) * 100
    assert np.sqrt((d2 ** 2).mean()) < 2.0 and (np.abs(d2[core]) <= 3).mean() >= 0.95
    j = json.loads(EXCESS.read_text())
    v = j["validation"]
    assert v["random_half_holdout_rms_pp"] < 2.0
    assert v["extrapolate_lt3000_to_ge3000_rms_pp"] > 3.0
    assert j["k_f_W_per_Hz"] == pytest.approx(3.5, abs=0.3) and j["k_c_W_per_A2Hz2"] == pytest.approx(5.5e-6, rel=0.2)
    assert "물리 기구 미규명" in j["what"]
