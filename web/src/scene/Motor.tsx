import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import * as THREE from "three";
import type { Geometry } from "../lib/api";
import { useStore } from "../lib/store";
import { motion } from "./motion";
import { Housing, Magnets, RotorCore, Shaft, ShieldFront, ShieldRear, Resolver, StatorCore, Terminal, Windings, BearingFront, BearingRear, CoolantFlow } from "./parts";
import { SectionFaces } from "./Section";

/** 프레임마다: 분해 정도를 목표로 부드럽게 따라가고, 회전자 각도와 권선 발광(3상 전류)을 갱신한다. 필요할 때만 다음 프레임을 요청한다. */
function Driver() {
  useFrame((st, dt) => {
    const s = useStore.getState();
    const de = s.explodeTarget - motion.e;
    if (Math.abs(de) > 1e-3) { motion.e += de * (1 - Math.exp(-dt * 3.2)); st.invalidate(); } else motion.e = s.explodeTarget;
    const run = s.spinning || s.drive.playing;
    if (run) {
      const ser = s.cycle?.series, dts = ser && ser.t_s.length > 1 ? ser.t_s[1] - ser.t_s[0] : 1, i = Math.max(0, Math.min(Math.floor(motion.driveT / dts), (ser?.t_s.length ?? 1) - 1));
      const rpm = s.drive.playing && ser ? ser.motor_rpm[i] : s.op?.speed_rpm ?? 1500;
      motion.angle += ((rpm / 60) * Math.PI * 2 * dt * s.spinSpeed) / 20;          // 화면 속도는 실제의 1/20 × 배율
      const wf = s.op?.waveforms;
      if (wf && s.showWindingGlow) {
        const peak = Math.max(...wf.ia.map(Math.abs), 1e-6), cur = s.drive.playing && ser ? ser.current_A[i] : (s.op?.current?.peak_A ?? 0);
        const k = Math.min(cur / (s.settings.Imax || 250), 1), idx = Math.floor((((4 * motion.angle) % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2) / (Math.PI * 2) * wf.ia.length) % wf.ia.length;
        motion.glow = [(wf.ia[idx] / peak) * k, (wf.ib[idx] / peak) * k, (wf.ic[idx] / peak) * k];
      }
      st.invalidate();
    } else if (motion.glow.some((v) => v !== 0)) { motion.glow = [0, 0, 0]; st.invalidate(); }
  }, -1);
  return null;
}

function Clipper({ geo }: { geo: Geometry }) {
  const gl = useThree((s) => s.gl), invalidate = useThree((s) => s.invalidate);
  const view = useStore((s) => s.view), frac = useStore((s) => s.sectionZ);
  const plane = useMemo(() => new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0), []);
  useEffect(() => {
    if (view === "section") { plane.constant = 0.01 * (frac * geo.stack_length_mm - geo.stack_length_mm / 2); gl.clippingPlanes = [plane]; } else gl.clippingPlanes = [];
    invalidate();
  }, [view, frac, geo, gl, plane, invalidate]);
  return null;
}

export function Motor({ geo }: { geo: Geometry }) {
  const coolant = useStore((s) => s.showCoolant);
  return (
    <>
      <Driver />
      <Clipper geo={geo} />
      <group scale={0.01} rotation={[0, Math.PI / 2, 0]}>
        <group position={[0, 0, -geo.stack_length_mm / 2]}>
          <Housing geo={geo} /><ShieldFront geo={geo} /><ShieldRear geo={geo} /><Terminal geo={geo} />
          <StatorCore geo={geo} /><Windings geo={geo} />
          <RotorCore geo={geo} /><Magnets geo={geo} /><Shaft geo={geo} />
          <BearingFront /><BearingRear /><Resolver />
          <CoolantFlow geo={geo} visible={coolant} />
          <SectionFaces geo={geo} />
        </group>
      </group>
    </>
  );
}
