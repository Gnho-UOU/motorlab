import type { FluxField } from "./api";

/** FEA가 푼 격자(A, |B|)를 그림으로 만든다. 자속선 = A의 등고선(marching squares), 바탕 = |B| 색.
 *  이것은 시각화이고 값은 서버가 준 FEA 결과 그대로다. */
const STOPS: [number, number, number][] = [[18, 6, 60], [58, 18, 110], [140, 40, 120], [214, 80, 80], [250, 160, 60], [255, 235, 140]];
function heat(t: number): [number, number, number] {
  const x = Math.min(Math.max(t, 0), 1) * (STOPS.length - 1), i = Math.min(Math.floor(x), STOPS.length - 2), f = x - i;
  return [0, 1, 2].map((k) => STOPS[i][k] + (STOPS[i + 1][k] - STOPS[i][k]) * f) as [number, number, number];
}

export function renderFluxCanvas(f: FluxField, mode: "lines" | "heat" | "both", size = 1024, levels = 26, bMax = 2.2): HTMLCanvasElement {
  const n = f.grid_n, c = document.createElement("canvas"); c.width = c.height = size;
  const g = c.getContext("2d")!, k = size / (n - 1);
  const A = f.A_Wb_per_m, B = f.B_T;
  if (mode !== "lines") {
    const img = g.createImageData(size, size);
    for (let py = 0; py < size; py++) for (let px = 0; px < size; px++) {
      const gx = px / k, gy = (size - 1 - py) / k, i = Math.min(n - 2, Math.floor(gx)), j = Math.min(n - 2, Math.floor(gy));
      const b00 = B[j][i], b10 = B[j][i + 1], b01 = B[j + 1][i], b11 = B[j + 1][i + 1];
      if (b00 === null || b10 === null || b01 === null || b11 === null) continue;
      const fx = gx - i, fy = gy - j, b = b00 * (1 - fx) * (1 - fy) + b10 * fx * (1 - fy) + b01 * (1 - fx) * fy + b11 * fx * fy;
      const [r, gg, bb] = heat(b / bMax), o = (py * size + px) * 4;
      img.data[o] = r; img.data[o + 1] = gg; img.data[o + 2] = bb; img.data[o + 3] = mode === "both" ? 170 : 235;
    }
    g.putImageData(img, 0, 0);
  }
  if (mode !== "heat") {
    let lo = Infinity, hi = -Infinity;
    for (const row of A) for (const v of row) if (v !== null) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
    g.lineWidth = Math.max(1.2, size / 700); g.strokeStyle = "rgba(255,255,255,0.92)"; g.lineCap = "round";
    for (let L = 1; L < levels; L++) {
      const lv = lo + ((hi - lo) * L) / levels; g.beginPath();
      for (let j = 0; j < n - 1; j++) for (let i = 0; i < n - 1; i++) {
        const a = A[j][i], b = A[j][i + 1], d = A[j + 1][i], e = A[j + 1][i + 1];
        if (a === null || b === null || d === null || e === null) continue;
        const pts: [number, number][] = [];
        const edge = (v0: number, v1: number, x0: number, y0: number, x1: number, y1: number) => { if ((v0 - lv) * (v1 - lv) < 0) { const t = (lv - v0) / (v1 - v0); pts.push([x0 + (x1 - x0) * t, y0 + (y1 - y0) * t]); } };
        edge(a, b, i, j, i + 1, j); edge(b, e, i + 1, j, i + 1, j + 1); edge(d, e, i, j + 1, i + 1, j + 1); edge(a, d, i, j, i, j + 1);
        if (pts.length >= 2) { g.moveTo(pts[0][0] * k, size - 1 - pts[0][1] * k); g.lineTo(pts[1][0] * k, size - 1 - pts[1][1] * k); }
      }
      g.stroke();
    }
  }
  return c;
}
