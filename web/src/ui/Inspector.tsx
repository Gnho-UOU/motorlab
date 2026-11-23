import { useEffect, useRef } from "react";
import { CycleChart } from "../charts/CycleChart";
import { DqPlane } from "../charts/Phasor";
import { EffMap } from "../charts/EffMap";
import { LossBars } from "../charts/LossBars";
import { Waves } from "../charts/Waves";
import { useStore, type Quality, type Tab } from "../lib/store";
import { motion } from "../scene/motion";
import { loadEff, loadFlux, loadOp, runCycle, setView } from "./actions";

const fmt = (x: number, d = 1) => x.toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d });
const TABS: [Tab, string][] = [["info", "정보"], ["operate", "운전점"], ["map", "효율맵"], ["cycle", "전비"], ["flux", "자속"], ["settings", "설정"]];

export function Inspector() {
  const tab = useStore((s) => s.tab), set = useStore((s) => s.set);
  return (
    <aside className="inspector">
      <nav className="tabs">{TABS.map(([k, n]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => set({ tab: k })}>{n}</button>)}</nav>
      <div className="tabbody">
        {tab === "info" && <Info />}{tab === "operate" && <Operate />}{tab === "map" && <MapTab />}{tab === "cycle" && <Cycle />}{tab === "flux" && <Flux />}{tab === "settings" && <Settings />}
      </div>
    </aside>
  );
}

function Info() {
  const parts = useStore((s) => s.parts), sel = useStore((s) => s.selected), set = useStore((s) => s.set);
  const p = parts.find((x) => x.id === sel);
  if (!p) return <div className="empty"><h2>모터를 해부해 보세요</h2><p>3D 모터의 부품을 누르거나 왼쪽 목록에서 고르면 그 부품으로 날아가 설명을 보여 줍니다.</p>
    <ul className="tips"><li><b>해부</b> 모드의 분해 슬라이더로 부품을 하나씩 빼 보세요.</li><li><b>단면</b> 모드에서 FEA로 푼 자속선을 볼 수 있습니다.</li><li><b>운전점</b> 탭에서 속도·토크를 정하면 모터가 돌고 3상 전류가 코일에서 빛납니다.</li><li><b>전비</b> 탭에서 WLTP를 달리며 효율을 볼 수 있습니다.</li></ul></div>;
  return (
    <div className="card">
      <div className="kicker">{p.name_en}</div><h2>{p.name}</h2>
      <div className={`badge ${p.dimensions_sourced ? "ok" : "warn"}`}>{p.dimensions_sourced ? "치수: 출처 있는 값으로 그린 형상" : "도식: 치수 출처가 없어 대략적인 모양으로 그렸습니다"}</div>
      <p className="role">{p.role}</p><p>{p.story}</p>
      <table className="specs"><tbody>{p.specs.map((s) => <tr key={s.label}><th>{s.label}</th><td>{s.value}<small>{s.source}</small></td></tr>)}</tbody></table>
      <button className="link" onClick={() => set({ selected: null })}>닫기</button>
    </div>
  );
}

function Slider({ label, value, unit, min, max, step, onChange }: { label: string; value: number; unit: string; min: number; max: number; step: number; onChange: (v: number) => void }) {
  return <div className="ctl"><label>{label}<b>{fmt(value, step < 1 ? 1 : 0)} {unit}</b></label><input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(+e.target.value)} /></div>;
}

