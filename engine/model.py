"""M1 모터 모델: 어느 (id, iq)에서나 자속·토크·전압을 돌려준다.

규약은 docs/ENGINE_SPEC.md 1·2장을 따른다. 전부 SI, 전류·전압은 상 첨두값,
크기 불변 dq 변환. 기획서 5.1·5.2절, 유도는 docs/derivations.md 1·2절.
P1에서는 ConstantParamModel만 둔다 (FluxMapModel은 P3).
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np
from scipy.interpolate import RegularGridInterpolator


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


class _DqModel:
    """flux()만 구현하면 토크·전압이 따라 나오는 공통 부분. 자속이 어떤 함수여도 전력 수지가 성립한다."""

    def torque(self, id, iq):
        """Te = 1.5·p·(ψd·iq − ψq·id) [N·m]  (기획서 5.2, derivations.md 2절).

        상수 파라미터 모델에서는 ψm·iq + (Ld−Lq)·id·iq 형태와 같은 값이다 (테스트 T7).
        """
        psi_d, psi_q = self.flux(id, iq)
        return 1.5 * self.p * (psi_d * np.asarray(iq, dtype=float) - psi_q * np.asarray(id, dtype=float))

    def voltage(self, id, iq, we):
        """정상상태 vd = Rs·id − ωe·ψq,  vq = Rs·iq + ωe·ψd [V]  (기획서 5.1, derivations.md 1절).

        we: 전기각속도 ωe = p·ωm [rad/s].
        """
        id, iq, we = (np.asarray(x, dtype=float) for x in (id, iq, we))
        psi_d, psi_q = self.flux(id, iq)
        return self.voltage_from_flux(id, iq, psi_d, psi_q, we)

    def voltage_from_flux(self, id, iq, psi_d, psi_q, we):
        """이미 구한 자속으로 전압을 만든다(같은 전류 격자를 속도마다 다시 보간하지 않으려고 분리). voltage()가 이것을 쓴다."""
        return self.Rs * id - we * psi_q, self.Rs * iq + we * psi_d


@dataclass(frozen=True)
class ConstantParamModel(_DqModel):
    """상수 파라미터 IPMSM: ψd = Ld·id + ψm, ψq = Lq·iq (기획서 5.1).

    p: 극쌍 수, Rs: 상저항 [Ω], Ld/Lq: d/q축 인덕턴스 [H], psi_m: 자석 쇄교자속 [Wb].
    입력 id, iq는 스칼라 또는 NumPy 배열(브로드캐스팅)이다.
    """

    p: int
    Rs: float
    Ld: float
    Lq: float
    psi_m: float
    turns_ratio: float = 1.0      # 권선 전환(engine/winding.py)으로 만든 모델의 턴 수 비 a (철손·잔여 손실을 원래 권선 기준으로 환산할 때 쓴다)

    def __post_init__(self):
        if self.p < 1 or int(self.p) != self.p:
            raise ValueError("p(극쌍 수)는 1 이상의 정수여야 한다")
        if self.Rs < 0 or self.Ld <= 0 or self.Lq <= 0 or self.psi_m < 0:
            raise ValueError("Rs ≥ 0, Ld > 0, Lq > 0, psi_m ≥ 0 이어야 한다")

    def flux(self, id, iq):
        """ψd = Ld·id + ψm,  ψq = Lq·iq  [Wb]"""
        id, iq = np.asarray(id, dtype=float), np.asarray(iq, dtype=float)
        return self.Ld * id + self.psi_m, self.Lq * iq


_GRID_TOL = 1e-9  # 격자 경계를 이 상대 폭 이내로 넘는 요청은 부동소수점 오차로 보고 경계로 당긴다
_REQUIRED_COLS = ("id_A", "iq_A", "psi_d_Wb", "psi_q_Wb")


@dataclass(frozen=True, eq=False)
class FluxMapModel(_DqModel):
    """FEA로 구한 자속 맵 ψd(id, iq), ψq(id, iq)를 보간하는 모델 (기획서 5.1, ENGINE_SPEC 2장).

    포화와 d·q 교차결합이 맵에 그대로 들어 있다. 격자 밖 요청은 오류이며 외삽하지 않는다.
    기본 보간은 선형이다. 맵이 촘촘하면 충분하고, 격자 간격에서 미분이 꺾이는 점은 알고 써야 한다.
    torque_fea: CSV에 FEA 토크 열이 있을 때 비교용으로만 보관한다 (토크는 자속에서 계산한다).
    source: CSV 머리 주석(출처·단위·조건) 전문.
    """

    p: int
    Rs: float
    id_axis: np.ndarray            # [A], 증가 순
    iq_axis: np.ndarray            # [A], 증가 순
    psi_d_map: np.ndarray          # [Wb], 모양 (n_id, n_iq)
    psi_q_map: np.ndarray          # [Wb]
    torque_fea: np.ndarray | None = None   # [N·m], 모양 (n_id, n_iq)
    source: str = ""
    method: str = "linear"
    turns_ratio: float = 1.0       # 권선 전환(engine/winding.py)으로 만든 모델의 턴 수 비 a (철손·잔여 손실을 원래 권선 기준으로 환산할 때 쓴다)
    _interp: RegularGridInterpolator = field(init=False, repr=False)

    def __post_init__(self):
        for name in ("id_axis", "iq_axis"):
            ax = getattr(self, name)
            if ax.ndim != 1 or ax.size < 2 or not np.all(np.diff(ax) > 0):
                raise ValueError(f"{name}은 점 2개 이상의 증가하는 1차원 배열이어야 한다")
        shape = (self.id_axis.size, self.iq_axis.size)
        for name in ("psi_d_map", "psi_q_map", "torque_fea"):
            m = getattr(self, name)
            if m is not None and m.shape != shape:
                raise ValueError(f"{name}의 모양 {m.shape}이 격자 {shape}와 다르다")
        values = np.stack([self.psi_d_map, self.psi_q_map], axis=-1)
        object.__setattr__(
            self, "_interp",
            RegularGridInterpolator((self.id_axis, self.iq_axis), values, method=self.method),
        )

    @classmethod
    def from_csv(cls, path, p: int, Rs: float, method: str = "linear") -> "FluxMapModel":
        """CSV에서 읽는다. 열: id_A, iq_A, psi_d_Wb, psi_q_Wb (+ 선택: torque_Nm). 행 순서는 상관없다.

        '#'로 시작하는 머리 주석(출처·형상·온도·회전자 위치 평균 방식)이 반드시 있어야 한다
        (CLAUDE.md: 출처 없는 숫자 금지). 격자는 (id, iq) 조합이 빠짐·중복 없이 모두 있어야 한다.
        """
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        comments = [l.lstrip("#").strip() for l in lines if l.lstrip().startswith("#")]
        if not comments:
            raise ValueError("자속 맵 CSV에는 '#'로 시작하는 머리 주석(출처·단위·조건)이 있어야 한다")
        body = [l for l in lines if l.strip() and not l.lstrip().startswith("#")]
        header = [c.strip() for c in body[0].split(",")]
        missing = [c for c in _REQUIRED_COLS if c not in header]
        if missing:
            raise ValueError(f"필수 열이 없다: {missing} (있는 열: {header})")
        arr = np.loadtxt(io.StringIO("\n".join(body[1:])), delimiter=",", ndmin=2)
        col = {name: arr[:, header.index(name)] for name in header}

        ids, iqs = np.unique(col["id_A"]), np.unique(col["iq_A"])
        ii, jj = np.searchsorted(ids, col["id_A"]), np.searchsorted(iqs, col["iq_A"])
        filled = np.zeros((ids.size, iqs.size), dtype=bool)
        filled[ii, jj] = True
        if arr.shape[0] != ids.size * iqs.size or not filled.all():
            raise ValueError(
                f"격자가 완전하지 않다: id {ids.size}점 × iq {iqs.size}점이면 {ids.size * iqs.size}행이어야 하는데 "
                f"{arr.shape[0]}행이고 서로 다른 (id, iq)는 {int(filled.sum())}개다 (빠짐 또는 중복)"
            )

        def grid(values):
            out = np.empty((ids.size, iqs.size))
            out[ii, jj] = values
            return out

        torque = grid(col["torque_Nm"]) if "torque_Nm" in col else None
        return cls(p=p, Rs=Rs, id_axis=ids, iq_axis=iqs, psi_d_map=grid(col["psi_d_Wb"]),
                   psi_q_map=grid(col["psi_q_Wb"]), torque_fea=torque, source="\n".join(comments), method=method)

    @staticmethod
    def _clamp(x, axis):
        lo, hi = axis[0], axis[-1]
        tol = _GRID_TOL * (hi - lo)
        if np.any((x < lo - tol) | (x > hi + tol)):
            raise ValueError(f"요청이 자속 맵 격자 범위 [{lo:g}, {hi:g}] A 밖이다 (외삽하지 않는다)")
        return np.clip(x, lo, hi)

    def flux(self, id, iq):
        """맵을 보간한 (ψd, ψq) [Wb]. 격자 밖이면 ValueError."""
        id, iq = np.broadcast_arrays(np.asarray(id, dtype=float), np.asarray(iq, dtype=float))
        x, y = self._clamp(id, self.id_axis), self._clamp(iq, self.iq_axis)
        if self.method == "linear":
            return self._bilinear(x, y)
        pts = np.stack([x, y], axis=-1)
        v = self._interp(pts.reshape(-1, 2)).reshape(id.shape + (2,))
        return v[..., 0], v[..., 1]

    def _bilinear(self, x, y):
        """쌍선형 보간(선형 RegularGridInterpolator와 같은 값). 격자 칸을 searchsorted로 찾아 네 모서리를 직접 읽는다.
        효율맵 한 장에서 맵을 수백 번 부르므로 scipy의 일반 N차원 구현보다 훨씬 빠르다(기획서 G2)."""
        ax, ay = self.id_axis, self.iq_axis
        i = np.clip(np.searchsorted(ax, x, side="right") - 1, 0, ax.size - 2)
        j = np.clip(np.searchsorted(ay, y, side="right") - 1, 0, ay.size - 2)
        u = (x - ax[i]) / (ax[i + 1] - ax[i])
        v = (y - ay[j]) / (ay[j + 1] - ay[j])
        w00, w10, w01, w11 = (1 - u) * (1 - v), u * (1 - v), (1 - u) * v, u * v
        out = []
        for m in (self.psi_d_map, self.psi_q_map):
            out.append(w00 * m[i, j] + w10 * m[i + 1, j] + w01 * m[i, j + 1] + w11 * m[i + 1, j + 1])
        return out[0], out[1]
