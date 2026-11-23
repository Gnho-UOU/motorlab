import { useFrame } from "@react-three/fiber";
import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { Geometry } from "../lib/api";
import { useStore } from "../lib/store";
import { COL, cast, copperMat, enamel, metal, plastic, steel } from "./materials";
import { DEG, endTurns, extrude, lathe, magnetPolys, mergeAll, ring, rot, rotorShape, slotPolys, statorShape } from "./geo";
import { motion } from "./motion";
import { Part, Spin } from "./Part";

/** 모터 좌표(mm): 축 = z, 고정자 적층은 z = 0 ~ L. 치수 출처가 있는 값은 주석에 적었고, 없는 것은 "도식"이라고 적었다. */
export const FRONT_Z = 136, REAR_Z = -52, SHIELD_T = 8.5;     // 하우징 몸통 z 범위(케이스 길이 205 mm = 몸통 188 + 앞뒤 덮개 8.5 + 8.5)
export const HUB_R = 55.32;                                    // 회전자 철심 안쪽 = 축 반지름 50.46 + 링 (TM-2004/217 RadSH)

function Bolts({ z, r, n, mat, dir = 1 }: { z: number; r: number; n: number; mat: THREE.Material; dir?: number }) {
  const ref = useRef<THREE.InstancedMesh>(null);
  const geo = useMemo(() => { const g = new THREE.CylinderGeometry(5.2, 5.2, 6, 6); g.rotateX(Math.PI / 2); return g; }, []);
  useLayoutEffect(() => {
    const m = ref.current!, o = new THREE.Object3D();
    for (let i = 0; i < n; i++) { const a = (i / n) * Math.PI * 2 + Math.PI / n; o.position.set(r * Math.cos(a), r * Math.sin(a), z + dir * 3); o.rotation.set(0, 0, a); o.updateMatrix(); m.setMatrixAt(i, o.matrix); }
    m.instanceMatrix.needsUpdate = true;
  }, [n, r, z, dir]);
  return <instancedMesh ref={ref} args={[geo, mat, n]} />;
}

export function Housing({ geo }: { geo: Geometry }) {
  const Ri = geo.stator.outer_radius_mm + 0.8, Ro = geo.housing.diameter_mm / 2, Rf = 158, zs = REAR_Z, ze = FRONT_Z;
  const body = useMemo(() => lathe([[Ri, zs], [Rf, zs], [Rf, zs + 11], [Ro, zs + 11], [Ro, zs + 38], [Ro - 4, zs + 38], [Ro - 4, zs + 52], [Ro, zs + 52],
    [Ro, ze - 52], [Ro - 4, ze - 52], [Ro - 4, ze - 38], [Ro, ze - 38], [Ro, ze - 11], [Rf, ze - 11], [Rf, ze], [Ri, ze], [Ri, zs]], 160), [Ri, Ro, zs, ze]);
  const mat = useMemo(() => cast(COL.alu), []), boltMat = useMemo(() => metal(COL.bolt, 0.5), []), hose = useMemo(() => plastic(0x1e5a7a, 0.5), []);
  return (
    <Part id="housing" info="housing">
      <mesh geometry={body} material={mat} />
      <Bolts z={zs + 11} r={153.5} n={12} mat={boltMat} />
      <Bolts z={ze - 11 - 6} r={153.5} n={12} mat={boltMat} />
      {[8, 108].map((z) => (
        <group key={z} position={[Ro + 2, 0, z]} rotation={[0, 0, -Math.PI / 2]}>
          <mesh material={mat} position={[0, 12, 0]}><cylinderGeometry args={[11, 13, 24, 40]} /></mesh>
          <mesh material={hose} position={[0, 28, 0]}><cylinderGeometry args={[13, 13, 12, 40]} /></mesh>
        </group>
      ))}
      <mesh material={mat} position={[-Ro - 8, 0, 60]} rotation={[0, 0, Math.PI / 2]}><cylinderGeometry args={[9, 10, 18, 32]} /></mesh>
    </Part>
  );
}

