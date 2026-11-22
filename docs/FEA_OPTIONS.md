# FEA 실행 환경 조사 (Mac에서 FEMM을 못 쓰는 문제)

2026-11-22 조사. 문제: FEMM은 Windows 전용이고, 사용자는 Windows PC 사정을 모른다. 이 문서는 대안 후보를 **확인한 것**과 **확인하지 못한 것**으로 나눠 기록한다.

## 1. 이 Mac의 환경 (직접 확인)

Intel Core i9-9880H, RAM 16 GB, macOS 15.7.1, 디스크 여유 약 380 GB. Xcode(clang, make)는 있다. cmake, Homebrew, Docker, Wine, 가상화 앱(Parallels·VMware·VirtualBox·UTM), Gmsh, Elmer는 없다. **Intel이라 x86 Windows VM이나 Wine이 에뮬레이션 없이 돈다.**

## 2. 후보 비교

| 후보 | FEMM과 같은 솔버인가 | 확인한 것 | 확인하지 못한 것 / 위험 |
| --- | --- | --- | --- |
| **xfemm** `femmcli` | FEMM 핵심 알고리즘을 표준 C++로 다시 쓴 포트 (자기 해석 `fmesher`, `fsolver`) | GitHub [crobarcro/xfemm](https://github.com/REOptimize-Systems/xfemm), GPL-3.0, 최근 커밋 2026-11-01, 저장소 갱신 2026-11-22. `femmcli --lua-script=<파일>` 은 "FEMM 전용 Lua 파일 명령줄 해석기". Lua 자기 명령 구현 파일(`LuaMagneticsCommands.cpp`)이 있다. Python `FemmSession`(`.fem`을 읽어 메시·해석, NumPy 결과). CMake로 빌드 | **macOS 빌드·실행 보고를 찾지 못했다**(CI는 Ubuntu만). 이슈 검색은 접근 제한으로 실패. FEMM과의 수치 일치를 문서화한 자료를 못 찾았다. 비선형 BH·영구자석 지원 여부를 직접 확인 못 했다(FEMM 포트라 지원할 가능성이 높으나 미확인). 재료 라이브러리 `matlib.dat`의 출처·재배포 조건 확인 필요 |
| ifemm | 아니다 | PyPI 메타데이터: "FEMM **솔루션 파일을 해석**하는" 파이썬 라이브러리(`.ans` 파서), MIT, 0.2.2. **솔버가 아니다** | 제외 |
| Windows VM (Parallels·VMware Fusion·VirtualBox) | 진짜 FEMM + pyfemm | Intel Mac이라 이론상 가능. 원래 계획(`run_femm.bat`)과 같은 방식 | Windows 라이선스·설치 이미지(수 GB 다운로드), 앱 설치가 필요. 이번 조사에서 직접 검증하지 않았다 |
| Wine / CrossOver | 진짜 FEMM | FEMM 위키: Linux에서 Wine으로 "정상 동작, 속도는 Windows와 비슷" (2012년경 Wine 1.x 시험) | **macOS는 문서에 없다.** pyfemm은 COM(win32com)을 쓰므로 Wine에서 안 될 위험이 크다. 명령줄 Lua 실행 옵션도 이번에 확인 못 했다 |
| GitHub Actions `windows-latest` | 진짜 FEMM | 저장소가 공개라 실행 시간 무료. FEMM 배포는 Windows `.exe`(`femm42bin_x64_22Oct2023.exe`), choco 패키지는 더 오래된 4.2.20190421. pyfemm은 win32com 사용 | **FEMM이 화면 없는 러너에서 시작하는지 미확인**. 푸시 → 실행 → 결과 받기 순환이라 개발 속도가 느리다 |
| Elmer FEM | 아니다(다른 솔버) | README의 미리 컴파일된 빌드는 Windows·WSL·VirtualBox VM뿐. macOS는 소스 빌드(Homebrew gcc·cmake). 안내문에 "out of date일 수 있음" 표기. Intel Ventura에서 Homebrew 빌드 실패 보고가 있었다 | 전동기 모델(형상·권선·BH)을 처음부터 짜야 한다. 솔버가 달라 FEMM 기준 검증 이점이 없다 |
| Gmsh + GetDP | 아니다 | PMSM 예제를 찾지 못했다 | 조사 중단 |

## 3. 권고

**1순위: xfemm `femmcli`를 이 Mac에서 직접 빌드해 쓴다.** 이유: (a) 네이티브라 VM·Windows가 필요 없다. (b) 입력이 FEMM의 Lua 명령 그대로라서, 같은 `.lua` 스크립트를 나중에 진짜 FEMM(연구실·Windows)에서도 돌려 **솔버 교차 검증**을 할 수 있다. (c) `CLAUDE.md`의 "FEMM은 분리" 규칙이 그대로 유지된다: 스크립트가 CSV만 남기고 `engine/`은 CSV만 읽는다.

**타당성 시험은 통과했다(아래 3-1). 다음은 P3 형상(`data/benchmarks/prius2004_ornl.md` 7절)으로 올라가는 것이다.** 문제가 생기면 2순위 GitHub Actions Windows 러너(비용 없음, 가장 간단한 시험부터), 3순위 Windows VM.

### 3-1. 타당성 시험 결과 (2026-11-22, 이 Mac, xfemm 커밋 `132515c`)

**빌드:** 성공. 단 **업스트림 그대로는 실패한다.** Apple clang 17(libc++)에서 세 가지가 컴파일되지 않아 13줄을 고쳤다: (1) `sincos()`는 GNU 확장(`femmcomplex.cpp`), (2) `std::ptr_fun`은 C++17에서 제거(`stringTools.h`; 프로젝트는 C++17을 지정하면서 GNU libstdc++에서만 통하는 코드를 쓴다), (3) `<malloc.h>`가 macOS에 없음(10개 파일). 수정은 `femm/build_xfemm_macos.sh`가 자동으로 적용한다(새 소스에서 63초, 이 스크립트로 처음부터 다시 빌드해 확인함). 패치는 GPL 파생물이라 저장소에 두지 않았다. 업스트림에 알리지는 않았다. CMake가 설정 중에 `github.com/dcm3c/tangle`(Tangle 메시 생성기)을 추가로 내려받는다.

**저장소 자체 테스트(`ctest`):** 55개 중 54개 통과(순차 실행). 실패 1건(`femmcli_femfile.check.ans`)은 검증 스크립트의 정규식 버그다. CMake 따옴표 안의 `\[`가 `[`로 처리돼 `^[Solution]$`가 되기 때문이고, 정규식을 고쳐 같은 파일을 검사하면 통과한다(파일에는 `[Solution]` 섹션이 있다). 열 해석 `hsolver_Temp1`은 병렬(-j4) 실행에서만 한 번 segfault했고 순차에서는 통과했다(자기 해석과 무관). 5개는 저장소가 비활성화해 둔 것이다.

**수치 정확도:**
- FEMM 위키 토크 벤치마크(저장소 테스트): 해석해 토크와 상대 오차 0.006% 이내, 이 Mac에서 통과.
- 직접 만든 해석해 시험 `femm/validation/run_checks.py`(21초, 진짜 FEMM에서도 같은 `.lua`를 돌릴 수 있다):

| 시험 | 해석해 | 결과 |
| --- | --- | --- |
| 선형: 균일장 속 원통(μr=10) | `Bx = 2μr/(μr+1)·B0` | 공기 메시 10 mm → 2 mm에서 오차 −0.85% → −0.34% |
| 영구자석: 균일 자화 원통(μr=1) | `Bx = (Br/2)(1 − (R/Rfar)²)` | 같은 메시에서 −0.96% → −0.31% (공기 메시를 1 mm로 줄이면 −0.13%) |
| 비선형 BH: 전류선 둘레 강판 원통(포화 포함) | `B = f(I/2πr)` | 최대 오차 0.37% (I = 300 A, 3000 A) |

**교훈(V3에 적용):** 공기 영역 메시가 거칠면 1차 요소 때문에 영구자석·선형 문제도 −1%대 오차가 남는다. 메시를 촘촘히 하면 단조롭게 해석해로 수렴한다(처음에 영구자석 −1.2%를 솔버 문제로 의심했으나 이산화 오차였다). 그래서 V3에서는 공극 주변 메시를 충분히 촘촘히 하고 **메시 수렴을 확인**한다.

**시험하지 않은 것:** xfemm의 Python 인터페이스(`FemmSession`), 회전자 위치에 따른 토크 맥동 계산 시간, 실제 전동기 규모 모델의 계산 시간, 진짜 FEMM과의 직접 비교.

## 4. 검증 방침 (솔버 신뢰도)

xfemm이 FEMM과 같은 값을 낸다는 자료를 못 찾았으므로, **xfemm 결과를 그대로 믿지 않는다.** V3에서 (1) 해석해 문제, (2) ORNL TM-423의 실측 역기전력(Table 3.4)·잠금 토크(Table 3.2), (3) 가능하면 진짜 FEMM에서 같은 `.lua`를 돌린 결과와 비교한다. 차이는 보고서에 그대로 적는다.

## 5. 라이선스 메모

xfemm은 GPL-3.0이다. 이 프로젝트는 xfemm을 외부 프로그램으로 실행만 하고 링크하지 않는다. 재료 라이브러리 `matlib.dat`(FEMM 배포 파일)의 재배포 조건은 공개 전에 확인한다.

## 6. 아직 모르는 것

- xfemm과 진짜 FEMM의 직접 수치 차이(해석해 시험으로만 확인했다. 같은 `.lua`를 진짜 FEMM에서 돌려 비교하는 것은 아직).
- 실제 전동기 규모 모델(영구자석 + 포화 강판 + 슬롯)의 계산 시간. 자속 맵 한 장에 필요한 (id, iq) 점 수와 회전자 위치 수를 곱하면 해석 횟수가 커질 수 있다.
- FEMM 명령줄 Lua 옵션(`-lua-script`)과 Wine·macOS 조합, FEMM이 GitHub Actions 러너에서 시작되는지(대안 경로, 필요해질 때만).
