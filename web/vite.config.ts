import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 개발 서버는 /api를 FastAPI(8000)로 넘긴다. 빌드 결과(web/dist)는 FastAPI가 그대로 서비스하고 Electron도 같은 서버를 연다.
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 1800 },
});
