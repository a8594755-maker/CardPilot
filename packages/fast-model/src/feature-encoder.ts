/**
 * Feature encoder: converts poker game state into a fixed-length numeric vector
 * suitable for MLP input. All values normalized to roughly [0, 1].
 *
 * V1 Feature layout (48 features):
 *   [0..4]   Hole cards: rank1, rank2, suited, paired, gap
 *   [5..29]  Board: 5 slots × 5 (rank + suit one-hot×4)
 *   [30..32] Street one-hot: flop, turn, river
 *   [33..39] Position one-hot: UTG, MP, HJ, CO, BTN, SB, BB
 *   [40]     In position (0/1)
 *   [41..44] Pot geometry: pot/100bb, toCall/100bb, SPR, potOdds
 *   [45..47] Action context: numVillains/5, facingBet, isAggressor
 *
 * V2 extends with betting history summary (54 features):
 *   [48]     is3betPot (0/1)
 *   [49]     isCheckRaised (0/1) — this street
 *   [50]     raiseCountStreet / 5
 *   [51]     raiseCountTotal / 10
 *   [52]     lastBetPotFrac / 2 — last bet as fraction of pot, capped
 *   [53]     allInPressure (0/1) — any opponent all-in
 */

const RANK_VALUES: Record<string, number> = {
  '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8,
  '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14,
};

const SUIT_INDEX: Record<string, number> = { 's': 0, 'h': 1, 'd': 2, 'c': 3 };

const POSITION_INDEX: Record<string, number> = {
  'UTG': 0, 'MP': 1, 'HJ': 2, 'CO': 3, 'BTN': 4, 'SB': 5, 'BB': 6,
};

/** Total number of features in V1 encoded vector */
export const FEATURE_COUNT = 48;

/** Total number of features in V2 encoded vector (with betting history) */
export const FEATURE_COUNT_V2 = 54;

function rankNorm(card: string): number {
  const r = RANK_VALUES[card[0]] ?? 0;
  return r / 14; // [0, 1]
}

function suitOneHot(card: string): [number, number, number, number] {
  const idx = SUIT_INDEX[card[1]] ?? 0;
  const out: [number, number, number, number] = [0, 0, 0, 0];
  out[idx] = 1;
  return out;
}

function encodeCard(card: string): number[] {
  return [rankNorm(card), ...suitOneHot(card)];
}

/**
 * Encode full game state into a fixed-length feature vector.
 *
 * @param holeCards   - Hero's two hole cards, e.g. ["Ah", "Ks"]
 * @param board       - Community cards (0-5 cards)
 * @param street      - "PREFLOP" | "FLOP" | "TURN" | "RIVER"
 * @param pot         - Current pot size
 * @param bigBlind    - Big blind amount
 * @param toCall      - Amount hero must call (0 if can check)
 * @param effectiveStack - Effective stack (min of hero/villain)
 * @param heroPosition   - Position string, e.g. "BTN", "BB"
 * @param heroInPosition - Whether hero acts last
 * @param numVillains    - Number of active opponents
 * @param isAggressor    - Whether hero was the preflop aggressor
 */
export function encodeFeatures(
  holeCards: [string, string],
  board: string[],
  street: string,
  pot: number,
  bigBlind: number,
  toCall: number,
  effectiveStack: number,
  heroPosition: string,
  heroInPosition: boolean,
  numVillains: number,
  isAggressor: boolean,
): number[] {
  const bb = bigBlind || 1;
  const features: number[] = [];

  // ── Hole cards (5 features) ──
  const r1 = RANK_VALUES[holeCards[0][0]] ?? 0;
  const r2 = RANK_VALUES[holeCards[1][0]] ?? 0;
  const suited = holeCards[0][1] === holeCards[1][1] ? 1 : 0;
  const paired = holeCards[0][0] === holeCards[1][0] ? 1 : 0;
  const gap = Math.abs(r1 - r2) / 12; // normalize to [0, 1]
  features.push(r1 / 14, r2 / 14, suited, paired, gap);

  // ── Board cards (25 features: 5 slots × 5) ──
  for (let i = 0; i < 5; i++) {
    if (i < board.length && board[i]) {
      features.push(...encodeCard(board[i]));
    } else {
      features.push(0, 0, 0, 0, 0); // empty slot
    }
  }

  // ── Street one-hot (3 features: flop, turn, river) ──
  const st = street.toUpperCase();
  features.push(
    st === 'FLOP' ? 1 : 0,
    st === 'TURN' ? 1 : 0,
    st === 'RIVER' ? 1 : 0,
  );

  // ── Position one-hot (7 features) ──
  const posIdx = POSITION_INDEX[heroPosition.toUpperCase()] ?? -1;
  for (let i = 0; i < 7; i++) {
    features.push(i === posIdx ? 1 : 0);
  }

  // ── In position (1 feature) ──
  features.push(heroInPosition ? 1 : 0);

  // ── Pot geometry (4 features) ──
  const potNorm = Math.min(pot / (100 * bb), 5); // cap at 500bb pots → 5
  const toCallNorm = Math.min(toCall / (100 * bb), 5);
  const spr = pot > 0 ? Math.min(effectiveStack / pot, 20) / 20 : 1; // SPR capped at 20 → [0, 1]
  const potOdds = (pot + toCall) > 0 ? toCall / (pot + toCall) : 0;
  features.push(potNorm, toCallNorm, spr, potOdds);

  // ── Action context (3 features) ──
  features.push(
    Math.min(numVillains, 5) / 5,
    toCall > 0 ? 1 : 0,     // facing bet
    isAggressor ? 1 : 0,
  );

  return features;
}

