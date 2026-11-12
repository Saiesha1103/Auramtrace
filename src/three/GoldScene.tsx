import { useEffect, useMemo, useRef } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Color, Group, Plane, Raycaster, Vector2, Vector3 } from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { LiquidRibbon, type StrandConfig } from './LiquidRibbon';
import { GoldNugget } from './GoldNugget';
import { HoloPlatform } from './HoloPlatform';
import { GoldParticles } from './GoldParticles';
import { WaveField } from './WaveField';
import { CustodyNodes } from './CustodyNodes';
import { NODE_SCROLL_RANGE, NODE_SCROLL_RANGE_NARROW, sceneClock } from './clock';
import { CUSTODY_NODES } from './nodes';

export interface GoldSceneProps {
  /** render continuously (hero on screen) or pause */
  active: boolean;
  /** prefers-reduced-motion: freeze time, render a single composed frame */
  reduced: boolean;
  /** lower geometry / particle budgets */
  lite: boolean;
  onReady?: () => void;
}

const STRANDS: StrandConfig[] = [
  { width: 0.46, thickness: 0.12, twist: 1, offset: 0, phase: 0, ripple: 0.06, glow: 1, segU: 900, segV: 28 },
  { width: 0.07, thickness: 0.05, twist: 3, offset: 0.62, phase: 1.7, ripple: 0.12, glow: 1.4, segU: 700, segV: 10 },
  { width: 0.05, thickness: 0.04, twist: 2, offset: 0.58, phase: 4.2, ripple: 0.1, glow: 1.4, segU: 700, segV: 10 },
  { width: 0.16, thickness: 0.035, twist: 2, offset: 0.92, phase: 2.9, ripple: 0.08, glow: 1.1, segU: 700, segV: 12 },
];
const STRANDS_LITE: StrandConfig[] = STRANDS.slice(0, 3).map((s) => ({
  ...s,
  segU: Math.round(s.segU * 0.6),
  segV: Math.max(8, Math.round(s.segV * 0.6)),
}));

/* ---------------------------------------------------------------- driver */

const pointerNdc = new Vector2(0, 0);
/** 1 while a pointer is moving over the page, 0 once it leaves / a touch ends */
const pointerState = { target: 0, lastMove: 0 };
const raycaster = new Raycaster();
const plane = new Plane(new Vector3(0, 0, 1), 0);
const hit = new Vector3();
const lookTarget = new Vector3();
const ndc = new Vector2();
const rigOrigin = new Vector3();

const ease = (delta: number, rate: number) => 1 - Math.pow(rate, Math.min(delta, 0.1)); // frame-rate independent

