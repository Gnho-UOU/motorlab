# Motor Lab

EV 구동용 매입형 영구자석 동기전동기(IPMSM)를 "설계 변수 → dq 모델 → 운전 영역(MTPA·약계자) → 효율맵 → 주행 사이클 전비"까지 한 흐름으로 계산하는 해석 도구입니다. 계산은 순수 Python 엔진(NumPy·SciPy)이 맡고, 결과는 공개 실측(ORNL의 2004 Toyota Prius 구동모터)과 FEA(xfemm)로 검증한 뒤 3D 웹 화면에 보여 줍니다. 모든 상수와 재료값에는 출처와 단위를 달고, 맞지 않는 결과도 원인 탐색 과정과 함께 숨기지 않고 기록합니다.

## 진행 현황 (갱신: 2026-11-23)

| 단계 | 내용 | 상태 |
| --- | --- | --- |
| P1 엔진 코어 M1·M2 | dq 모델, MTPA, 약계자, 토크-속도 곡선 | 완료 (해석해 테스트 통과) |
| P2 M3 손실·효율맵 | 동손, 철손, 기계손, 효율맵 40×60 1.5초 | 완료 |
| P3 FEA 연동·검증 | xfemm 전체 모터 모델, dq 자속 맵, ORNL 실측 비교 | 완료, **G1 관문은 미달** (고속 효율 +10%p) |
| P4 M4 전비·화면 | WLTP·UDDS·HWFET 전비, FastAPI, React 3D 스튜디오, Electron 셸 | 구현 (화면은 사용자 검토 중, 설치 파일 미검증) |
| P5 M5 자석 소재·감자 | 제조사 데이터시트 곡선, 온도별 무릎점, 소재별 토크·전비, FEA 감자 확인 | 완료 |
| 예제 모터 비교 | 연구실 예제 IPMSM을 xfemm으로 풀어 JMAG와 비교 | 토크·전압·THD 2~3% 일치, 코깅·철손은 미해결 |
| P5 M6 최적화 | NSGA-II 파레토 | 예정 |
| P6 정리·보완 | 검증 보고서 최종본, 면담 준비 | 예정 |

**핵심 결과**
- ORNL Prius 잠금 토크 FEA/측정 0.94~1.00, 무부하 공극 자속밀도 일치. 모터 효율은 물리 모델이 주요 영역에서 +3.7%p, 4000 rpm 이상에서 약 +10%p 높다(G1 미달, 원인 탐색 중).
- WLTP 전비 약 10 km/kWh(모터 입력 기준, 순수 전기 구동 환산). 자석 소재(N45SH, N38UH)를 바꿔도 WLTP는 ±0.6% 이내이고, 핵심은 고온 감자 여유다(N45SH 150 °C는 최대 토크 전류에서 무릎점을 넘는다).
- 연구실 예제 모터(8극 48슬롯)를 JMAG 결과와 비교하면 역기전력 THD 15.41 % 대 15.10 %, 평균 토크 +1.7%, 토크 리플 8.49 % 대 8.22 %, 단자 전압 +2.5 %다. 코깅 토크는 JMAG보다 40~50% 크다(원인 미확인).

**알려진 한계** (자세한 내용은 `docs/validation_report.md`): 고속 필요 전류와 효율 미해결, 3D 효과·엔드턴 누설 없음(2D), 자석 온도는 상수(열 모델 M7 전), 페라이트 감자 판정 불가(자료 미확보), 데모 배포·설치 파일 미검증.

## 검증 한눈에 보기
![검증 요약](docs/figures/validation_summary.png)

(a) 잠금 토크와 (b) 공극 자속밀도는 FEA가 ORNL 실측과 맞고, (c) 효율과 (d) 필요 전류는 저속에서는 맞지만 고속에서 물리 모델이 실측과 **맞지 않는다**(G1 미달). 교정에 쓴 값은 자석 Br 1.06 T 하나이다. 그림은 `python notebooks/11_validation_figures.py`로 다시 만든다. 한계와 원인 탐색은 `docs/validation_report.md`, 컨택용 2쪽 요약은 [docs/summary.pdf](docs/summary.pdf)(원본 `docs/summary.html`).

