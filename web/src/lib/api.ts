/** 서버 API 타입과 호출. 계산은 전부 서버(엔진)가 하고 화면은 받은 값을 그린다.
 *  데스크톱 앱(Electron)에서는 preload가 window.motorlab.apiBase를 넣어 준다. 브라우저에서는 같은 출처(또는 Vite 프록시)를 쓴다. */
declare global { interface Window { motorlab?: { apiBase?: string; platform?: string; version?: string } } }
const BASE: string = window.motorlab?.apiBase ?? (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export interface CycleInfo { id: string; name: string; distance_km: number; duration_s: number; source: string }
export interface Validation {
  reference: string; physical_core_mean_error_pp: number; physical_high_speed_mean_error_pp: number;
  empirical_core_mean_error_pp: number; empirical_high_speed_mean_error_pp: number; empirical_is_calibration: boolean; g1_status: string;
}
export interface Presets {
  motors: { id: string; name: string; sources: string; limits: { Imax_A: number; Vdc_V: number; k_mod: number; note: string }; winding_R_21C_ohm: number }[];
  cycles: CycleInfo[];
  vehicle: { mass_kg: number; road_a_N: number; road_b_Ns_m: number; road_c_Ns2_m2: number };
  validation: Validation;
  model_notes: { physical: string; empirical: string };
}
export type Pt = [number, number];
export interface Geometry {
  slots: number; poles: number; stack_length_mm: number; source: string;
  stator: { bore_radius_mm: number; outer_radius_mm: number; slot_outline_mm: Pt[]; slot_angle_offset_deg: number };
  rotor: { outer_radius_mm: number; inner_radius_mm: number; magnets_mm: Pt[][]; pole_angle_offset_deg: number };
  winding: { slot_layout: string[]; coil_pitch_slots: number; turns_per_slot: number; end_winding_extension_mm: number; end_winding_source: string };
  housing: { diameter_mm: number; length_mm: number; source: string };
}
export interface PartSpec { label: string; value: string; source: string }
export interface PartInfo { id: string; name: string; name_en: string; role: string; story: string; specs: PartSpec[]; dimensions_sourced: boolean }
export interface EffResult {
  speed_rpm: number[]; torque_Nm: number[]; eta: (number | null)[][]; max_torque_Nm: (number | null)[]; base_speed_rpm: number;
  peak_eta: number; model_note: string; elapsed_ms: number;
}
export interface Waveforms { theta_deg: number[]; ia: number[]; ib: number[]; ic: number[]; va: number[]; vb: number[]; vc: number[]; beta_deg: number }
export interface OperatingPoint {
  feasible: boolean; reason?: string; speed_rpm: number; torque_Nm: number; em_torque_Nm?: number; id_A?: number; iq_A?: number;
  current?: { peak_A: number; rms_A: number; beta_deg: number };
  voltage?: { vd_V: number; vq_V: number; peak_V: number; ll_rms_V: number; limit_peak_V: number; ratio_to_limit: number };
  flux?: { psi_d_Wb: number; psi_q_Wb: number; psi_Wb: number };
  power_W?: { shaft_out: number; input: number; loss_total: number; copper: number; iron: number; mechanical: number; excess: number };
  efficiency?: number; mode?: string; waveforms?: Waveforms; model_note?: string;
}
export interface CycleResult {
  cycle: string; model: string; distance_km: number; km_per_kWh: number; wh_per_km: number;
  energy_kWh: Record<string, number>; shortfall: { time_s: number; wheel_energy_fraction: number };
  series: { t_s: number[]; speed_kmh: number[]; motor_rpm: number[]; torque_Nm: number[]; elec_power_kW: number[]; loss_kW: number[]; efficiency: (number | null)[]; current_A: number[] };
  operating_points: { motor_rpm: number[]; torque_Nm: number[] };
  scope_note: string; model_note: string; validation: Validation; elapsed_ms: number;
}
export interface FluxInfo { state: string; label: string; id_A: number; iq_A: number; torque_Nm: number }
export interface FluxField extends FluxInfo { rotor_deg: number; grid_n: number; half_size_mm: number; A_Wb_per_m: (number | null)[][]; B_T: (number | null)[][]; source: string; note: string }

async function call<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(BASE + path, body === undefined ? undefined : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}
export const api = {
  presets: () => call<Presets>("/api/presets"),
  geometry: () => call<Geometry>("/api/geometry/prius2004"),
  parts: () => call<{ parts: PartInfo[] }>("/api/parts"),
  fluxList: () => call<{ states: FluxInfo[] }>("/api/flux"),
  flux: (s: string) => call<FluxField>(`/api/flux/${s}`),
  efficiency: (b: object) => call<EffResult>("/api/efficiency", b),
  operatingPoint: (b: object) => call<OperatingPoint>("/api/operating_point", b),
  cycle: (b: object) => call<CycleResult>("/api/cycle", b),
};
