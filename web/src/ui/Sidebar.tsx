import { useStore } from "../lib/store";
import { TOUR } from "../scene/tour";
import { goTour, loadFlux, selectPart } from "./actions";

const ICON: Record<string, string> = { housing: "▣", stator_core: "◍", windings: "≋", rotor_core: "◉", magnets: "▰", shaft: "━", terminal: "⚡", resolver: "◔", bearings: "◎" };

export function Sidebar() {
  const parts = useStore((s) => s.parts), selected = useStore((s) => s.selected), hidden = useStore((s) => s.hidden), set = useStore((s) => s.set), step = useStore((s) => s.tourStep);
  const coolant = useStore((s) => s.showCoolant), glow = useStore((s) => s.showWindingGlow), flux = useStore((s) => s.showFlux), view = useStore((s) => s.view), hasFlux = useStore((s) => !!s.flux);
  return (
    <aside className="sidebar">
      <h3>부품</h3>
      <ul className="parts">
        {parts.map((p) => (
          <li key={p.id} className={selected === p.id ? "on" : ""} onClick={() => selectPart(p.id)} onMouseEnter={() => set({ hovered: p.id })} onMouseLeave={() => set({ hovered: null })}>
            <span className="ico">{ICON[p.id] ?? "◇"}</span><span className="nm">{p.name.replace(/ \(.*\)$/, "")}</span>
            {!p.dimensions_sourced && <em title="치수 출처가 없는 도식 형상">도식</em>}
            <button className="eye" title="숨기기/보이기" onClick={(e) => { e.stopPropagation(); set({ hidden: { ...hidden, [p.id]: !hidden[p.id] } }); }}>{hidden[p.id] ? "◌" : "●"}</button>
          </li>
        ))}
      </ul>
      <h3>레이어</h3>
      <label className="chk"><input type="checkbox" checked={glow} onChange={(e) => set({ showWindingGlow: e.target.checked })} />3상 전류 발광</label>
      <label className="chk"><input type="checkbox" checked={coolant} onChange={(e) => set({ showCoolant: e.target.checked })} />냉각수 흐름</label>
      <label className="chk"><input type="checkbox" checked={flux} onChange={(e) => { set({ showFlux: e.target.checked }); if (e.target.checked) { if (!hasFlux) void loadFlux(useStore.getState().fluxState); if (view !== "section") set({ view: "section", explodeTarget: 0 }); } }} />FEA 자속 분포(단면)</label>
      <h3>해부 투어</h3>
      <ol className="tour">{TOUR.map((t, i) => <li key={t.title} className={step === i ? "on" : ""} onClick={() => goTour(i)}>{t.title}</li>)}</ol>
    </aside>
  );
}
