"""P4: 위상 파형과 위상자 (engine/waveforms.py). dq 값을 한 전기 주기의 3상 파형으로 되돌린다 (역 Park, 크기 불변).

화면의 3상 파형·위상자는 이 값을 그린다. 화면에 삼각함수 계산을 두지 않기 위해 엔진이 만든다.
"""
import numpy as np
import pytest

from engine.waveforms import phase_waveforms


def test_amplitude_zero_sum_and_phase_order():
    w = phase_waveforms(id=-80.0, iq=120.0, vd=-30.0, vq=250.0, n=360)
    Is = np.hypot(-80.0, 120.0)
    for key in ("ia", "ib", "ic"):
        assert np.max(np.abs(w[key])) == pytest.approx(Is, rel=1e-4)
    np.testing.assert_allclose(w["ia"] + w["ib"] + w["ic"], 0.0, atol=1e-9)
    # b상은 a상보다 120° 늦다: ia가 최대인 순간 후 120°에 ib가 최대
    k_a, k_b = np.argmax(w["ia"]), np.argmax(w["ib"])
    assert (k_b - k_a) % 360 == 120
    assert np.max(np.abs(w["va"])) == pytest.approx(np.hypot(-30.0, 250.0), rel=1e-4)


def test_round_trip_through_park_transform():
    """파형을 다시 크기 불변 Park 변환하면 처음 id, iq가 나온다."""
    id_, iq = -55.0, 90.0
    w = phase_waveforms(id_, iq, 0.0, 0.0, n=120)
    th = w["theta_deg"] * np.pi / 180
    d = 2 / 3 * (w["ia"] * np.cos(th) + w["ib"] * np.cos(th - 2 * np.pi / 3) + w["ic"] * np.cos(th + 2 * np.pi / 3))
    q = -2 / 3 * (w["ia"] * np.sin(th) + w["ib"] * np.sin(th - 2 * np.pi / 3) + w["ic"] * np.sin(th + 2 * np.pi / 3))
    np.testing.assert_allclose(d, id_, atol=1e-9)
    np.testing.assert_allclose(q, iq, atol=1e-9)


def test_current_angle_is_atan2_of_dq():
    """전류각 beta = atan2(−id, iq)가 결과에 같이 들어 있다."""
    w = phase_waveforms(-100.0, 100.0, 0.0, 100.0, n=60)
    assert w["beta_deg"] == pytest.approx(45.0)
    assert w["theta_deg"][0] == 0 and len(w["theta_deg"]) == 60


def test_rejects_too_few_samples():
    with pytest.raises(ValueError):
        phase_waveforms(0.0, 1.0, 0.0, 1.0, n=3)
