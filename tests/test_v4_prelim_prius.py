"""V4 예비: FEA 자속 맵(제3자 형상, 미검증)을 넣은 엔진 결과를 ORNL 실측과 비교한다.

조정한 계수가 없다. 통과 기준은 실측이 가진 불확실성(잠금 토크 337~400 N·m, 전류 정의의 모호함)에 맞춘 느슨한 범위이며,
"검증 통과"가 아니라 "예비 비교가 이 범위 안에 있다"는 회귀 표시다. 고속(> 2000 rpm)에서는 엔진이 필요 전류를 적게 예측하며
(비율 0.63~0.82) 이 어긋남은 data/benchmarks/prius2004_ornl.md와 docs/FEA_OPTIONS.md에 기록했다.
"""
import math
from pathlib import Path

import numpy as np
import pytest

from engine.model import FluxMapModel
from engine.operating import Limits, mtpa_point, optimal_current

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "data" / "flux_maps" / "prius2004_xfemm_delta0_25A.csv"
PERF = ROOT / "data" / "benchmarks" / "prius2004_perf_map.csv"


@pytest.fixture(scope="module")
def prius() -> FluxMapModel:
    return FluxMapModel.from_csv(MAP, p=4, Rs=0.0)


def test_map_loads_with_source_header(prius):
    assert prius.id_axis[0] == -250 and prius.id_axis[-1] == 0
    assert prius.iq_axis[0] == 0 and prius.iq_axis[-1] == 250
    assert "제3자" in prius.source and "xfemm" in prius.source


def test_no_load_flux_is_above_ornl_estimate_by_about_20_percent(prius):
    """FEA ψd(0,0) ≈ 0.210 Wb, ORNL 역기전력 상수 환산 0.174 Wb (+21%). 보정하지 않은 사실의 기록."""
    psi0 = float(prius.flux(0.0, 0.0)[0])
    assert 0.20 < psi0 < 0.22
    assert 1.15 < psi0 / 0.174 < 1.27


@pytest.mark.parametrize("I, lo, hi", [(150.0, 221.0, 260.0), (250.0, 337.0, 400.0)])
def test_mtpa_torque_within_ornl_locked_rotor_range(prius, I, lo, hi):
    """ORNL 잠금 토크: 150 A에서 221~260 N·m, 250 A에서 337~400 N·m (TM-423 Fig. 3.10, Table 3.2, TM-185)."""
    d, q = mtpa_point(prius, I)
    assert lo <= float(prius.torque(d, q)) <= hi


def test_required_current_matches_measurement_at_low_speed(prius):
    """속도 ≤ 1900 rpm, 토크 60~282 N·m에서 엔진 필요 전류 / (측정 상전류 실효값 × √2)가 0.85~1.05.

    측정 전류의 첨두/실효·상/선 구분은 보고서에 명시가 없어 '상 실효값'으로 가정했다(ornl.md 5절 3번).
    """
    lines = [l for l in PERF.read_text().splitlines() if l.strip() and not l.startswith("#")]
    hdr = lines[0].split(",")
    A = np.loadtxt(lines[1:], delimiter=",")
    col = {h: A[:, i] for i, h in enumerate(hdr)}
    sel = np.nonzero((col["torque_Nm"] > 55) & (col["torque_Nm"] < 290) & (col["speed_rpm"] > 500) & (col["speed_rpm"] < 1950))[0]
    pick = sel[np.linspace(0, len(sel) - 1, 6).astype(int)]
    lim = Limits(Imax=250.0, Vdc=500.0, k_mod=2 / math.pi)
    ratios = []
    for k in pick:
        d, q, ok = optimal_current(prius, lim, float(col["torque_Nm"][k]), col["speed_rpm"][k] * math.pi / 30)
        assert ok
        ratios.append(math.hypot(d, q) / (col["Iac_rms_A"][k] * math.sqrt(2)))
    assert all(0.85 <= r <= 1.05 for r in ratios), np.round(ratios, 2)


# --- 전체 모터 모델(공극 메시)의 잠금 회전자 토크 vs ORNL (data/fea/prius2004_full_locked_torque.csv) -----------------------
FULL_LOCKED = ROOT / "data" / "fea" / "prius2004_full_locked_torque.csv"
ORNL_LOCKED = ROOT / "data" / "benchmarks" / "prius2004_locked_torque.csv"
CURRENTS = [50, 75, 100, 125, 150, 200, 250]
FIG_3_10_PEAK = {50: 74, 75: 118, 100: 154, 125: 199, 150: 221, 200: 286, 250: 337}   # TM-423 Fig. 3.10 (2005년 8월 데이터 우선)


