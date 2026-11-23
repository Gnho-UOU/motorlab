"""M5 자석 소재와 감자 검토: 제조사 감자 곡선으로 온도별 Br·HcJ·무릎점을 구하고, 자석 동작점이 무릎점 아래로 내려가는지 본다.

기획서 5.6절(감자 검토). 1단계는 자기 등가회로(부하선 + 회복선)로 어림하고, 최악 조건은 FEA로 확인한다(FEA 확인은 이 모듈 밖).
근거: 소결 NdFeB의 감자 곡선, 표 값, 온도계수는 data/materials/magnets.json 과 magnet_demag_curves.csv (Arnold 데이터시트, 출처 포함).

기호와 단위: H는 감자 방향 자계의 크기 [kA/m] (양수), J 자기분극 [T], B 자속밀도 [T], μ0 = 4π·10⁻⁷ H/m.
  B = J − μ0·H                       (H가 자석 안에서 자화 반대 방향일 때, μ0·H를 T로 쓰려면 H[kA/m]·μ0·10³)
  Hk: J가 0.9·Br이 되는 자계 (무릎점 정의, Arnold TN 0901 'Hk, A Key Magnetic Figure of Merit'의 0.9·Br 정의).
      최신 IEC 정의는 기울어진 선을 쓰는 변형이 있어 값이 조금 다를 수 있다(여기서는 가로선 정의).
  온도 보간: 곡선이 있는 8개 온도(−40…180 °C) 사이를 선형 보간한다. 범위 밖은 오류다(외삽하지 않는다).
  부하선: 자석이 퍼미언스 계수 Pc를 보는 회로에서 B = Pc·μ0·H. 곡선과의 교점이 무부하 동작점이다.
  전기자 감자: d축 전류가 자석에 거는 자계는 id에 비례한다. H = H0 + κ·max(−id, 0), κ [kA/m per A]는 형상·권선 상수다.
      κ는 FEA 두 점(무부하와 id가 큰 점)에서 구한다(demag_coupling). 이 형상에서 κ는 소재(Br, μr)와 온도에 거의 무관했다(femm/demag_check.py 결과, ±3%).
      처음에는 "자석 자속이 d축 쇄교자속 ψd/ψm에 비례한다"고 가정했으나 FEA와 2배 이상 어긋나 기각했다(docs/validation_report.md M5 절):
      IPM의 d축 전기자 자속은 대부분 자석을 지나지 않고 회전자 철심을 지난다.
감자 곡선이 없는 소재(페라이트 등)는 NotImplementedError를 낸다. 출처 없는 값으로 판정하지 않는다.
"""
from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.optimize import brentq

from engine.model import FluxMapModel

ROOT = Path(os.environ.get("MOTORLAB_ROOT") or Path(__file__).resolve().parents[1])
MU0 = 4e-7 * np.pi          # H/m
_MU0_KAPM = MU0 * 1e3       # [T per kA/m]


