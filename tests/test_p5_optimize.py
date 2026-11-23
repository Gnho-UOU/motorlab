"""M6 설계 최적화 (engine/optimize.py): 설계 공간, 라틴 하이퍼큐브, 파레토, 가우스 과정 대리모델, NSGA-II, 후보 선택.

엔진은 FEA를 모른다. 평가 함수(비싼 계산)는 호출자가 CSV로 넘기고 엔진은 그 표를 읽어 대리모델을 만들고 최적화한다(CLAUDE.md: engine은 femm에 의존하지 않는다).
이 테스트는 답을 아는 합성 문제로 각 부품을 점검한다.
"""
import numpy as np
import pytest

from engine.optimize import (DesignSpace, GPSurrogate, hypervolume_2d, latin_hypercube, pareto_mask, run_nsga2,
                             select_diverse)


def test_design_space_roundtrip_and_bounds():
    sp = DesignSpace(["a", "b"], [0.0, 10.0], [2.0, 20.0])
    u = np.array([[0.0, 0.0], [1.0, 1.0], [0.5, 0.25]])
    x = sp.scale(u)
    assert np.allclose(x, [[0.0, 10.0], [2.0, 20.0], [1.0, 12.5]])
    assert np.allclose(sp.unscale(x), u)
    with pytest.raises(ValueError):
        DesignSpace(["a"], [1.0], [1.0])                                   # 상한 > 하한이어야 한다


def test_latin_hypercube_has_one_sample_per_stratum_and_is_reproducible():
    u = latin_hypercube(20, 4, seed=3)
    assert u.shape == (20, 4) and u.min() >= 0 and u.max() <= 1
    for j in range(4):
        assert sorted(np.floor(u[:, j] * 20).astype(int)) == list(range(20))
    assert np.array_equal(u, latin_hypercube(20, 4, seed=3))
    assert not np.array_equal(u, latin_hypercube(20, 4, seed=4))


def test_pareto_mask_minimization():
    F = np.array([[1.0, 5.0], [2.0, 3.0], [3.0, 4.0], [4.0, 1.0], [2.5, 3.5], [1.0, 5.0]])
    # [3,4]와 [2.5,3.5]는 [2,3]에 지배된다. 같은 점은 서로 지배하지 않는다.
    assert pareto_mask(F).tolist() == [True, True, False, True, False, True]


def test_hypervolume_2d_known_rectangles():
    F = np.array([[1.0, 3.0], [2.0, 1.0]])
    assert hypervolume_2d(F, ref=(4.0, 4.0)) == pytest.approx((4 - 1) * (4 - 3) + (4 - 2) * (3 - 1))
    assert hypervolume_2d(np.array([[5.0, 5.0]]), ref=(4.0, 4.0)) == 0.0   # 기준점 밖


def test_gp_surrogate_interpolates_a_smooth_function_and_reports_uncertainty():
    rng = np.random.default_rng(0)
    f = lambda x: np.sin(3 * x[:, 0]) + 0.5 * x[:, 1] ** 2
    X = latin_hypercube(40, 2, seed=1)
    gp = GPSurrogate().fit(X, f(X))
    Xt = rng.random((200, 2))
    mean, std = gp.predict(Xt)
    assert np.sqrt(np.mean((mean - f(Xt)) ** 2)) < 0.03
    _, std_train = gp.predict(X)
    assert std_train.max() < std.mean()                                    # 학습점에서 불확실성이 훨씬 작다
    assert gp.loo_rmse() < 0.08


def test_nsga2_recovers_the_known_pareto_front():
    """ZDT1형 문제: f1 = x0, f2 = g·(1 − sqrt(x0/g)), g = 1 + 9·mean(x1..). 참 파레토 전선은 x1.. = 0, f2 = 1 − sqrt(f1)."""
    sp = DesignSpace(["x0", "x1", "x2"], [0, 0, 0], [1, 1, 1])

    def model(X):
        g = 1 + 9 * X[:, 1:].mean(axis=1)
        return np.stack([X[:, 0], g * (1 - np.sqrt(X[:, 0] / g))], axis=1), np.zeros((len(X), 0))
    X, F, G = run_nsga2(model, sp, pop=60, gens=120, seed=1)
    assert F.shape[1] == 2 and pareto_mask(F).all()
    assert np.max(np.abs(F[:, 1] - (1 - np.sqrt(F[:, 0])))) < 0.02       # 참 전선 위
    assert hypervolume_2d(F, ref=(1.1, 1.1)) > 0.80 * hypervolume_2d(
        np.stack([np.linspace(0, 1, 400), 1 - np.sqrt(np.linspace(0, 1, 400))], axis=1), ref=(1.1, 1.1))
    X2, F2, _ = run_nsga2(model, sp, pop=60, gens=120, seed=1)
    assert np.array_equal(X, X2)                                           # 같은 시드면 같은 결과


def test_nsga2_respects_constraints():
    """제약 x0 ≥ 0.5 (g = 0.5 − x0 ≤ 0): 해는 모두 제약을 지켜야 한다."""
    sp = DesignSpace(["x0", "x1"], [0, 0], [1, 1])

    def model(X):
        return np.stack([X[:, 0], 1 - X[:, 0] + X[:, 1]], axis=1), (0.5 - X[:, 0])[:, None]
    X, F, G = run_nsga2(model, sp, pop=40, gens=60, seed=0)
    assert (X[:, 0] >= 0.5 - 1e-9).all() and len(X) > 5


def test_select_diverse_keeps_extremes_and_spreads():
    F = np.stack([np.linspace(0, 1, 21), 1 - np.linspace(0, 1, 21)], axis=1)
    idx = select_diverse(F, 5)
    assert len(set(idx)) == 5 and 0 in idx and 20 in idx
    sel = np.sort(F[idx, 0])
    assert np.diff(sel).min() > 0.15                                       # 고르게 퍼진다
