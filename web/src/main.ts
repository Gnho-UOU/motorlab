import "./style.css";
import { getGeometry, getPresets, postCycle, postEfficiency, type CycleResult, type EffResult, type Presets } from "./api";
import { buildMotor } from "./scene";
import { drawCycle, drawEfficiencyMap, effAt, type MapGeom } from "./charts";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const fmt = (x: number, d = 2) => x.toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d });
let presets: Presets, lastEff: EffResult | null = null, lastGeom: MapGeom | null = null, lastCycle: CycleResult | null = null;

function busy(on: boolean) { $("busy").hidden = !on; }

function effBody() {
  return { Vdc: +$<HTMLInputElement>("vdc").value, Imax: +$<HTMLInputElement>("imax").value, winding_C: +$<HTMLInputElement>("temp").value,
           model: $<HTMLSelectElement>("model").value, n_torque: 50, n_speed: 70 };
}

let effSeq = 0, timer: number | undefined;
async function refreshEff() {
  const my = ++effSeq; busy(true);
  $("v-vdc").textContent = `${$<HTMLInputElement>("vdc").value} V`; $("v-imax").textContent = `${$<HTMLInputElement>("imax").value} A`; $("v-temp").textContent = `${$<HTMLInputElement>("temp").value} °C`;
  try {
    const r = await postEfficiency(effBody());
    if (my !== effSeq) return;
    lastEff = r;
    lastGeom = drawEfficiencyMap($<HTMLCanvasElement>("effmap"), r, lastCycle ? { rpm: lastCycle.operating_points.motor_rpm, Nm: lastCycle.operating_points.torque_Nm } : undefined);
    $("eff-kv").innerHTML = `<span>최고 효율</span><b>${fmt(r.peak_eta * 100, 1)} %</b><span>기저 속도</span><b>${fmt(r.base_speed_rpm, 0)} rpm</b><span>저속 최대 토크</span><b>${fmt(r.max_torque_Nm[0] ?? 0, 0)} N·m</b><span>계산 시간</span><b>${fmt(r.elapsed_ms / 1000, 1)} s</b>`;
    $("eff-badge").textContent = r.model_note;
    $("eff-badge").className = "badge" + (effBody().model === "empirical" ? " warn" : "");
  } catch (e) { $("eff-badge").textContent = String(e); }
  finally { if (my === effSeq) busy(false); }
}
const schedule = () => { clearTimeout(timer); timer = window.setTimeout(refreshEff, 350); };

async function runCycle() {
  busy(true);
  try {
    const mass = $<HTMLInputElement>("mass").value;
    const r = await postCycle({ cycle: $<HTMLSelectElement>("cycle").value, regen_ratio: +$<HTMLInputElement>("regen").value / 100, Vdc: +$<HTMLInputElement>("vdc").value,
      Imax: +$<HTMLInputElement>("imax").value, winding_C: +$<HTMLInputElement>("temp").value, model: $<HTMLSelectElement>("model").value, vehicle: mass ? { mass_kg: +mass } : {} });
    lastCycle = r;
    const e = r.energy_kWh;
    $("cyc-result").innerHTML = `<div class="big">${fmt(r.km_per_kWh)} <small>km/kWh</small> · ${fmt(r.wh_per_km, 0)} <small>Wh/km</small></div>
      <div class="kv"><span>주행 거리</span><b>${fmt(r.distance_km)} km</b><span>바퀴 구동 에너지</span><b>${fmt(e.wheel_traction)} kWh</b><span>기어 손실(구동)</span><b>${fmt(e.gear_loss_traction, 3)} kWh</b>
      <span>모터 손실(구동)</span><b>${fmt(e.motor_loss_traction, 3)} kWh</b><span>모터 전기 소비</span><b>${fmt(e.motor_in)} kWh</b><span>회생 회수</span><b>${fmt(e.regen)} kWh</b>
      <span>마찰 제동으로 버린 에너지</span><b>${fmt(e.friction_brake)} kWh</b><span>순 전기 에너지</span><b>${fmt(e.net)} kWh</b>
      <span>모터가 못 낸 구동 에너지</span><b>${fmt(r.shortfall.wheel_energy_fraction * 100, 2)} %</b></div><p class="note">${r.scope_note}</p><p class="note">${r.model_note}</p>`;
    $("dock-label").textContent = `${r.cycle} 전비`; $("dock-val").textContent = `${fmt(r.km_per_kWh)} km/kWh`;
    $("dock-sub").textContent = `${r.model === "physical" ? "물리 모델" : "경험식 포함(보정)"} · 모터 입력 기준 · 실험적`;
    drawCycle($<HTMLCanvasElement>("cycplot"), r);
    if (lastEff) drawEfficiencyMap($<HTMLCanvasElement>("opmap"), lastEff, { rpm: r.operating_points.motor_rpm, Nm: r.operating_points.torque_Nm });
  } catch (e) { $("cyc-result").textContent = String(e); }
  finally { busy(false); }
}

