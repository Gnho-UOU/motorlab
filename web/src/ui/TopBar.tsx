import { useStore } from "../lib/store";
import { goTour, playTour, pauseTour, setView, stopTour } from "./actions";

const Logo = () => (
  <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden><circle cx="16" cy="16" r="14" fill="none" stroke="#d98d55" strokeWidth="2" /><circle cx="16" cy="16" r="9" fill="none" stroke="#4cc9f0" strokeWidth="1.4" />
    {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => <rect key={i} x="15" y="3.5" width="2" height="5" rx="1" fill="#d98d55" transform={`rotate(${i * 45} 16 16)`} />)}<circle cx="16" cy="16" r="3" fill="#e9ecf1" /></svg>
);

export function TopBar() {
  const view = useStore((s) => s.view), step = useStore((s) => s.tourStep), playing = useStore((s) => s.tourPlaying), explode = useStore((s) => s.explodeTarget);
  const set = useStore((s) => s.set), xray = useStore((s) => s.xray);
  return (
    <header className="topbar">
      <div className="brand"><Logo /><b>MOTOR LAB</b><span>Toyota Prius 2004 · MG2 IPMSM 8극 48슬롯</span></div>
      <div className="seg" role="tablist">
        {([["assembled", "외관"], ["section", "단면"], ["exploded", "해부"]] as const).map(([v, n]) => <button key={v} className={view === v ? "on" : ""} onClick={() => { setView(v); }}>{n}</button>)}
      </div>
      {view === "exploded" && <label className="slider"><span>분해</span><input type="range" min={0} max={1} step={0.01} value={explode} onChange={(e) => set({ explodeTarget: +e.target.value })} /></label>}
      <label className="chk"><input type="checkbox" checked={xray} onChange={(e) => set({ xray: e.target.checked })} />X-ray</label>
      <div className="grow" />
      <div className="tourctl">
        {step < 0 ? <button className="primary" onClick={playTour}>▶ 해부 투어</button> : (
          <>
            <button onClick={() => goTour(step - 1)} disabled={step === 0}>◀</button>
            <button className="primary" onClick={playing ? pauseTour : playTour}>{playing ? "❚❚ 일시정지" : "▶ 이어서"}</button>
            <button onClick={() => goTour(step + 1)}>▶</button><button onClick={stopTour}>✕</button>
          </>)}
      </div>
    </header>
  );
}