def _load_locked():
    from scipy.interpolate import CubicSpline

    fea = np.array([[float(x) for x in l.split(",")] for l in FULL_LOCKED.read_text().splitlines()[1:]])
    lines = [l for l in ORNL_LOCKED.read_text().splitlines() if l.strip() and not l.startswith("#")]
    meas = np.loadtxt(lines[1:], delimiter=",")
    curves = {}
    for Ia in CURRENTS:
        s = fea[fea[:, 0] == Ia]
        curves[Ia] = CubicSpline(s[:, 1], s[:, 2])
    return curves, meas


def test_full_model_peak_torque_vs_current_matches_ornl_fig_3_10():
    """전류별 최대 토크 FEA / ORNL = 0.99~1.09 (중앙 1.04). 형상·자석은 제3자 값이고 조정한 계수는 없다."""
    curves, _ = _load_locked()
    g = np.linspace(0, 56.25, 5626)
    ratios = [curves[Ia](g).max() / FIG_3_10_PEAK[Ia] for Ia in CURRENTS]
    assert all(0.95 <= r <= 1.12 for r in ratios), np.round(ratios, 2)


def test_full_model_torque_angle_curves_match_ornl_with_one_angle_origin():
    """토크-각도 곡선 모양: 영점 c 하나(250 A에서만 결정)와 거울 방향을 가정하면 7개 전류 모두 상관계수 > 0.98, RMS < 12%.

    거울 방향과 영점은 ORNL 각도 기준을 모르기 때문에 둔 가정이다. 같은 방향(거울 아님)으로는 250 A에서도 RMS가 최대의 58%다.
    """
    curves, meas = _load_locked()
    ang = meas[:, 0]
    cs = [(np.sqrt(np.mean((curves[250](c - ang) - meas[:, 7]) ** 2)), c) for c in np.arange(100, 200, 0.05)
          if (c - ang).min() >= 0 and (c - ang).max() <= 56.25]
    c = min(cs)[1]
    for k, Ia in enumerate(CURRENTS):
        m, f = meas[:, 1 + k], curves[Ia](c - ang)
        assert np.corrcoef(f, m)[0, 1] > 0.98
        assert np.sqrt(np.mean((f - m) ** 2)) / m.max() < 0.12


# --- 전체 모터 모델 자속 맵 (공극 메시, 두 위치 평균) ------------------------------------------------------------------------
FULL_MAP = ROOT / "data" / "flux_maps" / "prius2004_fullmodel_25A.csv"
CAL_MAP = ROOT / "data" / "flux_maps" / "prius2004_fullmodel_Br1056_25A.csv"   # Br을 무부하 역기전력 환산값에 맞춘 보정 맵


def test_full_model_map_flux_torque_agrees_with_stress_torque():
    """전체 모델 맵에서 자속 기반 토크와 두 위치 평균 Henrotte 토크가 ±8% 안이다 (AGE 단일 위치는 ±22%)."""
    m = FluxMapModel.from_csv(FULL_MAP, p=4, Rs=0.0)
    ID, IQ = np.meshgrid(m.id_axis, m.iq_axis, indexing="ij")
    Tf = m.torque(ID, IQ)
    sel = Tf > 20
    diff = m.torque_fea[sel] / Tf[sel] - 1
    assert np.abs(diff).max() < 0.08, (diff.min(), diff.max())


def test_calibrated_br_map_matches_back_emf_by_construction_and_locked_torque_independently():
    """Br = 1.056 T는 무부하 자속 0.174 Wb(ORNL 역기전력 환산)에 맞춘 보정값이다. 보정에 쓰지 않은 잠금 토크로 확인한다:
    250 A MTPA 토크 ≈ 337 N·m (ORNL 2005년 시험 337, 2004년 시험 400)."""
    m = FluxMapModel.from_csv(CAL_MAP, p=4, Rs=0.0)
    assert abs(float(m.flux(0.0, 0.0)[0]) - 0.174) < 0.002
    d, q = mtpa_point(m, 250.0)
    assert 325.0 <= float(m.torque(d, q)) <= 350.0


