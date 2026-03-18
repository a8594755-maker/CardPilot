// Board-dependent hand combo isomorphism for lossless compression.
//
// On a given board, many hand combos are strategically identical because
// they only differ in suits that don't affect gameplay (no flush possible,
// or suits are interchangeable).
//
// Example: On Ks 7h 2d flop, Ac Qc and Ac Qd are strategically different
// (clubs vs diamonds have different flush draw potential). But Ad Qc and
// Ah Qc may or may not be equivalent depending on board suits.
//
// Algorithm:
// 1. Analyze which board suits are "represented" (appear on board)
// 2. For unrepresented suits, they're interchangeable unless they form
//    flush draws with each other
// 3. For each combo, compute a canonical key based on:
//    - Rank pair (ordered)
//    - Suit relationship to board (same suit as board card X, off-suit, etc.)
//    - Whether the two hole cards share a suit
// 4. Group combos with identical canonical keys
//
// This compresses ~1176 combos to ~150-300 groups (lossless).

import { indexToRank, indexToSuit } from '../abstraction/card-index.js';

export interface IsomorphismMap {
  /** Number of isomorphic groups (< numCombos) */
  numGroups: number;
  /** Maps local combo index → group index */
  comboToGroup: Uint16Array;
  /** Inverse: which combos belong to each group */
  groupToCombos: number[][];
  /** How many combos each group represents (for weighting) */
  groupWeight: Float32Array;
  /** One representative combo per group */
  groupRepresentative: Uint16Array;
}

/**
 * Compute hand isomorphism for a set of valid combos on a specific board.
 *
 * Two combos are in the same isomorphism group if swapping interchangeable
 * suits would transform one into the other. The strategic implications
 * (hand strength, draws, blockers) are identical.
 */
export function computeHandIsomorphism(
  board: number[],
  validCombos: Array<[number, number]>,
): IsomorphismMap {
  const n = validCombos.length;

  // Analyze board suit structure
  const boardSuits = board.map((c) => indexToSuit(c));

  // Count occurrences of each suit on the board
  const suitCount = new Uint8Array(4);
  for (const s of boardSuits) suitCount[s]++;

  // Determine suit equivalence classes for the board
  // Two suits are interchangeable if:
  // 1. They appear the same number of times on the board
  // 2. They appear in the same rank positions (modulo suit swap)
  const suitCanonical = computeBoardSuitCanonical(board);

  // For each combo, compute its canonical key
  const keys = new Array<string>(n);
  for (let i = 0; i < n; i++) {
    keys[i] = computeComboCanonicalKey(validCombos[i], board, suitCanonical);
  }

  // Group by canonical key
  const groupMap = new Map<string, number[]>();
  for (let i = 0; i < n; i++) {
    const key = keys[i];
    let group = groupMap.get(key);
    if (!group) {
      group = [];
      groupMap.set(key, group);
    }
    group.push(i);
  }

  // Build output
  const numGroups = groupMap.size;
  const comboToGroup = new Uint16Array(n);
  const groupToCombos: number[][] = [];
  const groupWeight = new Float32Array(numGroups);
  const groupRepresentative = new Uint16Array(numGroups);

  let gIdx = 0;
  for (const [, combos] of groupMap) {
    groupToCombos.push(combos);
    groupWeight[gIdx] = combos.length;
    groupRepresentative[gIdx] = combos[0];
    for (const ci of combos) {
      comboToGroup[ci] = gIdx;
    }
    gIdx++;
  }

  return {
    numGroups,
    comboToGroup,
    groupToCombos,
    groupWeight,
    groupRepresentative,
  };
}

/**
 * Compute canonical suit mapping for a board.
 *
 * Returns an array where suitCanonical[originalSuit] = canonical suit ID.
 * Suits that are interchangeable get the same canonical ID.
 *
 * The canonical mapping assigns IDs in order of first appearance on the board,
 * with unrepresented suits getting IDs based on how many board cards they could
 * form flush draws with.
 */
