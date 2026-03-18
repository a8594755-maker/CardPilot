// Estimated preflop ranges for spots not covered by GTO Wizard data.
// Used for 3-bet calling ranges and multi-way cold-call ranges.
//
// These are poker-knowledge-based approximations. Replace with actual
// GTO data (e.g., from GTO Wizard exports) when available.

import type { GtoWizardRangeEntry } from '../data-loaders/gto-wizard-json.js';

// ═══════════════════════════════════════════════════════════
// Hand classification helpers
// ═══════════════════════════════════════════════════════════

const RANKS = '23456789TJQKA';

function rankIndex(r: string): number {
  return RANKS.indexOf(r);
}

/** Parse hand class like "AKs" → { r1: 12, r2: 11, suited: true, pair: false } */
function parseHand(hand: string): { r1: number; r2: number; suited: boolean; pair: boolean } {
  const r1 = rankIndex(hand[0]);
  const r2 = rankIndex(hand[1]);
  if (hand.length === 2) {
    return { r1, r2, suited: false, pair: true };
  }
  return { r1, r2, suited: hand[2] === 's', pair: false };
}

function isPair(hand: string): boolean {
  return hand.length === 2;
}

function isSuited(hand: string): boolean {
  return hand.length === 3 && hand[2] === 's';
}

function isConnected(hand: string): boolean {
  const { r1, r2 } = parseHand(hand);
  return Math.abs(r1 - r2) === 1;
}

function isOneGap(hand: string): boolean {
  const { r1, r2 } = parseHand(hand);
  return Math.abs(r1 - r2) === 2;
}

function isTwoGap(hand: string): boolean {
  const { r1, r2 } = parseHand(hand);
  return Math.abs(r1 - r2) === 3;
}

function highRank(hand: string): number {
  const { r1, r2 } = parseHand(hand);
  return Math.max(r1, r2);
}

function lowRank(hand: string): number {
  const { r1, r2 } = parseHand(hand);
  return Math.min(r1, r2);
}

function hasAce(hand: string): boolean {
  return hand[0] === 'A' || hand[1] === 'A';
}

// ═══════════════════════════════════════════════════════════
// BTN calling BB 3-bet (estimated)
// ═══════════════════════════════════════════════════════════

/**
 * Estimate BTN's calling range vs BB's 3-bet.
 * Based on standard GTO theory for 50-100bb stack depths.
 *
 * Strong hands that call 3-bet:
 * - TT-QQ (call, sometimes 4-bet with KK+)
 * - AK, AQs (always call)
 * - AJs, ATs (sometimes call)
 * - KQs, KJs (sometimes call)
 * - Suited connectors 76s-T9s (as bluff-catchers / implied odds)
 * - Some suited aces A5s-A2s (blockers + nut flush)
 */
function estimateBtnCalling3bet(hand: string, stackBB: number): number {
  const h = parseHand(hand);
  const high = Math.max(h.r1, h.r2);
  const low = Math.min(h.r1, h.r2);

  // Pairs
  if (h.pair) {
    if (high >= 12) return 0.5; // AA: mix call/4-bet
    if (high >= 11) return 0.6; // KK: mix call/4-bet
    if (high >= 10) return 0.9; // QQ: mostly call
    if (high >= 9) return 0.85; // JJ: mostly call
    if (high >= 8) return 0.75; // TT: call
    if (high >= 7) return 0.5; // 99: mix call/fold
    if (high >= 5) return 0.25; // 66-88: sometimes call (set mine)
    if (stackBB >= 80) return 0.15; // 22-55: deep enough to set mine
    return 0.05; // too shallow to set mine
  }

  // Suited hands
  if (h.suited) {
    if (high === 12) {
      // Ace-x suited
      if (low >= 10) return 0.9; // AKs, AQs, AJs: strong call
      if (low >= 8) return 0.6; // ATs, A9s: mixed
      if (low <= 5) return 0.35; // A2s-A5s: blocker + nut flush draw
      return 0.2; // A6s-A8s: marginal
    }
    if (high === 11 && low >= 10) return 0.7; // KQs: call
    if (high === 11 && low >= 9) return 0.4; // KJs: mixed
    // Suited connectors (implied odds in 3-bet pots)
    if (isConnected(hand) && low >= 5) return 0.3; // 76s-T9s
    if (isOneGap(hand) && low >= 5) return 0.15; // 86s, 97s, T8s
    return 0;
  }

  // Offsuit hands
  if (high === 12) {
    // Ace-x offsuit
    if (low >= 11) return 0.85; // AKo: strong call
    if (low >= 10) return 0.45; // AQo: mixed
    if (low >= 9) return 0.15; // AJo: mostly fold
    return 0;
  }
  if (high === 11 && low >= 10) return 0.2; // KQo: sometimes call
  return 0; // other offsuit: fold to 3-bet
}

