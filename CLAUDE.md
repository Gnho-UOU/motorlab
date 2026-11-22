# Motor Lab — EV 구동모터(IPMSM) 설계·효율·전비 통합 해석 도구

전기차 구동용 매입형 영구자석 동기전동기(IPMSM)를 "설계 변수 → dq 모델 → 운전 영역(MTPA·약계자) → 효율맵 → 주행사이클 전비"로 한 번에 계산하는 개인 프로젝트다. 계산은 순수 Python 엔진이 맡고, 결과는 공개 실측(ORNL 프리우스 2004)과 FEA로 검증한 뒤 3D 웹 UI에 보여 준다.

목적: 울산대 임동국 교수(전동기 설계·다물리·최적화), 한양대 임명섭 교수(EV 구동모터·영구자석·주행사이클 전비) 연구실 컨택용 포트폴리오이자, 사용자 본인의 모터 공부 도구.

사용자: 전기전자공학 3학년. 한국어로 소통한다. 바이브코딩으로 진행하지만 **모든 수식과 코드를 본인이 설명할 수 있어야 한다**(면담 대비).

## 먼저 읽을 것
1. `docs/HANDOFF.md` — 현재 상태, 정해진 결정, 남은 질문, 첫 작업
2. `docs/ENGINE_SPEC.md` — 엔진 규약, 모듈 인터페이스, V1 테스트 목록
3. `docs/PLAN.pdf` (텍스트판: `docs/PLAN.txt`) — 전체 기획서(목표·비목표·수식·검증·일정·리스크)

## 반드시 지킬 규칙
- **엔진 우선.** `engine/`은 UI·서버 코드에 의존하지 않는 순수 Python 패키지다. UI(`web/`)와 서버(`api/`)에는 계산식을 두지 않는다. 화면의 모든 숫자는 엔진이 계산한 값이다.
- **근거 없는 보정계수 금지.** 결과를 맞추려고 임의 계수를 넣지 않는다. 모든 상수·재료값·벤치마크 값은 `data/`에 출처(문헌·쪽수·URL)와 단위를 함께 기록한다. 출처를 댈 수 없는 숫자는 넣지 않는다. (이전 프로젝트 motor-analyzer의 실패 원인이다.)
- **SI 단위.** 엔진 내부와 인터페이스는 SI(A, V, H, Wb, Ω, rad/s, N·m, W, K 또는 °C 명시). rpm·deg·mH 같은 표시 단위는 경계(API·UI)에서만 변환하고, 변수명에 접미사를 붙인다(`speed_rpm`, `beta_deg`).
- **테스트 먼저.** 엔진 함수는 pytest 테스트를 먼저 쓰고 구현한다. `docs/ENGINE_SPEC.md`의 V1 테스트는 항상 통과 상태를 유지한다.
- **단계 관문.** 기획서 9장 순서(P0 → P1 → P2 → P3 → G1 → P4 → P5 → P6)를 지킨다. G1(검증 관문) 통과 전에는 M4 이후 기능·UI 확장을 시작하지 않는다.
- **범위 고정.** 기획서 4장의 M1~M8 밖 기능은 만들지 않는다. 새 기능이 필요해 보이면 먼저 사용자에게 묻고, 승인되면 기획서를 고친 뒤 작업한다.
- **설명 가능성.** 함수 docstring에 수식과 근거 문헌(기획서 5장 절 번호 포함)을 적는다. 수식 유도는 `docs/derivations.md`에 계속 정리한다. 변경을 보고할 때는 무엇을 왜 바꿨는지 한국어로 쉽게 설명한다.
- **FEMM은 분리.** FEMM은 Windows 전용이다. `femm/` 스크립트는 Windows에서 실행되어 자속 맵 CSV를 `data/flux_maps/`에 남기는 역할만 한다. `engine/`은 femm/pyfemm을 import하지 않고 CSV만 읽는다.
- **건드리지 말 것.** GitHub `Gnho-UOU/motor-analyzer` 저장소는 수정하지 않는다(참고만 가능).
- `reference/`와 `web/prototype/`은 참고용 초안이다. 검증되지 않았으니 그대로 복사해 쓰지 말고 아이디어만 참고한다.

## 계획된 구조
```
engine/      model.py(M1) operating.py(M2) losses.py(M3) vehicle.py(M4) magnet.py(M5) optimize.py(M6)
femm/        FEMM 일괄 계산 스크립트(Windows) + run_femm.bat
data/        주행사이클, 강판·자석 데이터, 벤치마크 값, flux_maps/  (각 파일에 출처·단위 기록)
tests/       pytest (V1~V3)
notebooks/   검증 노트북, 보고서 그림
api/         FastAPI
web/         3D UI (web/prototype/는 초안)
docs/        기획서, 엔진 설계서, 수식 유도 노트, 검증 보고서
```

## 기술 스택
Python 3.12, NumPy, SciPy, pytest, Matplotlib, Jupyter / 최적화: pymoo, scikit-learn / FEA: FEMM 4.2 + pyfemm / 서버: FastAPI / 화면: Three.js, TypeScript.
엔진 런타임 의존성은 NumPy·SciPy로 제한한다(pandas는 노트북에서만).
