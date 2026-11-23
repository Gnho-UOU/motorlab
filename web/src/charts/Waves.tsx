import { useEffect, useRef } from "react";
import type { Waveforms } from "../lib/api";
import { motion } from "../scene/motion";

const COLS = ["#e0533f", "#e8b730", "#3d8bd9"];

/** 한 전기 주기의 3상 전류. 회전자가 돌면 세로선이 따라 움직인다(자속·권선 발광과 같은 위상). */
export function Waves({ w, kind = "i", running }: { w: Waveforms; kind?: "i" | "v"; running: boolean }) {
  const cv = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let raf = 0;
    const draw = () => {
      const c = cv.current; if (!c) return;
      const dpr = Math.min(window.devicePixelRatio, 2), W = c.clientWidth, H = c.clientHeight; if (c.width !== W * dpr) { c.width = W * dpr; c.height = H * dpr; }
      const g = c.getContext("2d")!; g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
      const ys = kind === "i" ? [w.ia, w.ib, w.ic] : [w.va, w.vb, w.vc], peak = Math.max(...ys.flat().map(Math.abs)) * 1.1 || 1, n = w.theta_deg.length;
      g.strokeStyle = "#262b33"; g.beginPath(); g.moveTo(0, H / 2); g.lineTo(W, H / 2); g.stroke();
      ys.forEach((y, k) => { g.strokeStyle = COLS[k]; g.lineWidth = 1.8; g.beginPath(); y.forEach((v, i) => { const px = (i / (n - 1)) * W, py = H / 2 - (v / peak) * (H / 2 - 4); i ? g.lineTo(px, py) : g.moveTo(px, py); }); g.stroke(); });
      const ph = ((((4 * motion.angle) % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2)) / (Math.PI * 2);
      g.strokeStyle = "rgba(255,255,255,.65)"; g.beginPath(); g.moveTo(ph * W, 0); g.lineTo(ph * W, H); g.stroke();
      g.fillStyle = "#8d96a3"; g.font = "10px system-ui"; g.fillText(`${kind === "i" ? "상전류" : "상전압"} ±${(peak / 1.1).toFixed(0)} ${kind === "i" ? "A" : "V"} · 한 전기 주기`, 6, 12);
      if (running) raf = requestAnimationFrame(draw);
    };
    draw(); return () => cancelAnimationFrame(raf);
  }, [w, kind, running]);
  return <canvas ref={cv} style={{ width: "100%", height: 110, borderRadius: 8, background: "#0f1216" }} />;
}
