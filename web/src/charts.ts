import type { CycleResult, EffResult } from "./api";

/** 색 척도(viridis 근사)와 그리기. 값 계산은 하지 않고 서버가 준 배열을 색으로 바꾸기만 한다. */
const STOPS: [number, number, number][] = [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]];
function color(t: number): string {
  const x = Math.min(Math.max(t, 0), 1) * (STOPS.length - 1), i = Math.min(Math.floor(x), STOPS.length - 2), f = x - i;
  const c = STOPS[i].map((v, k) => Math.round(v + (STOPS[i + 1][k] - v) * f));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}
const css = (n: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim() || "#23201d";

export interface MapGeom { x0: number; y0: number; w: number; h: number; xmax: number; ymax: number }
export const ETA_RANGE: [number, number] = [0.70, 0.97];

export function drawEfficiencyMap(cv: HTMLCanvasElement, r: EffResult, points?: { rpm: number[]; Nm: number[] }): MapGeom {
  const ctx = cv.getContext("2d")!; const W = cv.width, H = cv.height;
  ctx.clearRect(0, 0, W, H);
  const m = { l: 52, r: 62, t: 14, b: 40 };
  const geom: MapGeom = { x0: m.l, y0: m.t, w: W - m.l - m.r, h: H - m.t - m.b, xmax: r.speed_rpm[r.speed_rpm.length - 1], ymax: r.torque_Nm[r.torque_Nm.length - 1] };
  const X = (v: number) => geom.x0 + (v / geom.xmax) * geom.w, Y = (v: number) => geom.y0 + geom.h - (v / geom.ymax) * geom.h;
  const dx = r.speed_rpm[1] - r.speed_rpm[0], dy = r.torque_Nm[1] - r.torque_Nm[0];
  for (let i = 0; i < r.torque_Nm.length; i++) for (let j = 0; j < r.speed_rpm.length; j++) {
    const e = r.eta[i][j]; if (e === null) continue;
    ctx.fillStyle = color((e - ETA_RANGE[0]) / (ETA_RANGE[1] - ETA_RANGE[0]));
    ctx.fillRect(X(r.speed_rpm[j] - dx / 2), Y(r.torque_Nm[i] + dy / 2), (dx / geom.xmax) * geom.w + 1, (dy / geom.ymax) * geom.h + 1);
  }
  ctx.strokeStyle = css("--ink"); ctx.lineWidth = 2; ctx.beginPath();
  let started = false;
  r.max_torque_Nm.forEach((t, j) => { if (t === null) return; const x = X(r.speed_rpm[j]), y = Y(Math.min(t, geom.ymax)); started ? ctx.lineTo(x, y) : ctx.moveTo(x, y); started = true; });
  ctx.stroke();
  ctx.setLineDash([5, 4]); ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(X(r.base_speed_rpm), geom.y0); ctx.lineTo(X(r.base_speed_rpm), geom.y0 + geom.h); ctx.stroke(); ctx.setLineDash([]);
  if (points) { ctx.fillStyle = "rgba(255,255,255,.75)"; ctx.strokeStyle = "rgba(0,0,0,.5)"; for (let k = 0; k < points.rpm.length; k++) { ctx.beginPath(); ctx.arc(X(points.rpm[k]), Y(points.Nm[k]), 1.8, 0, 6.3); ctx.fill(); } }
  ctx.fillStyle = css("--ink"); ctx.font = "12px sans-serif"; ctx.textAlign = "center";
  for (let v = 0; v <= geom.xmax; v += 1000) { ctx.fillText(String(v), X(v), H - 22); }
  ctx.fillText("모터 속도 [rpm]", geom.x0 + geom.w / 2, H - 6);
  ctx.textAlign = "right";
  for (let v = 0; v <= geom.ymax; v += 50) ctx.fillText(String(v), geom.x0 - 6, Y(v) + 4);
  ctx.save(); ctx.translate(12, geom.y0 + geom.h / 2); ctx.rotate(-Math.PI / 2); ctx.textAlign = "center"; ctx.fillText("전자기 토크 [N·m]", 0, 0); ctx.restore();
  // 색 막대
  const bx = W - m.r + 18, bh = geom.h;
  for (let k = 0; k < bh; k++) { ctx.fillStyle = color(1 - k / bh); ctx.fillRect(bx, geom.y0 + k, 12, 1); }
  ctx.fillStyle = css("--ink"); ctx.textAlign = "left";
  ctx.fillText(`${Math.round(ETA_RANGE[1] * 100)}%`, bx + 16, geom.y0 + 8); ctx.fillText(`${Math.round(ETA_RANGE[0] * 100)}%`, bx + 16, geom.y0 + bh);
  return geom;
}

export function effAt(r: EffResult, g: MapGeom, px: number, py: number): { rpm: number; Nm: number; eta: number | null } | null {
  const rpm = ((px - g.x0) / g.w) * g.xmax, Nm = ((g.y0 + g.h - py) / g.h) * g.ymax;
  if (rpm < 0 || rpm > g.xmax || Nm < 0 || Nm > g.ymax) return null;
  const j = Math.min(r.speed_rpm.length - 1, Math.max(0, Math.round((rpm / g.xmax) * (r.speed_rpm.length - 1))));
  const i = Math.min(r.torque_Nm.length - 1, Math.max(0, Math.round(((Nm - r.torque_Nm[0]) / (g.ymax - r.torque_Nm[0])) * (r.torque_Nm.length - 1))));
  return { rpm, Nm, eta: r.eta[i][j] };
}

export function drawCycle(cv: HTMLCanvasElement, r: CycleResult): void {
  const ctx = cv.getContext("2d")!; const W = cv.width, H = cv.height; ctx.clearRect(0, 0, W, H);
  const m = { l: 44, r: 44, t: 10, b: 28 }, w = W - m.l - m.r, h = H - m.t - m.b;
  const t = r.series.t_s, tmax = t[t.length - 1];
  const vmax = Math.max(...r.series.speed_kmh) * 1.05, Tmax = Math.max(...r.series.torque_Nm.map(Math.abs)) * 1.1;
  const X = (v: number) => m.l + (v / tmax) * w;
  ctx.strokeStyle = "rgba(0,0,0,.12)"; ctx.beginPath(); ctx.moveTo(m.l, m.t + h / 2); ctx.lineTo(m.l + w, m.t + h / 2); ctx.stroke();
  const line = (ys: number[], ymin: number, ymax: number, col: string) => { ctx.strokeStyle = col; ctx.lineWidth = 1.4; ctx.beginPath(); ys.forEach((y, k) => { const px = X(t[k]), py = m.t + h - ((y - ymin) / (ymax - ymin)) * h; k ? ctx.lineTo(px, py) : ctx.moveTo(px, py); }); ctx.stroke(); };
  line(r.series.speed_kmh, 0, vmax, css("--cu"));
  line(r.series.torque_Nm, -Tmax, Tmax, "#3f6fb5");
  ctx.fillStyle = css("--ink"); ctx.font = "11px sans-serif"; ctx.textAlign = "center";
  for (let v = 0; v <= tmax; v += 300) ctx.fillText(String(v), X(v), H - 12);
  ctx.fillText("시간 [s]", m.l + w / 2, H - 1);
  ctx.textAlign = "left"; ctx.fillStyle = css("--cu"); ctx.fillText(`속도 (최대 ${vmax.toFixed(0)} km/h)`, m.l + 4, m.t + 10);
  ctx.fillStyle = "#3f6fb5"; ctx.fillText(`전자기 토크 (±${Tmax.toFixed(0)} N·m, 회생 −)`, m.l + 4, m.t + 24);
}
