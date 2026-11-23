import { useEffect, useRef } from "react";
import { useStore } from "../lib/store";
import { motion } from "../scene/motion";
import { TOUR } from "../scene/tour";
import { goTour, stopTour } from "./actions";

/** 투어 설명 자막. */
export function TourCaption() {
  const step = useStore((s) => s.tourStep), parts = useStore((s) => s.parts);
  if (step < 0) return null;
  const st = TOUR[step], p = parts.find((x) => x.id === st.infoId);
  return (
    <div className="caption">
      <div className="dots">{TOUR.map((t, i) => <i key={t.title} className={i === step ? "on" : ""} onClick={() => goTour(i)} />)}</div>
      <h3>{st.title}</h3><p>{st.blurb}</p>
      {p && st.part !== "전체" && st.part !== "횡단면" && <small>{p.specs.slice(0, 3).map((s) => `${s.label} ${s.value}`).join(" · ")}</small>}
      <button onClick={stopTour}>투어 끝내기</button>
    </div>
  );
}

/** 드라이브 모드: 사이클 시간을 흘려 보내고 속도·회전수·토크·효율 계기를 보여 준다. 시각은 motion.driveT(프레임 정확), 화면 갱신은 15 Hz. */
export function DriveHud() {
  const drive = useStore((s) => s.drive), r = useStore((s) => s.cycle), set = useStore((s) => s.set);
  const last = useRef(0);
  useEffect(() => {
    if (!drive.playing || !r) return;
    let raf = 0, prev = performance.now();
    const tmax = r.series.t_s[r.series.t_s.length - 1];
    const tick = (now: number) => {
      const dt = (now - prev) / 1000; prev = now;
      motion.driveT += dt * useStore.getState().drive.speed;
      if (motion.driveT >= tmax) { motion.driveT = 0; }
      if (now - last.current > 66) { last.current = now; set({ drive: { ...useStore.getState().drive, t: motion.driveT } }); }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick); return () => cancelAnimationFrame(raf);
  }, [drive.playing, r, set]);
  if (!r || !drive.playing) return null;
  const s = r.series, dts = s.t_s[1] - s.t_s[0], i = Math.max(0, Math.min(Math.floor(drive.t / dts), s.t_s.length - 1));
  const eta = s.efficiency[i], tq = s.torque_Nm[i], kw = s.elec_power_kW[i];
  return (
    <div className="hud">
      <div className="gauge"><small>차속</small><b>{s.speed_kmh[i].toFixed(0)}</b><span>km/h</span></div>
      <div className="gauge"><small>모터 회전</small><b>{s.motor_rpm[i].toFixed(0)}</b><span>rpm</span></div>
      <div className={`gauge ${tq < 0 ? "regen" : ""}`}><small>{tq < 0 ? "회생 토크" : "구동 토크"}</small><b>{Math.abs(tq).toFixed(0)}</b><span>N·m</span></div>
      <div className={`gauge ${kw < 0 ? "regen" : ""}`}><small>전기 동력</small><b>{kw.toFixed(1)}</b><span>kW</span></div>
      <div className="gauge"><small>모터 효율</small><b>{eta === null ? "—" : (eta * 100).toFixed(0)}</b><span>%</span></div>
      <div className="gauge"><small>시간</small><b>{drive.t.toFixed(0)}</b><span>s</span></div>
    </div>
  );
}

export function StatusBar() {
  const status = useStore((s) => s.status), sel = useStore((s) => s.selected), parts = useStore((s) => s.parts), fps = useStore((s) => s.fps), hov = useStore((s) => s.hovered);
  const nm = (id: string | null) => parts.find((p) => p.id === id)?.name;
  return <footer className="status"><span>{status}</span><span className="grow" /><span>{hov ? `가리킴: ${nm(hov)}` : sel ? `선택: ${nm(sel)}` : "부품을 눌러 보세요"}</span><span>{fps ? `${fps} fps` : "대기"}</span></footer>;
}
