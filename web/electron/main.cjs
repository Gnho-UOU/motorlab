/** Motor Lab 데스크톱 셸(Electron).
 *  1) 파이썬 엔진 서버(FastAPI)를 빈 포트에서 띄운다(개발: 저장소의 .venv, 배포: 함께 묶은 motorlab-server 실행 파일).
 *  2) 서버가 /api/health에 응답하면 같은 서버가 내는 화면(web/dist)을 창에 연다. 같은 출처라 CORS 문제가 없다.
 *  3) GPU 가속: 블록리스트 무시, GPU 래스터화, 고성능 GPU 선호. 창을 닫으면 서버도 끈다.
 *  --smoke-test: 창이 뜨고 화면이 로드되면 0으로 종료한다(자동 점검용). */
const { app, BrowserWindow, shell } = require("electron");
const { spawn } = require("node:child_process");
const net = require("node:net");
const path = require("node:path");
const fs = require("node:fs");
const http = require("node:http");

app.commandLine.appendSwitch("ignore-gpu-blocklist");
app.commandLine.appendSwitch("enable-gpu-rasterization");
app.commandLine.appendSwitch("enable-zero-copy");
app.commandLine.appendSwitch("force_high_performance_gpu");

const smoke = process.argv.includes("--smoke-test");
let server = null;

function freePort() { return new Promise((res, rej) => { const s = net.createServer(); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => res(p)); }); s.on("error", rej); }); }
function waitHealth(port, ms = 60000) {
  const t0 = Date.now();
  return new Promise((res, rej) => {
    const tick = () => http.get({ host: "127.0.0.1", port, path: "/api/health", timeout: 1500 }, (r) => { r.resume(); r.statusCode === 200 ? res() : retry(); }).on("error", retry);
    const retry = () => (Date.now() - t0 > ms ? rej(new Error("엔진 서버가 시작되지 않았다")) : setTimeout(tick, 300));
    tick();
  });
}

function startServer(port) {
  const packaged = app.isPackaged, root = packaged ? process.resourcesPath : path.resolve(__dirname, "..", "..");
  const exe = path.join(root, process.platform === "win32" ? "motorlab-server.exe" : "motorlab-server");
  if (packaged && fs.existsSync(exe)) return spawn(exe, ["--port", String(port)], { cwd: root, stdio: "inherit" });
  const py = process.env.MOTORLAB_PYTHON || path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  return spawn(py, ["-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", String(port)], { cwd: root, stdio: "inherit" });
}

async function createWindow() {
  const port = await freePort();
  server = startServer(port);
  server.on("exit", (c) => { if (c) console.error(`엔진 서버가 종료됨 (${c})`); });
  await waitHealth(port);
  const win = new BrowserWindow({ width: 1560, height: 940, minWidth: 1100, minHeight: 700, backgroundColor: "#0c0e11", title: "Motor Lab", show: false,
    webPreferences: { preload: path.join(__dirname, "preload.cjs"), contextIsolation: true, sandbox: false } });
  win.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: "deny" }; });
  win.once("ready-to-show", () => win.show());
  win.webContents.on("did-finish-load", () => { if (smoke) setTimeout(() => app.quit(), 1500); });
  await win.loadURL(`http://127.0.0.1:${port}/`);
}

app.whenReady().then(() => createWindow().catch((e) => { console.error(e); app.exit(1); }));
app.on("window-all-closed", () => app.quit());
app.on("quit", () => { if (server && !server.killed) server.kill(); });