function SceneDriver({ reduced, lite, rig }: { reduced: boolean; lite: boolean; rig: React.RefObject<Group | null> }) {
  const { camera } = useThree();
  const wide = useThree((s) => s.size.width / s.size.height >= 1.15);
  const setDpr = useThree((s) => s.setDpr);
  const perf = useRef({ acc: 0, frames: 0, dpr: Math.min(window.devicePixelRatio || 1, lite ? 1.25 : 1.75) });

  useFrame((_, delta) => {
    if (!reduced) sceneClock.time += Math.min(delta, 1 / 20);
    const k = reduced ? 1 : ease(delta, 0.0025);
    const kSlow = reduced ? 1 : ease(delta, 0.02);

    // pointer presence fades out after ~2.5s idle so particles settle back into place
    const idle = performance.now() - pointerState.lastMove > 2500;
    const presenceTarget = idle ? 0 : pointerState.target;
    sceneClock.presence += (presenceTarget - sceneClock.presence) * kSlow;

    // with no pointer (touch, idle), a slow figure-eight drift keeps a gentle parallax alive
    const t = sceneClock.time;
    const driftW = 1 - sceneClock.presence;
    const tx = pointerNdc.x * sceneClock.presence + Math.sin(t * 0.17) * 0.22 * driftW;
    const ty = pointerNdc.y * sceneClock.presence + Math.sin(t * 0.11 + 1.3) * 0.14 * driftW;
    sceneClock.px += (tx - sceneClock.px) * k * 0.5;
    sceneClock.py += (ty - sceneClock.py) * k * 0.5;

    // scroll is eased so dolly and custody progression glide instead of stepping
    sceneClock.scrollEased += (sceneClock.scroll - sceneClock.scrollEased) * (reduced ? 1 : ease(delta, 0.004));
    const [a, b] = wide ? NODE_SCROLL_RANGE : NODE_SCROLL_RANGE_NARROW;
    const p = Math.min(1, Math.max(0, (sceneClock.scrollEased - a) / (b - a)));
    sceneClock.nodeProgress = p * (CUSTODY_NODES.length - 1);

    // camera parallax + scroll dolly
    const s = sceneClock.scrollEased;
    const cx = sceneClock.px * 0.7;
    const cy = 1.4 + sceneClock.py * 0.45 + s * 1.2;
    camera.position.x += (cx - camera.position.x) * k * 0.6;
    camera.position.y += (cy - camera.position.y) * k * 0.6;
    camera.position.z = 14 + s * 3.5;
    lookTarget.set(sceneClock.px * 0.25, -0.25 - s * 0.6, 0);
    camera.lookAt(lookTarget);

    // project pointer onto the rig's z=0 plane for particle interaction
    const g = rig.current;
    if (g) {
      raycaster.setFromCamera(ndc.set(sceneClock.px, sceneClock.py), camera);
      g.updateWorldMatrix(true, false);
      plane.normal.set(0, 0, 1).transformDirection(g.matrixWorld);
      plane.constant = -plane.normal.dot(rigOrigin.setFromMatrixPosition(g.matrixWorld));
      if (raycaster.ray.intersectPlane(plane, hit)) {
        g.worldToLocal(hit);
        sceneClock.wx = hit.x;
        sceneClock.wy = hit.y;
      }
    }

    // adaptive resolution: if frames run long for ~1s, step the pixel ratio down (never below 1)
    if (!reduced) {
      const pf = perf.current;
      pf.acc += delta;
      pf.frames++;
      if (pf.frames >= 60) {
        const avg = pf.acc / pf.frames;
        if (avg > 1 / 42 && pf.dpr > 1) {
          pf.dpr = Math.max(1, pf.dpr - 0.25);
          setDpr(pf.dpr);
        }
        pf.acc = 0;
        pf.frames = 0;
      }
    }
  }, -1);
  return null;
}

/** In reduced-motion mode the canvas renders on demand; redraw when scroll changes node progression. */
function DemandOnScroll() {
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    const on = () => invalidate();
    window.addEventListener('scroll', on, { passive: true });
    return () => window.removeEventListener('scroll', on);
  }, [invalidate]);
  return null;
}

/* ------------------------------------------------------------- post fx */

function PostFX({ lite }: { lite: boolean }) {
  const { gl, scene, camera, size } = useThree();
  const dpr = useThree((s) => s.viewport.dpr);
  const composer = useMemo(() => {
    const c = new EffectComposer(gl);
    c.addPass(new RenderPass(scene, camera));
    const bloom = new UnrealBloomPass(new Vector2(256, 256), lite ? 0.38 : 0.48, 0.45, 0.92);
    c.addPass(bloom);
    c.addPass(new OutputPass());
    return c;
  }, [gl, scene, camera, lite]);

  useEffect(() => {
    composer.setPixelRatio(gl.getPixelRatio());
    composer.setSize(size.width, size.height);
  }, [composer, gl, size, dpr]);

  useEffect(() => () => composer.dispose(), [composer]);

  useFrame((_, delta) => composer.render(delta), 1);
  return null;
}

/* ---------------------------------------------------------------- layout */