function Operate() {
  const op = useStore((s) => s.op), inp = useStore((s) => s.opInput), set = useStore((s) => s.set), spin = useStore((s) => s.spinning), busy = useStore((s) => s.opBusy), st = useStore((s) => s.settings), spd = useStore((s) => s.spinSpeed);
  const t = useRef<number>();
  const ch = (p: Partial<typeof inp>) => { set({ opInput: { ...inp, ...p } }); clearTimeout(t.current); t.current = window.setTimeout(loadOp, 220); };
  return (
    <div>
      <Slider label="속도" value={inp.speed_rpm} unit="rpm" min={200} max={6000} step={50} onChange={(v) => ch({ speed_rpm: v })} />
      <Slider label="샤프트 토크" value={inp.torque_Nm} unit="N·m" min={5} max={330} step={5} onChange={(v) => ch({ torque_Nm: v })} />
      <div className="row"><button className={spin ? "primary" : ""} onClick={() => set({ spinning: !spin })}>{spin ? "❚❚ 정지" : "▶ 구동 시뮬레이션"}</button>
        <label className="ctl inline">화면 속도 ×<input type="number" min={0.25} max={4} step={0.25} value={spd} onChange={(e) => set({ spinSpeed: +e.target.value || 1 })} /></label></div>
      <p className="hint">화면의 회전은 실제의 1/20 속도입니다. 코일의 빛은 3상 전류의 순간값입니다.</p>
      {busy && <div className="hint">계산 중…</div>}
      {op && !op.feasible && <div className="badge bad">{op.reason}</div>}
      {op?.feasible && (
        <>
          <div className="bigrow"><div><small>효율</small><b>{fmt(op.efficiency! * 100, 1)}%</b></div><div><small>모터 입력</small><b>{fmt(op.power_W!.input / 1000, 2)} kW</b></div><div><small>축 출력</small><b>{fmt(op.power_W!.shaft_out / 1000, 2)} kW</b></div></div>
          <div className={`badge ${op.mode!.startsWith("전압") ? "warn" : "ok"}`}>{op.mode} · 전압 사용률 {fmt(op.voltage!.ratio_to_limit * 100, 0)}%</div>
          <div className="two"><div><DqPlane id={op.id_A!} iq={op.iq_A!} imax={st.Imax} beta={op.current!.beta_deg} /></div>
            <table className="kv"><tbody>
              <tr><th>id</th><td>{fmt(op.id_A!)} A</td></tr><tr><th>iq</th><td>{fmt(op.iq_A!)} A</td></tr><tr><th>상전류(실효)</th><td>{fmt(op.current!.rms_A)} A</td></tr><tr><th>전류각 β</th><td>{fmt(op.current!.beta_deg, 0)}°</td></tr>
              <tr><th>선간전압(실효)</th><td>{fmt(op.voltage!.ll_rms_V, 0)} V</td></tr><tr><th>쇄교자속</th><td>{fmt(op.flux!.psi_Wb * 1000, 0)} mWb</td></tr></tbody></table></div>
          <h4>손실 분해</h4><LossBars op={op} />
          <h4>3상 전류</h4><Waves w={op.waveforms!} kind="i" running={spin} />
          <h4>3상 전압</h4><Waves w={op.waveforms!} kind="v" running={spin} />
          <p className="note">{op.model_note}</p>
        </>)}
    </div>
  );
}

function Params() {
  const st = useStore((s) => s.settings), set = useStore((s) => s.set), t = useRef<number>();
  const ch = (p: Partial<typeof st>) => { set({ settings: { ...st, ...p } }); clearTimeout(t.current); t.current = window.setTimeout(() => { void loadEff(); void loadOp(); }, 350); };
  return (<>
    <Slider label="DC 링크 전압" value={st.Vdc} unit="V" min={300} max={650} step={10} onChange={(v) => ch({ Vdc: v })} />
    <Slider label="최대 전류" value={st.Imax} unit="A" min={100} max={400} step={10} onChange={(v) => ch({ Imax: v })} />
    <Slider label="권선 온도" value={st.winding_C} unit="°C" min={20} max={180} step={5} onChange={(v) => ch({ winding_C: v })} />
    <div className="ctl"><label>손실 모델</label><select value={st.model} onChange={(e) => ch({ model: e.target.value as "physical" | "empirical" })}><option value="physical">물리 모델 (동손 + 무부하 + 기어)</option><option value="empirical">경험식 포함 (벤치마크에 맞춘 보정)</option></select></div>
  </>);
}

function MapTab() {
  const eff = useStore((s) => s.eff), busy = useStore((s) => s.effBusy), set = useStore((s) => s.set), inp = useStore((s) => s.opInput), pts = useStore((s) => s.cycle?.operating_points);
  return (
    <div>
      <Params />
      {busy && <div className="hint">계산 중… (엔진이 효율맵을 다시 풉니다)</div>}
      {eff && <EffMap eff={eff} op={inp} points={pts ? { rpm: pts.motor_rpm, Nm: pts.torque_Nm } : undefined} onPick={(rpm, Nm) => { set({ opInput: { speed_rpm: Math.round(rpm / 50) * 50 || 200, torque_Nm: Math.max(5, Math.round(Nm / 5) * 5) }, tab: "operate" }); void loadOp(); }} height={310} />}
      {eff && <div className="kvgrid"><span>최고 효율</span><b>{fmt(eff.peak_eta * 100, 1)}%</b><span>기저 속도</span><b>{fmt(eff.base_speed_rpm, 0)} rpm</b><span>저속 최대 토크</span><b>{fmt(eff.max_torque_Nm[0] ?? 0, 0)} N·m</b><span>계산 시간</span><b>{fmt(eff.elapsed_ms / 1000, 1)} s</b></div>}
      {eff && <div className={`badge ${useStore.getState().settings.model === "empirical" ? "warn" : "ok"}`}>{eff.model_note}</div>}
    </div>
  );
}

