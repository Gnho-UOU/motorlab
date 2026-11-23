"""M8 권선 전환: 운전 중 결선(턴 수)을 바꿔 고속 영역을 넓히는 효과를 비교한다. (기획서 4장 M8: Y↔Δ, 직렬↔병렬)

모델. 같은 철심·자석에서 상당 턴 수를 a배로 바꾼 모터를 인버터 단자에서 보면(기자력 N·i가 같으면 같은 자기 상태):
    i' = i / a,   ψ'(i') = a·ψ(a·i'),   R' = a²·R,   T' = T,   v' = a·v
이다(ψ는 쇄교자속, 턴 수에 비례하고 같은 기자력에서 자속밀도는 같다. 도체 단면적이 1/a가 되어 R ∝ a²). 단자 전류 한계(인버터)와 직류 링크 전압은 그대로다:
a < 1이면 같은 단자 전류에서 기자력이 a배라 저속 토크는 작지만 역기전력이 a배라 기저속도가 오른다. 유도는 docs/derivations.md 16절.
결선과 a의 대응: 직렬 ↔ 2병렬 a = 1/2. Y ↔ Δ: 같은 N이면 Δ는 상전압이 선간전압이라 역기전력이 선간 기준 √3배 작게 보이므로 Y(N) 대비 a = 1/√3
(Δ 한 상 N턴 = Y 한 상 N/√3턴과 단자 특성이 같다). 전환 순간의 과도·접촉기 손실, 전환 조건의 히스테리시스는 모델에 없다.

한계: 철손·기계손 같은 모델 밖 손실은 원래 권선과 같은 자속밀도·전류 기준으로 환산한다(engine/losses.py의 turns_ratio). 동손은 R = a²R이라 같은 기자력에서 불변이다
(도체 총 단면적·구리 부피가 같다고 본다). 병렬 경로 사이 순환 전류, 전환 접점 저항은 없다.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np

from .losses import EfficiencyMap, efficiency_map
from .model import ConstantParamModel, FluxMapModel
from .operating import Limits, max_torque_curve


def reconfigure(model, a: float):
    """턴 수 비 a의 같은 모터를 단자에서 본 모델 (모듈 머리 식). ConstantParamModel과 FluxMapModel만 지원한다."""
    if not a > 0:
        raise ValueError("턴 수 비 a는 양수여야 한다")
    if isinstance(model, ConstantParamModel):
        return dataclasses.replace(model, Rs=model.Rs * a * a, Ld=model.Ld * a * a, Lq=model.Lq * a * a, psi_m=model.psi_m * a,
                                   turns_ratio=model.turns_ratio * a)
    if isinstance(model, FluxMapModel):
        return dataclasses.replace(model, Rs=model.Rs * a * a, id_axis=model.id_axis / a, iq_axis=model.iq_axis / a,
                                   psi_d_map=model.psi_d_map * a, psi_q_map=model.psi_q_map * a, turns_ratio=model.turns_ratio * a)
    raise TypeError("ConstantParamModel 또는 FluxMapModel만 지원한다")


@dataclass(frozen=True)
class WindingComparison:
    """base: 기준 결선의 효율맵, other: 턴 수 a배 결선의 효율맵(전류는 그 결선의 단자 전류), best: 셀마다 입력 전력이 작은 결선을 고른 맵.
    best의 id, iq는 기준 결선 단자 전류로 환산한 값(= a·other의 단자 전류, 기자력이 같은 기준)이라 동손 1.5·R·I²이 결선과 무관하게 같은 식이다.
    choice: 0 = 기준 결선, 1 = 다른 결선(실행 가능하지 않은 셀은 0). limits_other: 맵 범위로 줄인 other의 한계(a > 1이면 줄 수 있다)."""

    a: float
    base: EfficiencyMap
    other: EfficiencyMap
    best: EfficiencyMap
    choice: np.ndarray
    limits_other: Limits
    tmax_base: np.ndarray
    tmax_other: np.ndarray


def compare_windings(model, limits: Limits, a: float, T_grid, speed_grid, iron=None, mech=None, excess=None) -> WindingComparison:
    """기준 결선과 턴 수 a배 결선의 효율맵을 같은 격자로 만들고, 셀마다 효율이 좋은 쪽을 고른 맵(전환 전략의 상한)을 돌려준다.

    FluxMapModel이면 a배 결선이 맵 범위를 넘는 전류를 요구하지 않도록 단자 전류 한계를 min(Imax, 맵 최대 전류 / a)로 줄인다(외삽하지 않는다)."""
    other = reconfigure(model, a)
    lim_o = limits
    if isinstance(other, FluxMapModel):
        i_cap = float(min(-other.id_axis[0], other.iq_axis[-1]))        # 전동 사분면 id ∈ [−Imax, 0], iq ∈ [0, Imax]를 덮는 최대 전류
        lim_o = dataclasses.replace(limits, Imax=min(limits.Imax, i_cap))
    base_map = efficiency_map(model, limits, T_grid, speed_grid, iron, mech, excess)
    oth_map = efficiency_map(other, lim_o, T_grid, speed_grid, iron, mech, excess)
    pick_o = oth_map.feasible & (~base_map.feasible | (oth_map.P_in < np.where(base_map.feasible, base_map.P_in, np.inf)))
    feas = base_map.feasible | oth_map.feasible

    def choose(field, scale_other=1.0):
        return np.where(pick_o, getattr(oth_map, field) * scale_other, getattr(base_map, field))

    best = EfficiencyMap(base_map.T_grid, base_map.speed_grid, np.where(pick_o, oth_map.id * a, base_map.id) * np.where(feas, 1.0, np.nan),
                         np.where(pick_o, oth_map.iq * a, base_map.iq) * np.where(feas, 1.0, np.nan), choose("T_act"), feas,
                         choose("P_cu"), choose("P_fe"), choose("P_mech"), choose("P_excess"), choose("P_in"), choose("P_out"), choose("eta"))
    tb = max_torque_curve(model, limits, speed_grid).T_max
    to = max_torque_curve(other, lim_o, speed_grid).T_max
    return WindingComparison(a, base_map, oth_map, best, pick_o.astype(int), lim_o, tb, to)
