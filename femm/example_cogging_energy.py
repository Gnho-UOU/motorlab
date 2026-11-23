"""코깅 토크의 해석기 내부 검증: Henrotte(가중 응력 텐서) 토크와 자기 에너지·공동 에너지 미분의 일치.

무부하(전류 0)에서 토크 = ∂W'/∂θ = −∂W/∂θ (가상 일). xfemm이 계산하는 두 값이 같은 모양·크기면 코깅 토크 값이 토크 계산 방식의 오차가 아니다.
같은 모델(예제 모터, 기본 메시), 회전자 한 슬롯 피치(7.5°)를 12점(JMAG 비교와 같은 간격)으로 푼다. 에너지 미분은 주기 중심 차분이다.
실행: FEMMCLI=<femmcli> python femm/example_cogging_energy.py   → data/fea/example_motor_cogging_energy.csv
"""
import csv
import math
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import example_motor as em  # noqa: E402
import prius_full as pf  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.magnet import load_grade  # noqa: E402

G = load_grade("N45SH")
JOBS = int(os.environ.get("JOBS", "16"))
N = 12
STEP = 7.5 / N


def solve(rotor_deg: float):
    femmcli = os.environ.get("FEMMCLI", "femmcli")
    g = em.model_dict(G.br(50.0), G.mu_r(50.0), "jfe", em.P)
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "build.lua").write_text(em.lua_model(g, em.build(rotor_deg, None, em.P), "m.fem"))
        subprocess.run([femmcli, "-q", "--lua-script=build.lua"], cwd=d, capture_output=True, text=True, timeout=3600, check=True)
        lines = (d / "m.fem").read_text().splitlines()
        lines.insert(1, "[DoSmartMesh] = 0")
        (d / "m2.fem").write_text("\n".join(lines) + "\n")
        lua = pf._driver((0.0, 0.0, 0.0), "full.fem") + 'mo_clearblock()\nmo_groupselectblock()\nprint(format("EN %.12g %.12g", mo_blockintegral(2), mo_blockintegral(17)))\n'
        (d / "run.lua").write_text('open("m2.fem")\n' + lua)
        out = subprocess.run([femmcli, "-q", "--lua-script=run.lua"], cwd=d, capture_output=True, text=True, timeout=3600)
    pt = [l.split() for l in out.stdout.splitlines() if l.startswith("PT ")]
    en = [l.split() for l in out.stdout.splitlines() if l.startswith("EN ")]
    if len(pt) != 1 or len(en) != 1:
        raise RuntimeError(out.stdout[-800:] + out.stderr[-400:])
    return float(pt[0][1]), float(en[0][1]), float(en[0][2])


def main() -> None:
    pos = [STEP * k for k in range(N)]
    with ThreadPoolExecutor(max_workers=JOBS) as ex:
        res = list(ex.map(solve, pos))
    T = np.array([r[0] for r in res]); W = np.array([r[1] for r in res]); Wc = np.array([r[2] for r in res])
    h = math.radians(STEP)
    dW = -(np.roll(W, -1) - np.roll(W, 1)) / (2 * h)
    dWc = (np.roll(Wc, -1) - np.roll(Wc, 1)) / (2 * h)
    with open(ROOT / "data" / "fea" / "example_motor_cogging_energy.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rotor_deg", "torque_henrotte_Nm", "energy_J", "coenergy_J", "torque_from_energy_Nm", "torque_from_coenergy_Nm"])
        for k in range(N):
            w.writerow([f"{pos[k]:.4f}", f"{T[k]:.4f}", f"{W[k]:.8f}", f"{Wc[k]:.8f}", f"{dW[k]:.4f}", f"{dWc[k]:.4f}"])
    print("p-p Henrotte", np.ptp(T), "−dW/dθ", np.ptp(dW), "dW'/dθ", np.ptp(dWc))


if __name__ == "__main__":
    main()
