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
- `FluxMapModel.from_csv(path, p, Rs)` (**엔진 쪽 구현 완료, 실제 FEA 맵은 P3에서 대기 중**): 격자 (id, iq) → (ψd, ψq) 표를 `scipy.interpolate.RegularGridInterpolator`(기본 선형)로 보간. 포화·교차결합이 자연스럽게 반영된다. 격자 밖 요청은 오류(외삽 금지, 부동소수점 오차 1e-9 상대는 경계로 당긴다). 머리 주석이 없는 CSV는 오류, 형식 전문은 `data/flux_maps/README.md`. 상수 모델을 격자로 찍은 CSV는 선형 보간이 정확히 재현하므로 두 모델이 같은 결과를 낸다(`tests/test_p3_fluxmap.py`).
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
    # 주어진 (토크, 속도)에서 제약을 만족하며 objective를 최소화. "current": 전류 크기(기본), "loss": loss_fn(id, iq) [W]
    # (losses.loss_objective가 동손 + 철손 함수를 만든다). T ≥ 0 (전동)만 다룬다. "loss"는 시험 제어기가 효율 최고점을 고르는 것과 같다
```

- 탐색 범위는 전동 사분면 id ∈ [−Imax, 0], iq ∈ [0, Imax]. (Ld ≤ Lq인 IPMSM에서 id > 0은 토크·전압 모두 불리하다.) 회생(T < 0)은 M4에서 확장한다.

- 제약: id² + iq² ≤ Imax², vd² + vq² ≤ Vmax² (**Rs 전압강하 포함**).
- 방법(권장): dq 평면 격자 전수 탐색(예: 401×401, NumPy 벡터화)으로 후보를 고른 뒤 국소 보정(`scipy.optimize`). 상수 파라미터 모델은 해석해와 비교해 정확도를 확인한다.
- 모드 판정: 전압 제약이 비활성이면 MTPA, 전류·전압 둘 다 활성이면 FW, 전압 제약만 활성이고 전류가 Imax 미만이면 MTPV.
- 출력 그림(노트북): T-N 곡선, 출력 곡선, dq 전류 평면(전류원, 속도별 전압타원, MTPA 궤적, 운전 궤적).
- `reference/draft_getCurve.js`는 폐기된 초안의 격자 탐색 예시다(Rs 무시, 미검증). 아이디어만 참고.

## 4. V1 테스트 (P1 완료 조건)

해석해가 있는 경우로 엔진을 검증한다. 수치 허용오차는 상대 0.1% 이하(격자 해상도에 맞게 조정하되 근거를 주석으로).

**P1 완료 조건은 V1(T1~T8)이다.** 기획서 9장 초안은 "V1·V2"라고 썼지만, V2(교재 수치 예제)는 주 교재를 정해야 쓸 수 있었다. 주 교재가 없는 상태라 교재마다 같은 모양인 **돌극 동기기 전력-부하각식**(ORNL/TM-2004/185 식 (1)~(3)과 같은 형태)을 정답지로 대신했다(`tests/test_v2_textbook.py`, 부하각 경로라서 id·iq 유도와 독립). 교재 수치 예제는 주 교재가 정해지면 추가한다. (기획서 PLAN.txt 9장도 같이 고쳤다. PLAN.pdf는 원본 그대로 둔다.)

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

## 5. M3 — 손실·효율맵 (`engine/losses.py`, P2)

**계수 원칙.** 철손·기계손·구리 온도계수는 출처 있는 값이 아직 `data/`에 없다. 그래서 기본값을 두지 않고 전부 필수 인자로 받는다. 테스트는 합성 값(테스트 전용)을 쓰고, 실제 값은 강판 데이터시트·ORNL 보고서를 읽은 뒤 `data/`에 출처와 함께 넣는다.

```python
@dataclass(frozen=True)
class IronParams:       # 치·요크 분리 손실 (기획서 5.4)
    k_h: float          # 히스테리시스 계수 [W/(kg·Hz·T^β)]
    k_e: float          # 와전류 계수 [W/(kg·Hz²·T²)]
    beta: float         # Steinmetz 지수
    m_tooth: float      # 치 질량 [kg]
    m_yoke: float       # 요크 질량 [kg]
    c_tooth: float      # 치 자속밀도 환산계수 [T/Wb]: B_tooth = c_tooth·|ψ|
    c_yoke: float       # 요크 자속밀도 환산계수 [T/Wb]

@dataclass(frozen=True)
class MechParams:       # P_mech = a·ω + b·ω³
    a: float            # [W/(rad/s)]
    b: float            # [W/(rad/s)³]

