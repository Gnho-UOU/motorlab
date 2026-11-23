# Motor Lab

EV 구동용 매입형 영구자석 동기전동기(IPMSM)를 설계 변수에서 효율맵, 주행사이클 전비까지 한 흐름으로 계산하는 Python 해석 도구입니다. 결과는 공개 실측 데이터(ORNL 프리우스 2004)와 FEA로 검증하고, 3D 웹 화면에서 보여 줍니다.

상태: **P4 진행 중** — M4 전비(WLTP·UDDS·HWFET), FastAPI, 3D 화면이 동작한다(WLTP 순수 전기 구동 환산 약 10 km/kWh, 모터 입력 기준, 실험적). G1은 미달을 기록한 채 사용자 결정으로 진행했다. P1 엔진 코어(M1·M2) 완료. P2(M3 손실·효율맵) 구현: 효율맵 2400점 0.8초, 손실 수지 테스트 통과. 철손·기계손 계수는 출처 있는 실제 값 대기 중(테스트는 합성 값). P3: FluxMapModel, Prius FEA 모델(xfemm, 전체 모터 공극 메시), dq 자속 맵, ORNL 실측과 예비 비교(저속 필요 전류 엔진/측정 1.01; 고속 필요 전류는 0.72~0.77로 미해결). 형상은 ORNL 해체 측정(자석 18.9 × 6.5 mm, 공극 0.73 mm 등), 자석 Br은 무부하 역기전력에 맞춘 교정값(독립 측정 세 개가 확인), 잠금 토크 0.94~1.00. 한계는 docs/FEA_OPTIONS.md 3-4·3-6절. **G1 관문 평가: 물리 모델만으로는 미달** — 모터 효율이 ORNL 실측보다 주요 영역 +3.7%p, 고속 +10%p 높음(경험적 잔여 손실을 넣으면 RMS 1.3%p지만 같은 벤치마크에 맞춘 보정), 자세한 내용은 docs/validation_report.md.

- 기획서: `docs/PLAN.pdf`
- 엔진 설계서: `docs/ENGINE_SPEC.md`
- 수식 유도: `docs/derivations.md`
- 검증 노트북: `notebooks/01_operating_region.ipynb` (T-N 곡선, dq 전류 평면), `notebooks/02_efficiency_map.ipynb` (효율맵, 손실 분포)
- 3D 스튜디오(P4): `web/` (React + TypeScript + react-three-fiber), 서버 `api/main.py`(FastAPI), 데스크톱 셸 `web/electron/`. 초안은 `web/prototype/index.html`(검증되지 않은 참고용)
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
