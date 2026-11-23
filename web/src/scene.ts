import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { Geometry, Pt } from "./api";

/** 서버가 준 단면 윤곽(mm)으로 고정자·권선·회전자·자석을 압출해 그린다. 수치 계산은 하지 않고 회전·배치만 한다. */
export interface MotorView { setCutaway(on: boolean): void; setSpin(on: boolean): void; dispose(): void }

const rot = (p: Pt, a: number): THREE.Vector2 => new THREE.Vector2(p[0] * Math.cos(a) - p[1] * Math.sin(a), p[0] * Math.sin(a) + p[1] * Math.cos(a));
const polyPath = (pts: THREE.Vector2[], path: THREE.Path) => { path.moveTo(pts[0].x, pts[0].y); for (const p of pts.slice(1)) path.lineTo(p.x, p.y); path.closePath(); return path; };

export function buildMotor(canvas: HTMLCanvasElement, g: Geometry): MotorView {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.localClippingEnabled = true;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xeeedea);
  const camera = new THREE.PerspectiveCamera(38, 1, 1, 3000);
  camera.position.set(240, -330, 430);
  camera.up.set(0, 0, 1);
  const controls = new OrbitControls(camera, canvas);
  controls.target.set(0, 0, g.stack_length_mm / 2);
  controls.enableDamping = true;
  scene.add(new THREE.AmbientLight(0xffffff, 0.75));
  const sun = new THREE.DirectionalLight(0xffffff, 1.4); sun.position.set(300, -200, 500); scene.add(sun);

  const L = g.stack_length_mm;
  const clip = new THREE.Plane(new THREE.Vector3(0, 0, -1), L / 2);
  const mats: THREE.MeshStandardMaterial[] = [];
  const mat = (color: number, metal = 0.35, rough = 0.55) => { const m = new THREE.MeshStandardMaterial({ color, metalness: metal, roughness: rough, side: THREE.DoubleSide }); mats.push(m); return m; };
  const steel = mat(0x8c9097), copper = mat(0xb86a35, 0.6, 0.4), rotorSteel = mat(0x9aa0a8), magN = mat(0xc4503a, 0.5, 0.4), magS = mat(0x3f6fb5, 0.5, 0.4), shaftM = mat(0x6d7279);
  const extrude = (shape: THREE.Shape, depth: number, m: THREE.Material, z0 = 0) => {
    const geo = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: false, curveSegments: 48 });
    const mesh = new THREE.Mesh(geo, m); mesh.position.z = z0; return mesh;
  };

  // 고정자: 바깥 원 − (보어 + 슬롯 윤곽을 따라 도는 구멍)
  const pitch = (2 * Math.PI) / g.slots, off = (g.stator.slot_angle_offset_deg * Math.PI) / 180;
  const stator = new THREE.Shape(); stator.absarc(0, 0, g.stator.outer_radius_mm, 0, 2 * Math.PI, false);
  const bore: THREE.Vector2[] = [];
  const slotAt = (k: number) => g.stator.slot_outline_mm.map((p) => rot(p, off + k * pitch));
  for (let k = 0; k < g.slots; k++) {
    const cur = slotAt(k), prev = slotAt((k + g.slots - 1) % g.slots);
    const a0 = Math.atan2(prev[prev.length - 1].y, prev[prev.length - 1].x), a1 = Math.atan2(cur[0].y, cur[0].x);
    let d = a1 - a0; while (d < 0) d += 2 * Math.PI;
    for (let s = 1; s < 4; s++) { const a = a0 + (d * s) / 4; bore.push(new THREE.Vector2(g.stator.bore_radius_mm * Math.cos(a), g.stator.bore_radius_mm * Math.sin(a))); }
    bore.push(...cur);
  }
  stator.holes.push(polyPath(bore, new THREE.Path()));
  const statorMesh = extrude(stator, L, steel); scene.add(statorMesh);
  for (let k = 0; k < g.slots; k++) {
    const sh = new THREE.Shape(slotAt(k)); const m = extrude(sh, L, copper); m.scale.set(0.97, 0.97, 1); scene.add(m);
  }

  // 회전자: 원판 − 자석 구멍, 자석은 극마다 N/S 색으로
  const ppitch = (2 * Math.PI) / g.poles, poff = (g.rotor.pole_angle_offset_deg * Math.PI) / 180;
  const rotorGroup = new THREE.Group(); scene.add(rotorGroup);
  const disc = new THREE.Shape(); disc.absarc(0, 0, g.rotor.outer_radius_mm, 0, 2 * Math.PI, false);
  const hub = new THREE.Path(); hub.absarc(0, 0, g.rotor.inner_radius_mm, 0, 2 * Math.PI, true); disc.holes.push(hub);
  for (let j = 0; j < g.poles; j++) for (const arm of g.rotor.magnets_mm) disc.holes.push(polyPath(arm.map((p) => rot(p, poff + j * ppitch)), new THREE.Path()));
  rotorGroup.add(extrude(disc, L, rotorSteel));
  for (let j = 0; j < g.poles; j++) for (const arm of g.rotor.magnets_mm) rotorGroup.add(extrude(new THREE.Shape(arm.map((p) => rot(p, poff + j * ppitch))), L, j % 2 ? magS : magN));
  const shaft = new THREE.Mesh(new THREE.CylinderGeometry(g.rotor.inner_radius_mm, g.rotor.inner_radius_mm, L + 60, 48), shaftM);
  shaft.rotation.x = Math.PI / 2; shaft.position.z = L / 2; rotorGroup.add(shaft);

  const floor = new THREE.Mesh(new THREE.CircleGeometry(520, 64), new THREE.MeshBasicMaterial({ color: 0xe4e2dd }));
  floor.position.z = -2; scene.add(floor);

  let spin = false, raf = 0;
  const resize = () => { const w = innerWidth, h = innerHeight; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); };
  addEventListener("resize", resize); resize();
  const loop = () => { raf = requestAnimationFrame(loop); if (spin) rotorGroup.rotation.z += 0.01; controls.update(); renderer.render(scene, camera); };
  loop();
  return {
    setCutaway(on) { for (const m of mats) m.clippingPlanes = on ? [clip] : []; },
    setSpin(on) { spin = on; },
    dispose() { cancelAnimationFrame(raf); removeEventListener("resize", resize); renderer.dispose(); },
  };
}
