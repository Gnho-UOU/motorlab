import { CameraControls, ContactShadows, Environment, Lightformer, PerformanceMonitor } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Bloom, EffectComposer, Outline, Selection, SMAA, ToneMapping } from "@react-three/postprocessing";
import { ToneMappingMode } from "postprocessing";
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import type CameraControlsImpl from "camera-controls";
import { useStore } from "../lib/store";
import { Motor } from "./Motor";
import { partRefs } from "./motion";
import { TOUR } from "./tour";

type V3 = [number, number, number];
const POSES: Record<"hero" | "exploded" | "section", { pos: V3; target: V3 }> = {
  hero: { pos: [8.5, 3.4, 9.5], target: [0.2, 0, 0] },
  exploded: { pos: [3.5, 4.2, 16.5], target: [0.3, 0.5, 0] },
  section: { pos: [9.2, 0.6, 1.2], target: [0, 0, 0] },
};

/** 카메라: 부품을 고르면 그 부품의 경계 상자에 맞춰 날아가고, 보기 모드를 바꾸면 알맞은 자세로 돌아간다. */
function CameraRig() {
  const ref = useRef<CameraControlsImpl>(null);
  const nonce = useStore((s) => s.focusNonce), view = useStore((s) => s.view), step = useStore((s) => s.tourStep);
  const first = useRef(true);
  const invalidate = useThree((s) => s.invalidate), size = useThree((s) => s.size);
  /** 화면이 좁을수록 카메라를 멀리 둔다(가로로 긴 분해 배치가 잘리지 않게). */
  const away = (p: { pos: V3; target: V3 }, extra = 1): [V3, V3] => { const k = Math.min(1.6, Math.max(1, 1.15 / (size.width / size.height))) * extra; return [p.pos.map((v, i) => p.target[i] + (v - p.target[i]) * k) as V3, p.target]; };
  useEffect(() => {
    const c = ref.current; if (!c) return;
    const p = view === "section" ? away(POSES.section, 0.8) : view === "exploded" ? away(POSES.exploded) : away(POSES.hero);
    if (first.current) { first.current = false; c.setLookAt(...p[0], ...p[1], false); invalidate(); return; }
    c.setLookAt(...p[0], ...p[1], true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, invalidate]);
  useEffect(() => {
    const c = ref.current, s = useStore.getState(); if (!c || nonce === 0) return;
    const st = step >= 0 ? TOUR[step] : null;
    const tp = (q: number[][]) => away({ pos: q[0] as V3, target: q[1] as V3 });
    if (st?.pose && !s.focusId) { const q = tp(st.pose); c.setLookAt(...q[0], ...q[1], true); return; }
    const o = s.focusId ? partRefs[s.focusId] : null;
    if (o) {
      const box = new THREE.Box3().setFromObject(o);
      if (!box.isEmpty()) c.fitToBox(box, true, { paddingLeft: 0.4, paddingRight: 0.4, paddingTop: 0.4, paddingBottom: 0.4 });
    } else if (st?.pose) { const q = tp(st.pose); c.setLookAt(...q[0], ...q[1], true); }
  }, [nonce, step]);
  return <CameraControls ref={ref} makeDefault minDistance={1.2} maxDistance={40} smoothTime={0.35} draggingSmoothTime={0.1} dollySpeed={0.7} />;
}

/** 초당 프레임 수와 GPU 정보를 잰다. 요청 시 렌더(frameloop="demand")라서 움직이지 않으면 프레임이 없다. */
function Perf() {
  const gl = useThree((s) => s.gl);
  const n = useRef(0), t0 = useRef(performance.now());
  useEffect(() => {
    const ctx = gl.getContext(), ext = ctx.getExtension("WEBGL_debug_renderer_info");
    const name = ext ? String(ctx.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : "알 수 없음";
    useStore.getState().set({ gpu: `${name} · WebGL${gl.capabilities.isWebGL2 ? "2" : "1"}` });
  }, [gl]);
  useFrame(() => {
    n.current++; const t = performance.now();
    if (t - t0.current > 1000) { useStore.getState().set({ fps: Math.round((n.current * 1000) / (t - t0.current)) }); n.current = 0; t0.current = t; }
  });
  useEffect(() => { const id = setInterval(() => { if (performance.now() - t0.current > 2500) useStore.getState().set({ fps: 0 }); }, 1500); return () => clearInterval(id); }, []);
  return null;
}

function Lights() {
  return (
    <>
      <Environment resolution={256} background={false}>
        <Lightformer form="rect" intensity={3.2} position={[0, 6, 6]} scale={[12, 3, 1]} color="#fff4e6" />
        <Lightformer form="rect" intensity={2.0} position={[-8, 2, -3]} scale={[8, 4, 1]} rotation-y={Math.PI / 2} color="#cfe3ff" />
        <Lightformer form="rect" intensity={2.4} position={[8, 1, 4]} scale={[6, 5, 1]} rotation-y={-Math.PI / 2} color="#ffd9b8" />
        <Lightformer form="ring" intensity={1.2} position={[0, -4, 0]} scale={9} rotation-x={Math.PI / 2} color="#ffffff" />
      </Environment>
      <directionalLight position={[6, 10, 8]} intensity={1.0} />
      <ambientLight intensity={0.15} />
    </>
  );
}

export function Studio() {
  const geo = useStore((s) => s.geometry), quality = useStore((s) => s.quality);
  const [dpr, setDpr] = useState(Math.min(window.devicePixelRatio, 2));
  if (!geo) return null;
  const fx = quality !== "low";
  return (
    <Canvas frameloop="demand" dpr={dpr} camera={{ fov: 30, near: 0.1, far: 200, position: [8.5, 3.4, 9.5] }}
      gl={{ antialias: quality === "low", powerPreference: "high-performance", stencil: false, alpha: false, toneMapping: THREE.NoToneMapping }}
      onPointerMissed={() => useStore.getState().set({ selected: null })}>
      <color attach="background" args={["#0c0e11"]} />
      <fog attach="fog" args={["#0c0e11", 26, 60]} />
      <PerformanceMonitor onDecline={() => setDpr((d) => Math.max(1, d - 0.5))} onIncline={() => setDpr((d) => Math.min(Math.min(window.devicePixelRatio, 2), d + 0.25))} />
      <Lights />
      <Selection>
        {fx && (
          <EffectComposer multisampling={0} enableNormalPass={false}>
            <Outline blur edgeStrength={quality === "high" ? 5 : 3} visibleEdgeColor={0xffa65c} hiddenEdgeColor={0x6b4222} width={900} />
            <Bloom mipmapBlur intensity={quality === "high" ? 0.55 : 0.35} luminanceThreshold={0.85} luminanceSmoothing={0.25} />
            <SMAA />
            <ToneMapping mode={ToneMappingMode.ACES_FILMIC} />
          </EffectComposer>
        )}
        <Motor geo={geo} />
      </Selection>
      <ContactShadows position={[0, -1.72, 0]} opacity={0.55} scale={22} blur={2.6} far={5} resolution={512} color="#000000" />
      <mesh rotation-x={-Math.PI / 2} position={[0, -1.74, 0]}><circleGeometry args={[40, 64]} /><meshStandardMaterial color="#14171c" roughness={0.9} metalness={0.1} /></mesh>
      <CameraRig />
      <Perf />
    </Canvas>
  );
}
