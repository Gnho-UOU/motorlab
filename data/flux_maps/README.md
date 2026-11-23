# 자속 맵 CSV 형식

Windows에서 FEMM으로 계산한 dq 자속 맵을 이 폴더에 둔다. `engine/model.py`의 `FluxMapModel.from_csv()`가 읽는다. `engine/`은 femm·pyfemm을 import하지 않고 이 CSV만 읽는다 (CLAUDE.md).

## 파일 구조

```
# 출처: <형상 보고서·쪽수 또는 설계 파일>, FEMM 4.2 / pyfemm <버전>
# 형상: <극수, 슬롯 수, 적층 길이 등 주요 치수와 출처>
# 조건: 자석 온도 <°C>, 회전자 위치 평균 <방식: 전기각 N점 평균 등>, 선형/비선형 재료 <BH 곡선 출처>
# 단위: id_A [A, 첨두], iq_A [A, 첨두], psi_d_Wb·psi_q_Wb [Wb, 상 쇄교자속 첨두], torque_Nm [N·m]
id_A,iq_A,psi_d_Wb,psi_q_Wb,torque_Nm
-250,0,0.0375,0,0
...
```

- `#`로 시작하는 머리 주석이 **반드시** 있어야 한다. 없으면 `from_csv`가 오류를 낸다 (출처 없는 숫자 금지).
- 필수 열: `id_A`, `iq_A`, `psi_d_Wb`, `psi_q_Wb`. 선택 열: `torque_Nm` (FEA가 직접 계산한 토크, 엔진 토크와 비교용으로만 보관).
- 격자는 (id, iq) 조합이 **빠짐·중복 없이** 모두 있어야 한다. 행 순서는 상관없다.
- 엔진이 요청하는 범위(전동 운전: id ∈ [−Imax, 0], iq ∈ [0, Imax])를 덮어야 한다. 격자 밖 요청은 오류다 (외삽 금지).
- 부호·정의는 `docs/ENGINE_SPEC.md` 1장: 크기 불변 dq 변환, 전류는 첨두값, ψd = Ld·id + ψm 꼴의 d축 정렬.
- 선형 보간을 쓰므로 격자는 포화 곡선을 충분히 따라갈 만큼 촘촘해야 한다 (간격 선택은 P3에서 FEMM 계산 시간과 함께 결정).

## 현재 파일

- `prius2004_xfemm_delta0_25A.csv`: 2004 Prius, 25 A 간격 11 x 11점(id −250~0, iq 0~250 A). 형상·재료는 제3자 값(`data/benchmarks/prius2004_geometry.json`), 솔버는 xfemm `femmcli`. **회전자 위치 한 곳(δ = 0)에서만 계산**했고 `torque_Nm`은 그 위치의 AGE 순간 토크(비교용)다. 만든 방법과 한계는 `docs/FEA_OPTIONS.md` 3-2절과 CSV 머리 주석을 본다. 다시 만들기: `FEMMCLI=<femmcli 경로> python femm/make_flux_map.py <출력.csv> 25`.
- `prius2004_fullmodel_25A.csv`, `prius2004_fullmodel_Br1056_25A.csv`: 전체 모터 모델(공극 메시, 두 위치 평균), **제3자 형상**. 앞의 것은 Br 1.24 T, 뒤의 것은 Br만 1.056 T로 무부하 역기전력에 맞춘 보정 맵이다(`docs/FEA_OPTIONS.md` 3-3~3-5절).
- `prius2004_fullmodel_ornl_25A.csv`, `prius2004_fullmodel_pocket_25A.csv`: **쓰지 않는다.** 앞의 것은 TM-217 집중 정수 모델의 자석 5.31 mm 형상 + Br 1.065 T, 뒤의 것은 "자석 5.31 mm가 6.5 mm 포켓 안에 있다"는 가설 형상이다. TM-2010/253 해체 측정이 자석이 6.5 mm 두께 전체임을 확인해서 가설은 폐기했다. 기각된 시도의 기록으로 남긴다(`docs/FEA_OPTIONS.md` 3-6절 3)).
- **`prius2004_fullmodel_teardown_25A.csv` (현재 기본)**: 해체 치수 형상(`data/benchmarks/prius2004_geometry_teardown.json`: 자석 18.9 × 6.5 mm, 공극 0.73 mm, 적층 83.6 mm) + 자석 Br 1.06 T(무부하 역기전력에 맞춘 교정값). 다시 만들기: `PRIUS_BR_T=1.06 FEMMCLI=<femmcli> python femm/validate_full.py fluxmap <출력.csv>` (약 50분, 이어 달리기 가능).