// ═══════════════════════════════════════════════════════════
// SB cold-call vs BTN open (estimated)
// ═══════════════════════════════════════════════════════════

/**
 * Estimate SB's cold-calling range vs BTN open.
 * SB is OOP and sandwiched (BB behind), so this is a tight range.
 * ~12-15% of hands.
 *
 * Mostly suited hands and medium pairs.
 * Strong hands go to 3-bet, not cold-call.
 */
function estimateSbColdCall(hand: string): number {
  const h = parseHand(hand);
  const high = Math.max(h.r1, h.r2);
  const low = Math.min(h.r1, h.r2);

  if (h.pair) {
    if (high >= 10) return 0; // TT+: should 3-bet
    if (high >= 5) return 0.6; // 55-99: cold-call for set mining
    return 0.3; // 22-44: sometimes cold-call
  }

  if (h.suited) {
    if (high === 12) {
      // Axs
      if (low >= 11) return 0; // AKs: should 3-bet
      if (low >= 9) return 0.4; // ATs-AQs: mixed 3-bet/call
      return 0.5; // A2s-A9s: good cold-call (nut flush potential)
    }
    if (high === 11 && low >= 9) return 0.4; // KJs, KQs: mixed
    if (high === 11 && low >= 7) return 0.25; // K8s-KTs: sometimes
    if (isConnected(hand) && low >= 4) return 0.55; // 65s-T9s: good cold-call
    if (isOneGap(hand) && low >= 5) return 0.35; // 86s, 97s, T8s
    if (high === 10 && low >= 8) return 0.3; // T9s, T8s: playable
    return 0;
  }

  // Offsuit: very few cold-calls from SB
  if (high === 12 && low >= 10) return 0.15; // AQo, AJo, ATo: sometimes
  if (high === 11 && low >= 10) return 0.1; // KQo, KJo: rarely
  return 0;
}

// ═══════════════════════════════════════════════════════════
// BTN cold-call vs CO open (estimated)
// ═══════════════════════════════════════════════════════════

/**
 * Estimate BTN's cold-calling range vs CO open.
 * BTN has position so can cold-call wider than SB. ~18-20% of hands.
 */
function estimateBtnColdCallVsCo(hand: string): number {
  const h = parseHand(hand);
  const high = Math.max(h.r1, h.r2);
  const low = Math.min(h.r1, h.r2);

  if (h.pair) {
    if (high >= 11) return 0; // KK+: should 3-bet
    if (high >= 10) return 0.4; // QQ, TT-JJ: mix call/3-bet
    if (high >= 4) return 0.7; // 44-99: flat call
    return 0.35; // 22-33: sometimes
  }

  if (h.suited) {
    if (high === 12) {
      // Axs
      if (low >= 11) return 0; // AKs: 3-bet
      if (low >= 9) return 0.5; // ATs-AQs: mix
      return 0.55; // A2s-A9s: cold-call (suited playability)
    }
    if (high === 11) {
      if (low >= 9) return 0.5; // KJs, KQs: mix
      if (low >= 7) return 0.35; // K8s-KTs
      return 0;
    }
    if (high === 10 && low >= 7) return 0.45; // T8s-TJs
    if (isConnected(hand) && low >= 3) return 0.6; // 54s-T9s
    if (isOneGap(hand) && low >= 4) return 0.4; // 75s, 86s, 97s
    if (isTwoGap(hand) && low >= 5) return 0.2; // 85s, 96s, T7s
    return 0;
  }

  // Offsuit
  if (high === 12 && low >= 9) return 0.35; // ATo-AQo: sometimes flat
  if (high === 11 && low >= 10) return 0.25; // KJo, KQo
  if (high === 10 && low >= 9) return 0.15; // QJo, QTo
  return 0;
}

// ═══════════════════════════════════════════════════════════
// BB multi-way defense (adjusted for pot odds)
// ═══════════════════════════════════════════════════════════

