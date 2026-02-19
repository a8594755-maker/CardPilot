// ── Chip Animation Types & Settings ──

export type AnimationSpeed = "off" | "normal" | "slow";

export interface ChipTransfer {
  id: string;
  from: { x: number; y: number };
  to: { x: number; y: number };
  amount: number;
  kind: "toPot" | "toWinner";
  seat?: number;
  createdAt: number;
  /** Stage durations derived from speed setting */
  timing: StageTiming;
}

/** 3-stage timing for each chip transfer animation */
export interface StageTiming {
  /** Stage 1: flight from origin to destination */
  flight: number;
  /** Stage 2: hold/pause at destination */
  hold: number;
  /** Stage 3: merge/fade into stack */
  merge: number;
  /** Pot pulse duration on arrival (toPot only) */
  potPulse: number;
  /** Winner glow duration on arrival (toWinner only) */
  winnerGlow: number;
}

// ── Speed presets (ms) ──

interface SpeedPreset {
  toPot: StageTiming;
  toWinner: StageTiming;
}

const SPEED_MAP: Record<AnimationSpeed, SpeedPreset> = {
  off: {
    toPot: { flight: 0, hold: 0, merge: 0, potPulse: 0, winnerGlow: 0 },
    toWinner: { flight: 0, hold: 0, merge: 0, potPulse: 0, winnerGlow: 0 },
  },
  normal: {
    toPot: { flight: 240, hold: 110, merge: 90, potPulse: 240, winnerGlow: 0 },
    toWinner: { flight: 300, hold: 120, merge: 100, potPulse: 0, winnerGlow: 300 },
  },
  slow: {
    toPot: { flight: 340, hold: 150, merge: 120, potPulse: 320, winnerGlow: 0 },
    toWinner: { flight: 420, hold: 170, merge: 130, potPulse: 0, winnerGlow: 380 },
  },
};

export function getTiming(speed: AnimationSpeed, kind: ChipTransfer["kind"]): StageTiming {
  return SPEED_MAP[speed][kind];
}

/** Total duration of all 3 stages combined */
export function getTotalDuration(timing: StageTiming): number {
  return timing.flight + timing.hold + timing.merge;
}

// ── LocalStorage persistence ──
const STORAGE_KEY = "cardpilot_chip_anim_speed";

export function loadAnimationSpeed(): AnimationSpeed {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "off" || v === "normal" || v === "slow") return v;
  } catch { /* SSR / privacy */ }
  // Respect prefers-reduced-motion
  if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return "off";
  }
  return "normal";
}

export function saveAnimationSpeed(speed: AnimationSpeed): void {
  try {
    localStorage.setItem(STORAGE_KEY, speed);
  } catch { /* ignore */ }
}

/** Check if user prefers reduced motion */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// ── Anchor utilities ──

/**
 * Get the center of `el` in coordinates relative to `container`.
 * Returns null if either element is missing.
 */
export function getAnchorCenter(
  el: HTMLElement | null,
  container: HTMLElement | null,
): { x: number; y: number } | null {
  if (!el || !container) return null;
  const er = el.getBoundingClientRect();
  const cr = container.getBoundingClientRect();
  return {
    x: er.left + er.width / 2 - cr.left,
    y: er.top + er.height / 2 - cr.top,
  };
}

let _nextId = 0;
export function nextTransferId(): string {
  return `ct-${++_nextId}-${Date.now()}`;
}