function Rig({ lite, reduced }: { lite: boolean; reduced: boolean }) {
  const rig = useRef<Group>(null);
  const flow = useRef<Group>(null);
  const dust = useRef<Group>(null);
  const floor = useRef<Group>(null);
  const { viewport, size } = useThree();
  const wide = size.width / size.height >= 1.15;

  // composition: scene sits right of the copy on wide screens, below it on narrow
  const vw = viewport.getCurrentViewport().width;
  const x = wide ? Math.min(Math.max(vw * 0.27, 1.8), 4.8) : 0.6;
  const y = wide ? -0.15 : -2.2;
  const scale = wide ? Math.min(0.92, vw / 18.5) : Math.min(0.7, vw / 9.5);

  useFrame(() => {
    if (!flow.current) return;
    const t = sceneClock.time;
    flow.current.rotation.y = -0.5 + Math.sin(t * 0.15) * 0.07 + sceneClock.px * 0.08;
    flow.current.rotation.x = 0.1 - sceneClock.py * 0.05;
    // gentle depth layering: near dust drifts against the camera, the floor lags behind the scroll
    if (dust.current) dust.current.position.set(-sceneClock.px * 0.35, -sceneClock.py * 0.2, 0);
    if (floor.current) floor.current.position.y = sceneClock.scrollEased * 0.9;
  });

  const strands = lite ? STRANDS_LITE : STRANDS;

  return (
    <>
      <SceneDriver reduced={reduced} lite={lite} rig={rig} />
      <group ref={rig} position={[x, y, 0]} scale={scale}>
        {/* the right lobe of the loop wraps the nugget; the left lobe sweeps down under the copy */}
        <group ref={flow}>
          <group position={[-2.55, 0.05, 0]} rotation={[0, 0, 0.3]}>
            {strands.map((s, i) => (
              <LiquidRibbon key={i} config={s} />
            ))}
            <CustodyNodes />
          </group>
        </group>
        <GoldNugget position={[0, 0.35, 0]} scale={0.7} />
        <HoloPlatform y={-2.3} />
        <group ref={dust}>
        <GoldParticles
          count={lite ? 700 : 1800}
          spread={[16, 10, 8]}
          size={lite ? 26 : 22}
          rise={0.12}
          intensity={0.9}
        />
        <GoldParticles
          count={lite ? 80 : 160}
          spread={[3.2, 5, 3]}
          centre={[0, 0.2, 0]}
          size={34}
          rise={0.35}
          intensity={1.2}
          seed={21}
        />
        </group>
      </group>
      <group ref={floor}>
        <WaveField density={lite ? 0.6 : 1} />
      </group>
    </>
  );
}

/* ---------------------------------------------------------------- canvas */

export default function GoldScene({ active, reduced, lite, onReady }: GoldSceneProps) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (reduced) return;
    const onMove = (e: PointerEvent) => {
      const el = host.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      pointerNdc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      pointerState.target = 1;
      pointerState.lastMove = performance.now();
    };
    const onLeave = () => {
      pointerState.target = 0;
    };
    const onUp = (e: PointerEvent) => {
      if (e.pointerType !== 'mouse') pointerState.target = 0; // a lifted finger is no longer "present"
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    document.documentElement.addEventListener('pointerleave', onLeave);
    window.addEventListener('pointerup', onUp, { passive: true });
    window.addEventListener('pointercancel', onUp, { passive: true });
    return () => {
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
      window.removeEventListener('pointermove', onMove);
      document.documentElement.removeEventListener('pointerleave', onLeave);
    };
  }, [reduced]);

  return (
    <div ref={host} className="gold-canvas">
      <Canvas
        dpr={lite ? [1, 1.25] : [1, 1.75]}
        frameloop={reduced ? 'demand' : active ? 'always' : 'never'}
        camera={{ fov: 32, position: [0, 1.4, 14], near: 0.1, far: 80 }}
        gl={{ antialias: false, alpha: false, powerPreference: 'high-performance', stencil: false }}
        onCreated={({ gl, scene }) => {
          scene.background = new Color('#060504');
          gl.toneMappingExposure = 0.9;
          // give the browser one frame to paint before revealing
          requestAnimationFrame(() => onReady?.());
        }}
      >
        <Rig lite={lite} reduced={reduced} />
        {reduced && <DemandOnScroll />}
        <PostFX lite={lite} />
      </Canvas>
    </div>
  );
}
