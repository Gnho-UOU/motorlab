#!/usr/bin/env bash
# macOS에서 xfemm의 femmcli(FEMM Lua 명령줄 해석기)를 빌드한다. docs/FEA_OPTIONS.md 참조.
#
# 업스트림 xfemm은 Linux 기준이라 macOS(Apple clang, libc++)에서 세 가지가 컴파일되지 않는다.
# 이 스크립트는 받은 소스에 그 세 가지만 고친다 (총 13줄, 의미 변경 없음):
#   1) sincos()는 GNU 확장 -> sin, cos 호출          (libfemm/liblua/femmcomplex.cpp)
#   2) std::ptr_fun은 C++17에서 제거 -> 람다          (libfemm/stringTools.h)
#   3) <malloc.h>가 macOS에 없음 -> <stdlib.h>        (cfemm 아래 10개 파일)
# 패치 결과물은 GPL-3.0 파생물이므로 이 저장소에 두지 않는다. 소스는 $XFEMM_DIR(저장소 밖)에 받는다.
#
# 필요: git, cmake(pip install cmake 또는 brew install cmake), Xcode 명령줄 도구. 인터넷(소스와 Tangle 메시 생성기
# github.com/dcm3c/tangle을 CMake가 설정 중에 내려받는다).
# 사용:  femm/build_xfemm_macos.sh   ->  $XFEMM_DIR/cfemm/bin/femmcli
set -euo pipefail

DIR="${XFEMM_DIR:-$HOME/.local/src/xfemm}"
REV=132515315c8e9491d2995bc8d17cc7107dbb7620   # 이 스크립트를 시험한 커밋 (2026-11-01)

command -v cmake >/dev/null || { echo "cmake가 필요하다: pip install cmake 또는 brew install cmake" >&2; exit 1; }
[ -d "$DIR/.git" ] || git clone -q https://github.com/REOptimize-Systems/xfemm "$DIR"
git -C "$DIR" checkout -q "$REV"

python3 - "$DIR/cfemm" <<'EOF'
import pathlib, re, sys
root = pathlib.Path(sys.argv[1])

def patch(path, subs):
    b = path.read_bytes()          # 바이트 단위: 원본의 CRLF 줄바꿈을 보존한다
    n = b
    for pat, rep in subs:
        n = re.sub(pat, rep, n)
    if n != b:
        path.write_bytes(n)
        print("patched", path.relative_to(root))

patch(root / "libfemm/liblua/femmcomplex.cpp",
      [(rb"sincos\(x\.im, &sin_x, &cos_x\);", b"sin_x = sin(x.im); cos_x = cos(x.im);")])
patch(root / "libfemm/stringTools.h",
      [(rb"std::not1\(std::ptr_fun<int, int>\(std::isspace\)\)", b"[](unsigned char c) { return !std::isspace(c); }")])
for p in root.rglob("*"):
    if p.suffix in (".cpp", ".h", ".c", ".hpp") and p.is_file():
        patch(p, [(rb'#include\s*[<"]malloc\.h[>"]', b"#include <stdlib.h>")])
EOF

cmake -S "$DIR/cfemm" -B "$DIR/build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$DIR/build" -j"$(sysctl -n hw.ncpu)"
echo "완료: $DIR/cfemm/bin/femmcli"