/**
 * Adjust BB's defense range for multi-way pots.
 *
 * In multi-way, BB gets much better pot odds (e.g., 3:1 instead of 2:1),
 * so speculative hands (set mining, suited connectors, suited aces) become
 * profitable to defend. BUT garbage hands (72o, 83o) are still dominated
 * and structurally unplayable — don't blindly add them.
 *
 * Takes existing BB frequencies and boosts speculative categories.
 */
export function adjustBBMultiWayDefense(
  entries: GtoWizardRangeEntry[],
  numPlayers: number,
): GtoWizardRangeEntry[] {
  if (numPlayers <= 2) return entries;

  // Boost factor scales with number of players (better pot odds)
  const boostFactor = numPlayers === 3 ? 1.0 : 1.2;

  return entries.map((entry) => {
    const hand = entry.hand;
    const existing = entry.mix.call ?? 0;
    const raise = entry.mix.raise ?? 0;

    let boost = 0;

    // 1. Small pairs (22-66): set mining value with multi-way implied odds
    if (isPair(hand) && lowRank(hand) <= 4) {
      boost = 0.4 * boostFactor; // 22-55: strong boost
    } else if (isPair(hand) && lowRank(hand) <= 6) {
      boost = 0.25 * boostFactor; // 66-77: moderate boost
    }

    // 2. Suited connectors (54s-T9s): straight + flush draw potential
    if (isSuited(hand) && isConnected(hand) && lowRank(hand) >= 3) {
      boost = 0.35 * boostFactor;
    }

    // 3. Suited aces (A2s-A9s): nut flush draw value
    if (isSuited(hand) && hasAce(hand) && highRank(hand) === 12 && lowRank(hand) <= 7) {
      boost = 0.3 * boostFactor;
    }

    // 4. Suited gappers (86s, 97s, T8s): hidden equity
    if (isSuited(hand) && isOneGap(hand) && lowRank(hand) >= 4) {
      boost = 0.2 * boostFactor;
    }

    // 5. Suited two-gappers (85s, 96s): marginal boost
    if (isSuited(hand) && isTwoGap(hand) && lowRank(hand) >= 4) {
      boost = 0.1 * boostFactor;
    }

    // Don't boost garbage offsuit hands — no structural improvement from pot odds
    // 72o, 83o, 94o etc. remain fold

    if (boost === 0) return entry;

    const newCall = Math.min(1.0, existing + boost);
    const newFold = Math.max(0, 1.0 - newCall - raise);

    return {
      ...entry,
      mix: { ...entry.mix, call: newCall, fold: newFold },
    };
  });
}

// ═══════════════════════════════════════════════════════════
// Public API: generate estimated range entries
// ═══════════════════════════════════════════════════════════

/** All 169 hand classes in standard order */
function allHandClasses(): string[] {
  const hands: string[] = [];
  for (let i = RANKS.length - 1; i >= 0; i--) {
    for (let j = RANKS.length - 1; j >= 0; j--) {
      if (i === j) {
        hands.push(RANKS[i] + RANKS[j]); // pair
      } else if (i > j) {
        hands.push(RANKS[i] + RANKS[j] + 's'); // suited
        hands.push(RANKS[i] + RANKS[j] + 'o'); // offsuit
      }
    }
  }
  return hands;
}

export type EstimatedSpot = 'BTN_vs_BB_facing_3bet' | 'SB_vs_BTN_cold_call' | 'BTN_vs_CO_cold_call';

/**
 * Generate estimated range entries for spots missing from GTO Wizard data.
 * Returns entries in the same format as GtoWizardRangeEntry.
 */
export function generateEstimatedRange(spot: EstimatedSpot, stackBB = 100): GtoWizardRangeEntry[] {
  const hands = allHandClasses();
  const entries: GtoWizardRangeEntry[] = [];

  for (const hand of hands) {
    let callFreq: number;

    switch (spot) {
      case 'BTN_vs_BB_facing_3bet':
        callFreq = estimateBtnCalling3bet(hand, stackBB);
        break;
      case 'SB_vs_BTN_cold_call':
        callFreq = estimateSbColdCall(hand);
        break;
      case 'BTN_vs_CO_cold_call':
        callFreq = estimateBtnColdCallVsCo(hand);
        break;
    }

    entries.push({
      format: 'estimated',
      spot,
      hand,
      mix: {
        call: callFreq,
        fold: 1.0 - callFreq,
      },
    });
  }

  return entries;
}
