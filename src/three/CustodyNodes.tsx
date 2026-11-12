import { useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { AdditiveBlending, BufferAttribute, BufferGeometry, Group, Points, ShaderMaterial, Vector3 } from 'three';
import { flowCurve } from './curve';
import { CUSTODY_NODES, labelSafe, nodeLabelEls } from './nodes';
import { sceneClock } from './clock';

const vertex = /* glsl */ `
uniform float uTime;
uniform float uPixelRatio;
uniform float uProgress;
attribute float aIndex;
varying float vPulse;
varying float vCurrent;
varying float vReached;
void main(){
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_Position = projectionMatrix * mv;
  vPulse = fract(uTime * 0.45 - aIndex * 0.18);
  // custody progression: the current node swells, passed nodes stay lit
  vCurrent = 1.0 - clamp(abs(uProgress - aIndex), 0.0, 1.0);
  vReached = clamp(uProgress - aIndex + 1.0, 0.0, 1.0);
  gl_PointSize = 150.0 * uPixelRatio * (1.0 + vCurrent * 0.45) / -mv.z;
}
`;
const fragment = /* glsl */ `
varying float vPulse;
varying float vCurrent;
varying float vReached;
void main(){
  float d = length(gl_PointCoord - 0.5) * 2.0;
  float core = smoothstep(0.16, 0.0, d);
  float halo = smoothstep(1.0, 0.0, d);
  halo *= halo;
  float ring = smoothstep(0.05, 0.0, abs(d - (0.25 + vPulse * 0.7))) * (1.0 - vPulse);
  // steady orbit ring marks the node currently in custody
  float orbit = smoothstep(0.045, 0.0, abs(d - 0.46)) * vCurrent;
  vec3 col = vec3(1.0, 0.86, 0.6) * core * (3.0 + vReached * 0.8)
           + vec3(1.0, 0.62, 0.22) * (halo * (0.55 + vReached * 0.25 + vCurrent * 0.35) + ring * 0.9 + orbit * 1.1);
  gl_FragColor = vec4(col, 1.0);
}
`;

const tmp = new Vector3();
const world = new Vector3();

export function CustodyNodes() {
  const group = useRef<Group>(null);
  const pts = useRef<Points>(null);
  const mat = useRef<ShaderMaterial>(null);
  const { camera, size, viewport, gl } = useThree();

  const geometry = useMemo(() => {
    const g = new BufferGeometry();
    g.setAttribute('position', new BufferAttribute(new Float32Array(CUSTODY_NODES.length * 3), 3));
    g.setAttribute('aIndex', new BufferAttribute(new Float32Array(CUSTODY_NODES.map((_, i) => i)), 1));
    return g;
  }, []);
  const uniforms = useMemo(() => ({ uTime: { value: 0 }, uPixelRatio: { value: 1 }, uProgress: { value: 0 } }), []);

  useFrame(() => {
    const t = sceneClock.time;
    const attr = geometry.attributes.position as BufferAttribute;
    if (mat.current) {
      mat.current.uniforms.uTime.value = t;
      mat.current.uniforms.uPixelRatio.value = viewport.dpr;
      mat.current.uniforms.uProgress.value = sceneClock.nodeProgress;
    }
    const g = group.current;
    if (!g) return;
    g.updateWorldMatrix(true, false);
    const current = Math.round(sceneClock.nodeProgress);
    // read layout once, before any label writes this frame
    const canvasRect = gl.domElement.getBoundingClientRect();
    const blocks = labelSafe.copyEls.map((e) => e.getBoundingClientRect());
    CUSTODY_NODES.forEach((node, i) => {
      flowCurve(node.u, t, tmp);
      attr.setXYZ(i, tmp.x, tmp.y, tmp.z);
      const el = nodeLabelEls[i];
      if (!el) return;
      world.copy(tmp).applyMatrix4(g.matrixWorld).project(camera);
      const x = (world.x * 0.5 + 0.5) * size.width;
      const y = (-world.y * 0.5 + 0.5) * size.height;
      el.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0)`;
      // card box in viewport px: centred on the anchor, ~30–95px above it
      let w = Number(el.dataset.w);
      if (!w) {
        w = (el.firstElementChild as HTMLElement | null)?.offsetWidth ?? 190;
        if (w) el.dataset.w = String(w);
      }
      const L = canvasRect.left + x - w / 2;
      const R = L + w;
      const T = canvasRect.top + y - 98;
      const B = canvasRect.top + y - 24;
      const overlapsCopy = blocks.some((r) => L < r.right + 14 && R > r.left - 14 && T < r.bottom + 10 && B > r.top - 10);
      const hide = overlapsCopy || T < labelSafe.minY || world.z > 1;
      if (el.dataset.hidden !== String(hide)) {
        el.dataset.hidden = String(hide);
        el.style.opacity = hide ? '0' : '1';
      }
      const state = i === current ? 'current' : i < current ? 'reached' : 'upcoming';
      if (el.dataset.state !== state) el.dataset.state = state;
    });
    attr.needsUpdate = true;
  });

  return (
    <group ref={group}>
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
    </group>
  );
}