function fillInfo() {
  const v = presets.validation, m = presets.motors[0], veh = presets.vehicle;
  $("info").innerHTML = `<h3>${m.name}</h3><p>${m.sources}</p>
    <h4>검증 상태 (ORNL 실측 대비)</h4>
    <div class="kv"><span>물리 모델 효율 편차, 주요 영역(1000~4000 rpm)</span><b>${fmt(v.physical_core_mean_error_pp, 1)} %p</b>
    <span>물리 모델, 4000 rpm 이상</span><b>${fmt(v.physical_high_speed_mean_error_pp, 1)} %p</b>
    <span>경험식 포함, 주요 영역</span><b>${fmt(v.empirical_core_mean_error_pp, 1)} %p</b>
    <span>경험식 포함, 4000 rpm 이상</span><b>${fmt(v.empirical_high_speed_mean_error_pp, 1)} %p</b></div>
    <p class="note">양수는 모델이 측정보다 효율을 높게 예측한다는 뜻이다. ${v.reference}. ${v.g1_status}. 경험식은 같은 벤치마크에 맞춘 보정이다.</p>
    <h4>차량 (EPA 2004 Prius 시험 차량)</h4>
    <div class="kv"><span>등가 질량</span><b>${fmt(veh.mass_kg, 0)} kg</b><span>도로 부하 A</span><b>${fmt(veh.road_a_N, 1)} N</b><span>B</span><b>${fmt(veh.road_b_Ns_m, 3)} N·s/m</b><span>C</span><b>${fmt(veh.road_c_Ns2_m2, 4)} N·s²/m²</b></div>
    <h4>한계</h4><p class="note">${m.limits.note}</p><p class="note">${presets.model_notes.physical}</p><p class="note">${presets.model_notes.empirical}</p>
    <p class="note">화면의 모든 숫자는 서버의 엔진(Python)이 계산한 값이다. 이 화면에는 계산식이 없다.</p>`;
}

async function main() {
  presets = await getPresets(); fillInfo();
  const sel = $<HTMLSelectElement>("cycle");
  sel.innerHTML = presets.cycles.map((c) => `<option value="${c.id}">${c.name} · ${fmt(c.distance_km, 1)} km</option>`).join("");
  const geo = await getGeometry();
  $("geo-note").textContent = "단면 도식: 자석 포켓만 그린 단순화 형상(공기 장벽 생략)";
  const view = buildMotor($<HTMLCanvasElement>("scene"), geo);
  view.setCutaway(true);
  $<HTMLInputElement>("cut").onchange = (e) => view.setCutaway((e.target as HTMLInputElement).checked);
  $<HTMLInputElement>("spin").onchange = (e) => view.setSpin((e.target as HTMLInputElement).checked);
  for (const id of ["vdc", "imax", "temp"]) $<HTMLInputElement>(id).oninput = schedule;
  $<HTMLSelectElement>("model").onchange = () => { refreshEff(); };
  $<HTMLInputElement>("regen").oninput = () => { $("v-regen").textContent = `${$<HTMLInputElement>("regen").value} %`; };
  $("v-regen").textContent = "100 %";
  $("run").onclick = runCycle;
  document.querySelectorAll<HTMLButtonElement>("#tabs button").forEach((b) => (b.onclick = () => {
    document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("on", x === b));
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("on", t.id === `tab-${b.dataset.tab}`));
  }));
  const cv = $<HTMLCanvasElement>("effmap");
  cv.onmousemove = (ev) => {
    if (!lastEff || !lastGeom) return;
    const rect = cv.getBoundingClientRect(), sx = cv.width / rect.width;
    const h = effAt(lastEff, lastGeom, (ev.clientX - rect.left) * sx, (ev.clientY - rect.top) * sx);
    $("eff-hover").textContent = h ? `${fmt(h.rpm, 0)} rpm, ${fmt(h.Nm, 0)} N·m → ${h.eta === null ? "낼 수 없는 영역" : `효율 ${fmt(h.eta * 100, 1)} %`}` : "";
  };
  await refreshEff();
}
main().catch((e) => { document.body.insertAdjacentHTML("beforeend", `<pre class="err">${String(e)}</pre>`); });
