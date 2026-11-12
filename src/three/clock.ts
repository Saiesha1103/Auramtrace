/**
 * Single source of truth for scene time and pointer state, advanced once per
 * frame by <SceneDriver/>. Components read from here instead of each running
 * their own clocks, which keeps every element moving in one rhythm.
 */
export const sceneClock = {
  time: 8.0, // non-zero start so the first frame is already a composed pose
  /** pointer in normalised device coords, smoothed (-1..1) */
  px: 0,
  py: 0,
  /** pointer projected onto the scene's z=0 plane (local space), smoothed */
  wx: 0,
  wy: 0,
  /** 0..1 how strongly the pointer is "present" (eases out when idle/absent, so particles settle) */
  presence: 0,
  /** 0..1 how far the hero has been scrolled out (raw, set by ScrollTrigger) */
  scroll: 0,
  /** eased copy of `scroll`, used for motion so it never steps */
  scrollEased: 0,
  /** custody progression along the loop: 0 = Issue current … 4 = Reconcile current */
  nodeProgress: 0,
};

/**
 * Hero scroll range over which custody nodes activate one after another.
 * Wide layouts: the scene is beside the copy, so it plays over the first scroll gesture
 * (before upper labels reach the nav). Narrow layouts: the scene sits below the copy,
 * so it plays once the scene has scrolled into view.
 */
export const NODE_SCROLL_RANGE: [number, number] = [0.0, 0.14];
export const NODE_SCROLL_RANGE_NARROW: [number, number] = [0.2, 0.55];
