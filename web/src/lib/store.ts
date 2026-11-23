import { create } from "zustand";
import type { CycleResult, EffResult, FluxField, FluxInfo, Geometry, OperatingPoint, PartInfo, Presets } from "./api";

export type ViewMode = "assembled" | "section" | "exploded";
export type Quality = "low" | "medium" | "high";
export type Tab = "info" | "operate" | "map" | "cycle" | "flux" | "settings";

export interface Settings { Vdc: number; Imax: number; winding_C: number; model: "physical" | "empirical" }

interface State {
  presets: Presets | null; geometry: Geometry | null; parts: PartInfo[]; fluxList: FluxInfo[];
  selected: string | null; hovered: string | null; hidden: Record<string, boolean>; xray: boolean;
  view: ViewMode; explodeTarget: number; sectionZ: number; polarityColors: boolean;
  tourStep: number; tourPlaying: boolean;
  focusNonce: number; focusId: string | null;
  tab: Tab; settings: Settings; quality: Quality; fps: number; gpu: string;
  eff: EffResult | null; effBusy: boolean;
  op: OperatingPoint | null; opInput: { speed_rpm: number; torque_Nm: number }; opBusy: boolean;
  spinning: boolean; spinSpeed: number;
  showFlux: boolean; fluxState: string; flux: FluxField | null; fluxMode: "lines" | "heat" | "both";
  showCoolant: boolean; showWindingGlow: boolean;
  cycle: CycleResult | null; cycleBusy: boolean; drive: { playing: boolean; t: number; speed: number };
  status: string;
  set: (p: Partial<State>) => void;
}

export const useStore = create<State>((set) => ({
  presets: null, geometry: null, parts: [], fluxList: [],
  selected: null, hovered: null, hidden: {}, xray: false,
  view: "assembled", explodeTarget: 0, sectionZ: 0.5, polarityColors: true,
  tourStep: -1, tourPlaying: false,
  focusNonce: 0, focusId: null,
  tab: "info", settings: { Vdc: 500, Imax: 250, winding_C: 100, model: "physical" }, quality: "high", fps: 0, gpu: "",
  eff: null, effBusy: false,
  op: null, opInput: { speed_rpm: 2000, torque_Nm: 100 }, opBusy: false,
  spinning: false, spinSpeed: 1,
  showFlux: false, fluxState: "mtpa250", flux: null, fluxMode: "both",
  showCoolant: false, showWindingGlow: true,
  cycle: null, cycleBusy: false, drive: { playing: false, t: 0, speed: 8 },
  status: "준비",
  set: (p) => set(p),
}));