def test_calibrated_br_map_required_current_matches_measurement_at_low_speed():
    """보정 맵: 속도 < 1950 rpm에서 엔진 필요 전류 / (측정 상전류 실효값 × √2)가 0.93~1.07 (보정 전 0.88~0.95).

    고속(> 2400 rpm)은 0.61~0.94로 맞지 않는다. 측정 전압이 육각파 한계(총 실효 약 240 V)라 전압 한계 가정은 원인이 아니며,
    원인은 미해결이다 (docs/FEA_OPTIONS.md 3-4절). 그래서 고속은 검사하지 않는다.
    """
    m = FluxMapModel.from_csv(CAL_MAP, p=4, Rs=0.0)
    lines = [l for l in PERF.read_text().splitlines() if l.strip() and not l.startswith("#")]
    col = {h: v for h, v in zip(lines[0].split(","), np.loadtxt(lines[1:], delimiter=",").T)}
    sel = np.nonzero((col["torque_Nm"] > 55) & (col["torque_Nm"] < 290) & (col["speed_rpm"] > 500) & (col["speed_rpm"] < 1950))[0]
    lim = Limits(Imax=250.0, Vdc=500.0, k_mod=2 / math.pi)
    ratios = []
    for k in sel[np.linspace(0, len(sel) - 1, 6).astype(int)]:
        d, q, ok = optimal_current(m, lim, float(col["torque_Nm"][k]), col["speed_rpm"][k] * math.pi / 30)
        assert ok
        ratios.append(math.hypot(d, q) / (col["Iac_rms_A"][k] * math.sqrt(2)))
    assert all(0.93 <= r <= 1.07 for r in ratios), np.round(ratios, 2)


# --- 모터 효율 vs ORNL Table B-1 (data/fea/prius2004_efficiency_validation.csv, notebooks/03_prius_efficiency_validation.py) ---
EFF = ROOT / "data" / "fea" / "prius2004_efficiency_validation.csv"


def _load_eff():
    A = np.array([[float(x) for x in l.split(",")] for l in EFF.read_text().splitlines()[1:]])
    sp, T = A[:, 0], A[:, 1]
    return sp, T, (A[:, 6] - A[:, 5]) * 100          # Δη(엔진 - 실측) [%p]


def test_efficiency_overall_bias_is_a_few_points_high():
    """엔진 효율은 실측보다 체계적으로 높다(전체 평균 +3.0%p). 기록용: 이 범위를 벗어나면 모델이 바뀐 것이다."""
    sp, T, dE = _load_eff()
    assert len(dE) == 382
    assert 2.0 < dE.mean() < 4.0 and np.sqrt((dE ** 2).mean()) < 5.0


def test_efficiency_matches_where_copper_loss_dominates():
    """동손이 지배적인 고토크(200 N·m 이상 90행)에서는 평균 +0.66%p, 범위 −3.25~+2.72%p이고 90%가 ±2.5%p 안이다
    (단, R20을 같은 표의 저속 행에서 역산했으므로 독립 검증은 아니다)."""
    sp, T, dE = _load_eff()
    hi = T >= 200
    assert abs(dE[hi].mean()) < 1.5
    assert (np.abs(dE[hi]) <= 2.5).mean() > 0.85
    assert np.abs(dE[hi]).max() < 4.0


def test_efficiency_error_grows_with_speed_documents_g1_miss():
    """G1 미달의 기록: 주요 영역(1000~4000 rpm, 30~200 N·m) 평균 +3%p 안팎, 4000 rpm 이상 +8%p 안팎 (docs/validation_report.md).

    이 테스트는 미달을 숨기지 않고 고정하는 회귀 표시다. 철손·고속 자속 특성을 개선하면 이 범위가 줄어들어야 하고,
    그때 이 테스트를 갱신한다.
    """
    sp, T, dE = _load_eff()
    core = (sp >= 1000) & (sp <= 4000) & (T >= 30) & (T <= 200)
    assert 2.0 < dE[core].mean() < 4.5
    assert (np.abs(dE[core]) <= 3.0).mean() < 0.7          # 통과 기준(3%p)을 70% 넘게 만족하지 못한다
    assert dE[sp >= 4000].mean() > 6.0
