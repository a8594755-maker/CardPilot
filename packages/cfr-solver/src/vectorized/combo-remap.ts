// Combo remapping for multi-street solving.
//
// When a new community card is dealt (turn/river), some hand combos become
// invalid (blocker: one of the hand's cards matches the new card).
// This module maps combo indices between parent and child street.
//
// Parent = current street (e.g., turn with 4 board cards)
// Child  = next street (e.g., river with 5 board cards after dealing 1 card)

import { enumerateValidCombos, buildBlockerMatrix } from './combo-utils.js';
import type { ValidCombos } from './combo-utils.js';

export interface ComboMapping {
  /** The dealt card index (0-51) */
  dealtCard: number;

  /** Parent combo count */
  parentNC: number;

  /** Child combo count (always < parentNC) */
  childNC: number;

  /** parentToChild[parentIdx] = childIdx, or -1 if blocked by dealt card */
  parentToChild: Int32Array;

  /** childToParent[childIdx] = parentIdx */
  childToParent: Int32Array;

  /** The child street's valid combos */
  childCombos: ValidCombos;

  /** The child's blocker matrix */
  childBlockerMatrix: Uint8Array;
}

/**
 * Build a mapping from parent combo indices to child combo indices after
 * dealing a new card.
 *
 * @param parentCombos - Valid combos on the parent street
 * @param parentBoard - Board cards on the parent street (indices 0-51)
 * @param dealtCard - The new card being dealt (index 0-51)
 */
export function buildComboMapping(
  parentCombos: ValidCombos,
  parentBoard: number[],
  dealtCard: number,
): ComboMapping {
  const childBoard = [...parentBoard, dealtCard];
  const childCombos = enumerateValidCombos(childBoard);
  const childNC = childCombos.numCombos;
  const parentNC = parentCombos.numCombos;

  const parentToChild = new Int32Array(parentNC);
  parentToChild.fill(-1);

  const childToParent = new Int32Array(childNC);

  // For each parent combo, check if it survives (not blocked by dealt card)
  for (let pi = 0; pi < parentNC; pi++) {
    const [c1, c2] = parentCombos.combos[pi];
    if (c1 === dealtCard || c2 === dealtCard) {
      // Blocked — this combo is invalid on the child street
      continue;
    }

    // Find this combo in child's valid combos using globalToLocal
    const globalId = parentCombos.comboIds[pi];
    const childIdx = childCombos.globalToLocal[globalId];
    if (childIdx >= 0) {
      parentToChild[pi] = childIdx;
      childToParent[childIdx] = pi;
    }
  }

  const childBlockerMatrix = buildBlockerMatrix(childCombos.combos);

  return {
    dealtCard,
    parentNC,
    childNC,
    parentToChild,
    childToParent,
    childCombos,
    childBlockerMatrix,
  };
}

/**
 * Remap a reach vector from parent to child street.
 * Combos blocked by the dealt card get reach 0 on the child street.
 *
 * @param parentReach - Reach probabilities on parent street (length = parentNC)
 * @param mapping - ComboMapping from buildComboMapping
 * @returns Reach probabilities on child street (length = childNC)
 */
export function remapReachToChild(parentReach: Float32Array, mapping: ComboMapping): Float32Array {
  const childReach = new Float32Array(mapping.childNC);
  for (let ci = 0; ci < mapping.childNC; ci++) {
    const pi = mapping.childToParent[ci];
    childReach[ci] = parentReach[pi];
  }
  return childReach;
}

/**
 * Remap an EV vector from child back to parent street.
 * Sets EV=0 for combos that were blocked by the dealt card.
 *
 * @param childEV - Per-combo EV on child street (length = childNC)
 * @param mapping - ComboMapping from buildComboMapping
 * @returns Per-combo EV on parent street (length = parentNC)
 */
export function remapEVToParent(childEV: Float32Array, mapping: ComboMapping): Float32Array {
  const parentEV = new Float32Array(mapping.parentNC);
  for (let pi = 0; pi < mapping.parentNC; pi++) {
    const ci = mapping.parentToChild[pi];
    if (ci >= 0) {
      parentEV[pi] = childEV[ci];
    }
    // Blocked combos stay 0
  }
  return parentEV;
}

/**
 * Get the number of remaining cards that can be dealt after a given board.
 * = 52 - board.length
 */
export function numRemainingCards(board: number[]): number {
  return 52 - board.length;
}

/**
 * Enumerate all possible cards that can be dealt (not on the board or dead).
 */
export function enumerateDealableCards(board: number[]): number[] {
  const dead = new Set(board);
  const cards: number[] = [];
  for (let c = 0; c < 52; c++) {
    if (!dead.has(c)) cards.push(c);
  }
  return cards;
}
