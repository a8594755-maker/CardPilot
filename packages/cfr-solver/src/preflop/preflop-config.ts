// Preflop solver configurations for different game formats.
//
// Each config defines the betting structure, stack depth, and solver parameters
// for a specific game type.

import type { PreflopSolveConfig } from './preflop-types.js';

// ── Predefined configs ──

export const PREFLOP_CONFIGS: Record<string, PreflopSolveConfig> = {
  cash_6max_100bb: {
    name: 'cash_6max_100bb',
    players: 6,
    stackSize: 100,
    sbSize: 0.5,
    bbSize: 1.0,
    ante: 0,
    openSize: 2.5,
    threeBetIPMultiplier: 3.0,   // 3× open = 7.5bb
    threeBetOOPMultiplier: 3.5,  // 3.5× open = 8.75bb
    fourBetMultiplier: 2.25,     // 2.25× 3bet
    iterations: 1_000_000,
    realizationIP: 1.0,
    realizationOOP: 0.60,  // Quadratic model: k = 0.40, max IP bonus = 10% of pot
    rake: 0.05,            // 5% rake (standard online cash game)
    rakeCap: 3.0,          // 3bb cap
  },

  cash_6max_50bb: {
    name: 'cash_6max_50bb',
    players: 6,
    stackSize: 50,
    sbSize: 0.5,
    bbSize: 1.0,
    ante: 0,
    openSize: 2.5,
    threeBetIPMultiplier: 3.0,
    threeBetOOPMultiplier: 3.5,
    fourBetMultiplier: 2.25,
    iterations: 1_000_000,
    realizationIP: 1.0,
    realizationOOP: 0.60,  // Quadratic model: k = 0.40, max IP bonus = 10% of pot
    rake: 0.05,            // 5% rake
    rakeCap: 2.0,          // 2bb cap (shallower stacks → lower cap)
  },

  cash_6max_100bb_ante: {
    name: 'cash_6max_100bb_ante',
    players: 6,
    stackSize: 100,
    sbSize: 0.5,
    bbSize: 1.0,
    ante: 0.25,               // 0.25bb per player = 1.5bb total ante
    openSize: 2.5,
    threeBetIPMultiplier: 3.0,
    threeBetOOPMultiplier: 3.5,
    fourBetMultiplier: 2.25,
    iterations: 1_000_000,
    realizationIP: 1.0,
    realizationOOP: 0.60,  // Quadratic model: k = 0.40, max IP bonus = 10% of pot
    rake: 0.05,            // 5% rake
    rakeCap: 3.0,          // 3bb cap
  },
};

export type PreflopConfigName = keyof typeof PREFLOP_CONFIGS;

export function getPreflopConfig(name: string): PreflopSolveConfig {
  const config = PREFLOP_CONFIGS[name];
  if (!config) {
    throw new Error(`Unknown preflop config: ${name}. Available: ${Object.keys(PREFLOP_CONFIGS).join(', ')}`);
  }
  return config;
}

// ── Sizing helpers ──

/**
 * Compute the 3-bet size given the open size and whether the 3-bettor is IP or OOP.
 */
export function compute3BetSize(config: PreflopSolveConfig, isIP: boolean): number {
  const mult = isIP ? config.threeBetIPMultiplier : config.threeBetOOPMultiplier;
  return Math.min(config.openSize * mult, config.stackSize);
}

/**
 * Compute the 4-bet size given the 3-bet size.
 */
export function compute4BetSize(config: PreflopSolveConfig, threeBetSize: number): number {
  return Math.min(threeBetSize * config.fourBetMultiplier, config.stackSize);
}

/**
 * Compute initial pot (blinds + antes).
 */
export function computeInitialPot(config: PreflopSolveConfig): number {
  return config.sbSize + config.bbSize + config.ante * config.players;
}

/**
 * Determine if a seat is "in position" relative to another in postflop.
 * BTN(3) > CO(2) > HJ(1) > MP/UTG(0) > BB(5) > SB(4) in positional advantage.
 * More precisely: the player who acts LAST postflop is IP.
 * Postflop order (heads-up): SB/BB acts first, BTN last.
 * General rule: higher seat index among non-blind = more IP.
 */
export function isIPPostflop(seatA: number, seatB: number): boolean {
  // In heads-up pots, the player closer to the button acts last postflop.
  // For blinds: SB acts first, BB acts second.
  // For non-blinds vs blinds: non-blind acts last (IP).
  // For non-blind vs non-blind: higher seat (closer to BTN) acts last (IP).

  // Postflop acting order: SB(4) → BB(5) → UTG(0) → HJ(1) → CO(2) → BTN(3)
  const postflopOrder = [4, 5, 0, 1, 2, 3]; // index = acting position (earlier = OOP)
  const orderA = postflopOrder.indexOf(seatA);
  const orderB = postflopOrder.indexOf(seatB);
  return orderA > orderB; // Later = IP
}
