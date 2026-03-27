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
 *
 * V3 extends with equity/draw/blocker features (65 features):
 *   [54]     handStrength — equity vs random on current board (0-1)
 *   [55]     flushDraw — 4 to flush, need 1 more (binary)
 *   [56]     straightDraw — 0=none, 0.5=gutshot, 1.0=OESD
 *   [57]     overcards — hero ranks above all board ranks / 2
 *   [58]     nutFlushBlocker — holds ace of dominant board suit (binary)
 *   [59]     pairBlocker — holds card matching highest board rank (binary)
 *   [60]     boardPaired — board has repeated rank (binary)
 *   [61]     boardFlushDraw — 3+ board cards same suit (binary)
 *   [62]     boardConnected — 3+ board ranks within span of 5 (binary)
 *   [63]     handRank — made hand category / 10 (0.1-1.0)
 *   [64]     comboDrawPotential — flush draw AND straight draw (binary)
 */

const RANK_VALUES: Record<string, number> = {
  '2': 2,
  '3': 3,
  '4': 4,
  '5': 5,
  '6': 6,
  '7': 7,
  '8': 8,
  '9': 9,
  T: 10,
  J: 11,
  Q: 12,
  K: 13,
  A: 14,
};

const SUIT_INDEX: Record<string, number> = { s: 0, h: 1, d: 2, c: 3 };

const POSITION_INDEX: Record<string, number> = {
  UTG: 0,
  MP: 1,
  HJ: 2,
  CO: 3,
  BTN: 4,
  SB: 5,
  BB: 6,
};

/** Total number of features in V1 encoded vector */
export const FEATURE_COUNT = 48;

/** Total number of features in V2 encoded vector (with betting history) */
export const FEATURE_COUNT_V2 = 54;

/** Total number of features in V3 encoded vector (with equity/draw/blocker features) */
export const FEATURE_COUNT_V3 = 65;

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
  features.push(st === 'FLOP' ? 1 : 0, st === 'TURN' ? 1 : 0, st === 'RIVER' ? 1 : 0);

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
  const potOdds = pot + toCall > 0 ? toCall / (pot + toCall) : 0;
  features.push(potNorm, toCallNorm, spr, potOdds);

  // ── Action context (3 features) ──
  features.push(
    Math.min(numVillains, 5) / 5,
    toCall > 0 ? 1 : 0, // facing bet
    isAggressor ? 1 : 0,
  );

  return features;
}

// ── V2 action history types (minimal, matching game state) ──

