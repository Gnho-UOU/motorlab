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

없음. 첫 파일은 ORNL 프리우스 2004 형상으로 FEMM을 돌린 뒤 이 폴더에 추가한다.
