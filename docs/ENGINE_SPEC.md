# 엔진 설계서 (초안 v0.1)

`engine/` 패키지의 규약, 모듈 인터페이스, 검증 테스트를 정한다. 수식의 근거와 전체 맥락은 `docs/PLAN.pdf` 5장(계산 모델)과 6장(검증 계획)을 따른다. 이 문서는 P1(M1·M2)을 바로 시작할 수 있을 만큼 자세히 쓰고, M3 이후는 인터페이스 윤곽만 둔다. 구현하며 바뀌는 점은 이 문서를 먼저 고친다.

## 1. 공통 규약

| 항목 | 규약 |
| --- | --- |
| 단위 | 전부 SI. 인덕턴스 H, 자속 Wb, 전류 A(첨두값), 전압 V(첨두값), 속도 rad/s |
| dq 변환 | 크기 불변(amplitude-invariant) Park 변환. 전류·전압은 상 첨두값과 같은 크기 |
| 전력 | P = 1.5 (vd·id + vq·iq) |
| 극수 | `p` = 극쌍 수(pole pairs). ωe = p·ωm |
| 전류각 | 필요할 때만 사용. id = −Is·sin β, iq = Is·cos β (β = 0이면 q축) |
| 부호 | 전동 모드 T > 0, ωm > 0. IPMSM은 Ld < Lq, 약계자에서 id < 0 |
| 배열 | 모든 계산 함수는 NumPy 배열을 받아 브로드캐스팅으로 벡터 계산 (스칼라도 허용) |
| 자료형 | 파라미터·결과는 `@dataclass(frozen=True)`. 결과 표는 열 이름을 가진 배열 묶음(dataclass) |
| 의존성 | 런타임: numpy, scipy만 |
| 문서화 | 모든 공개 함수 docstring에 수식, 단위, 기획서 절 번호, 근거 문헌 |

## 2. M1 — 모터 모델 (`engine/model.py`)

모든 모델은 같은 인터페이스(Protocol)를 따른다.

```python
class MotorModel(Protocol):
    p: int            # 극쌍 수
    Rs: float         # 상저항 [Ω] (기준 온도에서)

    def flux(self, id, iq) -> tuple[ndarray, ndarray]:
        """ψd, ψq [Wb]"""
    def torque(self, id, iq) -> ndarray:
        """Te = 1.5 p (ψd iq − ψq id) [N·m]"""
    def voltage(self, id, iq, we) -> tuple[ndarray, ndarray]:
        """vd = Rs id − we ψq,  vq = Rs iq + we ψd [V] (정상상태)"""
```

- `ConstantParamModel(p, Rs, Ld, Lq, psi_m)`: ψd = Ld·id + ψm, ψq = Lq·iq. 1단계 개발과 해석해 검증용.
- `FluxMapModel.from_csv(path, p, Rs)` (**P3에서 구현. P1 범위 아님**): 격자 (id, iq) → (ψd, ψq) 표를 `scipy.interpolate.RegularGridInterpolator`로 보간. 포화·교차결합이 자연스럽게 반영된다. 격자 밖 요청은 오류(외삽 금지).
  - CSV 열: `id_A, iq_A, psi_d_Wb, psi_q_Wb` (+ 선택: `torque_Nm` FEA 직접값). 파일 머리 주석에 출처·형상·온도·회전자 위치 평균 방식 기록.
  - `torque()`는 자속으로 계산한 값을 기본으로 하고, FEA 토크 열이 있으면 비교용으로 함께 보관.
- 온도: `Rs(T) = R20 (1 + α_cu (T − 20))`, 자석 온도에 따른 ψm 변화는 M5에서 다룬다. P1에서는 Rs·ψm 모두 상수이고, `α_cu`는 출처를 달아 P2(`losses.py`)에서 넣는다.

## 3. M2 — 운전 영역 (`engine/operating.py`)

```python
@dataclass(frozen=True)
class Limits:
    Imax: float            # 전류 제한 [A, 첨두]
    Vdc: float             # 직류 링크 [V]
    k_mod: float = 1/sqrt(3)   # Vmax = k_mod·Vdc (선형 SVPWM 한계). 과변조는 설정값으로만

def mtpa_point(model, Is) -> (id, iq)
def base_speed(model, limits) -> wm
    # Imax의 MTPA점에서 |v| = Vmax가 되는 기계 속도 [rad/s]. Rs 포함 닫힌 해 (derivations.md 5절)
def max_torque_curve(model, limits, speeds) -> TorqueSpeedTable
    # 열: speed (rad/s, 기계), T_max, id, iq, mode ∈ {"MTPA","FW","MTPV","INFEASIBLE"}, P_mech, feasible
    # 영전류에서도 |v| > Vmax인 속도는 feasible=False, T_max·id·iq = NaN, mode = "INFEASIBLE"
def optimal_current(model, limits, T, speed, objective="current") -> (id, iq, feasible)
    # 주어진 (토크, 속도)에서 제약을 만족하며 전류 크기를 최소화(나중에 objective="loss"). T ≥ 0 (전동)만 다룬다
```

- 탐색 범위는 전동 사분면 id ∈ [−Imax, 0], iq ∈ [0, Imax]. (Ld ≤ Lq인 IPMSM에서 id > 0은 토크·전압 모두 불리하다.) 회생(T < 0)은 M4에서 확장한다.

