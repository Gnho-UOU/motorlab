"""전자강판 철손 모델 (engine/steel.py): JFE 35JN230 카탈로그 대표값에서 계수를 구하고 파형 철손을 계산한다.

모델: P(f, B) = k_h·f·B^α + k_e·(f·B)²  [W/kg]  (Bertotti 분리식에서 이상(excess) 항 생략)
  k_e는 고전 와전류식 π²·d²/(6·ρ_e·ρ_m) (두께 d, 비저항 ρ_e, 밀도 ρ_m: 카탈로그 값)이고, k_h·α는 50 Hz의 두 점(1.0 T, 1.5 T)에서 구한다.
  60 Hz의 두 점(W10/60, W15/60)은 맞추는 데 쓰지 않고 예측해서 검증한다.
"""
import math

import numpy as np
import pytest

from engine.steel import load_steel

S = load_steel("35JN230")


def test_classical_eddy_coefficient_from_catalog_values():
    d, rho_e, rho_m = 0.35e-3, 55e-8, 7600.0
    assert S.k_e == pytest.approx(math.pi ** 2 * d ** 2 / (6 * rho_e * rho_m), rel=1e-12)
    assert S.k_e == pytest.approx(4.82e-5, rel=0.01)


def test_reproduces_the_two_fifty_hz_points_it_was_built_from():
    assert S.loss_density(50.0, 1.0) == pytest.approx(0.89, rel=1e-9)
    assert S.loss_density(50.0, 1.5) == pytest.approx(2.10, rel=1e-9)


def test_predicts_the_held_out_sixty_hz_points():
    """맞추는 데 쓰지 않은 60 Hz 대표값(1.10, 2.60 W/kg)을 1% 안에서 예측한다. 고전 와전류 + 히스테리시스로 충분하다는 점검."""
    assert S.loss_density(60.0, 1.0) == pytest.approx(1.10, rel=0.01)
    assert S.loss_density(60.0, 1.5) == pytest.approx(2.60, rel=0.01)


def test_hysteresis_exponent_is_a_physical_value():
    assert 1.6 < S.alpha < 2.6


def test_waveform_loss_of_a_sinusoid_equals_the_closed_form():
    f = 200.0
    t = np.arange(120) / 120.0 / f
    bx = 1.2 * np.cos(2 * math.pi * f * t)
    by = np.zeros_like(bx)
    # 한 성분만 교번하면 그 성분의 식과 같다
    assert S.loss_from_waveform(bx, by, f) == pytest.approx(S.loss_density(f, 1.2), rel=1e-9)


def test_waveform_loss_adds_over_harmonics_and_ignores_dc():
    f = 100.0
    t = np.arange(240) / 240.0 / f
    b = 0.8 + 1.0 * np.cos(2 * math.pi * f * t) + 0.2 * np.cos(2 * math.pi * 5 * f * t)
    expected = S.loss_density(f, 1.0) + S.loss_density(5 * f, 0.2)
    assert S.loss_from_waveform(b, np.zeros_like(b), f) == pytest.approx(expected, rel=1e-9)


def test_rotating_flux_counts_both_components():
    f = 150.0
    t = np.arange(120) / 120.0 / f
    bx, by = 1.0 * np.cos(2 * math.pi * f * t), 1.0 * np.sin(2 * math.pi * f * t)
    assert S.loss_from_waveform(bx, by, f) == pytest.approx(2 * S.loss_density(f, 1.0), rel=1e-9)
