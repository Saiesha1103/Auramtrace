import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Group, IcosahedronGeometry, ShaderMaterial, Vector3 } from 'three';
import { mergeVertices } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { GOLD, NOISE } from './glsl';
import { sceneClock } from './clock';

/* --- tiny deterministic 3D value noise for the CPU-side sculpt --- */
function hash(x: number, y: number, z: number) {
  const s = Math.sin(x * 127.1 + y * 311.7 + z * 74.7) * 43758.5453;
  return s - Math.floor(s);
}
function smooth(t: number) {
  return t * t * (3 - 2 * t);
}
function valueNoise(x: number, y: number, z: number) {
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
  const xf = smooth(x - xi), yf = smooth(y - yi), zf = smooth(z - zi);
  const l = (a: number, b: number, t: number) => a + (b - a) * t;
  const c = (dx: number, dy: number, dz: number) => hash(xi + dx, yi + dy, zi + dz);
  return l(
    l(l(c(0, 0, 0), c(1, 0, 0), xf), l(c(0, 1, 0), c(1, 1, 0), xf), yf),
    l(l(c(0, 0, 1), c(1, 0, 1), xf), l(c(0, 1, 1), c(1, 1, 1), xf), yf),
    zf,
  );
}
function fbm(x: number, y: number, z: number) {
  let v = 0, a = 0.5, f = 1;
  for (let i = 0; i < 5; i++) {
    v += a * (valueNoise(x * f, y * f, z * f) * 2 - 1);
    f *= 2.1;
    a *= 0.5;
  }
  return v;
}

function sculptNugget() {
  const base = mergeVertices(new IcosahedronGeometry(1, 48));
  const pos = base.attributes.position;
  const v = new Vector3();
  for (let i = 0; i < pos.count; i++) {
    v.fromBufferAttribute(pos, i).normalize();
    // domain-warped lumpy body + ridges + pits, like native alluvial gold
    const wx = fbm(v.x * 1.7 + 11, v.y * 1.7, v.z * 1.7) * 0.6;
    const wy = fbm(v.x * 1.7, v.y * 1.7 + 23, v.z * 1.7) * 0.6;
    const broad = fbm(v.x * 2.2 + wx + 3.1, v.y * 2.2 + wy, v.z * 2.2 - 2.0) * 0.55;
    const ridged = (0.5 - Math.abs(fbm(v.x * 3.4 + 7, v.y * 3.4 + 9, v.z * 3.4))) * 0.16;
    const pits = Math.max(0, fbm(v.x * 5.5 + 4, v.y * 5.5, v.z * 5.5 + 1) - 0.12) * -0.2;
    // a couple of flat-ish facets read as cleaved metal
    const facet = Math.max(0, v.x * 0.6 + v.y * 0.7 - 0.55) * -0.35;
    const r = 1 + broad + ridged + pits + facet;
    v.multiplyScalar(r);
    v.set(v.x * 1.18, v.y * 0.86, v.z * 0.98);
    pos.setXYZ(i, v.x, v.y, v.z);
  }
  base.computeVertexNormals();
  return base;
}

const vertex = /* glsl */ `
varying vec3 vNormalW;
varying vec3 vPosW;
varying vec3 vObj;
void main(){
  vObj = position;
  vec4 w = modelMatrix * vec4(position, 1.0);
  vPosW = w.xyz;
  vNormalW = normalize(mat3(modelMatrix) * normal);
  gl_Position = projectionMatrix * viewMatrix * w;
}
`;

const fragment = /* glsl */ `
${NOISE}
${GOLD}
uniform float uTime;
varying vec3 vNormalW;
varying vec3 vPosW;
varying vec3 vObj;
void main(){
  vec3 V = normalize(cameraPosition - vPosW);
  vec3 N = normalize(vNormalW);
  // hammered micro texture
  vec3 p = vObj * 9.0;
  float a = snoise(p);
  float b = snoise(p + 11.7);
  float c = snoise(p - 5.3);
  N = normalize(N + vec3(a, b, c) * 0.08);
  float rough = 0.22 + 0.18 * smoothstep(-0.2, 0.6, snoise(vObj * 3.0));
  vec3 col = shadeGold(N, V, rough, vec3(1.0, 0.97, 0.9));
  // heat from the scanning beam below
  float under = smoothstep(0.2, -1.0, vObj.y);
  col += vec3(1.0, 0.55, 0.15) * under * 0.25 * (0.75 + 0.25 * sin(uTime * 2.0));
  gl_FragColor = vec4(col, 1.0);
}
`;

export function GoldNugget({ position = [0, 0, 0] as [number, number, number], scale = 0.78 }) {
  const group = useRef<Group>(null);
  const mat = useRef<ShaderMaterial>(null);
  const geometry = useMemo(sculptNugget, []);
  const uniforms = useMemo(() => ({ uTime: { value: 0 } }), []);

  useFrame(() => {
    const t = sceneClock.time;
    if (mat.current) mat.current.uniforms.uTime.value = t;
    const g = group.current;
    if (!g) return;
    g.rotation.y = t * 0.35;
    g.rotation.x = 0.35 + Math.sin(t * 0.4) * 0.18;
    g.rotation.z = Math.sin(t * 0.27) * 0.2;
    g.position.y = position[1] + Math.sin(t * 0.9) * 0.12;
  });

  return (
    <group ref={group} position={position} scale={scale}>
      <mesh geometry={geometry}>
        <shaderMaterial ref={mat} vertexShader={vertex} fragmentShader={fragment} uniforms={uniforms} />
      </mesh>
    </group>
  );
}
