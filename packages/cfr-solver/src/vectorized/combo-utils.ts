// Combo enumeration and blocker management for vectorized CFR.
//
// Given a board (3-5 cards), enumerate all valid 2-card hand combos
// (excluding those blocked by board cards) and build a blocker matrix
// that marks which combo pairs share a card (and thus can't coexist).

import { comboIndex } from '../abstraction/card-index.js';

export interface ValidCombos {
  /** The actual card pairs [c1, c2] with c1 < c2 */
  combos: Array<[number, number]>;
  /** comboIndex() for each combo (0..1325) */
  comboIds: Uint16Array;
  /** Number of valid combos */
  numCombos: number;
  /** Maps comboIndex(c1,c2) → local index in combos[] (-1 if not valid) */
  globalToLocal: Int16Array;
}

/**
 * Enumerate all valid 2-card combos for a given board.
 * Excludes any combo that shares a card with the board.
 *
 * For a flop (3 cards): ~1176 combos
 * For a turn (4 cards): ~1128 combos
 * For a river (5 cards): ~1081 combos
 */
export function enumerateValidCombos(board: number[]): ValidCombos {
  const dead = new Uint8Array(52);
  for (const c of board) dead[c] = 1;

  const combos: Array<[number, number]> = [];
  const ids: number[] = [];

  for (let c1 = 0; c1 < 52; c1++) {
    if (dead[c1]) continue;
    for (let c2 = c1 + 1; c2 < 52; c2++) {
      if (dead[c2]) continue;
      combos.push([c1, c2]);
      ids.push(comboIndex(c1, c2));
    }
  }

  const comboIds = new Uint16Array(ids);

  // Build globalToLocal: maps global comboIndex → local index
  const globalToLocal = new Int16Array(1326).fill(-1);
  for (let i = 0; i < combos.length; i++) {
    globalToLocal[ids[i]] = i;
  }

  return {
    combos,
    comboIds,
    numCombos: combos.length,
    globalToLocal,
  };
}

/**
 * Build a flat blocker matrix.
 * blockerMatrix[i * numCombos + j] = 1 if combos i and j share any card.
 *
 * This is symmetric: blockerMatrix[i,j] === blockerMatrix[j,i].
 * Diagonal is always 1 (a combo blocks itself).
 *
 * Used to zero out reach probabilities for blocked combos in
 * showdown evaluation and fold value computation.
 */
export function buildBlockerMatrix(combos: Array<[number, number]>): Uint8Array {
  const n = combos.length;
  const matrix = new Uint8Array(n * n);

  for (let i = 0; i < n; i++) {
    const [a1, a2] = combos[i];
    matrix[i * n + i] = 1; // self-blocks
    for (let j = i + 1; j < n; j++) {
      const [b1, b2] = combos[j];
      if (a1 === b1 || a1 === b2 || a2 === b1 || a2 === b2) {
        matrix[i * n + j] = 1;
        matrix[j * n + i] = 1;
      }
    }
  }

  return matrix;
}

/**
 * Build initial reach probability vector from weighted combos.
 *
 * Maps range (list of {combo, weight}) to a Float32Array indexed by
 * local combo index. Combos not in the range get 0 reach.
 */
export function buildReachFromRange(
  range: Array<{ combo: [number, number]; weight: number }>,
  validCombos: ValidCombos,
): Float32Array {
  const reach = new Float32Array(validCombos.numCombos);

  for (const { combo, weight } of range) {
    const c1 = Math.min(combo[0], combo[1]);
    const c2 = Math.max(combo[0], combo[1]);
    const globalId = comboIndex(c1, c2);
    const localId = validCombos.globalToLocal[globalId];
    if (localId >= 0) {
      reach[localId] = weight;
    }
  }

  return reach;
}
