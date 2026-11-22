"""V1 테스트용 가상 파라미터 (docs/ENGINE_SPEC.md 4장). 실제 모터 값이 아니다."""
import pytest

from engine.model import ConstantParamModel
from engine.operating import Limits

P = 4
LD = 0.15e-3   # H
LQ = 0.45e-3   # H
PSI_M = 0.075  # Wb
RS = 0.03      # Ohm (T3·T4는 Rs = 0, 나머지는 둘 다 사용)
IMAX = 250.0   # A
VDC = 350.0    # V


@pytest.fixture
def limits() -> Limits:
    return Limits(Imax=IMAX, Vdc=VDC)


@pytest.fixture
def model0() -> ConstantParamModel:
    """Rs = 0 (해석해 비교용)."""
    return ConstantParamModel(p=P, Rs=0.0, Ld=LD, Lq=LQ, psi_m=PSI_M)


@pytest.fixture
def model_rs() -> ConstantParamModel:
    """Rs = 0.03 Ω."""
    return ConstantParamModel(p=P, Rs=RS, Ld=LD, Lq=LQ, psi_m=PSI_M)


@pytest.fixture
def model_mtpv() -> ConstantParamModel:
    """MTPV 전용: ψm = 0.025 Wb → 특성전류 ψm/Ld = 166.7 A < Imax (T8)."""
    return ConstantParamModel(p=P, Rs=0.0, Ld=LD, Lq=LQ, psi_m=0.025)
