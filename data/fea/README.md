# data/fea — FEA 결과 표 (xfemm)

모든 파일은 `femm/` 스크립트가 만든 것이다(FEMM 4.2 호환 xfemm, 2D, 평면 해석). 단위는 SI이고 열 이름에 단위를 붙였다. 값은 계산 결과이고 측정이 아니다. 입력 출처는 각 스크립트 머리말과 `data/materials/README.md`에 있다.

| 파일 | 만든 스크립트 | 내용 |
|---|---|---|
| `prius2004_*.csv` | `femm/validate_full.py`, `femm/prius_full.py` 등 | ORNL Prius 2004 검증 (잠금 토크, 공극 자속, 효율 변형, 감자 확인, 자석 맵 점검) |
| `prius2004_input_sensitivity.csv` | `femm/prius_input_sensitivity.py` | 강판 곡선·적층률 변형별 ψd, ψq [Wb], 자속식 토크 [N·m]. 점 (id, iq) [A], 회전자 0°·3.75° 평균 |
| `example_motor_noload/loaded/ripple.csv`, `example_motor_cogging_*.csv` | `femm/example_motor_run.py` | 연구실 예제 IPMSM (자석 N45SH 50 °C, 적층률 0.97). 무부하 쇄교자속, 부하(전류각 β), 토크 리플(Henrotte), 코깅(메시·강판·Br 민감도) |
| `example_motor_iron_probes*.npz` | `femm/example_iron_run.py` | 철손 계산용 점 B(Bx, By) [T] 파형. 접미사 = 메시(medium/fine)와 점 밀도(d1/d2) |
| `design_opt_evals.csv` | `femm/design_opt_run.py` | M6 최적화: 설계마다 한 줄. 설계 변수 [mm, °], `T_Nm`(β를 최적화한 평균 토크), `beta_deg`, `V_peak_V`(단자 전압 기본파 첨두), `T33/T41/T49`, `V33/V41/V49`(β 33/41/49° 값), `H_demag_max_kApm`(150 °C, β = 49°, 자석 안 최악 점의 H), `demag_margin_150C`(1 − H/Hk), `magnet_area_mm2`(극당) |
| `flux_fields/` | 자속 맵 보조 | 필드 데이터 |

조건: 예제 모터는 4300 rpm, 상전류 첨두 330 A, 동기 전기각속도 ω_e = 2π·4300/60·4 rad/s, 상저항 0.033 Ω(50 °C), 쇄교자속은 직렬 32턴.
