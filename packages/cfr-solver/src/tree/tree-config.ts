// Betting tree configuration for HU SRP solver

import type { TreeConfig, BetSizeConfig } from '../types.js';

// V1: HU SRP at 50bb (2 bet sizes per street)
// BTN opens to 2.5bb, BB calls → pot = 5bb, effective stack = 47.5bb
export const V1_BET_SIZES: BetSizeConfig = {
  flop:  [0.33, 0.75],
  turn:  [0.50, 1.00],
  river: [0.75, 1.50],
};

export const V1_TREE_CONFIG: TreeConfig = {
  startingPot: 5,
  effectiveStack: 47.5,
  betSizes: V1_BET_SIZES,
  raiseCapPerStreet: 1,
};

// Standard: 5 bet sizes per street (33%, 50%, 75%, 100%, 150% pot)
export const STANDARD_BET_SIZES: BetSizeConfig = {
  flop:  [0.33, 0.50, 0.75, 1.00, 1.50],
  turn:  [0.33, 0.50, 0.75, 1.00, 1.50],
  river: [0.33, 0.50, 0.75, 1.00, 1.50],
};

// Standard 50bb: 5 sizes, 50bb stack
export const STANDARD_50BB_CONFIG: TreeConfig = {
  startingPot: 5,
  effectiveStack: 47.5,
  betSizes: STANDARD_BET_SIZES,
  raiseCapPerStreet: 1,
};

// Standard 100bb: 5 sizes, 100bb stack
export const STANDARD_100BB_CONFIG: TreeConfig = {
  startingPot: 5,
  effectiveStack: 97.5,
  betSizes: STANDARD_BET_SIZES,
  raiseCapPerStreet: 1,
};

// Pipeline: HU SRP at 50bb — simplified (no raises, 1 bet size per street)
// Designed for bulk CFR solving across all 1,755 isomorphic flops
export const PIPELINE_SRP_BET_SIZES: BetSizeConfig = {
  flop:  [0.33],   // 33% pot
  turn:  [0.66],   // 66% pot
  river: [0.75],   // 75% pot (all-in always available via tree builder)
};

export const PIPELINE_SRP_CONFIG: TreeConfig = {
  startingPot: 5,          // BTN opens 2.5bb, BB calls → pot = 5bb
  effectiveStack: 47.5,    // 50bb - 2.5bb
  betSizes: PIPELINE_SRP_BET_SIZES,
  raiseCapPerStreet: 0,    // No raises — only check/bet/fold/call
};

// Pipeline: HU 3-bet pot at 50bb — simplified (no raises)
export const PIPELINE_3BET_BET_SIZES: BetSizeConfig = {
  flop:  [0.33],   // 33% pot
  turn:  [0.66],   // 66% pot
  river: [0.75],   // 75% pot
};

export const PIPELINE_3BET_CONFIG: TreeConfig = {
  startingPot: 13.5,       // BTN opens 2.5bb, BB 3-bets 8bb, BTN calls → pot ≈ 13.5bb
  effectiveStack: 41.25,   // 50bb - 8.75bb (BB invested)
  betSizes: PIPELINE_3BET_BET_SIZES,
  raiseCapPerStreet: 0,
};

// Config name → TreeConfig registry
export type TreeConfigName =
  | 'v1_50bb'
  | 'standard_50bb'
  | 'standard_100bb'
  | 'pipeline_srp'
  | 'pipeline_3bet';

export function getTreeConfig(name: TreeConfigName): TreeConfig {
  switch (name) {
    case 'v1_50bb': return V1_TREE_CONFIG;
    case 'standard_50bb': return STANDARD_50BB_CONFIG;
    case 'standard_100bb': return STANDARD_100BB_CONFIG;
    case 'pipeline_srp': return PIPELINE_SRP_CONFIG;
    case 'pipeline_3bet': return PIPELINE_3BET_CONFIG;
  }
}

// Default solve params per config
export function getSolveDefaults(name: TreeConfigName): { iterations: number; buckets: number } {
  switch (name) {
    case 'v1_50bb': return { iterations: 50000, buckets: 50 };
    case 'standard_50bb': return { iterations: 200000, buckets: 100 };
    case 'standard_100bb': return { iterations: 200000, buckets: 100 };
    case 'pipeline_srp': return { iterations: 200000, buckets: 100 };
    case 'pipeline_3bet': return { iterations: 200000, buckets: 100 };
  }
}

// Get human-readable label for a config
export function getConfigLabel(name: TreeConfigName): string {
  switch (name) {
    case 'v1_50bb': return 'V1 50bb (2 sizes)';
    case 'standard_50bb': return 'Standard 50bb (5 sizes)';
    case 'standard_100bb': return 'Standard 100bb (5 sizes)';
    case 'pipeline_srp': return 'Pipeline SRP 50bb (no raise)';
    case 'pipeline_3bet': return 'Pipeline 3-bet 50bb (no raise)';
  }
}

// Get output directory suffix for a config
export function getConfigOutputDir(name: TreeConfigName): string {
  switch (name) {
    case 'v1_50bb': return 'v2_hu_srp_50bb';
    case 'standard_50bb': return 'standard_hu_srp_50bb';
    case 'standard_100bb': return 'standard_hu_srp_100bb';
    case 'pipeline_srp': return 'pipeline_hu_srp_50bb';
    case 'pipeline_3bet': return 'pipeline_hu_3bet_50bb';
  }
}

// Get stack label for metadata
export function getStackLabel(name: TreeConfigName): string {
  switch (name) {
    case 'v1_50bb': return '50bb';
    case 'standard_50bb': return '50bb';
    case 'standard_100bb': return '100bb';
    case 'pipeline_srp': return '50bb';
    case 'pipeline_3bet': return '50bb';
  }
}

/**
 * Calculate actual bet amount from pot fraction, capped at effective stack.
 * Returns the bet amount (what the player puts into the pot).
 */
export function calcBetAmount(
  potSize: number,
  fraction: number,
  playerStack: number
): number {
  const bet = Math.round(potSize * fraction * 100) / 100;
  return Math.min(bet, playerStack);
}

/**
 * Calculate raise amount given a facing bet.
 * raise_size = facing_bet + (pot_after_call * fraction)
 * This models a raise to: call + fraction * new_pot
 */
export function calcRaiseAmount(
  potSize: number,
  facingBet: number,
  fraction: number,
  playerStack: number
): number {
  const potAfterCall = potSize + facingBet;
  const raiseTotal = facingBet + Math.round(potAfterCall * fraction * 100) / 100;
  return Math.min(raiseTotal, playerStack);
}
