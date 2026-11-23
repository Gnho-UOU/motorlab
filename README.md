# Motor Lab

EV 구동용 매입형 영구자석 동기전동기(IPMSM)를 설계 변수에서 효율맵, 주행사이클 전비까지 한 흐름으로 계산하는 Python 해석 도구입니다. 결과는 공개 실측 데이터(ORNL 프리우스 2004)와 FEA로 검증하고, 3D 웹 화면에서 보여 줍니다.

상태: P1 엔진 코어(M1·M2) 완료. P2(M3 손실·효율맵) 구현: 효율맵 2400점 0.8초, 손실 수지 테스트 통과. 철손·기계손 계수는 출처 있는 실제 값 대기 중(테스트는 합성 값). P3: FluxMapModel, Prius FEA 모델(xfemm, 전체 모터 공극 메시), dq 자속 맵, ORNL 실측과 예비 비교(저속 필요 전류 엔진/측정 1.01; 고속 필요 전류는 0.72~0.77로 미해결). 형상은 ORNL 해체 측정(자석 18.9 × 6.5 mm, 공극 0.73 mm 등), 자석 Br은 무부하 역기전력에 맞춘 교정값(독립 측정 세 개가 확인), 잠금 토크 0.94~1.00. 한계는 docs/FEA_OPTIONS.md 3-4·3-6절. **G1 관문 평가: 물리 모델만으로는 미달** — 모터 효율이 ORNL 실측보다 주요 영역 +3.7%p, 고속 +10%p 높음(경험적 잔여 손실을 넣으면 RMS 1.3%p지만 같은 벤치마크에 맞춘 보정), 자세한 내용은 docs/validation_report.md.

- 기획서: `docs/PLAN.pdf`
- 엔진 설계서: `docs/ENGINE_SPEC.md`
- 수식 유도: `docs/derivations.md`
- 검증 노트북: `notebooks/01_operating_region.ipynb` (T-N 곡선, dq 전류 평면), `notebooks/02_efficiency_map.ipynb` (효율맵, 손실 분포)
- 3D 화면 초안: `web/prototype/index.html`

## 실행
```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest
```
