"""M6 FEA 평가기(femm/design_opt_run.py)의 순수 함수: FEA 없이 점검할 수 있는 부분.

전류각에 대한 포물선 꼭짓점, 자석 면적, 감자 프로브가 자석 안에 있는지, 타당한 형상의 라틴 하이퍼큐브 표본.
"""
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from matplotlib.path import Path as MPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "femm"))
import design_opt_run as d  # noqa: E402
import example_motor as em  # noqa: E402


def test_quadratic_peak_finds_vertex_and_clips_to_the_range():
    betas = (33.0, 41.0, 49.0)
    t = [-0.1 * (b - 42.0) ** 2 + 350 for b in betas]
    bs, ts = d.quadratic_peak(betas, t)
    assert bs == pytest.approx(42.0) and ts == pytest.approx(350.0)
    # 꼭짓점이 구간 밖이면 끝점
    bs2, _ = d.quadratic_peak(betas, [-0.1 * (b - 60.0) ** 2 + 350 for b in betas])
    assert bs2 == 49.0
    # 위로 볼록하지 않은 경우(최대 지점 선택)
    bs3, ts3 = d.quadratic_peak(betas, [1.0, 2.0, 5.0])
    assert bs3 == 49.0 and ts3 == pytest.approx(5.0)


def test_magnet_area_of_the_baseline_design():
    assert d.magnet_area(d.BASE_X) == pytest.approx(2 * 22.9 * 2.6 + 2 * 14.0 * 3.2)


def test_demag_probes_lie_inside_the_magnets_with_unit_directions():
    p = d.design_p(d.BASE_X)
    z = {k: v * em.MM for k, v in em.rotor_points(p).items()}
    rect1 = MPath([(z[f"Z{k}"].real, z[f"Z{k}"].imag) for k in (2, 3, 6, 7)])
    rect1m = MPath([(z[f"Z{k}"].real, -z[f"Z{k}"].imag) for k in (2, 3, 6, 7)])
    rect2 = MPath([(z["Z12"].real, -z["Z13"].imag), (z["Z11"].real, -z["Z13"].imag), (z["Z11"].real, z["Z13"].imag), (z["Z12"].real, z["Z13"].imag)])
    probes = d.magnet_probes(p)
    assert len(probes) == 6 * 3 * 2 + 3 * 12
    for pt, n in probes:
        assert abs(abs(n) - 1.0) < 1e-12
        assert any(r.contains_point((pt.real, pt.imag)) for r in (rect1, rect1m, rect2))
    # V자 자석의 자화 방향은 자석 길이 방향에 수직이다 (길이 방향 = m_theta_1)
    pt, n = probes[0]
    along = complex(math.cos(math.radians(p["m_theta_1"])), math.sin(math.radians(p["m_theta_1"])))
    assert abs((n * along.conjugate()).real) < 1e-12


def test_valid_lhs_designs_are_valid_in_bounds_and_reproducible():
    x = d.valid_lhs(8, seed=11)
    assert x.shape == (8, 5) and np.all(x >= d.SPACE.lower) and np.all(x <= d.SPACE.upper)
    assert all(em.geometry_ok(d.design_p(row))[0] for row in x)
    assert np.array_equal(x, d.valid_lhs(8, seed=11))


def test_baseline_is_inside_the_design_space_and_valid():
    assert np.all(np.array(d.BASE_X) >= d.SPACE.lower) and np.all(np.array(d.BASE_X) <= d.SPACE.upper)
    assert em.geometry_ok(d.design_p(d.BASE_X)) == (True, "ok")
