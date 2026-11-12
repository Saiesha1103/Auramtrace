import { useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { AdditiveBlending, BufferAttribute, BufferGeometry, Points, ShaderMaterial, Vector2 } from 'three';
import { sceneClock } from './clock';

const vertex = /* glsl */ `
uniform float uTime;
uniform vec2 uMouse;
uniform float uPresence;
uniform float uPixelRatio;
uniform float uSize;
uniform float uRise;
uniform float uHeight;
attribute float aSeed;
attribute float aScale;
varying float vAlpha;
varying float vHot;
void main(){
  vec3 p = position;
  float t = uTime;
  float half_ = uHeight * 0.5;
  p.y = mod(p.y + t * uRise * (0.4 + aSeed) + half_, uHeight) - half_;
  p.x += sin(t * 0.3 + aSeed * 20.0 + p.y * 0.6) * 0.25;
  p.z += cos(t * 0.25 + aSeed * 13.0) * 0.2;

  // pointer reaction: particles part around the cursor and catch light
  vec2 d = p.xy - uMouse;
  float dist = length(d);
  float push = smoothstep(1.6, 0.0, dist) * uPresence;
  vec2 dir = d / max(dist, 0.001);
  // part softly around the cursor with a slight swirl, like dust in a warm draft
  p.xy += (dir * 0.55 + vec2(-dir.y, dir.x) * 0.22) * push;
  p.z += push * 0.3;
  vHot = push;

  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = uSize * aScale * uPixelRatio * (1.0 + push * 0.9) / -mv.z;
  float twinkle = 0.55 + 0.45 * sin(t * (1.2 + aSeed * 3.0) + aSeed * 40.0);
  float fadeY = smoothstep(half_, half_ * 0.6, abs(p.y));
  vAlpha = twinkle * fadeY;
}
`;

const fragment = /* glsl */ `
uniform float uIntensity;
varying float vAlpha;
varying float vHot;
void main(){
  float d = length(gl_PointCoord - 0.5);
  float a = smoothstep(0.5, 0.0, d);
  float core = smoothstep(0.18, 0.0, d);
  vec3 col = mix(vec3(0.95, 0.55, 0.16), vec3(1.0, 0.9, 0.68), core + vHot * 0.6);
  gl_FragColor = vec4(col * (a * 0.6 + core) * vAlpha * uIntensity * (1.0 + vHot * 1.5), 1.0);
}
`;

interface Props {
  count: number;
  spread: [number, number, number];
  centre?: [number, number, number];
  size: number;
  rise: number;
  intensity: number;
  seed?: number;
}

function rand(seed: number) {
  let s = seed;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

export function GoldParticles({ count, spread, centre = [0, 0, 0], size, rise, intensity, seed = 7 }: Props) {
  const mat = useRef<ShaderMaterial>(null);
  const pts = useRef<Points>(null);
  const dpr = useThree((s) => s.viewport.dpr);

  const geometry = useMemo(() => {
    const r = rand(seed * 9973 + 1);
    const pos = new Float32Array(count * 3);
    const seeds = new Float32Array(count);
    const scales = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      pos[i * 3] = centre[0] + (r() - 0.5) * spread[0];
      pos[i * 3 + 1] = centre[1] + (r() - 0.5) * spread[1];
      pos[i * 3 + 2] = centre[2] + (r() - 0.5) * spread[2];
      seeds[i] = r();
      // mostly fine dust, a few larger embers
      scales[i] = r() < 0.06 ? 2.2 + r() * 1.5 : 0.5 + r() * 0.9;
    }
    const g = new BufferGeometry();
    g.setAttribute('position', new BufferAttribute(pos, 3));
    g.setAttribute('aSeed', new BufferAttribute(seeds, 1));
    g.setAttribute('aScale', new BufferAttribute(scales, 1));
    return g;
  }, [count, spread, centre, seed]);

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uMouse: { value: new Vector2(99, 99) },
      uPresence: { value: 0 },
      uPixelRatio: { value: 1 },
      uSize: { value: size },
      uRise: { value: rise },
      uHeight: { value: spread[1] },
      uIntensity: { value: intensity },
    }),
    [size, rise, spread, intensity],
  );

  useFrame(() => {
    const m = mat.current;
    if (!m) return;
    m.uniforms.uTime.value = sceneClock.time;
    // cursor is in rig space; compensate for any parallax offset on this layer's parent
    const off = pts.current?.parent?.position;
    (m.uniforms.uMouse.value as Vector2).set(sceneClock.wx - (off?.x ?? 0), sceneClock.wy - (off?.y ?? 0));
    m.uniforms.uPresence.value = sceneClock.presence;
    m.uniforms.uPixelRatio.value = dpr;
  });

  return (
    <points ref={pts} geometry={geometry} frustumCulled={false}>
      <shaderMaterial
        ref={mat}
        vertexShader={vertex}
        fragmentShader={fragment}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        blending={AdditiveBlending}
      />
    </points>
  );
}
