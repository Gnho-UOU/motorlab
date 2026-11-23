# data/materials: 자석·강판 물성 (M5)

모든 숫자는 제조사 공개 자료에서 왔고 값마다 출처가 있다. 찾지 못한 값은 `null`이며 계산은 그 값을 쓰지 않고 "판정 불가"로 멈춘다(CLAUDE.md: 출처 없는 숫자 금지).

| 파일 | 내용 | 출처 |
| --- | --- | --- |
| `magnets.json` | 자석 등급별 Br·HcB·HcJ·(BH)max·온도계수·최고 사용 온도 등. N45SH, N38UH(소결 NdFeB), Y30H-1(페라이트) | Arnold Magnetic Technologies N45SH 데이터시트 Rev. 210607, Arnold Neo Catalog Rev. 210607(2쪽 표, 41쪽 N38UH), Eclipse Magnetics 페라이트 데이터시트, Arnold TN 0205 |
| `magnet_demag_curves.csv` | N45SH·N38UH의 J-H 감자 곡선, 온도 −40~180 °C 8개 | 위 데이터시트의 벡터 그림을 `digitize_arnold_demag.py`로 읽음 |
| `digitize_arnold_demag.py` | 곡선 읽기 스크립트. 20 °C Br과 HcJ가 표 값과 같은지 스스로 검사 | |
| `steel_35JN230.json` | JFE 35JN230 강판(0.35 mm) 대표값·보증값 | JFE ELECTRICAL STEEL SHEETS 카탈로그 f1e-001 14쪽, 18쪽 |

## 곡선을 다시 만들려면
PDF 두 개(N45SH 데이터시트 1쪽, Neo 카탈로그 41쪽)를 받아 `python data/materials/digitize_arnold_demag.py N45SH.pdf 0 N45SH Neo_catalog.pdf 40 N38UH` (PyMuPDF 필요, 엔진 의존성이 아니다). 표준 출력의 본문을 `magnet_demag_curves.csv`의 머리글 주석 뒤에 붙인다.

## 알아 둘 점
- 데이터시트 곡선은 **공칭 Br과 최소 HcJ**를 보여 준다. 그래서 곡선으로 한 감자 검토는 실제 자석이 최소 보증값에 가까운 경우를 본다.
- 페라이트(Y30H-1)는 HcJ 온도계수와 등급별 감자 곡선을 찾지 못했다(TDK 사이트는 자동 접근이 403). 그래서 감자 판정을 하지 않는다.
- 강판 35JN230은 JFE 공개 카탈로그 값이고 Prius FEA 모델의 강판(pyleecan M400-50A, 손실표 출처 미확인)과 다르다. Prius 강판 교체는 하지 않았다.
- 이 폴더의 숫자는 모두 제조사 공개 자료에서 구했다.
