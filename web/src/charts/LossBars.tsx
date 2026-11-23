import type { OperatingPoint } from "../lib/api";

/** 손실 분해: 입력 전력이 어디로 가는가 (샤프트 출력, 동손, 철손, 기계손, 잔여). */
export function LossBars({ op }: { op: OperatingPoint }) {
  const p = op.power_W!, all = [["샤프트 출력", p.shaft_out, "#5ccf8f"], ["구리(동손)", p.copper, "#d98d55"], ["철심", p.iron, "#9a7be0"], ["무부하 실측(철심+기계)", p.mechanical, "#4cc9f0"], ["잔여(보정)", p.excess, "#e0b341"]] as const;
  const items = all.filter(([, v]) => v > 0);          // 물리 모델은 철손을 따로 두지 않고(무부하 실측에 포함) 잔여는 경험식을 켰을 때만 있다
  const tot = p.input || 1;
  return (
    <div>
      <div style={{ display: "flex", height: 16, borderRadius: 5, overflow: "hidden", background: "#0f1216" }}>
        {items.map(([n, v, c]) => <div key={n} title={`${n} ${v.toFixed(0)} W`} style={{ width: `${(v / tot) * 100}%`, background: c }} />)}
      </div>
      <div className="legend">{items.map(([n, v, c]) => <span key={n}><i style={{ background: c }} />{n} <b>{v < 1000 ? `${v.toFixed(0)} W` : `${(v / 1000).toFixed(2)} kW`}</b> <small>{((v / tot) * 100).toFixed(1)}%</small></span>)}</div>
    </div>
  );
}
