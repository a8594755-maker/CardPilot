// ── Chip Animation Types & Settings ──

export type AnimationSpeed = "off" | "fast" | "normal";

export interface ChipTransfer {
  id: string;
  from: { x: number; y: number };
  to: { x: number; y: number };
  amount: number;
  kind: "toPot" | "toWinner";
  seat?: number;
  createdAt: number;
  /** Duration in ms — derived from speed setting */
  duration: number;
}

// ── Speed presets (ms) ──
const SPEED_MAP: Record<AnimationSpeed, { toPot: number; toWinner: number }> = {
  off: { toPot: 0, toWinner: 0 },
  fast: { toPot: 250, toWinner: 400 },
  normal: { toPot: 450, toWinner: 750 },
};

export function getDuration(speed: AnimationSpeed, kind: ChipTransfer["kind"]): number {
  return SPEED_MAP[speed][kind];
}

// ── LocalStorage persistence ──
const STORAGE_KEY = "cardpilot_chip_anim_speed";

export function loadAnimationSpeed(): AnimationSpeed {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "off" || v === "fast" || v === "normal") return v;
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