- 제약: id² + iq² ≤ Imax², vd² + vq² ≤ Vmax² (**Rs 전압강하 포함**).
- 방법(권장): dq 평면 격자 전수 탐색(예: 401×401, NumPy 벡터화)으로 후보를 고른 뒤 국소 보정(`scipy.optimize`). 상수 파라미터 모델은 해석해와 비교해 정확도를 확인한다.
- 모드 판정: 전압 제약이 비활성이면 MTPA, 전류·전압 둘 다 활성이면 FW, 전압 제약만 활성이고 전류가 Imax 미만이면 MTPV.
- 출력 그림(노트북): T-N 곡선, 출력 곡선, dq 전류 평면(전류원, 속도별 전압타원, MTPA 궤적, 운전 궤적).
- `reference/draft_getCurve.js`는 폐기된 초안의 격자 탐색 예시다(Rs 무시, 미검증). 아이디어만 참고.

## 4. V1 테스트 (P1 완료 조건)

해석해가 있는 경우로 엔진을 검증한다. 수치 허용오차는 상대 0.1% 이하(격자 해상도에 맞게 조정하되 근거를 주석으로).

**P1 완료 조건은 V1(T1~T8)이다.** 기획서 9장 초안은 "V1·V2"라고 썼지만, V2(교재 수치 예제)는 주 교재를 정해야 쓸 수 있으므로 교재 확정 후 추가하고 P2 시작 전까지 마친다. (기획서 PLAN.txt 9장도 같이 고쳤다. PLAN.pdf는 원본 그대로 둔다.)

| 번호 | 내용 | 기대값 |
| --- | --- | --- |
| T1 | 비돌극(Ld = Lq)이면 모든 Is에서 MTPA가 id = 0 | id = 0 |
| T2 | IPMSM MTPA 수치해 = 해석식 id = [ψm − √(ψm² + 8(Lq−Ld)² Is²)] / [4(Lq−Ld)] | 해석식과 일치 |
| T3 | Rs = 0일 때 기저속도 ωe = Vmax / √((ψm + Ld·id)² + (Lq·iq)²), (id, iq)는 Imax의 MTPA점 | 일치 |
| T4 | ψm > Ld·Imax이면 최고속도 ωe,max = Vmax / (ψm − Ld·Imax) (Rs = 0), 그 이상 속도는 infeasible | 일치 |
| T5 | 전력 수지: 1.5(vd·id + vq·iq) = Te·ωm + 1.5·Rs·(id² + iq²) | 항등식 성립 |
| T6 | `max_torque_curve`의 T_max는 속도에 대해 비증가, 모든 점이 두 제약을 만족 | 성립 |
| T7 | 토크 식 두 형태 일치: 1.5p(ψd iq − ψq id) = 1.5p(ψm iq + (Ld−Lq) id iq) | 일치 |
| T8 | MTPV 영역(ψm < Ld·Imax인 **MTPV 전용 파라미터**, 아래): 같은 자속 크기 Ψ = Vmax/ωe에서 토크를 1차원 탐색한 값과 `max_torque_curve` 일치, 속도 스윕에 MTPA→FW→MTPV 세 모드가 순서대로 나타남 | 일치 |

**개발용 가상 파라미터** (실제 모터 아님, 테스트 전용): p = 4, Rs = 0 (T3·T4) 또는 0.03 Ω, Ld = 0.15 mH, Lq = 0.45 mH, ψm = 0.075 Wb, Imax = 250 A, Vdc = 350 V.
손계산 확인값(Rs = 0): Vmax = 202.07 V, Imax에서 MTPA 점 id = −125.0 A, iq = 216.51 A, T = 146.14 N·m, 기저속도 ωm = 449.05 rad/s(4288 rpm), 최고속도 ωm = 1347.2 rad/s(12,864 rpm), 특성전류 ψm/Ld = 500 A > Imax.
**MTPV 전용 파라미터** (T8 전용): 위와 같고 ψm = 0.025 Wb만 다르다. 특성전류 ψm/Ld = 166.7 A < Imax = 250 A이므로 Rs = 0에서 속도 상한이 없고(영전류 이전에 전류 제한 안쪽으로 자속이 0에 접근) MTPV 영역이 생긴다. 위 기본 파라미터는 ψm/Ld = 500 A > Imax라 MTPV가 생기지 않아 T1~T7로는 `mode="MTPV"` 분기를 검증할 수 없다.

프리우스 2004 파라미터는 P0에서 ORNL 보고서를 읽은 뒤 `data/benchmarks/`에 출처와 함께 넣는다. 기억이나 추정으로 채우지 않는다.

## 5. M3 이후 윤곽 (P2부터 상세화)

- `losses.py`: `copper_loss(model, id, iq, T_wind)`, `iron_loss(model, id, iq, we, steel)`(치·요크 자속밀도 × Steinmetz/Bertotti 분리식, 계수는 강판 데이터시트로 맞춤), `mech_loss(wm)`(a·ω + b·ω³), `efficiency_map(model, limits, T_grid, speed_grid)` → 효율·손실 성분 격자. 목표: 효율맵 1장 2초 이내.
- `vehicle.py`: `Vehicle`(질량, 등가질량계수, Cd, A, Crr, 기어비 G, 기어효율, 휠 반경), `load_cycle(name)`(WLTP/UDDS/HWFET, `data/cycles/`에 출처 기록), `run_cycle(vehicle, eff_map, cycle, regen_ratio)` → 에너지, 전비 km/kWh, 동작점 분포.
- `magnet.py`, `optimize.py`: P5에서 설계.

## 6. 남은 결정 (구현 중 사용자와 확인)
- 철손을 토크에 반영할지(등가 철손 저항 모델) — P2 검증 오차를 본 뒤 결정
- FluxMapModel 격자 해상도와 회전자 위치 평균 방식 — P3에서 FEMM 계산 시간과 함께 결정
