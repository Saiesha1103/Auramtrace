import { useMemo, useRef } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { ShaderMaterial, Vector2 } from 'three';
import { GOLD, NOISE } from './glsl';


import { seaState } from './seaState';

const vertex = /* glsl */ `
varying vec2 vUv;
void main(){
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

/**
 * A receding sea of molten gold. Each pixel below the horizon is projected
 * onto a ground plane, a domain-warped height field is sampled there, and the
 * resulting normal reflects the same studio environment as the hero gold.
 */
const fragment = /* glsl */ `
${NOISE}
${GOLD}
uniform float uTime;
uniform float uReveal;
uniform vec2 uRes;
varying vec2 vUv;

float heightAt(vec2 p, float t){
  // one warp sample + one detail sample keeps this cheap enough for full-screen use
  float w = snoise(vec3(p * 0.45, t * 0.08));
  float h = snoise(vec3(p * 0.7 + vec2(w, -w) * 1.6, t * 0.16)) * 0.65;
  h += sin(p.x * 1.9 + w * 2.0 + t * 0.6) * sin(p.y * 1.3 - t * 0.4) * 0.12;
  return h;
}

void main(){
  vec2 uv = vUv;
  float aspect = uRes.x / uRes.y;
  float t = uTime;

  // the horizon rises with scroll, with a slow molten swell along it
  float level = mix(-0.08, 0.3, uReveal);
  float wave = 0.012 * sin(uv.x * 7.0 + t * 0.7) + 0.008 * snoise(vec3(uv.x * 3.0, t * 0.2, 1.0));
  float horizon = level + wave;
  float below = horizon - uv.y;

  vec3 col = vec3(0.0018, 0.0012, 0.0008);

  // horizon glow in the air above the liquid
  col += vec3(1.0, 0.55, 0.15) * 0.22 * exp(-max(-below, 0.0) * 9.0) * smoothstep(0.0, 0.2, uReveal);

  if (below > 0.0) {
    float z = 1.0 / (below + 0.035);
    vec2 wp = vec2((uv.x - 0.5) * aspect * z * 0.9, z * 1.3 - t * 0.35);
    float e = 0.02 + z * 0.002;
    float h = heightAt(wp, t);
    float hx = heightAt(wp + vec2(e, 0.0), t) - h;
    float hz = heightAt(wp + vec2(0.0, e), t) - h;
    float amp = 0.95 / (1.0 + z * 0.05);
    vec3 N = normalize(vec3(-hx / e * amp, 1.0, -hz / e * amp));
    vec3 V = normalize(vec3(0.0, 0.32, 1.0));
    vec3 g = shadeGold(N, V, 0.1, vec3(1.0));
    // distance haze toward the glowing horizon
    float haze = smoothstep(9.0, 32.0, z);
    g = mix(g, vec3(1.0, 0.62, 0.22) * 0.9, haze * 0.6);
    // molten rim exactly at the edge
    float rim = exp(-below * 220.0);
    g += vec3(1.0, 0.8, 0.5) * rim * 1.5;
    col = g * smoothstep(0.0, 0.004, below);
  }

  gl_FragColor = vec4(col, 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

function Sea({ reduced }: { reduced: boolean }) {
  const mat = useRef<ShaderMaterial>(null);
  const { size } = useThree();
  const uniforms = useMemo(
    () => ({ uTime: { value: 4 }, uReveal: { value: 0 }, uRes: { value: new Vector2(1, 1) } }),
    [],
  );
  useFrame((_, delta) => {
    const m = mat.current;
    if (!m) return;
    if (!reduced) seaState.time += Math.min(delta, 1 / 20);
    m.uniforms.uTime.value = seaState.time;
    m.uniforms.uReveal.value = reduced ? 1 : seaState.reveal;
    m.uniforms.uRes.value.set(size.width, size.height);
  });
  return (
    <mesh frustumCulled={false}>
      <planeGeometry args={[2, 2]} />
      <shaderMaterial ref={mat} vertexShader={vertex} fragmentShader={fragment} uniforms={uniforms} depthTest={false} />
    </mesh>
  );
}

export default function MoltenSea({ active, reduced }: { active: boolean; reduced: boolean }) {
  return (
    <Canvas
      className="sea-canvas"
      dpr={[0.6, 0.8]}
      frameloop={reduced ? 'demand' : active ? 'always' : 'never'}
      gl={{ antialias: false, alpha: false, powerPreference: 'high-performance' }}
      onCreated={({ gl }) => {
        gl.toneMappingExposure = 0.95;
      }}
    >
      <Sea reduced={reduced} />
    </Canvas>
  );
}
