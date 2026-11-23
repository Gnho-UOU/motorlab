import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import type { Geometry, Pt } from "../lib/api";

export const rot = (p: Pt, a: number): THREE.Vector2 => new THREE.Vector2(p[0] * Math.cos(a) - p[1] * Math.sin(a), p[0] * Math.sin(a) + p[1] * Math.cos(a));
export const polyPath = (pts: THREE.Vector2[]): THREE.Path => { const p = new THREE.Path(); p.moveTo(pts[0].x, pts[0].y); for (const q of pts.slice(1)) p.lineTo(q.x, q.y); p.closePath(); return p; };
export const DEG = Math.PI / 180;

export function extrude(shape: THREE.Shape, depth: number, seg = 48): THREE.BufferGeometry {
  const g = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: false, curveSegments: seg });
  g.computeVertexNormals(); return g;
}

export function slotPolys(g: Geometry): THREE.Vector2[][] {
  const pitch = (2 * Math.PI) / g.slots, off = g.stator.slot_angle_offset_deg * DEG;
  return Array.from({ length: g.slots }, (_, k) => g.stator.slot_outline_mm.map((p) => rot(p, off + k * pitch)));
}

/** 고정자 단면: 바깥 원 − (보어 + 슬롯 윤곽을 따라 도는 구멍). */
export function statorShape(g: Geometry): THREE.Shape {
  const s = new THREE.Shape(); s.absarc(0, 0, g.stator.outer_radius_mm, 0, 2 * Math.PI, false);
  const slots = slotPolys(g), bore: THREE.Vector2[] = [];
  for (let k = 0; k < g.slots; k++) {
    const cur = slots[k], prev = slots[(k + g.slots - 1) % g.slots];
    const a0 = Math.atan2(prev[prev.length - 1].y, prev[prev.length - 1].x), a1 = Math.atan2(cur[0].y, cur[0].x);
    let d = a1 - a0; while (d < 0) d += 2 * Math.PI;
    for (let i = 1; i < 4; i++) { const a = a0 + (d * i) / 4; bore.push(new THREE.Vector2(g.stator.bore_radius_mm * Math.cos(a), g.stator.bore_radius_mm * Math.sin(a))); }
    bore.push(...cur);
  }
  s.holes.push(polyPath(bore)); return s;
}

export function magnetPolys(g: Geometry, arm: number): THREE.Vector2[][] {
  const pp = (2 * Math.PI) / g.poles, off = g.rotor.pole_angle_offset_deg * DEG;
  return Array.from({ length: g.poles }, (_, j) => g.rotor.magnets_mm[arm].map((p) => rot(p, off + j * pp)));
}

/** 회전자 단면: 바깥 원 − 자석 구멍 − 축 구멍(허브 안쪽). */
export function rotorShape(g: Geometry, hubR: number): THREE.Shape {
  const s = new THREE.Shape(); s.absarc(0, 0, g.rotor.outer_radius_mm, 0, 2 * Math.PI, false);
  const hub = new THREE.Path(); hub.absarc(0, 0, hubR, 0, 2 * Math.PI, true); s.holes.push(hub);
  for (const arm of [0, 1]) for (const poly of magnetPolys(g, arm)) s.holes.push(polyPath(poly));
  return s;
}

export function ring(rIn: number, rOut: number): THREE.Shape {
  const s = new THREE.Shape(); s.absarc(0, 0, rOut, 0, 2 * Math.PI, false);
  const h = new THREE.Path(); h.absarc(0, 0, rIn, 0, 2 * Math.PI, true); s.holes.push(h); return s;
}

/** (r, z) 단면 다각형을 축(z) 둘레로 돌려 속이 찬 회전체를 만든다. */
export function lathe(profile: [number, number][], seg = 96): THREE.BufferGeometry {
  const g = new THREE.LatheGeometry(profile.map(([r, z]) => new THREE.Vector2(r, z)), seg);
  g.rotateX(Math.PI / 2); g.computeVertexNormals(); return g;      // Y(회전축) → Z
}

export interface EndTurns { A: THREE.BufferGeometry; B: THREE.BufferGeometry; C: THREE.BufferGeometry }

/** 엔드턴(코일 머리): 코일 k는 슬롯 k에서 슬롯 k+피치로 건너간다. 돌출 높이는 코일마다 단계를 달리해 서로 겹치지 않게 한다.
 *  최대 돌출은 출처 값(TM-2004/137, 한쪽 약 38.1 mm)이고 곡선 모양은 도식이다. */
export function endTurns(g: Geometry, tubeR = 3.1): EndTurns {
  const L = g.stack_length_mm, ext = g.winding.end_winding_extension_mm, pitchSlots = g.winding.coil_pitch_slots;
  const slots = slotPolys(g);
  const rc = slots.map((p) => { const c = p.reduce((a, q) => a.add(q), new THREE.Vector2()).divideScalar(p.length); return { r: c.length(), a: Math.atan2(c.y, c.x) }; });
  const buckets: Record<string, THREE.BufferGeometry[]> = { A: [], B: [], C: [] };
  for (let k = 0; k < g.slots; k++) {
    if (k % (2 * pitchSlots) >= pitchSlots) continue;                       // 12칸마다 앞 6칸이 코일의 시작 변
    const ph = g.winding.slot_layout[k][0], level = k % pitchSlots, h = ext * (0.38 + 0.62 * (level / (pitchSlots - 1)));
    for (const side of [1, -1]) {
      const z0 = side > 0 ? L : 0, pts: THREE.Vector3[] = [];
      for (let i = 0; i <= 16; i++) {
        const t = i / 16, a = rc[k].a + t * pitchSlots * ((2 * Math.PI) / g.slots), bump = Math.pow(Math.sin(Math.PI * t), 0.75);
        const r = rc[k].r + 6 * Math.sin(Math.PI * t);
        pts.push(new THREE.Vector3(r * Math.cos(a), r * Math.sin(a), z0 + side * h * bump));
      }
      buckets[ph].push(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 40, tubeR, 8, false));
    }
  }
  const m = (k: string) => mergeGeometries(buckets[k], false)!;
  return { A: m("A"), B: m("B"), C: m("C") };
}

export function mergeAll(gs: THREE.BufferGeometry[]): THREE.BufferGeometry { return mergeGeometries(gs, false)!; }