function Cycle() {
  const presets = useStore((s) => s.presets), r = useStore((s) => s.cycle), busy = useStore((s) => s.cycleBusy), drive = useStore((s) => s.drive), set = useStore((s) => s.set);
  const cyc = useRef<HTMLSelectElement>(null), regen = useRef<HTMLInputElement>(null), mass = useRef<HTMLInputElement>(null);
  const t = useStore((s) => s.drive.t);
  if (!presets) return null;
  const e = r?.energy_kWh;
  return (
    <div>
      <div className="ctl"><label>주행 사이클</label><select ref={cyc}>{presets.cycles.map((c) => <option key={c.id} value={c.id}>{c.name} · {fmt(c.distance_km, 1)} km</option>)}</select></div>
      <div className="ctl"><label>회생 비율 <b>제동 동력 중 모터가 받는 몫</b></label><input ref={regen} type="range" min={0} max={100} step={5} defaultValue={100} /></div>
      <div className="ctl"><label>차량 등가 질량 [kg] <small>(비우면 EPA {fmt(presets.vehicle.mass_kg, 0)} kg)</small></label><input ref={mass} type="number" min={500} max={5000} step={50} placeholder="기본값" /></div>
      <button className="primary wide" disabled={busy} onClick={() => void runCycle(cyc.current!.value, +regen.current!.value / 100, mass.current!.value ? +mass.current!.value : null)}>{busy ? "계산 중…" : "전비 계산"}</button>
      <div className="badge warn">실험적 · 모터 입력 기준 순수 전기 구동 환산. 고속 구간 효율은 낙관적일 수 있습니다.</div>
      {r && e && (<>
        <div className="bigrow"><div><small>전비</small><b>{fmt(r.km_per_kWh, 2)}</b><small>km/kWh</small></div><div><small>에너지</small><b>{fmt(r.wh_per_km, 0)}</b><small>Wh/km</small></div><div><small>거리</small><b>{fmt(r.distance_km, 1)}</b><small>km</small></div></div>
        <div className="kvgrid"><span>바퀴 구동</span><b>{fmt(e.wheel_traction, 2)} kWh</b><span>기어 손실</span><b>{fmt(e.gear_loss_traction, 3)} kWh</b><span>모터 손실</span><b>{fmt(e.motor_loss_traction, 3)} kWh</b><span>모터 전기 소비</span><b>{fmt(e.motor_in, 2)} kWh</b><span>회생 회수</span><b>{fmt(e.regen, 2)} kWh</b><span>순 전기 에너지</span><b>{fmt(e.net, 2)} kWh</b><span>못 낸 구동 에너지</span><b>{fmt(r.shortfall.wheel_energy_fraction * 100, 2)} %</b></div>
        <h4>주행하며 보기</h4>
        <div className="row"><button className={drive.playing ? "primary" : ""} onClick={() => set({ drive: { ...drive, playing: !drive.playing }, tab: "cycle" })}>{drive.playing ? "❚❚ 정지" : "▶ 드라이브 모드"}</button>
          <label className="ctl inline">배속 ×<select value={drive.speed} onChange={(e2) => set({ drive: { ...drive, speed: +e2.target.value } })}>{[1, 4, 8, 16, 32].map((v) => <option key={v}>{v}</option>)}</select></label></div>
        <CycleChart r={r} t={t} onSeek={(x) => { motion.driveT = x; set({ drive: { ...drive, t: x } }); }} />
        <p className="note">{r.scope_note}</p><p className="note">{r.model_note}</p>
      </>)}
    </div>
  );
}

