import { Vector3 } from 'three';

/**
 * The infinity-loop centre line. Implemented twice — once in GLSL for the
 * ribbon surface and once in JS so the custody nodes / HTML labels can sit
 * exactly on the flow. Keep the two in sync.
 */
export const CURVE_PARAMS = {
  sx: 4.9, // horizontal reach of the loop
  sy: 3.5, // vertical lobe height
  sz: 2.0, // depth separation at the crossing (front strand vs. back strand)
};

export const CURVE_GLSL = /* glsl */ `
const float TAU = 6.28318530718;
vec3 flowCurve(float u, float t){
  float a = u * TAU;
  float s = sin(a), c = cos(a);
  float den = 1.0 + s * s;
  vec3 p = vec3(${CURVE_PARAMS.sx.toFixed(3)} * c / den,
                ${CURVE_PARAMS.sy.toFixed(3)} * s * c / den,
                ${CURVE_PARAMS.sz.toFixed(3)} * s);
  // slow breathing so the loop never looks static
  p.y += 0.22 * sin(a * 3.0 + t * 0.55);
  p.z += 0.30 * sin(a * 2.0 - t * 0.40);
  p.x += 0.12 * sin(a * 4.0 + t * 0.35);
  return p;
}
`;

export function flowCurve(u: number, t: number, out = new Vector3()): Vector3 {
  const a = u * Math.PI * 2;
  const s = Math.sin(a);
  const c = Math.cos(a);
  const den = 1 + s * s;
  out.set((CURVE_PARAMS.sx * c) / den, (CURVE_PARAMS.sy * s * c) / den, CURVE_PARAMS.sz * s);
  out.y += 0.22 * Math.sin(a * 3 + t * 0.55);
  out.z += 0.3 * Math.sin(a * 2 - t * 0.4);
  out.x += 0.12 * Math.sin(a * 4 + t * 0.35);
  return out;
}
