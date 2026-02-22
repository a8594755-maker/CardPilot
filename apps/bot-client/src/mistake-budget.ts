// ===== Controlled mistake injection =====
// Small, controllable deviations to make bot behavior more human-like

import type { Mix } from './types.js';

export interface MistakeConfig {
  enabled: boolean;
  mistakeEveryNHands: number;     // e.g., 25
  maxMistakeMagnitude: number;    // 0.0 - 1.0
  allowedSpots: 'all' | 'non_critical_only';
}

export interface MistakeResult {
  applied: boolean;
  description: string;
  sizingLeak: boolean; // if true, sizing engine should pick suboptimal size
}

// ===== Default configs per profile =====
export const DEFAULT_MISTAKE_CONFIGS: Record<string, MistakeConfig> = {
  gto_balanced: {
    enabled: false,
    mistakeEveryNHands: 999,
    maxMistakeMagnitude: 0,
    allowedSpots: 'non_critical_only',
  },
  limp_fish: {
    enabled: true,
    mistakeEveryNHands: 15,
    maxMistakeMagnitude: 0.6,
    allowedSpots: 'all',
  },
  tag: {
    enabled: true,
    mistakeEveryNHands: 30,
    maxMistakeMagnitude: 0.3,
    allowedSpots: 'non_critical_only',
  },
  lag: {
    enabled: true,
    mistakeEveryNHands: 20,
    maxMistakeMagnitude: 0.4,
    allowedSpots: 'non_critical_only',
  },
  nit: {
    enabled: true,
    mistakeEveryNHands: 40,
    maxMistakeMagnitude: 0.2,
    allowedSpots: 'non_critical_only',
  },
  postflop_trainer: {
    enabled: false,
    mistakeEveryNHands: 999,
    maxMistakeMagnitude: 0,
    allowedSpots: 'non_critical_only',
  },
};

function normalize(m: Mix): Mix {
  const sum = m.raise + m.call + m.fold;
  if (sum <= 0) return { raise: 0, call: 0, fold: 1 };
  return { raise: m.raise / sum, call: m.call / sum, fold: m.fold / sum };
}

// ===== Check if mistake should be injected =====
export function shouldInjectMistake(
  config: MistakeConfig | undefined,
  handNumber: number,
  handStrength: number,
  potSizeBB: number,
  isAllInDecision: boolean,
): boolean {
  if (!config || !config.enabled) return false;
  if (isAllInDecision) return false;
  if (config.allowedSpots === 'non_critical_only' && potSizeBB > 20) return false;

  // Strong hands: don't make mistakes (protect value)
  if (handStrength >= 0.80) return false;

  // Use hand number modulo for deterministic-ish timing
  if (handNumber % config.mistakeEveryNHands !== 0) return false;

  return true;
}

// ===== Inject a mistake into the mix =====
export function injectMistake(
  mix: Mix,
  config: MistakeConfig,
  handStrength: number,
  potSizeBB: number,
): { mix: Mix; result: MistakeResult } {
  // Error magnitude inversely proportional to hand strength and pot size
  const magnitude = config.maxMistakeMagnitude
    * (1 - handStrength)
    * Math.min(1, 10 / Math.max(potSizeBB, 1));

  const r = Math.random();
  let newMix = { ...mix };
  let description: string;
  let sizingLeak = false;

  if (r < 0.4) {
    // Passive leak: shift raise → call (called instead of raising)
    const shift = newMix.raise * magnitude * 0.5;
    newMix.raise -= shift;
    newMix.call += shift;
    description = 'passive_leak';
  } else if (r < 0.7) {
    // Loose leak: shift fold → call (called instead of folding)
    const shift = newMix.fold * magnitude * 0.3;
    newMix.fold -= shift;
    newMix.call += shift;
    description = 'loose_leak';
  } else {
    // Sizing leak: will affect sizing step
    sizingLeak = true;
    description = 'sizing_leak';
  }

  return {
    mix: normalize(newMix),
    result: {
      applied: true,
      description,
      sizingLeak,
    },
  };
}