function Flux() {
  const list = useStore((s) => s.fluxList), cur = useStore((s) => s.fluxState), mode = useStore((s) => s.fluxMode), show = useStore((s) => s.showFlux), flux = useStore((s) => s.flux), view = useStore((s) => s.view), sz = useStore((s) => s.sectionZ), set = useStore((s) => s.set);
  useEffect(() => { if (show && !flux) void loadFlux(cur); }, [show, flux, cur]);
  return (
    <div>
      <p className="note">이 프로젝트가 xfemm(FEMM 호환 솔버)으로 푼 2D 정자장 결과입니다. 자속선은 벡터 퍼텐셜 A의 등고선, 바탕색은 자속밀도 |B|입니다.</p>
      <label className="chk"><input type="checkbox" checked={show} onChange={(e) => { set({ showFlux: e.target.checked }); if (e.target.checked && view !== "section") setView("section"); }} />단면에 자속 분포 표시</label>
      <div className="ctl"><label>운전 상태</label>
        {list.map((f) => <label key={f.state} className="radio"><input type="radio" checked={cur === f.state} onChange={() => void loadFlux(f.state)} /><span><b>{f.label}</b><small>id {f.id_A.toFixed(0)} A, iq {f.iq_A.toFixed(0)} A → FEA 토크 {f.torque_Nm.toFixed(0)} N·m</small></span></label>)}</div>
      <div className="ctl"><label>표시</label><select value={mode} onChange={(e) => set({ fluxMode: e.target.value as "lines" | "heat" | "both" })}><option value="both">자속선 + 자속밀도</option><option value="lines">자속선만</option><option value="heat">자속밀도만</option></select></div>
      <Slider label="절단 위치 (적층 방향)" value={sz * 100} unit="%" min={5} max={95} step={5} onChange={(v) => set({ sectionZ: v / 100 })} />
      {flux && <><div className="badge ok">{flux.label}</div><p className="note">{flux.note}</p><p className="note">{flux.source}</p><p className="note">|B|의 색 척도는 0~2.2 T입니다. 슬롯 모서리의 점 값은 수치 특이점이라 실제보다 클 수 있습니다.</p></>}
    </div>
  );
}

function Settings() {
  const q = useStore((s) => s.quality), set = useStore((s) => s.set), gpu = useStore((s) => s.gpu), fps = useStore((s) => s.fps), presets = useStore((s) => s.presets);
  const desk = window.motorlab;
  return (
    <div>
      <div className="ctl"><label>그래픽 품질</label>
        <div className="seg">{(["low", "medium", "high"] as Quality[]).map((v) => <button key={v} className={q === v ? "on" : ""} onClick={() => set({ quality: v })}>{{ low: "낮음", medium: "보통", high: "높음" }[v]}</button>)}</div></div>
      <p className="hint">낮음: 후처리 끔. 보통: 윤곽·발광. 높음: 윤곽·발광·고해상도. 화면 해상도는 프레임이 떨어지면 자동으로 낮아집니다.</p>
      <table className="kv"><tbody><tr><th>GPU</th><td>{gpu || "확인 중"}</td></tr><tr><th>프레임</th><td>{fps ? `${fps} fps` : "정지 (움직일 때만 그림)"}</td></tr><tr><th>실행 환경</th><td>{desk ? `데스크톱 앱 ${desk.version ?? ""} (${desk.platform ?? ""})` : "웹 브라우저"}</td></tr></tbody></table>
      <p className="note">GPU 가속: WebGL2, 인스턴싱(자석 16개 = 2회, 볼트·베어링 볼 각 1회), 적층 무늬와 냉각수 입자는 셰이더가 계산, 요청 시 렌더(움직임이 없으면 그리지 않음), 고성능 GPU 요청, 적응형 해상도.</p>
      {presets && <><h4>검증 상태 (ORNL 실측 대비)</h4>
        <table className="kv"><tbody><tr><th>물리 모델 효율 편차(주요 영역)</th><td>{fmt(presets.validation.physical_core_mean_error_pp, 1)} %p</td></tr><tr><th>물리 모델, 4000 rpm 이상</th><td>{fmt(presets.validation.physical_high_speed_mean_error_pp, 1)} %p</td></tr><tr><th>경험식 포함, 주요 영역</th><td>{fmt(presets.validation.empirical_core_mean_error_pp, 1)} %p</td></tr></tbody></table>
        <p className="note">{presets.validation.reference}. {presets.validation.g1_status}. 양수는 모델이 측정보다 효율을 높게 예측한다는 뜻입니다. 경험식은 같은 벤치마크에 맞춘 보정이라 기본으로 끄고 쓰세요.</p>
        <p className="note">{presets.motors[0].limits.note}</p></>}
    </div>
  );
}
