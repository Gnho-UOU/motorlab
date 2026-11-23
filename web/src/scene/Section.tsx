import { useMemo } from "react";
import * as THREE from "three";
import type { Geometry } from "../lib/api";
import { useStore } from "../lib/store";
import { renderFluxCanvas } from "../lib/fluxCanvas";
import { COL } from "./materials";
import { magnetPolys, mergeAll, ring, rotorShape, slotPolys, statorShape } from "./geo";
import { Spin } from "./Part";
import { HUB_R } from "./parts";

const flat = (color: number, extra: Partial<THREE.MeshStandardMaterialParameters> = {}) => new THREE.MeshStandardMaterial({ color, metalness: 0.5, roughness: 0.5, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, ...extra });

/** 횡단면: 절단 평면(z = zc)에 부품 단면을 색으로 채워 그린다. 닫힌 입체를 자르면 속이 비어 보이므로 단면을 직접 그려 메운다.
 *  절단 위치를 바꿀 수 있다(적층 안쪽에서는 단면 모양이 같다). 분해 상태와는 함께 쓰지 않는다. */
export function SectionFaces({ geo }: { geo: Geometry }) {
  const view = useStore((s) => s.view), frac = useStore((s) => s.sectionZ), showFlux = useStore((s) => s.showFlux);
  const flux = useStore((s) => s.flux), fluxMode = useStore((s) => s.fluxMode);
  const L = geo.stack_length_mm, z = Math.min(Math.max(frac, 0), 1) * L - 0.4;       // 절단 평면보다 살짝 안쪽(남는 쪽)에 둬야 평면에 잘려 나가지 않는다
  const Ri = geo.stator.outer_radius_mm + 0.8, Ro = geo.housing.diameter_mm / 2;
  const faces = useMemo(() => {
    const slots = slotPolys(geo), byPhase: Record<string, THREE.BufferGeometry[]> = { A: [], B: [], C: [] };
    slots.forEach((p, k) => { const c = p.reduce((a, q) => a.add(q), new THREE.Vector2()).divideScalar(p.length); byPhase[geo.winding.slot_layout[k][0]].push(new THREE.ShapeGeometry(new THREE.Shape(p.map((q) => q.clone().sub(c).multiplyScalar(0.8).add(c))), 16)); });
    const mags: THREE.BufferGeometry[][] = [[], []];
    for (const arm of [0, 1]) magnetPolys(geo, arm).forEach((p, j) => mags[j % 2].push(new THREE.ShapeGeometry(new THREE.Shape(p))));
    const ribs: THREE.BufferGeometry[] = [];
    for (let i = 0; i < 12; i++) { const g = new THREE.PlaneGeometry(Ro - 5 - (Ri + 3), 3); g.translate((Ro - 5 + Ri + 3) / 2, 0, 0); g.rotateZ((i / 12) * Math.PI * 2); ribs.push(g); }
    return {
      stator: new THREE.ShapeGeometry(statorShape(geo), 48), rotor: new THREE.ShapeGeometry(rotorShape(geo, HUB_R), 48), hub: new THREE.ShapeGeometry(ring(0.1, HUB_R), 48),
      A: mergeAll(byPhase.A), B: mergeAll(byPhase.B), C: mergeAll(byPhase.C), magN: mergeAll(mags[0]), magS: mergeAll(mags[1]),
      wallIn: new THREE.ShapeGeometry(ring(Ri, Ri + 3), 96), wallOut: new THREE.ShapeGeometry(ring(Ro - 3, Ro), 96), water: new THREE.ShapeGeometry(ring(Ri + 3, Ro - 3), 96), ribs: mergeAll(ribs),
    };
  }, [geo, Ri, Ro]);
  const m = useMemo(() => ({ steelS: flat(0x9aa0a8), steelR: flat(0xb0b6bf), cu: flat(0xc47a42, { metalness: 0.8, roughness: 0.3 }), A: flat(COL.phaseA), B: flat(COL.phaseB), C: flat(COL.phaseC),
    N: flat(COL.magnetN), S: flat(COL.magnetS), alu: flat(COL.alu), water: flat(COL.water, { transparent: true, opacity: 0.5, metalness: 0, roughness: 0.2 }), hub: flat(0x7d838b) }), []);
  const tex = useMemo(() => {
    if (!flux) return null;
    const t = new THREE.CanvasTexture(renderFluxCanvas(flux, fluxMode, 1024)); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
  }, [flux, fluxMode]);
  if (view !== "section") return null;
  const R = flux ? flux.half_size_mm : geo.stator.outer_radius_mm;
  return (
    <group position={[0, 0, z]}>
      <mesh geometry={faces.stator} material={m.steelS} />
      <mesh geometry={faces.A} material={m.A} position={[0, 0, 0.06]} /><mesh geometry={faces.B} material={m.B} position={[0, 0, 0.06]} /><mesh geometry={faces.C} material={m.C} position={[0, 0, 0.06]} />
      <Spin>
        <mesh geometry={faces.rotor} material={m.steelR} />
        <mesh geometry={faces.magN} material={m.N} position={[0, 0, 0.06]} /><mesh geometry={faces.magS} material={m.S} position={[0, 0, 0.06]} />
        <mesh geometry={faces.hub} material={m.hub} />
        {showFlux && tex && <mesh position={[0, 0, 0.2]} renderOrder={5}><planeGeometry args={[2 * R, 2 * R]} /><meshBasicMaterial map={tex} transparent depthWrite={false} toneMapped={false} /></mesh>}
      </Spin>
      <mesh geometry={faces.wallIn} material={m.alu} /><mesh geometry={faces.wallOut} material={m.alu} /><mesh geometry={faces.water} material={m.water} /><mesh geometry={faces.ribs} material={m.alu} position={[0, 0, 0.06]} />
    </group>
  );
}