function Shield({ id, front, geo }: { id: string; front: boolean; geo: Geometry }) {
  const Rf = 158, zEdge = front ? FRONT_Z : REAR_Z, s = front ? 1 : -1;
  const body = useMemo(() => {
    const plate: [number, number][] = front
      ? [[62, zEdge], [Rf, zEdge], [Rf, zEdge + SHIELD_T], [62, zEdge + SHIELD_T], [62, zEdge - 18], [74, zEdge - 18], [74, zEdge], [62, zEdge]]
      : [[0, zEdge], [Rf, zEdge], [Rf, zEdge - SHIELD_T], [0, zEdge - SHIELD_T], [0, zEdge - 18], [74, zEdge - 18], [74, zEdge], [0, zEdge]];
    return lathe(plate, 160);
  }, [front, zEdge]);
  const mat = useMemo(() => cast(front ? COL.alu : COL.aluDark), [front]), boltMat = useMemo(() => metal(COL.bolt, 0.5), []);
  void geo;
  return (
    <Part id={id} info="housing">
      <mesh geometry={body} material={mat} />
      <Bolts z={zEdge + (front ? SHIELD_T - 6 : -SHIELD_T)} r={153.5} n={12} mat={boltMat} dir={s} />
    </Part>
  );
}
export const ShieldFront = (p: { geo: Geometry }) => <Shield id="shield_front" front geo={p.geo} />;
export const ShieldRear = (p: { geo: Geometry }) => <Shield id="shield_rear" front={false} geo={p.geo} />;

/** 3상 단자부: 치수 출처가 없어 도식이다. */
export function Terminal({ geo }: { geo: Geometry }) {
  const Ro = geo.housing.diameter_mm / 2, section = useStore((s) => s.view) === "section";   // 단면에서는 잘린 빈 상자가 보기 흉해 숨긴다
  const box = useMemo(() => plastic(COL.terminal, 0.55), []), lid = useMemo(() => plastic(0x3a3f46, 0.45), []);
  const boots = useMemo(() => [COL.phaseA, COL.phaseB, COL.phaseC].map((c) => plastic(c, 0.4)), []), cu = useMemo(() => copperMat(), []);
  return (
    <Part id="terminal" info="terminal">
      <group position={[0, Ro + 20, 52]} visible={!section}>
        <mesh material={box}><boxGeometry args={[84, 40, 118]} /></mesh>
        <mesh material={lid} position={[0, 22, 0]}><boxGeometry args={[88, 5, 122]} /></mesh>
        {[-34, 0, 34].map((z, i) => (
          <group key={z} position={[0, 22, z]}>
            <mesh material={boots[i]} position={[0, 10, 0]}><cylinderGeometry args={[11, 12, 20, 32]} /></mesh>
            <mesh material={cu} position={[0, 24, 0]}><cylinderGeometry args={[5, 5, 12, 24]} /></mesh>
          </group>
        ))}
      </group>
    </Part>
  );
}

export function StatorCore({ geo }: { geo: Geometry }) {
  const g = useMemo(() => extrude(statorShape(geo), geo.stack_length_mm, 64), [geo]);
  const mat = useMemo(() => steel(COL.steelStator), []);
  return <Part id="stator_core" info="stator_core"><mesh geometry={g} material={mat} /></Part>;
}

const PHASE_COL = { A: COL.phaseA, B: COL.phaseB, C: COL.phaseC } as const;

export function Windings({ geo }: { geo: Geometry }) {
  const L = geo.stack_length_mm;
  const et = useMemo(() => endTurns(geo), [geo]);
  const inSlot = useMemo(() => {
    const slots = slotPolys(geo), out: Record<string, THREE.BufferGeometry[]> = { A: [], B: [], C: [] };
    slots.forEach((p, k) => {
      const c = p.reduce((a, q) => a.add(q), new THREE.Vector2()).divideScalar(p.length);
      const shape = new THREE.Shape(p.map((q) => q.clone().sub(c).multiplyScalar(0.8).add(c)));
      out[geo.winding.slot_layout[k][0]].push(extrude(shape, L, 24));
    });
    return { A: mergeAll(out.A), B: mergeAll(out.B), C: mergeAll(out.C) };
  }, [geo, L]);
  const cu = useMemo(() => copperMat(), []);
  const sleeve = useMemo(() => ({ A: enamel(PHASE_COL.A), B: enamel(PHASE_COL.B), C: enamel(PHASE_COL.C) }), []);
  useFrame(() => { (["A", "B", "C"] as const).forEach((k, i) => { sleeve[k].emissiveIntensity = Math.abs(motion.glow[i]) * 1.6; }); }, 1);
  return (
    <Part id="windings" info="windings">
      {(["A", "B", "C"] as const).map((k) => (
        <group key={k}>
          <mesh geometry={inSlot[k]} material={cu} />
          <mesh geometry={et[k]} material={sleeve[k]} />
        </group>
      ))}
    </Part>
  );
}

