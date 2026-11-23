import * as THREE from "three";

/** 재질 공장. 부품마다 새 재질을 만든다(강조·반투명을 부품별로 따로 바꾸기 위해). */
export const COL = {
  steelStator: 0x8d939c, steelRotor: 0xa3a9b2, copper: 0xc47a42, alu: 0xb7bbc2, aluDark: 0x8f949b, bolt: 0x6e737b,
  shaft: 0x9aa0a8, magnetN: 0xd0553d, magnetS: 0x3f78c4, magnetRaw: 0x4a4d54, phaseA: 0xe0533f, phaseB: 0xe8b730, phaseC: 0x3d8bd9,
  water: 0x44b6e8, terminal: 0x2c3036, bearing: 0xc9ccd2, resolver: 0x2f6f5e,
};

let _noise: THREE.CanvasTexture | null = null;
/** 주조 알루미늄 느낌의 범프 텍스처(절차 생성, 오프라인에서도 동작). */
export function noiseTexture(): THREE.CanvasTexture {
  if (_noise) return _noise;
  const n = 256, c = document.createElement("canvas"); c.width = c.height = n;
  const g = c.getContext("2d")!; const img = g.createImageData(n, n);
  let s = 1337; const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
  for (let i = 0; i < n * n; i++) { const v = 150 + rnd() * 80; img.data.set([v, v, v, 255], i * 4); }
  g.putImageData(img, 0, 0);
  _noise = new THREE.CanvasTexture(c); _noise.wrapS = _noise.wrapT = THREE.RepeatWrapping; _noise.repeat.set(6, 6); return _noise;
}

/** 얇은 강판을 쌓은 철심의 적층 무늬: 셰이더(GPU)가 z 방향 줄무늬를 그린다. 간격이 화소보다 작아지면 저절로 흐려진다. */
export function laminate(m: THREE.MeshStandardMaterial, pitchMm = 0.33): THREE.MeshStandardMaterial {
  m.onBeforeCompile = (sh) => {
    sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\nvarying float vLamZ;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvLamZ = position.z;");
    sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\nvarying float vLamZ;")
      .replace("#include <color_fragment>", `#include <color_fragment>
        float lamW = fwidth(vLamZ) / ${pitchMm.toFixed(3)};
        float lamFade = 1.0 - smoothstep(0.30, 0.85, lamW);
        float lamS = 0.5 + 0.5 * sin(vLamZ * 6.2831853 / ${pitchMm.toFixed(3)});
        diffuseColor.rgb *= 1.0 - 0.20 * lamFade * lamS;`);
  };
  return m;
}

export const steel = (color: number, lam = true) => {
  const m = new THREE.MeshStandardMaterial({ color, metalness: 0.9, roughness: 0.38, envMapIntensity: 1.1 });
  return lam ? laminate(m) : m;
};
export const metal = (color: number, rough = 0.42, metalness = 0.88) => new THREE.MeshStandardMaterial({ color, metalness, roughness: rough, envMapIntensity: 1.1 });
export const cast = (color: number) => new THREE.MeshStandardMaterial({ color, metalness: 0.85, roughness: 0.52, bumpMap: noiseTexture(), bumpScale: 0.6, envMapIntensity: 1.0 });
export const copperMat = (color = COL.copper) => new THREE.MeshStandardMaterial({ color, metalness: 0.92, roughness: 0.28, emissive: 0x000000, envMapIntensity: 1.2 });
export const enamel = (color: number) => new THREE.MeshStandardMaterial({ color, metalness: 0.2, roughness: 0.35, emissive: color, emissiveIntensity: 0.0 });
export const plastic = (color: number, rough = 0.6) => new THREE.MeshStandardMaterial({ color, metalness: 0.05, roughness: rough });
export const glassy = (color: number, opacity = 0.35) => new THREE.MeshPhysicalMaterial({ color, metalness: 0, roughness: 0.1, transmission: 0, transparent: true, opacity });
