import { defineConfig } from "vite";

// 개발 서버는 /api를 FastAPI(8000)로 넘긴다. 빌드 결과(web/dist)는 FastAPI가 그대로 서비스한다.
export default defineConfig({
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
  build: { outDir: "dist", sourcemap: true },
});
