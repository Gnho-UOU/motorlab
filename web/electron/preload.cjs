// 렌더러(React)에 안전하게 노출하는 최소 정보. 계산은 하지 않는다.
const { contextBridge } = require("electron");
const q = new URLSearchParams(globalThis.location?.search ?? "");
contextBridge.exposeInMainWorld("motorlab", { apiBase: "", platform: process.platform, version: require("../package.json").version });
void q;
