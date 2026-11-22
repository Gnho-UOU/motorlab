"""M1 모터 모델: 어느 (id, iq)에서나 자속·토크·전압을 돌려준다.

규약은 docs/ENGINE_SPEC.md 1·2장을 따른다. 전부 SI, 전류·전압은 상 첨두값,
크기 불변 dq 변환. 기획서 5.1·5.2절, 유도는 docs/derivations.md 1·2절.
P1에서는 ConstantParamModel만 둔다 (FluxMapModel은 P3).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


class MotorModel(Protocol):
    """operating.py가 요구하는 인터페이스. 상수 모델과 자속 맵 모델이 같은 모양을 가진다."""

    p: int      # 극쌍 수
    Rs: float   # 상저항 [Ω]

    def flux(self, id, iq):
        """(ψd, ψq) [Wb]"""

    def torque(self, id, iq):
        """Te [N·m]"""

    def voltage(self, id, iq, we):
        """(vd, vq) [V], we = 전기각속도 [rad/s]"""


@dataclass(frozen=True)
class ConstantParamModel:
    """상수 파라미터 IPMSM: ψd = Ld·id + ψm, ψq = Lq·iq (기획서 5.1).

    p: 극쌍 수, Rs: 상저항 [Ω], Ld/Lq: d/q축 인덕턴스 [H], psi_m: 자석 쇄교자속 [Wb].
    입력 id, iq는 스칼라 또는 NumPy 배열(브로드캐스팅)이다.
    """

    p: int
    Rs: float
    Ld: float
    Lq: float
    psi_m: float

    def __post_init__(self):
        if self.p < 1 or int(self.p) != self.p:
            raise ValueError("p(극쌍 수)는 1 이상의 정수여야 한다")
        if self.Rs < 0 or self.Ld <= 0 or self.Lq <= 0 or self.psi_m < 0:
            raise ValueError("Rs ≥ 0, Ld > 0, Lq > 0, psi_m ≥ 0 이어야 한다")

    def flux(self, id, iq):
        """ψd = Ld·id + ψm,  ψq = Lq·iq  [Wb]"""
        id, iq = np.asarray(id, dtype=float), np.asarray(iq, dtype=float)
        return self.Ld * id + self.psi_m, self.Lq * iq

    def torque(self, id, iq):
        """Te = 1.5·p·(ψd·iq − ψq·id) [N·m]  (기획서 5.2, derivations.md 2절).

        ψm·iq + (Ld−Lq)·id·iq 형태와 같은 값이다 (테스트 T7).
        """
        psi_d, psi_q = self.flux(id, iq)
        return 1.5 * self.p * (psi_d * np.asarray(iq, dtype=float) - psi_q * np.asarray(id, dtype=float))

    def voltage(self, id, iq, we):
        """정상상태 vd = Rs·id − ωe·ψq,  vq = Rs·iq + ωe·ψd [V]  (기획서 5.1, derivations.md 1절).

        we: 전기각속도 ωe = p·ωm [rad/s].
        """
        id, iq, we = (np.asarray(x, dtype=float) for x in (id, iq, we))
        psi_d, psi_q = self.flux(id, iq)
        return self.Rs * id - we * psi_q, self.Rs * iq + we * psi_d
