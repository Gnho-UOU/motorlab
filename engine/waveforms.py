"""dq 값을 한 전기 주기의 3상 파형으로 되돌린다 (크기 불변 역 Park 변환, docs/ENGINE_SPEC.md 1장의 부호 규약).

  ia = id·cosθ − iq·sinθ
  ib = id·cos(θ − 120°) − iq·sin(θ − 120°)
  ic = id·cos(θ + 120°) − iq·sin(θ + 120°)

θ는 d축의 전기각이다(a상 축에서 잰다). 전압도 같은 식이다. 화면의 3상 파형·위상자가 이 값을 그린다.
전류각 β = atan2(−id, iq)는 q축에서 d(−) 쪽으로 잰 각이다(MTPA에서는 0 < β < 90°이고 약계자일수록 크다).
"""
from __future__ import annotations

import numpy as np


def _abc(d, q, th):
    two_pi_3 = 2 * np.pi / 3
    return tuple(d * np.cos(th - k) - q * np.sin(th - k) for k in (0.0, two_pi_3, -two_pi_3))


def phase_waveforms(id: float, iq: float, vd: float, vq: float, n: int = 120) -> dict:
    """한 전기 주기(0~360°, n점)의 3상 전류·전압. 반환 키: theta_deg, ia, ib, ic, va, vb, vc, beta_deg."""
    if n < 8:
        raise ValueError("n은 8 이상")
    theta = np.arange(n) * (2 * np.pi / n)
    ia, ib, ic = _abc(id, iq, theta)
    va, vb, vc = _abc(vd, vq, theta)
    return {"theta_deg": np.degrees(theta), "ia": ia, "ib": ib, "ic": ic, "va": va, "vb": vb, "vc": vc,
            "beta_deg": float(np.degrees(np.arctan2(-id, iq)))}
