// Preflop solver configurations for different game formats.
//
// Each config defines the betting structure, stack depth, and solver parameters
// for a specific game type.

import type { PreflopSolveConfig } from './preflop-types.js';
import { defaultPositionsForPlayers } from './preflop-types.js';

// ── Predefined configs ──

export const PREFLOP_CONFIGS: Record<string, PreflopSolveConfig> = {
  cash_6max_100bb: {
    name: 'cash_6max_100bb',
    players: 6,
    positionLabels: ['UTG', 'HJ', 'CO', 'BTN', 'SB', 'BB'],
    stackSize: 100,
    sbSize: 0.5,
    bbSize: 1.0,
    ante: 0,
    openSize: 2.5,
    threeBetIPMultiplier: 3.0, // 3× open = 7.5bb
    threeBetOOPMultiplier: 3.5, // 3.5× open = 8.75bb
    fourBetMultiplier: 2.25, // 2.25× 3bet
    reRaiseMultiplier: 2.25,
    maxRaiseLevel: 4,
    allowSmallBlindComplete: true,
    autoFoldUninvolvedAfterThreeBet: true,
    iterations: 1_000_000,
    realizationIP: 1.0,
    realizationOOP: 0.9, // Quadratic model: k = 0.10, max IP bonus = 2.5% of pot
  },

  cash_6max_50bb: {
    name: 'cash_6max_50bb',
    players: 6,
    positionLabels: ['UTG', 'HJ', 'CO', 'BTN', 'SB', 'BB'],
    stackSize: 50,
    sbSize: 0.5,
    bbSize: 1.0,
    ante: 0,
    openSize: 2.5,
    threeBetIPMultiplier: 3.0,
    threeBetOOPMultiplier: 3.5,
    fourBetMultiplier: 2.25,
    reRaiseMultiplier: 2.25,
    maxRaiseLevel: 4,
    allowSmallBlindComplete: true,
    autoFoldUninvolvedAfterThreeBet: true,
    iterations: 1_000_000,
    realizationIP: 1.0,
    realizationOOP: 0.9, // Quadratic model: k = 0.10, max IP bonus = 2.5% of pot
  },

  cash_6max_30bb: {
    name: 'cash_6max_30bb',
    players: 6,
    positionLabels: ['UTG', 'HJ', 'CO', 'BTN', 'SB', 'BB'],
    stackSize: 30,
    sbSize: 0.5,
    bbSize: 1.0,
    ante: 0,
    openSize: 2.5,
    threeBetIPMultiplier: 3.0,
    threeBetOOPMultiplier: 3.5,
    fourBetMultiplier: 2.25,
    reRaiseMultiplier: 2.25,
    maxRaiseLevel: 3, // shallow stack → fewer raise levels
    allowSmallBlindComplete: true,
    autoFoldUninvolvedAfterThreeBet: true,
    iterations: 1_000_000,
    realizationIP: 1.0,
    realizationOOP: 0.9,
  },

  cash_6max_200bb: {
    name: 'cash_6max_200bb',
    players: 6,
    positionLabels: ['UTG', 'HJ', 'CO', 'BTN', 'SB', 'BB'],
    stackSize: 200,
    sbSize: 0.5,
    bbSize: 1.0,
    ante: 0,
    openSize: 2.5,
    threeBetIPMultiplier: 3.0,
    threeBetOOPMultiplier: 3.5,
    fourBetMultiplier: 2.25,
    reRaiseMultiplier: 2.25,
    maxRaiseLevel: 4,
    allowSmallBlindComplete: true,
    autoFoldUninvolvedAfterThreeBet: true,
    iterations: 1_000_000,
    realizationIP: 1.0,
    realizationOOP: 0.9,
  },

  cash_6max_100bb_ante: {
    name: 'cash_6max_100bb_ante',
    players: 6,
    positionLabels: ['UTG', 'HJ', 'CO', 'BTN', 'SB', 'BB'],
    stackSize: 100,
    sbSize: 0.5,
    bbSize: 1.0,
    ante: 0.25, // 0.25bb per player = 1.5bb total ante
    openSize: 2.5,
    threeBetIPMultiplier: 3.0,
    threeBetOOPMultiplier: 3.5,
    fourBetMultiplier: 2.25,
    reRaiseMultiplier: 2.25,
    maxRaiseLevel: 4,
    allowSmallBlindComplete: true,
    autoFoldUninvolvedAfterThreeBet: true,
    iterations: 1_000_000,
    realizationIP: 1.0,
    realizationOOP: 0.9, // Quadratic model: k = 0.10, max IP bonus = 2.5% of pot
  },

  // ── HU configs — focused matchups for 3-bet/4-bet scenarios ──
  // These are much faster to solve than 6-max (2 players = smaller tree).
  // Generates: RFI, facing_open, facing_3bet, facing_4bet spots.

  // SB vs BB heads-up (the most common preflop matchup)
  hu_sb_bb_100bb: {
    name: 'hu_sb_bb_100bb',
    players: 2,
    positionLabels: ['SB', 'BB'],
    stackSize: 100,
    sbSize: 0.5,
    bbSize: 1.0,
    ante: 0,
    openSize: 2.5,
    threeBetIPMultiplier: 3.0, // BB 3-bet IP (doesn't apply HU since BB is OOP)
    threeBetOOPMultiplier: 3.5, // BB 3-bet OOP = 8.75bb
    fourBetMultiplier: 2.25, // SB 4-bet = ~19.7bb
    reRaiseMultiplier: 2.25,
    maxRaiseLevel: 4, // open → 3bet → 4bet → 5bet
    allowSmallBlindComplete: true,
    autoFoldUninvolvedAfterThreeBet: false,
    iterations: 1_000_000,
    realizationIP: 1.0,
    realizationOOP: 0.9,
  },

  hu_sb_bb_50bb: {
    name: 'hu_sb_bb_50bb',
    players: 2,
    positionLabels: ['SB', 'BB'],
    stackSize: 50,
    sbSize: 0.5,
    bbSize: 1.0,
    ante: 0,
    openSize: 2.5,
    threeBetIPMultiplier: 3.0,
    threeBetOOPMultiplier: 3.5,
    fourBetMultiplier: 2.25,
    reRaiseMultiplier: 2.25,
    maxRaiseLevel: 3, // shallow: open → 3bet → 4bet (often jam)
    allowSmallBlindComplete: true,
    autoFoldUninvolvedAfterThreeBet: false,
    iterations: 1_000_000,
    realizationIP: 1.0,
    realizationOOP: 0.9,
  },

  hu_sb_bb_25bb: {
    name: 'hu_sb_bb_25bb',
    players: 2,
    positionLabels: ['SB', 'BB'],
    stackSize: 25,
    sbSize: 0.5,
    bbSize: 1.0,
    ante: 0,
    openSize: 2.5,
    threeBetIPMultiplier: 3.0,
    threeBetOOPMultiplier: 3.5,
    fourBetMultiplier: 2.25,
    reRaiseMultiplier: 2.25,
    maxRaiseLevel: 2, // push/fold territory: open → 3bet (jam)
    allowSmallBlindComplete: true,
    autoFoldUninvolvedAfterThreeBet: false,
    iterations: 1_000_000,
    realizationIP: 1.0,
    realizationOOP: 0.92, // shallow → less postflop edge
  },

  // ── 3-player BTN/SB/BB — covers squeeze spots ──
  // BTN opens, SB can 3-bet or cold-call, BB can squeeze or cold-call.
  // Generates all squeeze + 3-bet + 4-bet scenarios for the 3 most
  // common positions.

  threeway_btn_sb_bb_100bb: {
    name: 'threeway_btn_sb_bb_100bb',
    players: 3,
    positionLabels: ['BTN', 'SB', 'BB'],
    stackSize: 100,
    sbSize: 0.5,
    bbSize: 1.0,
    ante: 0,
    openSize: 2.5,
    threeBetIPMultiplier: 3.0,
    threeBetOOPMultiplier: 3.5,
    fourBetMultiplier: 2.25,
    reRaiseMultiplier: 2.25,
    maxRaiseLevel: 4,
    allowSmallBlindComplete: true,
    autoFoldUninvolvedAfterThreeBet: true,
    iterations: 1_000_000,
    realizationIP: 1.0,
    realizationOOP: 0.9,
  },

  // ── 4-player CO/BTN/SB/BB — covers CO open + 3-bet dynamics ──

  fourway_co_btn_sb_bb_100bb: {
    name: 'fourway_co_btn_sb_bb_100bb',
    players: 4,
    positionLabels: ['CO', 'BTN', 'SB', 'BB'],
    stackSize: 100,
    sbSize: 0.5,
    bbSize: 1.0,
    ante: 0,
    openSize: 2.5,
    threeBetIPMultiplier: 3.0,
    threeBetOOPMultiplier: 3.5,
    fourBetMultiplier: 2.25,
    reRaiseMultiplier: 2.25,
    maxRaiseLevel: 4,
    allowSmallBlindComplete: true,
    autoFoldUninvolvedAfterThreeBet: true,
    iterations: 1_000_000,
    realizationIP: 1.0,
    realizationOOP: 0.9,
  },

  // ── HU with ante (tournament-style) ──

  hu_sb_bb_100bb_ante: {
    name: 'hu_sb_bb_100bb_ante',
    players: 2,
    positionLabels: ['SB', 'BB'],
    stackSize: 100,
    sbSize: 0.5,
    bbSize: 1.0,
    ante: 0.25,
    openSize: 2.5,
    threeBetIPMultiplier: 3.0,
    threeBetOOPMultiplier: 3.5,
    fourBetMultiplier: 2.25,
    reRaiseMultiplier: 2.25,
    maxRaiseLevel: 4,
    allowSmallBlindComplete: true,
    autoFoldUninvolvedAfterThreeBet: false,
    iterations: 1_000_000,
    realizationIP: 1.0,
    realizationOOP: 0.9,
  },

  hu_sb_bb_20bb_ante: {
    name: 'hu_sb_bb_20bb_ante',
    players: 2,
    positionLabels: ['SB', 'BB'],
    stackSize: 20,
    sbSize: 0.5,
    bbSize: 1.0,
    ante: 0.25,
    openSize: 2.0, // smaller open at 20bb
    threeBetIPMultiplier: 3.0,
    threeBetOOPMultiplier: 3.5,
    fourBetMultiplier: 2.25,
    reRaiseMultiplier: 2.25,
    maxRaiseLevel: 2, // open → 3bet (jam)
    allowSmallBlindComplete: false,
    autoFoldUninvolvedAfterThreeBet: false,
    iterations: 1_000_000,
    realizationIP: 1.0,
    realizationOOP: 0.94, // very shallow → minimal postflop edge
  },
};

