/** Haptic feedback via Vibration API. No-ops on desktop or unsupported browsers. */

type HapticPattern = 'tap' | 'action' | 'turn' | 'win' | 'error' | 'bounty';

const PATTERNS: Record<HapticPattern, number | number[]> = {
  tap: 8,
  action: 15,
  turn: [12, 50, 12],
  win: [15, 40, 15, 40, 20],
  error: [30, 30, 30],
  bounty: [20, 40, 20, 40, 30, 40, 30],
};

export function haptic(pattern: HapticPattern): void {
  if (typeof navigator === 'undefined' || typeof navigator.vibrate !== 'function') return;
  try {
    navigator.vibrate(PATTERNS[pattern]);
  } catch {
    /* silently ignore */
  }
}
