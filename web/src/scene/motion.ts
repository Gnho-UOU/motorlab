import type * as THREE from "three";

/** 해부(분해) 배치. 모터 좌표(mm): z는 축 방향(+ 앞쪽 = 출력축 쪽), y는 위. e = 0(조립) → 1(완전 분해).
 *  각 부품이 [t0, t1] 구간에서 차례로 움직여 "벗겨 내는" 순서가 보인다. */
export interface ExplodeCfg { dz: number; dy?: number; t0: number; t1: number }
export const EXPLODE: Record<string, ExplodeCfg> = {
  terminal: { dz: 230, dy: 190, t0: 0.0, t1: 0.5 },
  housing: { dz: 230, t0: 0.0, t1: 0.5 },
  shield_front: { dz: 430, t0: 0.05, t1: 0.6 },
  bearing_front: { dz: 275, t0: 0.15, t1: 0.7 },
  shield_rear: { dz: -440, t0: 0.05, t1: 0.6 },
  bearing_rear: { dz: -285, t0: 0.15, t1: 0.7 },
  resolver: { dz: -200, t0: 0.2, t1: 0.75 },
  rotor_core: { dz: -175, t0: 0.4, t1: 0.95 },
  magnets: { dz: -175, dy: 250, t0: 0.55, t1: 1.0 },
};
export const smooth = (x: number) => { const t = Math.min(Math.max(x, 0), 1); return t * t * (3 - 2 * t); };

/** 프레임마다 갱신되는 공유 상태(React 리렌더 없이 GPU 쪽에서 쓴다). */
export const motion = {
  e: 0,                    // 현재 분해 정도 0~1 (목표를 향해 부드럽게 따라간다)
  angle: 0,                // 회전자의 화면 회전각 [rad]
  driveT: 0,               // 드라이브 모드의 현재 시각 [s]
  glow: [0, 0, 0] as [number, number, number],   // 3상 전류 순간값 / 전류 한계 (−1~1), 권선 발광에 쓴다
};
/** 부품 그룹 참조(카메라가 부품으로 날아갈 때 경계 상자를 잰다). */
export const partRefs: Record<string, THREE.Object3D> = {};
