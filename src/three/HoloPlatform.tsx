import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { AdditiveBlending, DoubleSide, Mesh, ShaderMaterial } from 'three';
import { GOLD } from './glsl';
import { sceneClock } from './clock';

const passVertex = /* glsl */ `
varying vec2 vUv;
varying vec3 vPosW;
varying vec3 vNormalW;
varying vec3 vObj;
void main(){
  vUv = uv;
  vObj = position;
  vec4 w = modelMatrix * vec4(position, 1.0);
  vPosW = w.xyz;
  vNormalW = normalize(mat3(modelMatrix) * normal);
  gl_Position = projectionMatrix * viewMatrix * w;
}
`;

/** Dark brushed-bronze plinth that picks up the warm environment. */
const plinthFragment = /* glsl */ `
${GOLD}
uniform float uTime;
varying vec3 vPosW;
varying vec3 vNormalW;
varying vec3 vObj;
void main(){
  vec3 V = normalize(cameraPosition - vPosW);
  vec3 N = normalize(vNormalW);
  float r = length(vObj.xz);
  // concentric machining marks
  float lathe = 0.5 + 0.5 * sin(r * 160.0);
  vec3 col = shadeGold(N, V, 0.45 + lathe * 0.2, vec3(0.75, 0.62, 0.5)) * 0.16;
  // glowing seam on the rim
  float rim = smoothstep(0.85, 1.0, abs(N.y) < 0.5 ? 1.0 : 0.0);
  col += vec3(1.0, 0.6, 0.2) * rim * 0.05;
  gl_FragColor = vec4(col, 1.0);
}
`;

/** Holographic top face: rings, rotating dashes, sweeping scan. */
const discFragment = /* glsl */ `
uniform float uTime;
varying vec2 vUv;
const float PI = 3.14159265;
float ring(float r, float at, float w){ return smoothstep(w, 0.0, abs(r - at)); }
void main(){
  vec2 p = vUv * 2.0 - 1.0;
  float r = length(p);
  float a = atan(p.y, p.x);
  float t = uTime;
  float v = 0.0;
  v += ring(r, 0.30, 0.012) * 0.9;
  v += ring(r, 0.46, 0.006) * 0.6;
  v += ring(r, 0.62, 0.010) * (0.6 + 0.4 * step(0.5, fract(a * 6.0 / PI + t * 0.15)));
  v += ring(r, 0.78, 0.004) * 0.5;
  v += ring(r, 0.92, 0.008) * step(0.3, fract(a * 24.0 / PI - t * 0.25)) * 0.8;
  // tick marks
  float ticks = step(0.92, fract(a * 60.0 / PI)) * smoothstep(0.70, 0.72, r) * smoothstep(0.76, 0.74, r);
  v += ticks * 0.7;
  // expanding pulse
  float pulse = fract(t * 0.22);
  v += ring(r, pulse, 0.04) * (1.0 - pulse) * 0.9;
  // radar sweep
  float sweep = mod(a - t * 0.8, 2.0 * PI);
  v += smoothstep(1.2, 0.0, sweep) * 0.22 * smoothstep(0.95, 0.3, r) * smoothstep(0.1, 0.3, r);
  // hot core under the nugget
  v += smoothstep(0.32, 0.0, r) * 0.9;
  v *= smoothstep(1.0, 0.9, r);
  vec3 col = mix(vec3(0.9, 0.45, 0.10), vec3(1.0, 0.85, 0.55), smoothstep(0.4, 1.4, v));
  gl_FragColor = vec4(col * v * 0.7, 1.0);
}
`;

/** Vertical light column carrying the "scan" up into the nugget. */
const beamFragment = /* glsl */ `
uniform float uTime;
varying vec2 vUv;
varying vec3 vPosW;
varying vec3 vNormalW;
void main(){
  float h = vUv.y;
  vec3 V = normalize(cameraPosition - vPosW);
  float edge = 1.0 - abs(dot(normalize(vNormalW), V));
  float stripes = 0.55 + 0.45 * smoothstep(0.6, 1.0, sin(vUv.x * 220.0));
  float rise = 0.6 + 0.4 * sin(h * 26.0 - uTime * 3.0);
  float a = pow(1.0 - h, 1.6) * (0.25 + edge * 0.9) * stripes * rise;
  // scan band
  float scan = fract(uTime * 0.35);
  a += smoothstep(0.03, 0.0, abs(h - scan)) * 1.6 * (1.0 - h);
  vec3 col = vec3(1.0, 0.70, 0.32) * a * 0.22;
  gl_FragColor = vec4(col, 1.0);
}
`;

