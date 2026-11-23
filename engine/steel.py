"""전자강판 철손 모델 (기획서 5.4의 Bertotti 분리식에서 이상 항을 뺀 형태): 카탈로그 값에서 계수를 구하고 B 파형의 철손을 계산한다.

식 (B는 자속밀도 진폭 [T], f [Hz], 밀도당 손실 [W/kg]):
  P(f, B) = k_h·f·B^α + k_e·f²·B²
  k_e = π²·d²/(6·ρ_e·ρ_m)      고전 와전류 계수: 두께 d [m], 비저항 ρ_e [Ω·m], 밀도 ρ_m [kg/m³] (모두 카탈로그 값, 맞춤 없음)
  k_h, α                       50 Hz 두 점(W10/50, W15/50)에서: h(B) = W − k_e·50²·B² 라 하면 α = ln(h(1.5)/h(1.0))/ln 1.5, k_h = h(1.0)/50
검증: 60 Hz 두 점(W10/60, W15/60)은 맞추는 데 쓰지 않고 예측한다. 35JN230에서 1% 안에서 맞았다(tests/test_p5_steel.py).
한계: 이상(excess) 손실, 소형 루프(고조파) 보정, 회전 자속의 히스테리시스 증가, 가공(타발) 열화가 없다. 카탈로그에는 50·60 Hz 값뿐이라
수백 Hz 이상은 와전류가 지배하는 외삽이다(고전식은 두께 0.35 mm에서 1 kHz 부근까지 표피 효과가 작다는 가정).
파형 철손: 한 주기 B 파형의 각 성분(Bx, By)을 푸리에 분해해 고조파 k마다 P(k·f1, 진폭)을 더한다(직류 성분은 무시, 성분별 합산).
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SteelLoss:
    name: str
    k_h: float            # [W/(kg·Hz·T^α)]
    alpha: float
    k_e: float            # [W/(kg·Hz²·T²)]
    density_kg_m3: float

    def loss_density(self, f: float, B: float) -> float:
        """밀도당 철손 [W/kg], B는 진폭."""
        return self.k_h * f * abs(B) ** self.alpha + self.k_e * (f * B) ** 2

    def loss_from_waveform(self, bx, by, f1: float) -> float:
        """한 전기 주기를 고르게 나눈 파형 (bx, by) [T]의 밀도당 철손 [W/kg]. 직류 성분은 무시한다."""
        total = 0.0
        for comp in (np.asarray(bx, dtype=float), np.asarray(by, dtype=float)):
            n = comp.size
            amp = np.abs(np.fft.rfft(comp)) * 2.0 / n
            for k in range(1, amp.size):
                if amp[k] > 0.0:
                    total += self.loss_density(k * f1, amp[k])
        return total


def steel_from_catalog(name: str, thickness_m: float, resistivity_ohm_m: float, density_kg_m3: float,
                       w10_50: float, w15_50: float) -> SteelLoss:
    k_e = math.pi ** 2 * thickness_m ** 2 / (6.0 * resistivity_ohm_m * density_kg_m3)
    h1 = w10_50 - k_e * 50.0 ** 2 * 1.0 ** 2
    h15 = w15_50 - k_e * 50.0 ** 2 * 1.5 ** 2
    if h1 <= 0 or h15 <= 0:
        raise ValueError("와전류 항이 전체 손실을 넘는다: 카탈로그 값과 비저항·두께를 확인하라")
    alpha = math.log(h15 / h1) / math.log(1.5)
    return SteelLoss(name, h1 / 50.0, alpha, k_e, density_kg_m3)


def load_steel(name: str) -> SteelLoss:
    """data/materials/steel_<name>.json (JFE 카탈로그 값)에서 계수를 구한다."""
    root = Path(os.environ.get("MOTORLAB_ROOT") or ROOT)
    j = json.loads((root / "data" / "materials" / f"steel_{name}.json").read_text(encoding="utf-8"))
    w = j["typical"]["core_loss_W_per_kg"]
    return steel_from_catalog(name, j["thickness_mm"] * 1e-3, j["resistivity_uOhm_cm"] * 1e-8, j["assumed_density_kg_dm3"] * 1e3,
                              w["W10_50"], w["W15_50"])