export interface ActionRecord {
  seat: number;
  street: string;
  type: string; // 'fold' | 'check' | 'call' | 'raise' | 'all_in' | ...
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
        if (a.seat < 30 && checkedSeats & (1 << a.seat)) {
          isCheckRaised = true;
        }
      }
    } else if (a.type === 'check' && a.street === streetUpper && a.seat < 30) {
      checkedSeats |= 1 << a.seat;
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
    holeCards,
    board,
    street,
    pot,
    bigBlind,
    toCall,
    effectiveStack,
    heroPosition,
    heroInPosition,
    numVillains,
    isAggressor,
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
  const lastBetFrac =
    agg.lastBetAmount > 0 && pot > 0 ? Math.min(agg.lastBetAmount / pot, 2.0) / 2.0 : 0;
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

// ── V3 equity/draw/blocker features ──

import { evaluateHandBoard, evaluateBestHand } from '@cardpilot/poker-evaluator';
import { HandRank } from '@cardpilot/poker-evaluator';

// Card string → integer index (rank*4 + suit) for evaluateHandBoard
const RANK_TO_IDX: Record<string, number> = {
  '2': 0,
  '3': 1,
  '4': 2,
  '5': 3,
  '6': 4,
  '7': 5,
  '8': 6,
  '9': 7,
  T: 8,
  J: 9,
  Q: 10,
  K: 11,
  A: 12,
};
const SUIT_TO_IDX: Record<string, number> = { c: 0, d: 1, h: 2, s: 3 };

function cardToIdx(card: string): number {
  return (RANK_TO_IDX[card[0]] ?? 0) * 4 + (SUIT_TO_IDX[card[1]] ?? 0);
}

/**
 * Compute hand strength (equity vs uniform random) on current board.
 * Deterministic, exhaustive enumeration of all valid opponent combos.
 * ~1081 combos on flop, ~990 on turn, ~903 on river.
 */
function computeHandStrength(heroIndices: [number, number], boardIndices: number[]): number {
  if (boardIndices.length < 3) return 0.5; // no board yet

  const dead = new Set([heroIndices[0], heroIndices[1], ...boardIndices]);
  const heroValue = evaluateHandBoard(heroIndices[0], heroIndices[1], boardIndices);

  let wins = 0;
  let ties = 0;
  let total = 0;

  for (let c1 = 0; c1 < 52; c1++) {
    if (dead.has(c1)) continue;
    for (let c2 = c1 + 1; c2 < 52; c2++) {
      if (dead.has(c2)) continue;
      const oppValue = evaluateHandBoard(c1, c2, boardIndices);
      if (heroValue > oppValue) wins++;
      else if (heroValue === oppValue) ties++;
      total++;
    }
  }

  return total > 0 ? (wins + ties * 0.5) / total : 0.5;
}

/**
 * Detect flush draw: hero + board has exactly 4 cards of the same suit.
 * Returns true only if not yet a made flush (5+).
 */
function hasFlushDraw(heroCards: string[], board: string[]): boolean {
  const suitCounts: Record<string, number> = {};
  for (const c of [...heroCards, ...board]) {
    const s = c[1];
    suitCounts[s] = (suitCounts[s] || 0) + 1;
  }
  // Flush draw = exactly 4 of a suit, and at least one hero card in that suit
  for (const [suit, count] of Object.entries(suitCounts)) {
    if (count === 4 && heroCards.some((c) => c[1] === suit)) return true;
  }
  return false;
}

/**
 * Detect straight draw type.
 * Returns 0 = none, 0.5 = gutshot (4 outs), 1.0 = OESD (8 outs).
 *
 * Algorithm: check all possible 5-rank windows. Count how many unique
 * ranks from hero+board fall in each window. If 4 ranks in a 5-wide
 * window, it's a draw. Check gap pattern for OESD vs gutshot.
 */
function detectStraightDraw(heroCards: string[], board: string[]): number {
  const allCards = [...heroCards, ...board];
  // Collect unique rank values (2=0, ..., A=12)
  const rankSet = new Set<number>();
  for (const c of allCards) {
    rankSet.add(RANK_TO_IDX[c[0]] ?? 0);
  }
  // Ace can also be low (value -1 in our scheme, treat as special)
  if (rankSet.has(12)) rankSet.add(-1); // Ace-low

  const ranks = [...rankSet].sort((a, b) => a - b);

  // Check if we already have a made straight (5 consecutive)
  for (let i = 0; i <= ranks.length - 5; i++) {
    if (ranks[i + 4] - ranks[i] === 4) return 0; // made straight, no draw
  }

  let bestDraw = 0; // 0=none, 0.5=gutshot, 1.0=OESD

  // Check every 5-rank window for 4-card straight draws
  for (let low = -1; low <= 8; low++) {
    const high = low + 4;
    let count = 0;
    let hasHero = false;
    for (const r of ranks) {
      if (r >= low && r <= high) {
        count++;
        if (
          heroCards.some(
            (c) => (RANK_TO_IDX[c[0]] ?? 0) === r || (r === -1 && (RANK_TO_IDX[c[0]] ?? 0) === 12),
          )
        ) {
          hasHero = true;
        }
      }
    }
    if (count === 4 && hasHero) {
      // Determine if OESD or gutshot: check if both ends are open
      const missing: number[] = [];
      for (let r = low; r <= high; r++) {
        const lookFor = r === -1 ? 12 : r;
        if (!rankSet.has(r) && (r !== -1 || !rankSet.has(12))) {
          missing.push(r);
        }
      }
      if (missing.length === 1) {
        // One card missing from the window
        const m = missing[0];
        if (m === low || m === high) {
          // Missing card is at an end — this is OESD-like
          // But need to verify the other end extends
          bestDraw = Math.max(bestDraw, 1.0);
        } else {
          // Missing card is inside — gutshot
          bestDraw = Math.max(bestDraw, 0.5);
        }
      }
    }
  }

  return bestDraw;
}

/**
 * Count hero overcards (ranks above highest board rank).
 */
function countOvercards(heroCards: string[], board: string[]): number {
  if (board.length === 0) return 0;
  let maxBoardRank = 0;
  for (const c of board) {
    maxBoardRank = Math.max(maxBoardRank, RANK_TO_IDX[c[0]] ?? 0);
  }
  let count = 0;
  for (const c of heroCards) {
    if ((RANK_TO_IDX[c[0]] ?? 0) > maxBoardRank) count++;
  }
  return count;
}

/**
 * Check if hero holds ace of the dominant board suit (nut flush blocker).
 */
function hasNutFlushBlocker(heroCards: string[], board: string[]): boolean {
  if (board.length === 0) return false;
  // Find most common board suit
  const suitCounts: Record<string, number> = {};
  for (const c of board) {
    const s = c[1];
    suitCounts[s] = (suitCounts[s] || 0) + 1;
  }
  let bestSuit = '';
  let bestCount = 0;
  for (const [s, n] of Object.entries(suitCounts)) {
    if (n > bestCount) {
      bestCount = n;
      bestSuit = s;
    }
  }
  if (bestCount < 2) return false; // no flush possible
  // Check if hero has ace of that suit
  return heroCards.some((c) => c[0] === 'A' && c[1] === bestSuit);
}

/**
 * Check if hero holds card matching highest board rank (top pair blocker).
 */
function hasPairBlocker(heroCards: string[], board: string[]): boolean {
  if (board.length === 0) return false;
  let maxRank = '';
  let maxVal = -1;
  for (const c of board) {
    const v = RANK_TO_IDX[c[0]] ?? 0;
    if (v > maxVal) {
      maxVal = v;
      maxRank = c[0];
    }
  }
  return heroCards.some((c) => c[0] === maxRank);
}

/**
 * Check if board has a paired rank.
 */
function isBoardPaired(board: string[]): boolean {
  const ranks = new Set<string>();
  for (const c of board) {
    if (ranks.has(c[0])) return true;
    ranks.add(c[0]);
  }
  return false;
}

/**
 * Check if board has 3+ cards of the same suit (flush draw possible).
 */
function isBoardFlushDraw(board: string[]): boolean {
  const suitCounts: Record<string, number> = {};
  for (const c of board) {
    const s = c[1];
    suitCounts[s] = (suitCounts[s] || 0) + 1;
  }
  return Object.values(suitCounts).some((n) => n >= 3);
}

/**
 * Check if board is connected (3+ ranks within a 5-rank window).
 */
function isBoardConnected(board: string[]): boolean {
  const ranks = [...new Set(board.map((c) => RANK_TO_IDX[c[0]] ?? 0))].sort((a, b) => a - b);
  if (ranks.length < 3) return false;
  for (let i = 0; i <= ranks.length - 3; i++) {
    if (ranks[i + 2] - ranks[i] <= 4) return true;
  }
  return false;
}

/**
 * Get normalized hand rank (HIGH_CARD=0.1, PAIR=0.2, ..., ROYAL_FLUSH=1.0).
 */
function getNormalizedHandRank(heroCards: string[], board: string[]): number {
  if (board.length < 3) return 0;
  const allCards = [...heroCards, ...board];
  try {
    const eval_ = evaluateBestHand(allCards);
    return eval_.rank / 10; // HandRank goes 1-10
  } catch {
    return 0;
  }
}

/**
 * V3 feature encoder: extends V2 with 11 equity/draw/blocker features.
 * Returns a 65-dimensional vector.
 *
 * New features [54..64] are purely card-derived (hero + board),
 * independent of game state. They encode information that is critical
 * to GTO strategy but hard for the NN to infer from raw rank/suit encoding.
 */
export function encodeFeaturesV3(
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
  // Start with the V2 54-feature base
  const features = encodeFeaturesV2(
    holeCards,
    board,
    street,
    pot,
    bigBlind,
    toCall,
    effectiveStack,
    heroPosition,
    heroInPosition,
    numVillains,
    isAggressor,
    actions,
    players,
    mySeat,
  );

  // ── V3 equity/draw/blocker features (11 features) ──

  const heroIdx: [number, number] = [cardToIdx(holeCards[0]), cardToIdx(holeCards[1])];
  const boardIdx = board.map(cardToIdx);

  // [54] handStrength — equity vs random on current board
  features.push(board.length >= 3 ? computeHandStrength(heroIdx, boardIdx) : 0.5);

  // [55] flushDraw — 4 to flush, not yet made
  features.push(board.length >= 3 && hasFlushDraw(holeCards as string[], board) ? 1 : 0);

  // [56] straightDraw — 0=none, 0.5=gutshot, 1.0=OESD
  features.push(board.length >= 3 ? detectStraightDraw(holeCards as string[], board) : 0);

  // [57] overcards — hero ranks above all board ranks / 2
  features.push(countOvercards(holeCards as string[], board) / 2);

  // [58] nutFlushBlocker — holds ace of dominant board suit
  features.push(hasNutFlushBlocker(holeCards as string[], board) ? 1 : 0);

  // [59] pairBlocker — holds card matching highest board rank
  features.push(hasPairBlocker(holeCards as string[], board) ? 1 : 0);

  // [60] boardPaired — board has repeated rank
  features.push(isBoardPaired(board) ? 1 : 0);

  // [61] boardFlushDraw — 3+ board cards same suit
  features.push(isBoardFlushDraw(board) ? 1 : 0);

  // [62] boardConnected — 3+ board ranks within span of 5
  features.push(isBoardConnected(board) ? 1 : 0);

  // [63] handRank — made hand category / 10 (0.1-1.0)
  features.push(getNormalizedHandRank(holeCards as string[], board));

  // [64] comboDrawPotential — flush draw AND straight draw
  const fd = features[55];
  const sd = features[56];
  features.push(fd > 0 && sd > 0 ? 1 : 0);

  return features;
}