export type PreflopConfigName = keyof typeof PREFLOP_CONFIGS;

export function getPreflopConfig(name: string): PreflopSolveConfig {
  const config = PREFLOP_CONFIGS[name];
  if (!config) {
    throw new Error(
      `Unknown preflop config: ${name}. Available: ${Object.keys(PREFLOP_CONFIGS).join(', ')}`,
    );
  }
  const labels = config.positionLabels ?? defaultPositionsForPlayers(config.players);
  if (labels.length !== config.players) {
    throw new Error(
      `Invalid positionLabels length for ${name}: expected ${config.players}, got ${labels.length}`,
    );
  }

  return {
    ...config,
    positionLabels: [...labels],
    reRaiseMultiplier: config.reRaiseMultiplier ?? config.fourBetMultiplier,
    maxRaiseLevel: Math.max(1, config.maxRaiseLevel ?? 4),
    allowSmallBlindComplete: config.allowSmallBlindComplete ?? true,
    autoFoldUninvolvedAfterThreeBet: config.autoFoldUninvolvedAfterThreeBet ?? true,
  };
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
export function isIPPostflop(seatA: number, seatB: number, players = 6): boolean {
  // Seat layout assumption:
  //   [early positions..., BTN, SB, BB]
  // Postflop order:
  //   (HU) BB -> SB
  //   (3+ players) SB -> BB -> early positions in seat order -> BTN
  // Larger index in this postflop order means acts later (IP).
  const sbSeat = players - 2;
  const bbSeat = players - 1;

  function postflopOrderIndex(seat: number): number {
    if (players === 2) {
      if (seat === bbSeat) return 0;
      if (seat === sbSeat) return 1;
      return seat;
    }
    if (seat === sbSeat) return 0;
    if (seat === bbSeat) return 1;
    return seat + 2;
  }

  return postflopOrderIndex(seatA) > postflopOrderIndex(seatB);
}
