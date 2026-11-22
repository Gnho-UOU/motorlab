"""xfemm(`femmcli`) 또는 FEMM이 해석해 문제를 푸는지 확인한다. 기술한 조건에서만 통과한다.

사용법 (femmcli를 빌드했다면 그 경로를 FEMMCLI에 준다):
    FEMMCLI=/경로/xfemm/cfemm/bin/femmcli python femm/validation/run_checks.py

확인 내용
  1) uniform_cylinder: 균일장 속 선형 원통, 해석해 Bx = 2μr/(μr+1)·B0   (순수 선형)
  2) pm_cylinder: 균일 자화 원통, 해석해 Bx = (Br/2)(1 − (R/Rfar)²)      (영구자석)
  3) bh_shell: 전류선 둘레 비선형 강판, 해석해 B = f(I/2πr)               (비선형 BH, 포화 포함)
공기 영역 메시가 거칠면 1차 요소의 오차가 1% 이상 남는다 (docs/FEA_OPTIONS.md 6절). 그래서 1·2는 메시를
점점 촘촘히 해 오차가 단조롭게 줄고 0.5% 이내로 들어오는지를 검사한다.
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
FEMMCLI = os.environ.get("FEMMCLI", "femmcli")


def run(script: str, **params) -> list[dict[str, float]]:
    """파라미터 줄(`NAME = 값`)을 바꿔 임시 폴더에서 실행하고 RESULT 줄을 사전으로 돌려준다."""
    src = (HERE / script).read_text()
    for name, value in params.items():
        src, n = re.subn(rf"^{name} = .*$", f"{name} = {value}", src, flags=re.M)
        assert n == 1, f"{script}: 파라미터 줄 {name}을 찾지 못했다"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / script).write_text(src)
        out = subprocess.run([FEMMCLI, "-q", f"--lua-script={script}"], cwd=d, capture_output=True,
                             text=True, timeout=600)
    rows = [dict(kv.split("=") for kv in line.split()[1:]) for line in out.stdout.splitlines()
            if line.startswith("RESULT")]
    assert rows, f"{script}: 결과 없음\n{out.stdout[-500:]}\n{out.stderr[-500:]}"
    return [{k: float(v) for k, v in r.items()} for r in rows]


def mesh_study(script, solve_key, exact, mesh_param, levels) -> bool:
    errs = []
    for mesh_a, mesh_b in levels:
        bx = run(script, **{mesh_param[0]: mesh_a, mesh_param[1]: mesh_b})[0][solve_key]
        errs.append((bx / exact - 1) * 100)
        print(f"   {mesh_param[0]}={mesh_a:g}, {mesh_param[1]}={mesh_b:g}: {bx:.5f} T, 오차 {errs[-1]:+.2f}%")
    ok = all(abs(b) < abs(a) for a, b in zip(errs, errs[1:])) and abs(errs[-1]) < 0.5
    print("   ->", "통과 (단조 수렴, 마지막 0.5% 이내)" if ok else "실패")
    return ok


def main() -> int:
    levels = [(0.0004, 0.01), (0.0002, 0.004), (0.0002, 0.002)]
    ok = True
    print("1) uniform_cylinder (선형)")
    exact = 2 * 10 / 11 * 0.1
    ok &= mesh_study("uniform_cylinder.lua", "Bx", exact, ("MESH_IRON", "MESH_AIR"), levels)
    print("2) pm_cylinder (영구자석)")
    exact = 1.2 / 2 * (1 - (0.01 / 0.3) ** 2)
    ok &= mesh_study("pm_cylinder.lua", "Bx", exact, ("MESH_MAGNET", "MESH_AIR"), levels)
    print("3) bh_shell (비선형 BH)")
    for iamp in (300, 3000):
        for r in run("bh_shell.lua", IAMP=iamp):
            err = (r["B"] / r["expected"] - 1) * 100
            good = abs(err) < 1.0
            ok &= good
            print(f"   I={iamp} A, r={r['r']:.3f} m: B={r['B']:.5f} T, 해석해 {r['expected']:.5f} T, 오차 {err:+.2f}% "
                  f"{'' if good else '<- 실패'}")
    print("전체:", "통과" if ok else "실패")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
