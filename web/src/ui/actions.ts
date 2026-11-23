import { api } from "../lib/api";
import { useStore, type ViewMode } from "../lib/store";
import { motion } from "../scene/motion";
import { TOUR } from "../scene/tour";

const S = () => useStore.getState();
const set = (p: Parameters<ReturnType<typeof S>["set"]>[0]) => S().set(p);

export function setView(v: ViewMode, explode = v === "exploded" ? 1 : 0) {
  set({ view: v, explodeTarget: explode, tourStep: v === S().view ? S().tourStep : -1 });
}
export function selectPart(infoId: string, focusId: string | null = null) {
  set({ selected: infoId, tab: "info", focusId: focusId ?? infoId, focusNonce: S().focusNonce + 1 });
}

let effSeq = 0;
export async function loadEff() {
  const my = ++effSeq, s = S().settings; set({ effBusy: true });
  try { const eff = await api.efficiency({ ...s, n_torque: 50, n_speed: 70 }); if (my === effSeq) set({ eff, effBusy: false }); } catch (e) { set({ status: String(e), effBusy: false }); }
}
let opSeq = 0;
export async function loadOp() {
  const my = ++opSeq, s = S(); set({ opBusy: true });
  try { const op = await api.operatingPoint({ ...s.opInput, ...s.settings }); if (my === opSeq) set({ op, opBusy: false }); } catch (e) { set({ status: String(e), opBusy: false }); }
}
export async function loadFlux(state: string) {
  set({ fluxState: state }); try { set({ flux: await api.flux(state) }); } catch (e) { set({ status: String(e) }); }
}
export async function runCycle(cycle: string, regen: number, mass: number | null) {
  const s = S(); set({ cycleBusy: true, status: `${cycle} 계산 중…` });
  try {
    const r = await api.cycle({ cycle, regen_ratio: regen, ...s.settings, vehicle: mass ? { mass_kg: mass } : {} });
    motion.driveT = 0; set({ cycle: r, cycleBusy: false, drive: { ...s.drive, t: 0, playing: false }, status: `${cycle} 전비 ${r.km_per_kWh.toFixed(2)} km/kWh` });
  } catch (e) { set({ status: String(e), cycleBusy: false }); }
}

let tourTimer: number | undefined, focusTimer: number | undefined;
export function goTour(i: number) {
  const n = Math.max(0, Math.min(TOUR.length - 1, i)), st = TOUR[n];
  clearTimeout(focusTimer);
  set({ tourStep: n, view: st.view, explodeTarget: st.explode, selected: st.infoId, tab: "info", focusId: null, showFlux: !!st.flux, showCoolant: !!st.coolant, xray: false });
  if (st.flux && !S().flux) void loadFlux(S().fluxState);
  focusTimer = window.setTimeout(() => set({ focusId: st.focus, focusNonce: S().focusNonce + 1 }), st.explode > 0 ? 1300 : 200);
}
export function stopTour() { clearInterval(tourTimer); set({ tourStep: -1, tourPlaying: false }); }
export function playTour() {
  clearInterval(tourTimer); set({ tourPlaying: true }); if (S().tourStep < 0) goTour(0);
  tourTimer = window.setInterval(() => { const s = S(); if (s.tourStep >= TOUR.length - 1) { clearInterval(tourTimer); set({ tourPlaying: false }); } else goTour(s.tourStep + 1); }, 8000);
}
export function pauseTour() { clearInterval(tourTimer); set({ tourPlaying: false }); }
