"""M6 설계 최적화: 설계 공간, 라틴 하이퍼큐브 표본, 가우스 과정(GP) 대리모델, NSGA-II 다목적 최적화, 파레토 도구.

기획서 4장 M6 (NSGA-II, FEA 호출이 비싸므로 대리모델은 가우스 과정 회귀). 엔진은 FEA를 호출하지 않는다: 비싼 평가는 호출자(femm/design_opt_run.py)가
표로 쌓고, 이 모듈은 그 표로 대리모델을 만들어 NSGA-II를 돌리고 다음에 평가할 후보를 고른다(CLAUDE.md: engine은 femm에 의존하지 않는다).

규약: 모든 목적은 최소화 (최대화하고 싶은 양은 부호를 바꿔 넘긴다). 제약은 g ≤ 0이 만족.
의존성: scipy(라틴 하이퍼큐브), scikit-learn(GP), pymoo(NSGA-II). 마지막 둘은 선택 의존성(pip install -e ".[opt]")이라 쓸 때 불러온다.

GP 대리모델: 커널 = 상수 × Matern(ν = 5/2, 변수마다 길이 척도) + 백색 잡음. 출력은 표준화한다. 학습점을 하나씩 빼고 다시 예측한 오차(LOO)는
닫힌 식 r_i = [K⁻¹y]_i / [K⁻¹]_ii 로 구한다 (Rasmussen & Williams, Gaussian Processes for ML, 5.4.2절).
NSGA-II: Deb et al., IEEE Trans. Evol. Comput. 6(2), 2002 (pymoo 구현).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import qmc


@dataclass(frozen=True)
class DesignSpace:
    """이름과 상·하한이 있는 설계 변수 공간. scale: [0, 1]^d → 실제 값, unscale: 그 반대."""

    names: list
    lower: np.ndarray
    upper: np.ndarray

    def __post_init__(self):
        object.__setattr__(self, "lower", np.asarray(self.lower, dtype=float))
        object.__setattr__(self, "upper", np.asarray(self.upper, dtype=float))
        if not (len(self.names) == self.lower.size == self.upper.size) or not np.all(self.upper > self.lower):
            raise ValueError("이름·하한·상한의 개수가 같아야 하고 상한이 하한보다 커야 한다")

    @property
    def dim(self) -> int:
        return len(self.names)

    def scale(self, u):
        return self.lower + np.asarray(u, dtype=float) * (self.upper - self.lower)

    def unscale(self, x):
        return (np.asarray(x, dtype=float) - self.lower) / (self.upper - self.lower)


def latin_hypercube(n: int, d: int, seed: int = 0) -> np.ndarray:
    """[0, 1]^d의 라틴 하이퍼큐브 표본 n개: 변수마다 [0, 1]을 n등분한 칸에 하나씩 들어간다."""
    return qmc.LatinHypercube(d=d, seed=seed).random(n)


def pareto_mask(F) -> np.ndarray:
    """최소화 문제의 비지배 점(True). 같은 점은 서로 지배하지 않는다."""
    F = np.asarray(F, dtype=float)
    keep = np.ones(len(F), dtype=bool)
    for i in range(len(F)):
        dominated = np.all(F <= F[i], axis=1) & np.any(F < F[i], axis=1)
        if dominated.any():
            keep[i] = False
    return keep


def hypervolume_2d(F, ref) -> float:
    """두 목적(최소화)의 초체적: 파레토 점들과 기준점 ref가 둘러싼 넓이. 기준점 밖의 점은 무시한다."""
    F = np.asarray(F, dtype=float)
    F = F[np.all(F < np.asarray(ref), axis=1)]
    if len(F) == 0:
        return 0.0
    F = F[pareto_mask(F)]
    F = F[np.argsort(F[:, 0])]
    area, prev_y = 0.0, ref[1]
    for x, y in F:
        area += (ref[0] - x) * (prev_y - y)
        prev_y = y
    return float(area)


class GPSurrogate:
    """스칼라 출력 하나를 예측하는 가우스 과정 회귀. 입력은 [0, 1]^d로 정규화해서 넘기는 것을 권한다."""

    def __init__(self, n_restarts: int = 8, seed: int = 0):
        self.n_restarts, self.seed = n_restarts, seed
        self._gp = None

    def fit(self, X, y):
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
        X, y = np.asarray(X, dtype=float), np.asarray(y, dtype=float)
        kernel = (ConstantKernel(1.0, (1e-2, 1e4)) * Matern(length_scale=np.ones(X.shape[1]), length_scale_bounds=(5e-2, 1e2), nu=2.5)
                  + WhiteKernel(1e-6, (1e-10, 1e-1)))
        self._gp = GaussianProcessRegressor(kernel, normalize_y=True, n_restarts_optimizer=self.n_restarts, random_state=self.seed)
        self._gp.fit(X, y)
        self._X, self._y = X, y
        return self

    def predict(self, X):
        mean, std = self._gp.predict(np.asarray(X, dtype=float), return_std=True)
        return mean, std

    def loo_rmse(self) -> float:
        """학습점 하나씩 뺀 예측 오차의 RMS (원래 단위). 닫힌 식으로 구한다."""
        gp = self._gp
        K = gp.kernel_(self._X)
        Kinv = np.linalg.inv(K)
        yn = (self._y - gp._y_train_mean) / gp._y_train_std
        r = (Kinv @ yn) / np.diag(Kinv)
        return float(np.sqrt(np.mean(r ** 2)) * gp._y_train_std)


def run_nsga2(model, space: DesignSpace, pop: int = 100, gens: int = 200, seed: int = 1):
    """model(X) -> (F, G): X는 (n, d) 실제 값, F는 (n, n_obj) 최소화 목적, G는 (n, n_con) 제약(g ≤ 0이 만족, 열 0개 가능).
    NSGA-II를 돌려 비지배 해 (X, F, G)를 돌려준다. 같은 seed면 같은 결과."""
    from pymoo.algorithms.moo.nsga2 import NSGA2
    from pymoo.core.problem import Problem
    from pymoo.optimize import minimize

    probe_F, probe_G = model(space.scale(np.full((1, space.dim), 0.5)))
    n_obj, n_con = np.asarray(probe_F).shape[1], np.asarray(probe_G).shape[1]

    class _Problem(Problem):
        def __init__(self):
            super().__init__(n_var=space.dim, n_obj=n_obj, n_ieq_constr=n_con, xl=space.lower, xu=space.upper)

        def _evaluate(self, X, out, *args, **kwargs):
            F, G = model(X)
            out["F"] = np.asarray(F, dtype=float)
            if n_con:
                out["G"] = np.asarray(G, dtype=float)

    res = minimize(_Problem(), NSGA2(pop_size=pop), ("n_gen", gens), seed=seed, verbose=False)
    if res.X is None:
        return np.empty((0, space.dim)), np.empty((0, n_obj)), np.empty((0, n_con))
    X = np.atleast_2d(res.X)
    F = np.atleast_2d(res.F)
    G = np.atleast_2d(res.G) if n_con else np.empty((len(X), 0))
    return X, F, G


def select_diverse(F, k: int) -> list:
    """파레토 점 F(n, n_obj)에서 서로 멀리 떨어진 k개의 색인: 목적마다 최소인 점(양 끝)을 먼저 넣고, 가장 먼 점을 하나씩 더한다(목적별 0~1 정규화)."""
    F = np.asarray(F, dtype=float)
    rng = np.ptp(F, axis=0)
    Z = (F - F.min(axis=0)) / np.where(rng > 0, rng, 1.0)
    chosen = [int(np.argmin(F[:, j])) for j in range(F.shape[1])]
    chosen = list(dict.fromkeys(chosen))[:k]
    while len(chosen) < min(k, len(F)):
        d = np.min(np.linalg.norm(Z[:, None, :] - Z[None, chosen, :], axis=2), axis=1)
        d[chosen] = -1.0
        chosen.append(int(np.argmax(d)))
    return chosen
