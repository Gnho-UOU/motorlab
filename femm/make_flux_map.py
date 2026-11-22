"""Prius 모델(xfemm femmcli)로 dq 자속 맵 CSV를 만든다. data/flux_maps/README.md의 형식을 따른다.

사용법:  FEMMCLI=/경로/femmcli python femm/make_flux_map.py [출력.csv] [격자간격 A]
id 줄(열)마다 점들을 묶어 풀고 즉시 이어 쓰므로, 중간에 끊겨도 같은 출력 파일로 다시 실행하면 이어서 한다.

한계 (docs/FEA_OPTIONS.md 3-2절): 회전자 위치 δ = 0 한 곳에서만 푼다(xfemm AGE 회전이 큰 각도에서 부정확). 2D 해석이라 엔드턴 누설
인덕턴스가 없다. 형상·자석은 제3자 값(미검증). torque_Nm은 AGE 맥스웰 응력 토크로 이 위치의 순간값이며 비교용이다.
"""
from __future__ import annotations

import math
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import prius_run as pr  # noqa: E402

pr.POLES_IN_SECTOR = 1   # 1극 반대칭 섹터(점당 약 5~8초). δ = 0에서만 쓴다.
IMAX = 250.0

HEADER = """# 출처: 합성이 아닌 FEA 계산 결과. 형상·재료는 data/benchmarks/prius2004_geometry.json (pyleecan Toyota_Prius.json, 제3자 모델, ORNL 원문 값이 아니며 미검증).
# 솔버: xfemm femmcli (커밋 132515c, macOS 이식성 패치 3종, femm/build_xfemm_macos.sh). 2D 정자장, 비선형 BH(철심 M400-50A, 출처 미확인), 자석 Br20 = 1.24 T, mur = 1.05 (pyleecan 값).
# 조건: 1극(45°) 섹터 반대칭 경계, 공극 요소(AGE), 회전자 위치 δ = 0 한 곳(d축이 치 중심, 기준각 22.5°), 자석 온도 20 °C 가정, 슬롯 입구·치 끝 포함 형상. 섹터 쇄교자속 x 8 = 전체.
# dq: 크기 불변 Park 변환, d축 = 자석 N극 축, A상 축 대비 전기각 150°(코일 중심 기준 유도, 무부하 해석으로 149.9°~150.0° 확인). 전류는 상 첨두값.
# 한계: 엔드턴 누설 인덕턴스 없음(2D). 슬롯 맥동이 평균되지 않음(단일 위치, 무부하에서 위치별 ψd 변동 약 +-1%). torque_Nm은 AGE 토크이고 이 위치의 순간값(위치 평균이 아님): 자속 기반 토크와 -9%~+22% 차이.
# 단위: id_A, iq_A [A], psi_d_Wb, psi_q_Wb [Wb], torque_Nm [N·m]
"""


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "prius2004_xfemm_delta0.csv")
    step = float(sys.argv[2]) if len(sys.argv) > 2 else 25.0
    ids = np.arange(-IMAX, 1e-9, step)
    iqs = np.arange(0.0, IMAX + 1e-9, step)
    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            if line and not line.startswith("#") and not line.startswith("id_A"):
                a, b = line.split(",")[:2]
                done.add((round(float(a), 6), round(float(b), 6)))
    else:
        out.write_text(HEADER + "id_A,iq_A,psi_d_Wb,psi_q_Wb,torque_Nm\n")
    th = math.radians(pr.THETA0_ELEC_DEG)
    t0 = time.time()
    for i in ids:
        todo = [q for q in iqs if (round(float(i), 6), round(float(q), 6)) not in done]
        if not todo:
            continue
        idv, iqv = np.full(len(todo), i), np.array(todo)
        abc = pr.inverse_park(idv, iqv, np.full(len(todo), th))
        r = pr.solve_points([(a, b, c, 0.0) for a, b, c in abc])
        psid, psiq = pr.park(r["lambda_abc_Wb"], np.full(len(todo), th))
        with out.open("a") as f:
            for q, d, qq, T in zip(todo, psid, psiq, r["torque_Nm"]):
                f.write(f"{i:g},{q:g},{d:.6f},{qq:.6f},{T:.3f}\n")
        print(f"id = {i:6.1f} A 완료 ({len(todo)}점), 경과 {time.time() - t0:.0f}s", flush=True)
    print("끝:", out)


if __name__ == "__main__":
    main()
