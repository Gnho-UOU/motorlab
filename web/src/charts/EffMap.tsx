import { useEffect, useRef, useState } from "react";
import type { EffResult } from "../lib/api";

const STOPS: [number, number, number][] = [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]];
const color = (t: number) => { const x = Math.min(Math.max(t, 0), 1) * (STOPS.length - 1), i = Math.min(Math.floor(x), STOPS.length - 2), f = x - i; const c = STOPS[i].map((v, k) => Math.round(v + (STOPS[i + 1][k] - v) * f)); return `rgb(${c[0]},${c[1]},${c[2]})`; };
export const ETA0 = 0.70, ETA1 = 0.97;

/** 토크-속도 효율맵. 누르면 그 점이 운전점이 된다(서버 엔진이 다시 푼다). */
export function EffMap({ eff, op, points, onPick, height = 300 }: { eff: EffResult; op?: { speed_rpm: number; torque_Nm: number } | null; points?: { rpm: number[]; Nm: number[] }; onPick?: (rpm: number, Nm: number) => void; height?: number }) {
  const cv = useRef<HTMLCanvasElement>(null), [hover, setHover] = useState("");
  const geom = useRef({ x0: 46, y0: 10, w: 1, h: 1, xmax: 1, ymax: 1 });
  useEffect(() => {
    const c = cv.current!, dpr = Math.min(window.devicePixelRatio, 2), W = c.clientWidth, H = height;
    c.width = W * dpr; c.height = H * dpr; const g = c.getContext("2d")!; g.scale(dpr, dpr); g.clearRect(0, 0, W, H);
    const m = { l: 46, r: 46, t: 10, b: 34 }; const gm = { x0: m.l, y0: m.t, w: W - m.l - m.r, h: H - m.t - m.b, xmax: eff.speed_rpm[eff.speed_rpm.length - 1], ymax: eff.torque_Nm[eff.torque_Nm.length - 1] }; geom.current = gm;
    const X = (v: number) => gm.x0 + (v / gm.xmax) * gm.w, Y = (v: number) => gm.y0 + gm.h - (v / gm.ymax) * gm.h;
    g.fillStyle = "#0f1216"; g.fillRect(gm.x0, gm.y0, gm.w, gm.h);
    const dx = eff.speed_rpm[1] - eff.speed_rpm[0], dy = eff.torque_Nm[1] - eff.torque_Nm[0];
    eff.torque_Nm.forEach((T, i) => eff.speed_rpm.forEach((S, j) => { const e = eff.eta[i][j]; if (e === null) return; g.fillStyle = color((e - ETA0) / (ETA1 - ETA0)); g.fillRect(X(S - dx / 2), Y(T + dy / 2), (dx / gm.xmax) * gm.w + 1, (dy / gm.ymax) * gm.h + 1); }));
    g.strokeStyle = "#e9ecf1"; g.lineWidth = 2; g.beginPath(); let st = false;
    eff.max_torque_Nm.forEach((t, j) => { if (t === null) return; const x = X(eff.speed_rpm[j]), y = Y(Math.min(t, gm.ymax)); st ? g.lineTo(x, y) : g.moveTo(x, y); st = true; }); g.stroke();
    g.setLineDash([5, 4]); g.lineWidth = 1; g.strokeStyle = "rgba(233,236,241,.7)"; g.beginPath(); g.moveTo(X(eff.base_speed_rpm), gm.y0); g.lineTo(X(eff.base_speed_rpm), gm.y0 + gm.h); g.stroke(); g.setLineDash([]);
    g.fillStyle = "#e9ecf1"; g.font = "10px system-ui"; g.fillText("기저 속도", X(eff.base_speed_rpm) + 4, gm.y0 + 11);
    if (points) { g.fillStyle = "rgba(255,255,255,.7)"; for (let k = 0; k < points.rpm.length; k += 2) { g.beginPath(); g.arc(X(points.rpm[k]), Y(points.Nm[k]), 1.4, 0, 6.3); g.fill(); } }
    if (op) { const x = X(op.speed_rpm), y = Y(op.torque_Nm); g.strokeStyle = "#ff7a3d"; g.lineWidth = 1.5; g.beginPath(); g.moveTo(x - 9, y); g.lineTo(x + 9, y); g.moveTo(x, y - 9); g.lineTo(x, y + 9); g.stroke(); g.fillStyle = "#ff7a3d"; g.beginPath(); g.arc(x, y, 4, 0, 6.3); g.fill(); g.strokeStyle = "#fff"; g.lineWidth = 1.2; g.stroke(); }
    g.fillStyle = "#8d96a3"; g.font = "10px system-ui"; g.textAlign = "center";
    for (let v = 0; v <= gm.xmax; v += 1000) g.fillText(String(v), X(v), H - 20);
    g.fillText("모터 속도 [rpm]", gm.x0 + gm.w / 2, H - 6); g.textAlign = "right";
    for (let v = 0; v <= gm.ymax; v += 50) g.fillText(String(v), gm.x0 - 5, Y(v) + 3);
    g.save(); g.translate(10, gm.y0 + gm.h / 2); g.rotate(-Math.PI / 2); g.textAlign = "center"; g.fillText("전자기 토크 [N·m]", 0, 0); g.restore();
    const bx = W - m.r + 14; for (let k = 0; k < gm.h; k++) { g.fillStyle = color(1 - k / gm.h); g.fillRect(bx, gm.y0 + k, 10, 1); }
    g.fillStyle = "#8d96a3"; g.textAlign = "left"; g.fillText(`${ETA1 * 100 | 0}%`, bx + 13, gm.y0 + 8); g.fillText(`${ETA0 * 100 | 0}%`, bx + 13, gm.y0 + gm.h);
  }, [eff, op, points, height]);
  const at = (ev: React.MouseEvent) => { const r = cv.current!.getBoundingClientRect(), gm = geom.current, px = ev.clientX - r.left, py = ev.clientY - r.top; const rpm = ((px - gm.x0) / gm.w) * gm.xmax, Nm = ((gm.y0 + gm.h - py) / gm.h) * gm.ymax; return rpm < 0 || rpm > gm.xmax || Nm < 0 || Nm > gm.ymax ? null : { rpm, Nm }; };
  return (
    <div>
      <canvas ref={cv} style={{ width: "100%", height, cursor: onPick ? "crosshair" : "default", borderRadius: 8 }}
        onMouseMove={(e) => { const p = at(e); if (!p) return setHover(""); const j = Math.round((p.rpm / geom.current.xmax) * (eff.speed_rpm.length - 1)), i = Math.round(((p.Nm - eff.torque_Nm[0]) / (geom.current.ymax - eff.torque_Nm[0])) * (eff.torque_Nm.length - 1)); const v = eff.eta[Math.max(0, Math.min(i, eff.eta.length - 1))]?.[Math.max(0, Math.min(j, eff.speed_rpm.length - 1))]; setHover(`${p.rpm.toFixed(0)} rpm · ${p.Nm.toFixed(0)} N·m → ${v == null ? "낼 수 없는 영역" : `효율 ${(v * 100).toFixed(1)} %`}`); }}
        onMouseLeave={() => setHover("")} onClick={(e) => { const p = at(e); if (p && onPick) onPick(p.rpm, p.Nm); }} />
      <div className="hint">{hover || (onPick ? "맵을 누르면 그 운전점으로 계산합니다." : "")}</div>
    </div>
  );
}
