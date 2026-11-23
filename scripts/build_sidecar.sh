#!/bin/bash
# 데스크톱 배포용: 파이썬 엔진 서버를 하나의 실행 파일(web/sidecar/motorlab-server)로 묶는다. PyInstaller가 필요하다.
#   uv pip install --python .venv/bin/python pyinstaller
# 이후:  (cd web && npm run desktop:build)  ->  web/release/ 에 DMG(mac) / NSIS 설치기(win) / AppImage(linux)
# 주의: 이 스크립트와 설치 파일 생성은 이 저장소에서 아직 끝까지 검증하지 않았다(README "데스크톱 앱" 절).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p web/sidecar
.venv/bin/python -m PyInstaller --onefile --name motorlab-server --distpath web/sidecar --workpath /tmp/motorlab-pyi \
  --hidden-import scipy.special._cdflib --collect-submodules scipy.optimize --paths femm api/server.py
echo "-> web/sidecar/motorlab-server"
