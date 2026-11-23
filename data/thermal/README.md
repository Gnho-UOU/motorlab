# data/thermal — 열 모델(M7) 자료와 보정

| 파일 | 내용 | 출처 |
|---|---|---|
| `prius2004_steady.csv` | 연속 시험 4점(냉각수 입구 35~105 °C): 손실 분해, 권선·기름 온도 | ORNL/TM-2005/33 표 7~10 |
| `prius2004_peak_winding_transient.csv` | 첨두 시험 5곡선: 권선 온도 대 시간(900 rpm, 전류 136~187 Arms) | ORNL/TM-2005/33 그림 19(벡터 꺾은선 읽음), 표 13 |
| `fit_lptn.py` | 매개변수 보정(일회성 도구), `prius2004_lptn.json`을 쓴다 | 이 저장소 |
| `prius2004_lptn.json` | 열회로 매개변수와 값마다 출처, 보정 진단 | 위 두 자료 + 질량(TM-2010/253), 비열(Incropera 표 A.1) |

원문(표 16)의 케이스·기름 온도는 `notebooks/19_prius_thermal.py`에서 참고용으로만 쓰고 보정에는 쓰지 않았다. 엔진은 JSON만 읽는다(`engine.thermal.load_lptn`).
