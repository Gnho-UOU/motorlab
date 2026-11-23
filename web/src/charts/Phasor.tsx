/** dq 전류 평면: 전류 한계 원 안에서 운전점의 (id, iq)와 전류각을 보여 준다. */
export function DqPlane({ id, iq, imax, beta }: { id: number; iq: number; imax: number; beta: number }) {
  const S = 210, pad = 26, k = (S - 2 * pad) / imax, x = (i: number) => pad + (i + imax) * k, y = (q: number) => S - pad - q * k;
  const arc = `M ${x(-imax)} ${y(0)} A ${imax * k} ${imax * k} 0 0 1 ${x(0)} ${y(imax)}`;
  return (
    <svg viewBox={`0 0 ${S} ${S}`} width="100%" style={{ maxWidth: 260 }}>
      <rect x={pad} y={pad} width={imax * k} height={imax * k} fill="#0f1216" stroke="#262b33" />
      <path d={arc} fill="none" stroke="#e5645a" strokeWidth={1.5} strokeDasharray="4 3" />
      <line x1={x(0)} y1={y(0)} x2={x(id)} y2={y(iq)} stroke="#ff7a3d" strokeWidth={2.2} />
      <circle cx={x(id)} cy={y(iq)} r={5} fill="#ff7a3d" stroke="#fff" />
      <path d={`M ${x(0)} ${y(30)} A ${30 * k} ${30 * k} 0 0 0 ${x(-30 * Math.sin((beta * Math.PI) / 180))} ${y(30 * Math.cos((beta * Math.PI) / 180))}`} fill="none" stroke="#4cc9f0" />
      <text x={x(-imax) + 2} y={S - 8} fill="#8d96a3" fontSize="10">id [A]</text>
      <text x={x(0) + 6} y={pad + 8} fill="#8d96a3" fontSize="10">iq [A]</text>
      <text x={x(0) - 70} y={y(0) - 5} fill="#4cc9f0" fontSize="10">β {beta.toFixed(0)}°</text>
      <text x={pad + 4} y={pad + 12} fill="#e5645a" fontSize="10">전류 한계 {imax} A</text>
    </svg>
  );
}
