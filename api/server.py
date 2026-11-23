"""데스크톱 앱(Electron)이 띄우는 엔진 서버 진입점. PyInstaller로 묶으면 motorlab-server 실행 파일이 된다.
실행: python -m api.server --port 8000   (MOTORLAB_ROOT가 있으면 그 폴더의 data/·web/dist를 쓴다)"""
import argparse

import uvicorn

from api.main import app


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