const ringFragment = /* glsl */ `
uniform float uTime;
uniform float uSeed;
varying vec2 vUv;
void main(){
  float dash = step(0.35, fract(vUv.x * (8.0 + uSeed * 6.0) + uTime * (0.05 + uSeed * 0.04)));
  float glow = 0.35 + 0.65 * dash;
  gl_FragColor = vec4(vec3(1.0, 0.72, 0.36) * glow * 0.45, 1.0);
}
`;

function useTimeUniform() {
  return useMemo(() => ({ uTime: { value: 0 } }), []);
}

export function HoloPlatform({ y = -2.05 }: { y?: number }) {
  const mats = useRef<ShaderMaterial[]>([]);
  const scanRing = useRef<Mesh>(null);
  const plinthU = useTimeUniform();
  const discU = useTimeUniform();
  const beamU = useTimeUniform();
  const ringUs = useMemo(() => [0.1, 0.55, 0.9].map((s) => ({ uTime: { value: 0 }, uSeed: { value: s } })), []);

  const collect = (m: ShaderMaterial | null) => {
    if (m && !mats.current.includes(m)) mats.current.push(m);
  };

  useFrame(() => {
    const t = sceneClock.time;
    for (const m of mats.current) m.uniforms.uTime.value = t;
    if (scanRing.current) {
      const k = (Math.sin(t * 0.9) + 1) / 2;
      scanRing.current.position.y = 0.15 + k * 1.9;
      const s = 1.05 - k * 0.32;
      scanRing.current.scale.set(s, s, s);
    }
  });

  const additive = { transparent: true, blending: AdditiveBlending, depthWrite: false } as const;

  return (
    <group position={[0, y, 0]}>
      {/* plinth tiers */}
      <mesh position={[0, -0.16, 0]}>
        <cylinderGeometry args={[2.25, 2.5, 0.26, 128]} />
        <shaderMaterial ref={collect} vertexShader={passVertex} fragmentShader={plinthFragment} uniforms={plinthU} />
      </mesh>
      <mesh position={[0, 0.0, 0]}>
        <cylinderGeometry args={[1.65, 1.8, 0.1, 128]} />
        <shaderMaterial vertexShader={passVertex} fragmentShader={plinthFragment} uniforms={plinthU} />
      </mesh>

      {/* holographic top */}
      <mesh position={[0, 0.06, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[5.2, 5.2]} />
        <shaderMaterial ref={collect} vertexShader={passVertex} fragmentShader={discFragment} uniforms={discU} {...additive} />
      </mesh>

      {/* light column */}
      <mesh position={[0, 1.15, 0]}>
        <cylinderGeometry args={[0.7, 1.15, 2.2, 96, 1, true]} />
        <shaderMaterial
          ref={collect}
          vertexShader={passVertex}
          fragmentShader={beamFragment}
          uniforms={beamU}
          side={DoubleSide}
          {...additive}
        />
      </mesh>

      {/* travelling scan ring */}
      <mesh ref={scanRing} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.0, 0.008, 8, 128]} />
        <shaderMaterial ref={collect} vertexShader={passVertex} fragmentShader={ringFragment} uniforms={ringUs[0]} {...additive} />
      </mesh>

      {/* orbit rings */}
      {[
        { r: 2.75, tilt: 0.04, y: 0.05 },
        { r: 3.2, tilt: -0.05, y: 0.12 },
        { r: 3.75, tilt: 0.02, y: -0.05 },
      ].map((o, i) => (
        <mesh key={o.r} position={[0, o.y, 0]} rotation={[Math.PI / 2 + o.tilt, 0, 0]}>
          <torusGeometry args={[o.r, 0.006 + i * 0.002, 6, 220]} />
          <shaderMaterial ref={collect} vertexShader={passVertex} fragmentShader={ringFragment} uniforms={ringUs[i]} {...additive} />
        </mesh>
      ))}
    </group>
  );
}