@dataclass
class MagnetGrade:
    name: str
    props: dict
    temps_C: np.ndarray | None = None
    H_kApm: list | None = None      # 온도마다 감자 방향 자계 배열
    J_T: list | None = None         # 온도마다 자기분극 배열

    def _need_curves(self) -> None:
        if self.temps_C is None:
            raise NotImplementedError(f"{self.name}: 감자 곡선 자료가 없어 판정하지 않는다 (data/materials/magnets.json의 source 참고)")

    def _check_T(self, T: float) -> None:
        self._need_curves()
        if not (self.temps_C[0] - 1e-9 <= T <= self.temps_C[-1] + 1e-9):
            raise ValueError(f"{self.name}: 온도 {T} °C는 곡선 범위 {self.temps_C[0]:.0f}~{self.temps_C[-1]:.0f} °C 밖이다")

    def _interp_T(self, values: np.ndarray, T: float) -> float:
        self._check_T(T)
        return float(np.interp(T, self.temps_C, values))

    def _j_curve(self, k: int, H):
        """k번째 온도 곡선의 J(H). H=0 이하는 J(0), 곡선 끝(HcJ) 너머는 0 (감자 완료로 본다)."""
        return np.interp(H, self.H_kApm[k], self.J_T[k], right=0.0)

    # ---- 온도 의존 물성 ----
    def br(self, T: float) -> float:
        """잔류자속밀도 Br(T) [T]: 각 곡선의 J(H=0)을 온도로 보간."""
        self._need_curves()
        return self._interp_T(np.array([j[0] for j in self.J_T]), T)

    def hcj(self, T: float) -> float:
        """고유 보자력 HcJ(T) [kA/m]: J 곡선이 0이 되는 자계."""
        self._need_curves()
        return self._interp_T(np.array([h[-1] for h in self.H_kApm]), T)

    def hk(self, T: float) -> float:
        """무릎점 자계 Hk(T) [kA/m]: J = 0.9·Br이 되는 자계."""
        self._need_curves()
        hk = []
        for H, J in zip(self.H_kApm, self.J_T):
            target = 0.9 * J[0]
            i = int(np.argmax(J <= target))                 # J는 H에 대해 줄어든다. 처음으로 목표 이하가 된 점
            hk.append(float(np.interp(target, [J[i], J[i - 1]], [H[i], H[i - 1]])))
        return self._interp_T(np.array(hk), T)

    def polarization(self, H: float, T: float) -> float:
        """J(H, T) [T]: 이웃한 두 온도 곡선을 선형 보간."""
        self._check_T(T)
        k = int(np.clip(np.searchsorted(self.temps_C, T) - 1, 0, len(self.temps_C) - 2))
        w = (T - self.temps_C[k]) / (self.temps_C[k + 1] - self.temps_C[k])
        return float((1 - w) * self._j_curve(k, H) + w * self._j_curve(k + 1, H))

    def flux_density(self, H: float, T: float) -> float:
        """B(H, T) = J − μ0·H [T]."""
        return self.polarization(H, T) - _MU0_KAPM * H

    def hcb(self, T: float) -> float:
        """B = 0이 되는 자계 HcB(T) [kA/m]."""
        return brentq(lambda h: self.flux_density(h, T), 0.0, self.hcj(T), xtol=1e-9)

    def mu_r(self, T: float) -> float:
        """회복 비투자율: 곡선 직선부(H = 0 ~ 0.3·Hk)의 기울기. B = Br − μ0·μr·H."""
        H = np.linspace(0.0, 0.3 * self.hk(T), 25)
        B = np.array([self.flux_density(h, T) for h in H])
        return float(-np.polyfit(H, B, 1)[0] / _MU0_KAPM)

    # ---- 감자 검토 ----
    def demag_margin(self, H: float, T: float) -> float:
        """감자 여유 = 1 − H/Hk(T). 1이면 자계가 없다, 0이면 무릎점, 음수면 무릎점을 넘었다(비가역 감자 시작)."""
        return 1.0 - H / self.hk(T)

    def load_line_point(self, Pc: float, T: float) -> tuple[float, float]:
        """무부하 동작점 (H [kA/m], B [T]): 곡선 B = J − μ0H 와 부하선 B = Pc·μ0·H 의 교점."""
        h = brentq(lambda x: self.polarization(x, T) - (1.0 + Pc) * _MU0_KAPM * x, 0.0, self.hcj(T), xtol=1e-9)
        return h, Pc * _MU0_KAPM * h

def demag_coupling(H_noload: float, H_loaded: float, id_A: float) -> float:
    """감자 결합 상수 κ [kA/m per A] = (H_loaded − H_noload)/(−id). id < 0이어야 한다(FEA 두 점에서 구한다)."""
    if id_A >= 0:
        raise ValueError("id는 음수(감자 방향)여야 한다")
    return (H_loaded - H_noload) / (-id_A)


def field_after_armature(H0: float, kappa_kApm_per_A: float, id_A: float) -> float:
    """전기자 d축 전류 id [A] 뒤 자석 자계 [kA/m]. id ≥ 0(자화 보강)이면 H0를 그대로 둔다(줄어드는 효과는 다루지 않는다)."""
    return H0 + kappa_kApm_per_A * max(-id_A, 0.0)


