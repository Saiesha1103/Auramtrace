import { useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { AdditiveBlending, BufferAttribute, BufferGeometry, ShaderMaterial } from 'three';
import { sceneClock } from './clock';

/** Dotted "data terrain" that rolls beneath the scene, plus a fading floor grid. */
const dotsVertex = /* glsl */ `
uniform float uTime;
uniform float uPixelRatio;
varying float vA;
void main(){
  vec3 p = position;
  float t = uTime * 0.5;
  float h = sin(p.x * 0.35 + t) * 0.45 + sin(p.z * 0.5 - t * 0.8 + p.x * 0.15) * 0.35
          + sin((p.x + p.z) * 0.9 + t * 1.3) * 0.08;
  p.y += h;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = (2.2 + h * 1.2) * uPixelRatio * (10.0 / -mv.z);
  float edge = smoothstep(16.0, 6.0, abs(p.x)) * smoothstep(-14.0, -4.0, p.z) * smoothstep(7.0, 2.0, p.z);
  vA = (0.25 + 0.75 * smoothstep(-0.3, 0.8, h)) * edge;
}
`;
const dotsFragment = /* glsl */ `
varying float vA;
void main(){
  float d = length(gl_PointCoord - 0.5);
  float a = smoothstep(0.5, 0.1, d) * vA;
  gl_FragColor = vec4(vec3(1.0, 0.68, 0.3) * a * 0.55, 1.0);
}
`;

const gridVertex = /* glsl */ `
varying vec3 vW;
void main(){
  vec4 w = modelMatrix * vec4(position, 1.0);
  vW = w.xyz;
  gl_Position = projectionMatrix * viewMatrix * w;
}
`;
const gridFragment = /* glsl */ `
uniform float uTime;
varying vec3 vW;
float line(float x, float w){ float f = abs(fract(x) - 0.5); return smoothstep(w, 0.0, 0.5 - f); }
void main(){
  vec2 g = vW.xz * 0.9;
  float l = max(line(g.x, 0.035), line(g.y + uTime * 0.05, 0.035));
  float fade = smoothstep(11.0, 2.0, length(vW.xz - vec2(0.0, -2.0)));
  gl_FragColor = vec4(vec3(0.85, 0.52, 0.18) * l * fade * 0.06, 1.0);
}
`;

export function WaveField({ density = 1 }: { density?: number }) {
  const dotsMat = useRef<ShaderMaterial>(null);
  const gridMat = useRef<ShaderMaterial>(null);
  const dpr = useThree((s) => s.viewport.dpr);

  const geometry = useMemo(() => {
    const nx = Math.round(170 * density);
    const nz = Math.round(70 * density);
    const pos = new Float32Array(nx * nz * 3);
    let k = 0;
    for (let i = 0; i < nx; i++) {
      for (let j = 0; j < nz; j++) {
        pos[k++] = (i / (nx - 1) - 0.5) * 34;
        pos[k++] = 0;
        pos[k++] = (j / (nz - 1)) * -16 + 6;
      }
    }
    const g = new BufferGeometry();
    g.setAttribute('position', new BufferAttribute(pos, 3));
    return g;
  }, [density]);

  const dotsU = useMemo(() => ({ uTime: { value: 0 }, uPixelRatio: { value: 1 } }), []);
  const gridU = useMemo(() => ({ uTime: { value: 0 } }), []);

  useFrame(() => {
    if (dotsMat.current) {
      dotsMat.current.uniforms.uTime.value = sceneClock.time;
      dotsMat.current.uniforms.uPixelRatio.value = dpr;
    }
    if (gridMat.current) gridMat.current.uniforms.uTime.value = sceneClock.time;
  });

  const additive = { transparent: true, depthWrite: false, blending: AdditiveBlending } as const;

  return (
    <group>
      <points geometry={geometry} position={[0, -3.6, 0]} frustumCulled={false}>
        <shaderMaterial ref={dotsMat} vertexShader={dotsVertex} fragmentShader={dotsFragment} uniforms={dotsU} {...additive} />
      </points>
      <mesh position={[0, -2.32, -2]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[40, 24]} />
        <shaderMaterial ref={gridMat} vertexShader={gridVertex} fragmentShader={gridFragment} uniforms={gridU} {...additive} />
      </mesh>
    </group>
  );
}
