/**
 * Feature encoder: converts poker game state into a fixed-length numeric vector
 * suitable for MLP input. All values normalized to roughly [0, 1].
 *
 * Feature layout (48 features total):
 *   [0..4]   Hole cards: rank1, rank2, suited, paired, gap
 *   [5..29]  Board: 5 slots × 5 (rank + suit one-hot×4)
 *   [30..32] Street one-hot: flop, turn, river
 *   [33..39] Position one-hot: UTG, MP, HJ, CO, BTN, SB, BB
 *   [40]     In position (0/1)
 *   [41..44] Pot geometry: pot/100bb, toCall/100bb, SPR, potOdds
 *   [45..47] Action context: numVillains/5, facingBet, isAggressor
 */

const RANK_VALUES: Record<string, number> = {
  '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8,
  '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14,
};

const SUIT_INDEX: Record<string, number> = { 's': 0, 'h': 1, 'd': 2, 'c': 3 };

const POSITION_INDEX: Record<string, number> = {
  'UTG': 0, 'MP': 1, 'HJ': 2, 'CO': 3, 'BTN': 4, 'SB': 5, 'BB': 6,
};

/** Total number of features in the encoded vector */
export const FEATURE_COUNT = 48;

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