def _read_curves(path: Path) -> dict[str, dict[int, tuple[np.ndarray, np.ndarray]]]:
    rows: dict[str, dict[int, list]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#") or line.startswith("grade"):
            continue
        g, T, H, J = line.split(",")
        rows.setdefault(g, {}).setdefault(int(T), []).append((float(H), float(J)))
    return {g: {T: (np.array([p[0] for p in pts]), np.array([p[1] for p in pts])) for T, pts in by_T.items()} for g, by_T in rows.items()}


def load_grade(name: str) -> MagnetGrade:
    """등급 이름으로 물성과 감자 곡선을 읽는다. 모르는 등급은 KeyError."""
    props = json.loads((ROOT / "data" / "materials" / "magnets.json").read_text(encoding="utf-8"))["grades"]
    if name not in props:
        raise KeyError(f"모르는 자석 등급 {name}. 있는 등급: {sorted(props)}")
    p = props[name]
    if not p.get("demag_curves"):
        return MagnetGrade(name, p)
    by_T = _read_curves(ROOT / "data" / "materials" / "magnet_demag_curves.csv")[name]
    temps = np.array(sorted(by_T), dtype=float)
    return MagnetGrade(name, p, temps, [by_T[int(t)][0] for t in temps], [by_T[int(t)][1] for t in temps])


def map_for_magnet(base: FluxMapModel, lo: FluxMapModel, hi: FluxMapModel, br_lo: float, br_hi: float, br: float) -> FluxMapModel:
    """자석을 바꾼 모터의 자속 맵: ψ' = ψ_기준 + Δ(Br).

    lo, hi는 기준 형상에 자석(Br_lo, Br_hi)을 넣어 같은 FEA 방법으로 푼 (성긴) 맵이다. Δ = ψ_lo/hi − ψ_기준을 lo의 격자점에서 구하고
    Br에 대해 선형 보간한 뒤 쌍선형으로 기준 맵의 격자에 펼친다. 포화로 인한 Br 의존성(자석이 셀수록 철심이 더 포화되어 ψq가 줄어듦)이
    Δ에 들어 있어서 단순 겹침 ψd + (k−1)ψm보다 정확하다(femm/magnet_scaling_check.py가 FEA와 비교한 결과는 docs/validation_report.md).
    Br이 [br_lo, br_hi] 밖이면 외삽하지 않고 ValueError. FEA 토크 열은 기준 맵의 것이라 넘기지 않는다.
    """
    if not (br_lo - 1e-12 <= br <= br_hi + 1e-12):
        raise ValueError(f"Br {br} T는 맵 두 개가 덮는 [{br_lo}, {br_hi}] T 밖이다 (외삽하지 않는다)")
    if not (np.array_equal(lo.id_axis, hi.id_axis) and np.array_equal(lo.iq_axis, hi.iq_axis)):
        raise ValueError("lo와 hi 맵의 격자가 다르다")
    w = (br - br_lo) / (br_hi - br_lo)
    ii, qq = np.meshgrid(lo.id_axis, lo.iq_axis, indexing="ij")
    bd, bq = base.flux(ii, qq)
    delta = []
    for lo_map, hi_map, b in ((lo.psi_d_map, hi.psi_d_map, bd), (lo.psi_q_map, hi.psi_q_map, bq)):
        delta.append((1.0 - w) * (lo_map - b) + w * (hi_map - b))
    fi, fq = np.meshgrid(base.id_axis, base.iq_axis, indexing="ij")
    pts = np.stack([fi, fq], axis=-1).reshape(-1, 2)
    new = []
    for base_map, dl in zip((base.psi_d_map, base.psi_q_map), delta):
        interp = RegularGridInterpolator((lo.id_axis, lo.iq_axis), dl, method="linear")
        new.append(base_map + interp(pts).reshape(base_map.shape))
    note = f"자석 Br {br:.4f} T로 조정(map_for_magnet: 기준 맵 + 50 A 격자 가정 맵 Br {br_lo}, {br_hi} T 보간)"
    return dataclasses.replace(base, psi_d_map=new[0], psi_q_map=new[1], torque_fea=None, source=base.source + "\n" + note)
