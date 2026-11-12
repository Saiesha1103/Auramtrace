import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { BufferAttribute, BufferGeometry, ShaderMaterial } from 'three';
import { CURVE_GLSL } from './curve';
import { GOLD, NOISE } from './glsl';
import { sceneClock } from './clock';

export interface StrandConfig {
  width: number;
  thickness: number;
  twist: number;
  offset: number;
  phase: number;
  ripple: number;
  glow: number;
  segU: number;
  segV: number;
}

const vertex = /* glsl */ `
${CURVE_GLSL}
attribute vec2 aParam;
uniform float uTime;
uniform float uWidth;
uniform float uThick;
uniform float uTwist;
uniform float uOffset;
uniform float uPhase;
uniform float uRipple;
varying vec3 vNormalW;
varying vec3 vPosW;
varying vec2 vParam;
varying float vEdge;

vec3 surface(float u, float phi, out vec3 centre){
  float t = uTime;
  float a = u * TAU;
  vec3 c = flowCurve(u, t);
  float e = 0.0012;
  vec3 T = normalize(flowCurve(u + e, t) - flowCurve(u - e, t));
  vec3 side = normalize(cross(T, vec3(0.0, 0.0, 1.0)));
  vec3 nrm = cross(side, T);

  // strands spiral lazily around the main ribbon
  float o = uPhase + a * 2.0 + t * 0.25;
  c += (side * cos(o) + nrm * sin(o) * 0.55) * uOffset;

  float tw = uTwist * a + 0.85 * sin(a * 2.0 + t * 0.3 + uPhase);
  vec3 s2 = side * cos(tw) + nrm * sin(tw);
  vec3 n2 = -side * sin(tw) + nrm * cos(tw);

  float w = uWidth * (0.5 + 0.5 * (0.5 + 0.5 * sin(a * 2.0 + 1.3 + uPhase + t * 0.2)));
  float th = uThick * (0.75 + 0.25 * sin(a * 5.0 - t * 0.8 + uPhase));
  // travelling swell — reads as viscous liquid moving along the loop
  float swell = 1.0 + uRipple * sin(a * 14.0 + t * 2.2 + uPhase);
  centre = c;
  return c + s2 * cos(phi) * w * swell + n2 * sin(phi) * th * swell;
}

void main(){
  float u = aParam.x;
  float phi = aParam.y;
  vec3 centre, cA, cB;
  vec3 p  = surface(u, phi, centre);
  vec3 pu = surface(u + 0.0006, phi, cA);
  vec3 pv = surface(u, phi + 0.02, cB);
  vec3 n = normalize(cross(pu - p, pv - p));
  if (dot(n, p - centre) < 0.0) n = -n;

  vec4 world = modelMatrix * vec4(p, 1.0);
  vPosW = world.xyz;
  vNormalW = normalize(mat3(modelMatrix) * n);
  vParam = aParam;
  vEdge = abs(cos(phi));
  gl_Position = projectionMatrix * viewMatrix * world;
}
`;

const fragment = /* glsl */ `
${NOISE}
${GOLD}
uniform float uTime;
uniform float uGlow;
uniform float uPhase;
varying vec3 vNormalW;
varying vec3 vPosW;
varying vec2 vParam;
varying float vEdge;

void main(){
  vec3 V = normalize(cameraPosition - vPosW);
  vec3 N = normalize(vNormalW);
  if (!gl_FrontFacing) N = -N;

  // molten micro-surface: low-amplitude flowing normal perturbation
  vec3 q = vec3(vParam.x * 42.0 + uTime * 0.9, vParam.y * 1.3, uTime * 0.12 + uPhase);
  float n1 = snoise(q);
  float n2 = snoise(q + vec3(17.3, 5.1, 2.7));
  N = normalize(N + vec3(n1, n2, n1 * n2) * 0.07);

  // slow, bounded sway of the studio lights around the loop: highlights glide along the metal
  // like a showroom turntable, then return, so the composed pose is preserved
  float sway = 0.3 * sin(uTime * 0.11) + 0.12 * sin(uTime * 0.047 + 1.7);
  float cs = cos(sway), sn = sin(sway);
  mat3 rotY = mat3(cs, 0.0, -sn, 0.0, 1.0, 0.0, sn, 0.0, cs);
  vec3 col = shadeGold(rotY * N, rotY * V, 0.16 + 0.10 * n1, vec3(1.0));

  // energy pulses travelling along the flow (custody "events")
  float f = fract(vParam.x * 4.0 + uTime * 0.08 + uPhase * 0.1);
  float pulse = smoothstep(0.0, 0.015, f) * smoothstep(0.09, 0.0, f);
  col += vec3(1.0, 0.70, 0.30) * pulse * 1.4 * uGlow;

  // warm sub-surface glow at grazing angles
  float fres = pow(1.0 - clamp(dot(N, V), 0.0, 1.0), 3.0);
  col += vec3(1.0, 0.55, 0.16) * fres * 0.35 * uGlow;

  gl_FragColor = vec4(col, 1.0);
}
`;

function buildTube(segU: number, segV: number): BufferGeometry {
  const verts = (segU + 1) * (segV + 1);
  const params = new Float32Array(verts * 2);
  const positions = new Float32Array(verts * 3); // placeholder; real position is computed in the shader
  let k = 0;
  for (let i = 0; i <= segU; i++) {
    for (let j = 0; j <= segV; j++) {
      params[k++] = i / segU;
      params[k++] = (j / segV) * Math.PI * 2;
    }
  }
  const index: number[] = [];
  for (let i = 0; i < segU; i++) {
    for (let j = 0; j < segV; j++) {
      const a = i * (segV + 1) + j;
      const b = a + segV + 1;
      index.push(a, b, a + 1, b, b + 1, a + 1);
    }
  }
  const g = new BufferGeometry();
  g.setAttribute('position', new BufferAttribute(positions, 3));
  g.setAttribute('aParam', new BufferAttribute(params, 2));
  g.setIndex(index);
  return g;
}

export function LiquidRibbon({ config }: { config: StrandConfig }) {
  const matRef = useRef<ShaderMaterial>(null);
  const geometry = useMemo(() => buildTube(config.segU, config.segV), [config.segU, config.segV]);
  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uWidth: { value: config.width },
      uThick: { value: config.thickness },
      uTwist: { value: config.twist },
      uOffset: { value: config.offset },
      uPhase: { value: config.phase },
      uRipple: { value: config.ripple },
      uGlow: { value: config.glow },
    }),
    [config],
  );

  useFrame(() => {
    if (matRef.current) matRef.current.uniforms.uTime.value = sceneClock.time;
  });

  return (
    <mesh geometry={geometry} frustumCulled={false}>
      <shaderMaterial ref={matRef} vertexShader={vertex} fragmentShader={fragment} uniforms={uniforms} />
    </mesh>
  );
}
