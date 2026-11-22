// 참고용 발췌: 2D 대시보드 초안(폐기)의 최대 토크 곡선 격자 탐색 로직.
// 검증되지 않은 코드. Rs 무시, 상수 파라미터, p=4 고정. engine/operating.py 설계 시 아이디어 참고만 할 것.
// 규약: id = -i*sin(b), iq = i*cos(b), b = 0..90deg
  getCurve() {
    const par = this.state.par;
    const key = [par.psi, par.ld, par.lq, par.vdc, par.imax].join('|');
    if (this._cache && this._cache.key === key) return this._cache;
    const p = 4, psi = par.psi, ld = par.ld * 1e-3, lq = par.lq * 1e-3, vmax = par.vdc / Math.sqrt(3);
    const tq = (i, b) => 1.5 * p * (psi * i * Math.cos(b) + (lq - ld) * i * i * Math.sin(b) * Math.cos(b));
    const vol = (i, b, w) => w * Math.hypot(psi - ld * i * Math.sin(b), lq * i * Math.cos(b));
    const rows = [];
    for (let k = 0; k <= 80; k++) {
      const rpm = k * 150, w = p * rpm * Math.PI / 30;
      let best = { t: 0, i: 0, b: 0 };
      for (let bi = 0; bi <= 120; bi++) {
        const b = (bi / 120) * Math.PI / 2;
        let i = -1, hi = -1;
        for (let s = 0; s <= 40; s++) {
          const c = par.imax * (1 - s / 40);
          if (vol(c, b, w) <= vmax) { i = c; hi = s > 0 ? par.imax * (1 - (s - 1) / 40) : -1; break; }
        }
        if (i < 0) continue;
        if (hi > 0) {
          let lo = i, up = hi;
          for (let n = 0; n < 8; n++) { const m = (lo + up) / 2; if (vol(m, b, w) <= vmax) lo = m; else up = m; }
          i = lo;
        }
        const t = tq(i, b);
        if (t > best.t) best = { t: t, i: i, b: b };
      }
      rows.push({ rpm: rpm, t: best.t, i: best.i, b: best.b, pkw: best.t * rpm * Math.PI / 30 / 1000, id: -best.i * Math.sin(best.b), iq: best.i * Math.cos(best.b) });
    }
    const mtpa = [];
    for (let ii = 0; ii <= 40; ii++) {
      const i = par.imax * ii / 40;
      let bb = 0, bt = -1;
      for (let bi = 0; bi <= 90; bi++) { const b = bi / 90 * Math.PI / 2; const t = tq(i, b); if (t > bt) { bt = t; bb = b; } }
      mtpa.push({ id: -i * Math.sin(bb), iq: i * Math.cos(bb) });
    }
    const t0 = rows[0].t;
    const bRow = rows.find((q) => q.t < 0.985 * t0);
    let pmax = 0;
    rows.forEach((q) => { if (q.pkw > pmax) pmax = q.pkw; });
    this._cache = { key: key, rows: rows, mtpa: mtpa, tq: tq, vol: vol, vmax: vmax, tpeak: t0, base: bRow ? bRow.rpm : 12000, pmax: pmax };
    return this._cache;
  }

  interp(rows, rpm) {
    const x = Math.min(Math.max(rpm, 0), 12000) / 150;
    const k = Math.min(79, Math.floor(x));
    const f = x - k, a = rows[k], b = rows[k + 1];
