# 인수인계 (claude.ai 대화 → Claude Code)

작성: 2026-11-22. 이 폴더는 claude.ai 대화에서 기획까지 마친 상태로 Claude Code에 넘어왔다. 코드는 아직 한 줄도 없다.

## 지금까지 정해진 것
- 주제: EV 구동용 IPMSM 설계 → 효율맵 → 주행사이클 전비 통합 해석 도구. 기존 `Gnho-UOU/motor-analyzer`(유도기 교육용 시뮬레이터, 계산 근거·검증 부족)를 대체하는 새 프로젝트. motor-analyzer는 수정하지 않는다.
- 계산은 순수 Python 엔진, UI는 이후에 붙인다. 검증 통과 전 UI 확장 금지.
- 필수 범위 M1~M4(모터 모델, 운전 영역, 손실·효율맵, 주행사이클 전비). 확장 M5~M8은 순서대로.
- 최종 검증 기준: ORNL 프리우스 2004 구동모터(형상 보고서 ORNL/TM-2004/137 + 효율맵 측정 보고서). 이 모터는 "엔진 정답지"이고 설계 대상은 아니다. 설계 대상은 엔진 검증 후 현대 BEV급 사양으로 따로 정한다.
- FEA는 FEMM 4.2 + pyfemm. FEMM이 Windows 전용이라, Windows PC에서 `run_femm.bat` 더블클릭 한 번으로 계산 → CSV 저장 → GitHub 푸시까지 자동화한다(방법 1). 최적화 단계(M6)에서는 공유 폴더를 감시하는 작업 대기 모드(방법 2)를 검토한다.
- JMAG 등 상용 툴 리버싱은 하지 않는다. 나중에 연구실 라이선스를 쓸 수 있도록 FEA 부분은 교체 가능한 구조로 둔다.
- 일정(기획서 9장): P0 문헌·환경 준비(~12/6) → P1 엔진 코어 M1·M2(~1/3) → P2 손실·효율맵(~1/24) → P3 FEMM 연동·검증(~2/28) → G1 검증 관문 → P4 전비·UI 연결(~3/28) → 3/31 연구실 컨택 → P5 확장 → P6 정리.

## 폴더 안의 것
| 경로 | 내용 |
| --- | --- |
| `CLAUDE.md` | 프로젝트 규칙 (항상 적용) |
| `docs/PLAN.pdf`, `docs/PLAN.txt` | 전체 기획서 14쪽 (원본: claude.ai 문서) |
| `docs/ENGINE_SPEC.md` | 엔진 규약, M1·M2 인터페이스, V1 테스트 |
| `web/prototype/index.html` | 3D 쇼룸 초안 (Three.js 0.160, 산업용 유도기 모델, 부품 클릭 확대, 단자박스 Y/Δ 결선 편집). EV 모터로 바꾸고 엔진과 연결하는 건 P4 |
| `reference/draft_getCurve.js` | 폐기된 2D 초안의 최대 토크 격자 탐색 로직 (미검증, 참고만) |

## 2026-11-22 구현 시작 시 문서 정정
- P1 완료 조건을 "V1·V2"(기획서 초안)에서 "V1(T1~T8)"로 정정. V2는 교재 확정 후 P2 전까지. `PLAN.txt`와 `ENGINE_SPEC.md`에 반영, `PLAN.pdf`는 원본 유지.
- T8(MTPV) 추가: 기본 테스트 파라미터는 ψm/Ld > Imax라 MTPV 영역이 없어서 MTPV 전용 파라미터(ψm = 0.025 Wb)를 따로 둠.
- `base_speed()` 추가, `max_torque_curve`에 `feasible`·`INFEASIBLE` 추가, FluxMapModel은 P3로 이동 명시.
- 환경: 이 Mac에 Python 3.12가 없어 uv 0.13.9를 `~/.local/bin`에 설치(셸 설정 변경 없음)하고 `.venv`를 3.12로 만듦. 실행은 `.venv/bin/python -m pytest`.

## 아직 열린 질문 (사용자에게 확인)
1. FEMM을 돌릴 Windows PC가 본인 노트북인지 학교 PC인지 → 자동화 방식 결정. **2026-11-22 현재 사용자가 모름.** FEMM은 Windows 전용. **해결 방향 확정:** Mac에서 xfemm `femmcli`로 돌린다(빌드·해석해 시험 통과, 자세한 내용은 `docs/FEA_OPTIONS.md` 3-1절). 빌드는 `femm/build_xfemm_macos.sh`, 검증은 `femm/validation/run_checks.py`. Windows PC는 진짜 FEMM과의 교차 검증용으로만 필요하다.
2. 두 번째 벤치마크(닛산 리프 등 최근 BEV 모터)의 공개 데이터 여부 조사 여부
3. 수치 목표(기획서 3·6장)는 초안. ORNL 보고서의 측정 조건을 읽고 확정 → **측정 조건은 읽었음**(`data/benchmarks/prius2004_ornl.md` 3절): 효율맵은 DC 약 500 V, 냉각수 55 °C, 기어 손실 제외 모터 단독. 모터 효율은 인버터 제외. 수치 목표 확정은 V3 첫 결과를 본 뒤.

## 2026-11-22 ORNL 자료 확보 결과
- 보고서 3편 확보(TM-137, TM-185, TM-423). **형상 치수는 보고서에 없음.** 형상 후보는 제3자(pyleecan, Kaczmarek 2013)뿐이고 철심 재질이 서로 다름(M400-50A 대 M19). 상저항·철손 데이터도 없음. 자세한 내용은 `data/benchmarks/prius2004_ornl.md`.
- 실측 표 4개를 CSV로 옮김(`data/benchmarks/prius2004_*.csv`): 성능 맵 428점, 역기전력, 로터 손실, 잠금 토크. 원문 PDF는 `data/benchmarks/raw/`(git 제외).
- 상수 모델로 예비 점검: 저전류 토크는 실측과 맞고 250 A에서 약 2배 크다(포화). 그래서 V3(FEA 자속 맵)가 필요하다.
- V2는 주 교재 대신 돌극 동기기 전력-부하각식으로 대체(`tests/test_v2_textbook.py`).

## 첫 작업 (P0 마무리 + P1 시작)
1. 저장소 초기화: `git init`, Python 프로젝트 구성(pyproject.toml, engine/ tests/), .gitignore, README.
2. `docs/derivations.md` 시작: dq 모델, 토크식, MTPA 해석식 유도.
3. `docs/ENGINE_SPEC.md`의 V1 테스트(T1~T7)를 먼저 작성 → `engine/model.py`(ConstantParamModel) → `engine/operating.py`(mtpa_point, max_torque_curve, optimal_current).
4. 노트북 하나에 T-N 곡선과 dq 전류 평면 그림.
5. 각 단계 끝에 사용자에게 한국어로 무엇을 했고 수식이 어떻게 코드가 됐는지 짧게 설명.

## Claude Code에 처음 붙여넣을 지시문
```
이 폴더는 Motor Lab 프로젝트야. CLAUDE.md, docs/HANDOFF.md, docs/ENGINE_SPEC.md를 먼저 읽고,
필요하면 docs/PLAN.txt로 기획서 전체를 확인해줘.
그다음 HANDOFF.md의 "첫 작업"대로 P1(엔진 코어 M1·M2)을 시작하자.
코드를 쓰기 전에 구현 계획을 짧게 보여주고 내 승인을 받아줘.
테스트(V1의 T1~T7)를 먼저 쓰고, 구현하고, 테스트가 전부 통과하는 걸 보여줘.
설명은 한국어로, 수식이 코드의 어디에 대응하는지 알려줘.
```