export function RotorCore({ geo }: { geo: Geometry }) {
  const L = geo.stack_length_mm;
  const core = useMemo(() => extrude(rotorShape(geo, HUB_R), L, 64), [geo, L]);
  const plate = useMemo(() => extrude(ring(HUB_R, geo.rotor.outer_radius_mm - 2), 3.5, 48), [geo]);
  const mat = useMemo(() => steel(COL.steelRotor), []), pm = useMemo(() => metal(0x6a7078, 0.45), []);
  return (
    <Part id="rotor_core" info="rotor_core">
      <Spin>
        <mesh geometry={core} material={mat} />
        <mesh geometry={plate} material={pm} position={[0, 0, -3.5]} />
        <mesh geometry={plate} material={pm} position={[0, 0, L]} />
      </Spin>
    </Part>
  );
}

/** 자석 16개 = V자 한 극의 두 장 × 8극. 인스턴싱으로 두 번의 그리기 호출(draw call)에 끝낸다. 극성 색은 N 붉은색, S 푸른색(교육용). */
export function Magnets({ geo }: { geo: Geometry }) {
  const polarity = true;
  const L = geo.stack_length_mm, len = 83.1;
  const refs = [useRef<THREE.InstancedMesh>(null), useRef<THREE.InstancedMesh>(null)];
  const geos = useMemo(() => [0, 1].map((arm) => { const p = magnetPolys(geo, arm)[0].map((q) => rot([q.x, q.y], -geo.rotor.pole_angle_offset_deg * DEG)); return extrude(new THREE.Shape(p), len, 8); }), [geo]);
  const mat = useMemo(() => metal(0xffffff, 0.35, 0.6), []);
  useLayoutEffect(() => {
    const pp = (2 * Math.PI) / geo.poles, off = geo.rotor.pole_angle_offset_deg * DEG, o = new THREE.Object3D(), cN = new THREE.Color(COL.magnetN), cS = new THREE.Color(COL.magnetS), raw = new THREE.Color(COL.magnetRaw);
    refs.forEach((r) => {
      const m = r.current!;
      for (let j = 0; j < geo.poles; j++) { o.position.set(0, 0, (L - len) / 2); o.rotation.set(0, 0, off + j * pp); o.updateMatrix(); m.setMatrixAt(j, o.matrix); m.setColorAt(j, polarity ? (j % 2 ? cS : cN) : raw); }
      m.instanceMatrix.needsUpdate = true; if (m.instanceColor) m.instanceColor.needsUpdate = true;
    });
  }, [geo, L, polarity]);
  return (
    <Part id="magnets" info="magnets">
      <Spin>{geos.map((g, i) => <instancedMesh key={i} ref={refs[i]} args={[g, mat, geo.poles]} />)}</Spin>
    </Part>
  );
}

export function Shaft({ geo }: { geo: Geometry }) {
  const L = geo.stack_length_mm;
  const body = useMemo(() => lathe([[0, -50], [26, -50], [30, -50], [30, -34], [40, -34], [40, -6], [HUB_R, -6], [HUB_R, L + 6], [40, L + 6], [40, L + 26], [30, L + 26], [30, FRONT_Z + 4], [28, FRONT_Z + 4], [28, 172], [0, 172]], 96), [L]);
  const teeth = useRef<THREE.InstancedMesh>(null), tg = useMemo(() => new THREE.BoxGeometry(3.4, 3.4, 22), []);
  const mat = useMemo(() => metal(COL.shaft, 0.32), []);
  useLayoutEffect(() => { const m = teeth.current!, o = new THREE.Object3D(); for (let i = 0; i < 24; i++) { const a = (i / 24) * Math.PI * 2; o.position.set(29.2 * Math.cos(a), 29.2 * Math.sin(a), 160); o.rotation.set(0, 0, a); o.updateMatrix(); m.setMatrixAt(i, o.matrix); } m.instanceMatrix.needsUpdate = true; }, []);
  return (
    <Part id="shaft" info="shaft">
      <Spin><mesh geometry={body} material={mat} /><instancedMesh ref={teeth} args={[tg, mat, 24]} /></Spin>
    </Part>
  );
}

