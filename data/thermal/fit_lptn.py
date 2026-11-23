"""M7 열회로 매개변수 보정: ORNL/TM-2005/33의 측정으로 권선-철심 열전도도와 외부 경계 열전도도를 정하고 data/thermal/prius2004_lptn.json에 쓴다.

정한 순서와 근거 (맞춘 값과 물리/문헌 값을 구분한다):
  문헌·측정값(맞추지 않음): 권선 열용량 C_w = 구리 질량 6.8 kg × 385 J/(kg·K), 철심 열용량 C_s = 고정자 적층 질량 19.05 kg × 447 J/(kg·K),
    권선 저항 R21 = 0.069 Ω (21 °C), α_cu = 0.00393 /K.
    질량: ORNL/TM-2010/253 표 2.7 (data/benchmarks/prius2004_ornl.md), 비열: 교과서 값 (Incropera, Fundamentals of Heat and Mass Transfer, 부록 A 표 A.1, 300 K: 구리 385, 순철 447).
    규소강판의 비열은 순철과 몇 % 다를 수 있다(그 오차는 보정하지 않았다).
  G_sb (철심 → 외부 경계): ORNL 연속 시험 4점(표 9·10, data/thermal/prius2004_steady.csv)에서 기름 온도를 경계로 보고
    (동손 + 철손·잔여) / (T_철심 − T_기름), T_철심 = T_권선 − 동손/G_ws. 네 값의 평균. (철손·잔여는 모두 철심으로 간다고 가정. 기계손은 기름으로 가므로 뺀다.)
  G_ws, 철심 초기 온도: ORNL 그림 19의 첨두 시험 5곡선(data/thermal/prius2004_peak_winding_transient.csv, 권선 65~168 °C, 30~91 s)에 모델을 맞춘다.
    곡선마다 철심 초기 온도는 측정되지 않아 곡선당 하나씩 같이 맞춘다. 외부 경계 온도 T_b는 연속 시험 기름 온도 평균(122.1 °C)에 고정하고 민감도는 notebooks/19에서 본다.
이 스크립트는 일회성 보정 도구다(엔진은 JSON만 읽는다). 실행: python data/thermal/fit_lptn.py
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from engine.thermal import LPTNParams, simulate_cycle_copper  # noqa: E402

M_CU, CP_CU, M_FE, CP_FE = 6.8, 385.0, 19.05, 447.0
R21, ALPHA = 0.069, 0.00393


def load_steady():
    rows = [[float(x) for x in l.split(",")] for l in (ROOT / "data/thermal/prius2004_steady.csv").read_text().splitlines() if l[:1].isdigit()]
    return np.array(rows)


def load_peak():
    out = {}
    for l in (ROOT / "data/thermal/prius2004_peak_winding_transient.csv").read_text().splitlines():
        if l[:1].isdigit():
            tq, I, t, T = (float(x) for x in l.split(","))
            out.setdefault(int(tq), []).append((t, T, I))
    return {k: np.array(v) for k, v in sorted(out.items())}


def g_sb_from_steady(G_ws, steady):
    Tc, Tq, Pt, Pm, Pcu, Pco, Tw, To, dT, fl = steady.T
    Ts = Tw - Pcu / G_ws
    return float(np.mean((Pcu + Pco) / (Ts - To)))


def make_params(G_ws, G_sb, T_b, Ts0=None):
    return LPTNParams("prius2004", M_CU * CP_CU, M_FE * CP_FE, G_ws, G_sb, R21, ALPHA, T_b, Ts0 or {})


def simulate_curve(G_ws, G_sb, T_b, v, Ts0):
    p = make_params(G_ws, G_sb, T_b)
    r = simulate_cycle_copper(p, v[:, 0], np.full(len(v), v[0, 2]), np.zeros(len(v)), T_b, v[0, 1], Ts0, current_is_rms=True)
    return r["T_winding_C"]


def fit(T_b, steady, curves, G_ws0=150.0):
    keys = list(curves)
    G_sb = g_sb_from_steady(G_ws0, steady)

    def res(q, sel=None):
        G_ws = float(np.exp(q[0]))
        r = []
        for j, k in enumerate(keys):
            if sel and k not in sel:
                continue
            r += list(simulate_curve(G_ws, g_sb_from_steady(G_ws, steady), T_b, curves[k], q[1 + j]) - curves[k][:, 1])
        return np.array(r)

    q0 = [np.log(G_ws0)] + [60.0] * len(keys)
    f = least_squares(res, q0, bounds=([np.log(5)] + [0.0] * len(keys), [np.log(3000)] + [170.0] * len(keys)))
    G_ws = float(np.exp(f.x[0]))
    return G_ws, g_sb_from_steady(G_ws, steady), {str(k): float(f.x[1 + j]) for j, k in enumerate(keys)}, float(np.sqrt(np.mean(f.fun ** 2)))


def main() -> None:
    steady, curves = load_steady(), load_peak()
    T_b = float(np.mean(steady[:, 7]))
    G_ws, G_sb, Ts0, rms = fit(T_b, steady, curves)
    sens = {}
    for tb in (80.0, 100.0, 115.0, T_b):
        g, gs, _, r = fit(tb, steady, curves)
        sens[f"{tb:.1f}"] = {"G_ws": round(g, 1), "G_sb": round(gs, 1), "rms_K": round(r, 2)}
    out = {
        "__source__": "ORNL/TM-2005/33 (data/benchmarks/raw/ornl_pub57487_thermal.pdf)로 보정한 2노드(권선, 고정자 철심) 열회로. 보정 방법은 data/thermal/fit_lptn.py 머리말.",
        "parameters": {
            "C_winding_J_per_K": {"value": M_CU * CP_CU, "source": "구리 질량 6.8 kg(ORNL/TM-2010/253 표 2.7) × 385 J/(kg·K)(Incropera 표 A.1). 문헌값, 맞추지 않음"},
            "C_stator_J_per_K": {"value": M_FE * CP_FE, "source": "고정자 적층 질량 19.05 kg(ORNL/TM-2010/253) × 447 J/(kg·K)(Incropera 표 A.1 순철). 문헌값, 맞추지 않음"},
            "G_winding_stator_W_per_K": {"value": round(G_ws, 2), "source": f"그림 19 첨두 시험 5곡선에 맞춤 (RMS {rms:.2f} K, 철심 초기 온도는 곡선마다 맞춤)"},
            "G_stator_boundary_W_per_K": {"value": round(G_sb, 2), "source": "연속 시험 4점(표 9·10)의 평형에서 구함: 기름 온도를 경계로 둔 철심 → 기름 열전도도의 평균(네 값 34~44 W/K)"},
            "R21_ohm": {"value": R21, "source": "ORNL/TM-2010/253 표 2.7, 21 °C의 상저항 0.069 Ω"},
            "alpha_cu_per_K": {"value": ALPHA, "source": "구리의 저항 온도계수 0.00393 /K (benchmarks 효율 검증과 같은 값)"},
            "boundary_fit_C": {"value": round(T_b, 1), "source": "보정에 쓴 외부 경계 온도 = 연속 시험 기름 최종 온도 4점의 평균(114.3, 118.5, 125.3, 130.3 °C). 그림 19 시험의 실제 기름 온도는 측정 자료에 없다"},
        },
        "fit_initial_stator_C": {k: round(v, 1) for k, v in Ts0.items()},
        "provenance": {"fit_rms_K": round(rms, 3), "boundary_sensitivity": sens,
                       "note": "철심 초기 온도(곡선마다 하나)는 측정되지 않아 맞춘 값이다. T_b 80~122 °C에서 G_ws는 바뀌므로(boundary_sensitivity) 5~10초 안의 짧은 시험으로는 철심·외부 경계 매개변수를 따로 가르지 못한다."},
    }
    (ROOT / "data" / "thermal" / "prius2004_lptn.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"G_ws": G_ws, "G_sb": G_sb, "T_b": T_b, "rms": rms, "Ts0": Ts0, "sensitivity": sens}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