function computeBoardSuitCanonical(board: number[]): Uint8Array {
  const boardSuits = board.map((c) => indexToSuit(c));
  const boardRanks = board.map((c) => indexToRank(c));

  // Build a "suit signature" for each suit:
  // - How many board cards have this suit
  // - Which rank positions those cards are at
  const suitSigs = new Array<string>(4);
  for (let s = 0; s < 4; s++) {
    const positions: number[] = [];
    for (let i = 0; i < board.length; i++) {
      if (boardSuits[i] === s) positions.push(boardRanks[i]);
    }
    positions.sort((a, b) => a - b);
    suitSigs[s] = positions.join(',');
  }

  // Assign canonical IDs: suits with the same signature are interchangeable
  const canonical = new Uint8Array(4);
  const sigToId = new Map<string, number>();
  let nextId = 0;

  // Process suits in order of their first appearance on the board, then remaining
  const suitOrder: number[] = [];
  const seen = new Set<number>();
  for (const s of boardSuits) {
    if (!seen.has(s)) {
      suitOrder.push(s);
      seen.add(s);
    }
  }
  for (let s = 0; s < 4; s++) {
    if (!seen.has(s)) suitOrder.push(s);
  }

  for (const s of suitOrder) {
    const sig = suitSigs[s];
    if (sigToId.has(sig)) {
      canonical[s] = sigToId.get(sig)!;
    } else {
      sigToId.set(sig, nextId);
      canonical[s] = nextId++;
    }
  }

  return canonical;
}

/**
 * Compute canonical key for a hand combo relative to a board.
 *
 * The key encodes:
 * - Ranks of the two cards (ordered high-to-low)
 * - Canonical suit of each card
 * - Whether the two cards share a (canonical) suit
 *
 * Combos with identical keys are strategically equivalent.
 */
function computeComboCanonicalKey(
  combo: [number, number],
  board: number[],
  suitCanonical: Uint8Array,
): string {
  const r0 = indexToRank(combo[0]);
  const r1 = indexToRank(combo[1]);
  const s0 = indexToSuit(combo[0]);
  const s1 = indexToSuit(combo[1]);

  const cs0 = suitCanonical[s0];
  const cs1 = suitCanonical[s1];

  // Order by rank descending, break ties by canonical suit
  let rank0: number, rank1: number, csuit0: number, csuit1: number;
  if (r0 > r1 || (r0 === r1 && cs0 <= cs1)) {
    rank0 = r0;
    rank1 = r1;
    csuit0 = cs0;
    csuit1 = cs1;
  } else {
    rank0 = r1;
    rank1 = r0;
    csuit0 = cs1;
    csuit1 = cs0;
  }

  const suited = cs0 === cs1 ? 1 : 0;

  // Also encode the specific board-card interactions:
  // For each hole card, does it share a suit with a board card?
  // This matters for flush draws.
  const boardInteraction0 = computeBoardSuitInteraction(combo[0], board);
  const boardInteraction1 = computeBoardSuitInteraction(combo[1], board);

  // Order interactions to match the rank ordering
  let bi0: number, bi1: number;
  if (r0 > r1 || (r0 === r1 && cs0 <= cs1)) {
    bi0 = boardInteraction0;
    bi1 = boardInteraction1;
  } else {
    bi0 = boardInteraction1;
    bi1 = boardInteraction0;
  }

  return `${rank0},${rank1},${csuit0},${csuit1},${suited},${bi0},${bi1}`;
}

/**
 * Compute how many board cards share a suit with this card.
 * This is a proxy for flush draw potential.
 */
function computeBoardSuitInteraction(card: number, board: number[]): number {
  const cardSuit = indexToSuit(card);
  let count = 0;
  for (const bc of board) {
    if (indexToSuit(bc) === cardSuit) count++;
  }
  return count;
}

/**
 * Aggregate reach probabilities from combo-level to group-level.
 *
 * For each group, sums the reach of all combos in that group.
 */
export function aggregateReachToGroups(
  comboReach: Float32Array,
  iso: IsomorphismMap,
): Float32Array {
  const groupReach = new Float32Array(iso.numGroups);
  for (let c = 0; c < comboReach.length; c++) {
    groupReach[iso.comboToGroup[c]] += comboReach[c];
  }
  return groupReach;
}

/**
 * Expand group-level strategy back to combo-level.
 *
 * All combos in a group get the same strategy probabilities.
 */
export function expandGroupToComboStrategy(
  groupStrategy: Float32Array,
  iso: IsomorphismMap,
  numActions: number,
  numCombos: number,
): Float32Array {
  const comboStrategy = new Float32Array(numActions * numCombos);
  for (let a = 0; a < numActions; a++) {
    for (let c = 0; c < numCombos; c++) {
      comboStrategy[a * numCombos + c] = groupStrategy[a * iso.numGroups + iso.comboToGroup[c]];
    }
  }
  return comboStrategy;
}
