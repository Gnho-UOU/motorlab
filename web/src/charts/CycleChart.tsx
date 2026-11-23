import { useEffect, useRef } from "react";
import type { CycleResult } from "../lib/api";

/** 사이클 속도와 모터 효율 시계열. 재생 위치(세로선)를 누르면 거기로 이동한다. */
export function CycleChart({ r, t, onSeek }: { r: CycleResult; t: number; onSeek: (t: number) => void }) {
  const cv = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = cv.current!, dpr = Math.min(window.devicePixelRatio, 2), W = c.clientWidth, H = c.clientHeight; c.width = W * dpr; c.height = H * dpr;
    const g = c.getContext("2d")!; g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
    const s = r.series, tmax = s.t_s[s.t_s.length - 1], vmax = Math.max(...s.speed_kmh) * 1.08, X = (v: number) => 30 + (v / tmax) * (W - 40);
    g.fillStyle = "#0f1216"; g.fillRect(30, 6, W - 40, H - 28);
    g.strokeStyle = "#d98d55"; g.lineWidth = 1.5; g.beginPath(); s.speed_kmh.forEach((v, i) => { const y = H - 22 - (v / vmax) * (H - 28); i ? g.lineTo(X(s.t_s[i]), y) : g.moveTo(X(s.t_s[i]), y); }); g.stroke();
    g.strokeStyle = "#5ccf8f"; g.lineWidth = 1; g.beginPath(); let st = false; s.efficiency.forEach((e, i) => { if (e === null) { st = false; return; } const y = H - 22 - e * (H - 28); st ? g.lineTo(X(s.t_s[i]), y) : g.moveTo(X(s.t_s[i]), y); st = true; }); g.stroke();
    g.strokeStyle = "#fff"; g.beginPath(); g.moveTo(X(t), 6); g.lineTo(X(t), H - 22); g.stroke();
    g.fillStyle = "#8d96a3"; g.font = "10px system-ui"; g.textAlign = "center"; for (let v = 0; v <= tmax; v += 300) g.fillText(String(v), X(v), H - 8);
    g.textAlign = "left"; g.fillStyle = "#d98d55"; g.fillText("속도 [km/h]", 34, 16); g.fillStyle = "#5ccf8f"; g.fillText("모터 효율", 110, 16);
  }, [r, t]);
  return <canvas ref={cv} style={{ width: "100%", height: 130, cursor: "pointer", borderRadius: 8 }} onClick={(e) => { const b = cv.current!.getBoundingClientRect(), tmax = r.series.t_s[r.series.t_s.length - 1]; onSeek(Math.max(0, Math.min(tmax, ((e.clientX - b.left - 30) / (b.width - 40)) * tmax))); }} />;
}
