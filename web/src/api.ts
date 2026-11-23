/** 서버 API 타입과 호출. 계산은 전부 서버(엔진)가 하고 화면은 받은 값을 그린다. */
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
}
export interface EffResult {
  speed_rpm: number[]; torque_Nm: number[]; eta: (number | null)[][]; max_torque_Nm: (number | null)[]; base_speed_rpm: number;
  peak_eta: number; model_note: string; elapsed_ms: number;
}
export interface CycleResult {
  cycle: string; model: string; distance_km: number; km_per_kWh: number; wh_per_km: number;
  energy_kWh: Record<string, number>; shortfall: { time_s: number; wheel_energy_fraction: number };
  series: { t_s: number[]; speed_kmh: number[]; motor_rpm: number[]; torque_Nm: number[]; elec_power_kW: number[] };
  operating_points: { motor_rpm: number[]; torque_Nm: number[] };
  scope_note: string; model_note: string; validation: Validation; elapsed_ms: number;
}

async function call<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, body === undefined ? undefined : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}
export const getPresets = () => call<Presets>("/api/presets");
export const getGeometry = () => call<Geometry>("/api/geometry/prius2004");
export const postEfficiency = (b: object) => call<EffResult>("/api/efficiency", b);
export const postCycle = (b: object) => call<CycleResult>("/api/cycle", b);
