// Betting tree configuration for V1 HU SRP

import type { TreeConfig, BetSizeConfig } from '../types.js';

// V1: HU SRP at 50bb
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
