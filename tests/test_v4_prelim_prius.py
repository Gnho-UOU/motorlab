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
