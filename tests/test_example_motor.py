"""연구실 예제 IPMSM (femm/example_motor.py): 형상 수식이 강의 자료 값과 맞는지, FEA 결과가 JMAG 결과와 가까운지.

강의 자료의 값(수치 인용 허용, 파일은 저장소에 없다): 슬롯 '레이어 면적 82.71 mm²'(슬롯 면적, 점적률 45 %는 따로), 자석 두께 2.6/3.2 mm 길이 22.9/28 mm,
고정자 요크폭 12.5 mm, 치폭 5.8 mm, 슬롯 깊이 19.5 mm, 오프닝 1.4 mm, 폴슈 1.2 mm, 공극 0.8 mm.
JMAG 결과: 토크 350.64 N·m, 리플 8.22 %, 단자 전압 385.75 V, 상 역기전력 THD 15.10 %, 선간 THD 9.63 %.
"""
import csv
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "femm"))
import example_motor as em  # noqa: E402

FEA = ROOT / "data" / "fea"


def slot_area_mm2():
    """슬롯 코일 단면적 [mm²]: 강의 자료 코드와 같은 분해(삼각형 두 개 + 바닥 부채꼴)로 구한 두 배."""
    s = em.stator_points()
    C1, S5, S8 = s["C1"], s["S5"], s["S8"]
    dist = abs(s["S7"])
    ray = complex(math.cos(math.radians(180 / 48)), math.sin(math.radians(180 / 48)))
    S9 = dist * ray
    tri = lambda a, b, c: 0.5 * abs((b - a).real * (c - a).imag - (c - a).real * (b - a).imag)
    ang = math.radians(180 / 48) - math.atan2(S5.imag - C1.imag, S5.real - C1.real)
    sector = math.pi * em.P["slot_edge"] ** 2 * math.degrees(ang) / 360
    return 2 * (tri(S5, S8, S9) + tri(S5, S9, C1) + sector)


def test_slot_geometry_matches_lecture_dimensions():
    s = em.stator_points()
    assert abs(s["S4"]) == pytest.approx(100.0 - 12.5)                       # 요크폭 12.5
    assert abs(s["S4"]) - (em.P["rotor_outer"] + em.P["air_gap"] + em.P["shoe_thick"]) == pytest.approx(19.5, abs=0.05)   # 슬롯 깊이 19.5
    assert 2 * s["S5"].imag == pytest.approx(5.8)                            # 치폭 5.8
    assert 2 * em.P["slot_open"] == pytest.approx(1.4)                       # 오프닝 1.4
    assert slot_area_mm2() == pytest.approx(82.71, abs=0.1)                  # 슬롯의 레이어 면적 82.71 mm² (점적률을 곱하기 전의 슬롯 면적)


def test_magnet_dimensions_match_lecture():
    z = em.rotor_points()
    assert abs(z["Z3"] - z["Z2"]) == pytest.approx(22.9)
    assert abs(z["Z6"] - z["Z3"]) == pytest.approx(2.6)
    assert math.degrees(math.atan2((z["Z3"] - z["Z2"]).imag, (z["Z3"] - z["Z2"]).real)) % 360 == pytest.approx(229.9)
    assert abs(z["Z13"] - z["Z12"]) == pytest.approx(14.0)                   # 반쪽 14 mm (거울과 합쳐 28 mm)
    assert abs(z["Z11"] - z["Z12"]) == pytest.approx(3.2)
    for k in (1, 8):                                                         # 구멍은 브리지 1.5 mm 안쪽 원까지
        assert abs(z[f"Z{k}"]) == pytest.approx(66.0 - 1.5)
    assert abs(z["Z9"]) == pytest.approx(66.0 - 1.5)


def test_winding_pattern_is_balanced_three_phase():
    pat = em.SLOT_PATTERN
    for ph in "ABC":
        assert sum(s for p, s in pat if p == ph) == 0                        # 상마다 + 와 − 가 같은 수
        assert sum(1 for p, _ in pat if p == ph) == 4                        # 12슬롯 중 4슬롯


def test_fea_results_agree_with_jmag():
    """xfemm 결과 대 JMAG (해석기끼리의 비교, 허용 5 %). 값은 data/fea/example_motor_*.csv (femm/example_motor_run.py)."""
    loaded = [r for r in csv.DictReader(open(FEA / "example_motor_loaded.csv")) if r["variant"] == "nominal" and r["beta_deg"] in ("40", "40.0", "45", "45.0")]
    by = {}
    for r in loaded:
        by.setdefault(float(r["beta_deg"]), []).append(r)
    we = 2 * math.pi * 4300 / 60 * 4

    def at41(key_fn):
        a = np.mean([key_fn(r) for r in by[40.0]])
        b = np.mean([key_fn(r) for r in by[45.0]])
        return a + (b - a) * 0.2
    torque = at41(lambda r: float(r["torque_fea_Nm"]))
    assert torque == pytest.approx(350.64, rel=0.05)
    volt = at41(lambda r: math.hypot(0.033 * float(r["id_A"]) - we * float(r["psi_q_Wb"]), 0.033 * float(r["iq_A"]) + we * float(r["psi_d_Wb"])))
    assert volt == pytest.approx(385.75, rel=0.05)
    rows = list(csv.DictReader(open(FEA / "example_motor_ripple.csv")))
    t = np.array([float(r["torque_fea_Nm"]) for r in rows])
    assert 100 * (t.max() - t.min()) / t.mean() == pytest.approx(8.22, rel=0.15)


def test_back_emf_thd_matches_jmag():
    rows = list(csv.DictReader(open(FEA / "example_motor_noload.csv")))
    sel = [r for r in rows if float(r["rotor_deg"]) < 90 and abs(float(r["rotor_deg"]) / 3.75 - round(float(r["rotor_deg"]) / 3.75)) < 1e-6]
    la = np.array([[float(r["lambda_A_Wb"]), float(r["lambda_B_Wb"])] for r in sel])
    k = np.arange(1, 12)
    a = np.abs(np.fft.rfft(la[:, 0])) * 2 / len(sel)
    thd = 100 * math.sqrt(np.sum((k[1:] * a[2:12]) ** 2)) / (k[0] * a[1])
    assert thd == pytest.approx(15.10, rel=0.05)
    ll = np.abs(np.fft.rfft(la[:, 0] - la[:, 1])) * 2 / len(sel)
    thd_ll = 100 * math.sqrt(np.sum((k[1:] * ll[2:12]) ** 2)) / (k[0] * ll[1])
    assert thd_ll == pytest.approx(9.63, rel=0.05)