// ── V2 action history types (minimal, matching game state) ──

export interface ActionRecord {
  seat: number;
  street: string;
  type: string;     // 'fold' | 'check' | 'call' | 'raise' | 'all_in' | ...
  amount: number;
}

export interface PlayerRecord {
  seat: number;
  allIn: boolean;
  folded: boolean;
}

// ── V2 helper: single-pass action history aggregation ──

interface ActionAggregates {
  preflopRaises: number;
  isCheckRaised: boolean;
  raisesOnStreet: number;
  totalRaises: number;
  lastBetAmount: number;
}

/**
 * Aggregate all betting history stats in a single pass through actions.
 * Replaces 5 separate iterations with one.
 */
function aggregateActions(actions: ActionRecord[], street: string): ActionAggregates {
  let preflopRaises = 0;
  let raisesOnStreet = 0;
  let totalRaises = 0;
  let lastBetAmount = 0;
  let isCheckRaised = false;

  // For check-raise detection: track seats that checked on this street
  let checkedSeats = 0; // bitmask for seats 0-9

  const streetUpper = street.toUpperCase();

  for (let i = 0; i < actions.length; i++) {
    const a = actions[i];
    const isRaise = a.type === 'raise' || a.type === 'all_in';

    if (isRaise) {
      totalRaises++;
      if (a.street === 'PREFLOP') preflopRaises++;
      if (a.street === streetUpper) {
        raisesOnStreet++;
        if (a.amount > 0) lastBetAmount = a.amount;
        // Check-raise: this seat previously checked on this street
        if (a.seat < 30 && (checkedSeats & (1 << a.seat))) {
          isCheckRaised = true;
        }
      }
    } else if (a.type === 'check' && a.street === streetUpper && a.seat < 30) {
      checkedSeats |= (1 << a.seat);
    }
  }

  return { preflopRaises, isCheckRaised, raisesOnStreet, totalRaises, lastBetAmount };
}

/**
 * V2 feature encoder: extends V1 with 6 betting history summary features.
 * Returns a 54-dimensional vector.
 */
export function encodeFeaturesV2(
  holeCards: [string, string],
  board: string[],
  street: string,
  pot: number,
  bigBlind: number,
  toCall: number,
  effectiveStack: number,
  heroPosition: string,
  heroInPosition: boolean,
  numVillains: number,
  isAggressor: boolean,
  actions: ActionRecord[],
  players: PlayerRecord[],
  mySeat: number,
): number[] {
  // Start with the V1 48-feature base
  const features = encodeFeatures(
    holeCards, board, street, pot, bigBlind, toCall,
    effectiveStack, heroPosition, heroInPosition, numVillains, isAggressor,
  );

  // ── V2 betting history summary (6 features, single-pass aggregation) ──
  const agg = aggregateActions(actions, street);

  // [48] is3betPot: preflop had 2+ raises
  features.push(agg.preflopRaises >= 2 ? 1 : 0);

  // [49] isCheckRaised: someone check-raised on this street
  features.push(agg.isCheckRaised ? 1 : 0);

  // [50] raiseCountStreet: raises on current street, normalized
  features.push(Math.min(agg.raisesOnStreet, 5) / 5);

  // [51] raiseCountTotal: total raises across all streets, normalized
  features.push(Math.min(agg.totalRaises, 10) / 10);

  // [52] lastBetPotFrac: last bet as fraction of pot, capped at 2.0
  const lastBetFrac = (agg.lastBetAmount > 0 && pot > 0)
    ? Math.min(agg.lastBetAmount / pot, 2.0) / 2.0
    : 0;
  features.push(lastBetFrac);

  // [53] allInPressure: any opponent is all-in
  let hasAllInOpponent = false;
  for (let i = 0; i < players.length; i++) {
    if (players[i].allIn && !players[i].folded && players[i].seat !== mySeat) {
      hasAllInOpponent = true;
      break;
    }
  }
  features.push(hasAllInOpponent ? 1 : 0);

  return features;
}
