import { Select } from "@react-three/postprocessing";
import { useFrame } from "@react-three/fiber";
import { useEffect, useRef, type ReactNode } from "react";
import * as THREE from "three";
import { useStore } from "../lib/store";
import { EXPLODE, motion, partRefs, smooth } from "./motion";

/** 부품 하나: 분해 위치, 보이기/고립/X-ray, 호버·클릭, 강조 윤곽을 맡는다.
 *  id = 분해 배치 키, info = 부품 도감 id(여러 조각이 같은 도감 항목을 가리킬 수 있다). */
export function Part({ id, info, children }: { id: string; info: string; children: ReactNode }) {
  const g = useRef<THREE.Group>(null);
  const selected = useStore((s) => s.selected), hovered = useStore((s) => s.hovered), xray = useStore((s) => s.xray), hiddenMap = useStore((s) => s.hidden);
  const hidden = !!hiddenMap[info];
  const hot = selected === info || hovered === info;

  useEffect(() => { if (g.current) partRefs[id] = g.current; return () => { delete partRefs[id]; }; }, [id]);

  useFrame(() => {
    if (!g.current) return;
    const c = EXPLODE[id], k = c ? smooth((motion.e - c.t0) / (c.t1 - c.t0)) : 0;
    g.current.position.set(0, (c?.dy ?? 0) * k, (c?.dz ?? 0) * k);
  });

  useEffect(() => {
    if (!g.current) return;
    const dim = xray && !(selected === info);
    g.current.traverse((o) => {
      const m = (o as THREE.Mesh).material as THREE.Material | THREE.Material[] | undefined;
      if (!m) return;
      for (const mm of Array.isArray(m) ? m : [m]) {
        const ms = mm as THREE.MeshStandardMaterial;
        if (ms.userData.baseOpacity === undefined) { ms.userData.baseOpacity = ms.opacity; ms.userData.baseTransparent = ms.transparent; }
        ms.transparent = dim ? true : ms.userData.baseTransparent; ms.opacity = dim ? 0.12 : ms.userData.baseOpacity; ms.depthWrite = !dim;
        ms.needsUpdate = true;
      }
    });
  }, [xray, selected, info]);

  return (
    <group ref={g} visible={!hidden}
      onPointerOver={(e) => { e.stopPropagation(); useStore.getState().set({ hovered: info }); document.body.style.cursor = "pointer"; }}
      onPointerOut={() => { useStore.getState().set({ hovered: null }); document.body.style.cursor = ""; }}
      onClick={(e) => { e.stopPropagation(); const s = useStore.getState(); s.set({ selected: info, tab: "info", focusId: id, focusNonce: s.focusNonce + 1 }); }}>
      <Select enabled={hot}>{children}</Select>
    </group>
  );
}

/** 회전자와 함께 도는 묶음. 각도는 공유 상태에서 읽는다. */
export function Spin({ children }: { children: ReactNode }) {
  const g = useRef<THREE.Group>(null);
  useFrame(() => { if (g.current) g.current.rotation.z = motion.angle; });
  return <group ref={g}>{children}</group>;
}