function Bearing({ id, z }: { id: string; z: number }) {
  const outer = useMemo(() => lathe([[39, -11], [43, -11], [43, 11], [39, 11], [39, -11]], 64), []), inner = useMemo(() => lathe([[30, -11], [34, -11], [34, 11], [30, 11], [30, -11]], 64), []);
  const balls = useRef<THREE.InstancedMesh>(null), bg = useMemo(() => new THREE.SphereGeometry(2.9, 16, 12), []);
  const mat = useMemo(() => metal(COL.bearing, 0.22, 0.95), []), ballMat = useMemo(() => metal(0xe2e4e8, 0.12, 1), []);
  useLayoutEffect(() => { const m = balls.current!, o = new THREE.Object3D(); for (let i = 0; i < 14; i++) { const a = (i / 14) * Math.PI * 2; o.position.set(36.5 * Math.cos(a), 36.5 * Math.sin(a), 0); o.updateMatrix(); m.setMatrixAt(i, o.matrix); } m.instanceMatrix.needsUpdate = true; }, []);
  return (
    <Part id={id} info="bearings">
      <group position={[0, 0, z]}><mesh geometry={outer} material={mat} /><mesh geometry={inner} material={mat} /><instancedMesh ref={balls} args={[bg, ballMat, 14]} /></group>
    </Part>
  );
}
export const BearingFront = () => <Bearing id="bearing_front" z={127} />;
export const BearingRear = () => <Bearing id="bearing_rear" z={-43} />;

/** 레졸버: 도식(치수 출처 없음). 회전자 쪽 링은 축과 함께 돈다. */
export function Resolver() {
  const st = useMemo(() => extrude(ring(46, 58), 8, 48), []), ro = useMemo(() => extrude(ring(34, 45), 8, 48), []);
  const gm = useMemo(() => plastic(COL.resolver, 0.5), []), sm = useMemo(() => metal(0x8a9099, 0.4), []);
  return (
    <Part id="resolver" info="resolver">
      <group position={[0, 0, -28]}><mesh geometry={st} material={gm} /><Spin><mesh geometry={ro} material={sm} /></Spin></group>
    </Part>
  );
}

/** 냉각수 흐름: GPU 셰이더가 입자 위치를 계산한다(CPU는 시간 uniform만 갱신). 하우징 워터재킷 둘레를 따라 흐른다. */
export function CoolantFlow({ geo, visible }: { geo: Geometry; visible: boolean }) {
  const mat = useRef<THREE.ShaderMaterial>(null);
  const g = useMemo(() => {
    const n = 2600, a0 = new Float32Array(n), r = new Float32Array(n), z = new Float32Array(n), sp = new Float32Array(n), pos = new Float32Array(n * 3);
    let s = 7; const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
    const R = geo.housing.diameter_mm / 2;
    for (let i = 0; i < n; i++) { a0[i] = rnd() * 6.2832; r[i] = R - 10.5 + rnd() * 6; z[i] = REAR_Z + 14 + rnd() * (FRONT_Z - REAR_Z - 28); sp[i] = 0.5 + rnd() * 0.9; }
    const gg = new THREE.BufferGeometry(); gg.setAttribute("position", new THREE.BufferAttribute(pos, 3)); gg.setAttribute("aA", new THREE.BufferAttribute(a0, 1));
    gg.setAttribute("aR", new THREE.BufferAttribute(r, 1)); gg.setAttribute("aZ", new THREE.BufferAttribute(z, 1)); gg.setAttribute("aS", new THREE.BufferAttribute(sp, 1)); return gg;
  }, [geo]);
  useFrame((st) => { if (mat.current && visible) { mat.current.uniforms.uT.value = st.clock.elapsedTime; st.invalidate(); } });
  return (
    <points geometry={g} visible={visible} frustumCulled={false}>
      <shaderMaterial ref={mat} transparent depthWrite={false} blending={THREE.AdditiveBlending} uniforms={{ uT: { value: 0 } }}
        vertexShader={`attribute float aA; attribute float aR; attribute float aZ; attribute float aS; uniform float uT; varying float vS;
          void main(){ float a = aA + uT*aS*0.9; vec3 p = vec3(aR*cos(a), aR*sin(a), aZ); vS = aS;
          vec4 mv = modelViewMatrix*vec4(p,1.0); gl_PointSize = 2.4 * 300.0 / -mv.z; gl_Position = projectionMatrix*mv; }`}
        fragmentShader={`varying float vS; void main(){ vec2 d = gl_PointCoord-0.5; float a = smoothstep(0.5,0.0,length(d)); gl_FragColor = vec4(0.25+0.4*vS,0.75,1.0,a*0.9); }`} />
    </points>
  );
}
