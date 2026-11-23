"""femm/prius_magnet_eddy.py의 순수 계산: 블록 안 벡터 퍼텐셜 변화율에서 와전류 손실을 구하는 식과 블록 면적."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "femm"))
import prius_magnet_eddy as e  # noqa: E402


def test_eddy_loss_matches_the_analytic_value_and_vanishes_for_a_uniform_potential():
    N, T_period = 400, 1.0e-3
    t = np.arange(N) * T_period / N
    w = 2 * math.pi / T_period
    a = 1e-4
    # 블록마다 점 둘: A = ±a·sin(ωt) (평균 0, 편차 = 자기 자신). 점 4개 = 블록 2개
    A = np.stack([a * np.sin(w * t), -a * np.sin(w * t), a * np.sin(w * t), -a * np.sin(w * t)], axis=1)
    areas = (1.2e-4, 1.2e-4)
    p = e.eddy_loss(A, T_period / N, areas)
    for rho, got in zip(e.RHO, p):
        want = sum((1 / rho) * S * (a * w) ** 2 / 2 for S in areas) * e.STACK * 8
        assert got == pytest.approx(want, rel=1e-3)
    uniform = np.stack([a * np.sin(w * t)] * 4, axis=1)                   # 블록 안에서 모두 같으면 순 전류만 바뀌므로 와전류 손실은 0
    assert max(e.eddy_loss(uniform, T_period / N, areas)) == pytest.approx(0.0, abs=1e-12)


def test_block_area_is_a_few_hundred_square_millimetres():
    g = e.pf.load_geometry()
    a, b = e.block_areas(g)
    assert a == b and 50e-6 < a < 300e-6                                   # 18.9 × 6.5 mm 근방