테스트: `.venv/bin/python -m pytest` → 156개 통과(엔진 코어, 손실, 전비, API, 파형, 자석 M5, 예제 모터).

- 기획서: `docs/PLAN.pdf`
- 엔진 설계서: `docs/ENGINE_SPEC.md`
- 수식 유도: `docs/derivations.md`
- 검증 노트북: `notebooks/01_operating_region.ipynb` (T-N 곡선, dq 전류 평면), `notebooks/02_efficiency_map.ipynb` (효율맵, 손실 분포)
- 3D 스튜디오(P4): `web/` (React + TypeScript + react-three-fiber), 서버 `api/main.py`(FastAPI), 데스크톱 셸 `web/electron/`. 초안은 `web/prototype/index.html`(검증되지 않은 참고용)
- 자석 소재·감자(M5): `engine/magnet.py`, 자료 `data/materials/`(제조사 출처), 결과표 `notebooks/12_prius_magnet_check.py`, 소재별 토크·전비 `notebooks/13_prius_magnet_compare.py`
- 연구실 예제 모터 대 JMAG 비교(해석기끼리): `femm/example_motor.py`, `notebooks/14_example_motor_vs_jmag.py`
- 전비 계산: `notebooks/10_prius_fuel_economy.py`, 차량·사이클 데이터 `data/vehicles/`, `data/cycles/`

## 실행
```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest

# 화면 (P4): API 서버가 빌드된 화면까지 낸다
uv pip install --python .venv/bin/python -e ".[api]"
(cd web && npm install && npm run build)
.venv/bin/python -m uvicorn api.main:app --port 8000     # http://127.0.0.1:8000
# 또는 데스크톱 앱 창(Electron)으로: 엔진 서버를 알아서 띄우고 닫는다
(cd web && npm run desktop)
```
개발 중에는 `(cd web && npm run dev)`로 5173 포트에서 열면 `/api`가 8000으로 넘어간다.

### 스튜디오 화면
- **3D 모터**: 하우징(워터재킷, 볼트, 냉각 포트), 앞뒤 덮개, 3상 단자부, 고정자 철심(적층 무늬), 3상 권선(엔드턴 포함), 회전자, V자 자석 16개, 축·스플라인, 베어링, 레졸버. 치수는 ORNL 출처 값으로 그렸고, 출처가 없는 부품(단자부, 레졸버, 베어링)은 목록에 "도식"으로 표시한다.
- **해부**: 분해 슬라이더와 7단계 투어(하우징 → 고정자 → 회전자 → 자석 → 단면). 부품을 누르면 카메라가 날아가 출처가 있는 부품 도감을 보여 준다. X-ray, 숨기기, 단면(절단 위치 조절).
- **FEA 자속 분포**: 단면에 xfemm으로 푼 자속선과 자속밀도(무부하, MTPA 150·250 A, 약계자).
- **운전점**: 속도·토크를 정하면 엔진이 전류·전압·손실·효율을 풀고, 모터가 돌며 코일이 3상 전류로 빛난다. 효율맵을 누르면 그 점이 운전점이 된다.
- **전비·드라이브 모드**: WLTP·UDDS·HWFET를 달리며 속도·회전수·토크·전기 동력·효율 계기를 본다(실험적: 모터 입력 기준).
- **GPU 가속**: WebGL2, 인스턴싱(자석·볼트·베어링 볼), 적층 무늬와 냉각수 입자는 셰이더 계산, 움직임이 없으면 그리지 않는 요청 시 렌더, 고성능 GPU 요청, 프레임이 떨어지면 해상도 자동 하향. 설정 탭에서 GPU 이름과 fps를 본다.

### 데스크톱 앱(DMG/EXE)
`web/electron/main.cjs`가 엔진 서버를 빈 포트에 띄우고 화면을 연다(GPU 가속 플래그 포함). 개발 모드(`npm run desktop`)는 이 저장소에서 점검했다(창이 뜨고 API가 응답하고 종료 시 서버가 같이 꺼진다). 설치 파일은 `scripts/build_sidecar.sh`(PyInstaller로 엔진 서버를 한 파일로)와 `cd web && npm run desktop:build`(electron-builder: mac DMG, Windows NSIS, Linux AppImage)로 만들도록 설정했지만 **설치 파일 생성은 아직 끝까지 검증하지 않았다.**