def winding_resistance(R20, T_c, alpha_cu) -> Rs    # R20·(1 + α·(T − 20)), T는 °C
def copper_loss(model, id, iq) -> P_cu              # 1.5·Rs·(id² + iq²)
def iron_loss(model, id, iq, wm, iron) -> P_fe      # f = p·ωm/2π, B_k = c_k·|ψ|
def mech_loss(wm, mech) -> P_mech
def excess_loss(id, iq, wm, p, excess) -> P_excess      # k_f·f + k_c·Is_rms²·f², Is_rms² = (id² + iq²)/2
def loss_breakdown(model, id, iq, wm, iron, mech, excess=None) -> LossBreakdown
    # P_shaft = Te·ωm, P_in = P_shaft + P_cu + P_fe + P_excess, P_out = P_shaft − P_mech, η = P_out / P_in
def efficiency_map(model, limits, T_grid, speed_grid, iron, mech, excess=None) -> EfficiencyMap
    # 배열 모양 (n_T, n_speed). 동작점은 optimal_current_map(전류 최소)으로 정한다.
```

- `ExcessLossParams(k_f [W/Hz], k_c [W/(A²·Hz²)])`는 **경험적 잔여 손실**이다(물리 기구 미규명). 기본값이 없고 호출자가 출처(맞춘 데이터와 검증)와 함께 넘긴다. `excess=None`이면 0이다.
- `iron=None`, `mech=None`이면 해당 손실을 0으로 둔다 (그때 `P_in = 1.5(vd·id + vq·iq)`가 된다 — 테스트로 확인).
- 철손은 토크에 반영하지 않는다(등가 철손 저항 모델 생략, 6장 결정 유지). 철손은 입력 전력에만 더해진다.
- 자속밀도는 ψ 크기에 비례한다고 근사한다. 환산계수 c는 기하(권선 턴수, 치·요크 단면적)에서 오며 P3에서 FEA와 비교한다.
- `optimal_current_map(model, limits, T_grid, speeds) -> (id, iq, feasible)`는 `operating.py`에 둔다. 속도마다 dq 격자에서 "T 이상을 내는 점 중 전류 최소" 포락선을 구하고, 점마다 전류각을 확대 탐색으로 보정한다. 스칼라 `optimal_current`와 교차 검증한다. 보정이 전압 경계에서 실행 가능점을 못 찾으면 격자점을 그대로 쓰므로 실제 토크는 T_grid보다 약간 클 수 있고, 손실은 실제 토크로 계산한다.
- 목표: 효율맵 1장(40×60) 2초 이내.

## 5-1. M4: 차량·주행 사이클·전비 (`vehicle.py`, 구현됨)

- `Vehicle`(등가 질량 [kg], 도로 부하 `a [N]`, `b [N·s/m]`, `c [N·s²/m²]`, `motor_speed_gain` = ω_m/v = G/r_w [rad/s per m/s], 기어 무부하 손실 표). `load_vehicle(name)`은 `data/vehicles/<name>.json`(EPA·ORNL 출처 단위)을 읽어 SI로 바꾼다.
- `load_cycle(name)`: `WLTP`(클래스 3b), `UDDS`, `HWFET`. `data/cycles/*.csv`(출처·검산 거리 기록). `Cycle(t_s, v_ms, source)`.
- `run_cycle(vehicle, eff_map, cycle, regen_ratio) -> CycleResult`: 구간 중점 적분으로 `E_in`, `E_regen`, `E_net`, 바퀴 구동·제동 에너지, 기어·모터 손실, 마찰 제동, `shortfall`(모터가 못 낸 몫), 시계열, `km_per_kWh`, `Wh_per_km`. 유도와 한계는 `docs/derivations.md` 11절.
- `FluxMapModel`은 선형 보간을 numpy로 직접 구현(`_bilinear`, scipy와 같은 값)하고 `optimal_current_map`은 전류 격자의 자속을 속도마다 다시 구하지 않는다(`voltage_from_flux`). 효율맵 40×60이 1.5초다(기획서 G2).
- `waveforms.py`: `phase_waveforms(id, iq, vd, vq, n)` — dq를 한 전기 주기의 3상 전류·전압(크기 불변 역 Park)과 전류각 β로 되돌린다. 화면의 3상 파형·위상자·권선 발광이 이 값을 쓴다(화면에 삼각함수 계산을 두지 않는다).
- `CycleResult`의 구간별 배열: `loss_power_W`(모터 손실 동력), `efficiency`, `current_peak_A`(효율맵의 최소 전류 운전점을 보간). 드라이브 모드가 쓴다.
- `magnet.py`, `optimize.py`: P5에서 설계.

## 6. 남은 결정 (구현 중 사용자와 확인)
- 철손을 토크에 반영할지(등가 철손 저항 모델) — P2 검증 오차를 본 뒤 결정
- FluxMapModel 격자 해상도와 회전자 위치 평균 방식 — P3에서 FEMM 계산 시간과 함께 결정
