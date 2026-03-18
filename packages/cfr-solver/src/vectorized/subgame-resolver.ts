// Subgame resolver for on-the-fly Turn/River solving.
//
// This is the key to GTO+'s tiny file sizes:
// 1. Only the Flop strategy is stored permanently
// 2. When the user navigates to a specific Turn card, we:
//    a. Extract boundary reach probs from the Flop solve
//    b. Build a Turn->River tree (or Turn-only tree)
//    c. Solve it in ~0.1-1 second with vectorized CFR+
//    d. Display the result
//
// The process repeats for the River card.

import type { TreeConfig, Street } from '../types.js';
import type { WeightedCombo } from '../integration/preflop-ranges.js';
import { solveStreet, type StreetSolveResult } from './street-solver.js';
import { enumerateValidCombos, type ValidCombos } from './combo-utils.js';

export interface ResolveRequest {
  /** Result from the parent street's solve (contains boundary reach probs) */
  parentResult: StreetSolveResult;
  /** Which transition terminal in the parent tree leads here */
  transitionTerminalId: number;
  /** The new card dealt (Turn or River card index 0-51) */
  newCard: number;
  /** Tree config for the sub-street */
  treeConfig: TreeConfig;
  /** Original ranges (needed to map combos to the new board) */
  oopRange: WeightedCombo[];
  ipRange: WeightedCombo[];
  /** Parent board (before new card) */
  parentBoard: number[];
  /** Iterations for sub-street solving (default 500) */
  iterations?: number;
  onProgress?: (iter: number, elapsed: number) => void;
}

export interface ResolveResult {
  /** The solved sub-street */
  streetResult: StreetSolveResult;
  /** The new board (parent board + new card) */
  board: number[];
  /** The street that was resolved */
  street: Street;
}

/**
 * Resolve a sub-street (Turn or River) given boundary conditions from the parent.
 *
 * This is the "magic" of subgame solving:
 * 1. Take the reach probabilities from the parent's transition terminal
 * 2. Map them to the new board's combo space (some combos now blocked by new card)
 * 3. Build and solve a single-street tree
 * 4. Return the result
 */
export function resolveSubgame(request: ResolveRequest): ResolveResult {
  const {
    parentResult,
    transitionTerminalId,
    newCard,
    treeConfig,
    oopRange,
    ipRange,
    parentBoard,
    iterations = 500,
    onProgress,
  } = request;

  // Get boundary data from parent
  const boundary = parentResult.boundaryData.get(transitionTerminalId);
  if (!boundary) {
    throw new Error(
      `No boundary data for transition terminal ${transitionTerminalId}. ` +
        `Available: ${[...parentResult.boundaryData.keys()].join(', ')}`,
    );
  }

  // New board = parent board + new card
  const newBoard = [...parentBoard, newCard];

  // Determine which street we're resolving
  const street = determineStreet(newBoard);

  // Map parent reach probabilities to new board's combo space
  // Some combos are now blocked by the new card
  const newValidCombos = enumerateValidCombos(newBoard);

  // Map reach from parent combo space to new combo space
  const oopReachMapped = mapReachToNewBoard(
    boundary.oopReach,
    parentResult.validCombos,
    newValidCombos,
  );
  const ipReachMapped = mapReachToNewBoard(
    boundary.ipReach,
    parentResult.validCombos,
    newValidCombos,
  );

  // Override tree config with boundary pot and stacks
  const adjustedConfig: TreeConfig = {
    ...treeConfig,
    startingPot: boundary.pot,
    effectiveStack: boundary.stacks[0], // assume symmetric for now
  };

  // Solve the sub-street
  const streetResult = solveStreet({
    treeConfig: adjustedConfig,
    board: newBoard,
    street,
    oopRange,
    ipRange,
    iterations,
    initialReachOOP: oopReachMapped,
    initialReachIP: ipReachMapped,
    onProgress,
  });

  return {
    streetResult,
    board: newBoard,
    street,
  };
}

/**
 * Map reach probabilities from parent board's combo space to new board's combo space.
 *
 * When a new card is dealt:
 * - Combos that contain the new card are now blocked (reach = 0)
 * - Remaining combos keep their reach from the parent
 *
 * We need to re-index because the new board has a different set of valid combos.
 */
function mapReachToNewBoard(
  parentReach: Float32Array,
  parentCombos: ValidCombos,
  newCombos: ValidCombos,
): Float32Array {
  const newReach = new Float32Array(newCombos.numCombos);

  for (let newIdx = 0; newIdx < newCombos.numCombos; newIdx++) {
    // This combo must not contain the new card (already excluded by enumerateValidCombos)
    // Find its index in the parent combo space
    const globalId = newCombos.comboIds[newIdx];
    const parentIdx = parentCombos.globalToLocal[globalId];

    if (parentIdx >= 0 && parentIdx < parentReach.length) {
      newReach[newIdx] = parentReach[parentIdx];
    }
    // else: this combo wasn't in parent range (reach = 0)
  }

  return newReach;
}

/**
 * Determine which street we're on based on board length.
 */
function determineStreet(board: number[]): Street {
  switch (board.length) {
    case 4:
      return 'TURN';
    case 5:
      return 'RIVER';
    default:
      return 'FLOP'; // shouldn't happen in normal flow
  }
}

/**
 * Full solve pipeline: Flop -> Turn -> River with subgame resolving.
 *
 * Convenience function that solves the Flop, then resolves a specific
 * Turn and River card in sequence.
 *
 * @param turnCard - Turn card index (0-51), or undefined to skip
 * @param riverCard - River card index (0-51), or undefined to skip
 */
export function solveWithResolving(params: {
  treeConfig: TreeConfig;
  flopCards: [number, number, number];
  oopRange: WeightedCombo[];
  ipRange: WeightedCombo[];
  flopIterations?: number;
  turnCard?: number;
  turnIterations?: number;
  riverCard?: number;
  riverIterations?: number;
  /** Which transition terminal to follow (default: 0 = first one, typically check-check) */
  transitionPath?: number;
  onProgress?: (stage: string, iter: number, elapsed: number) => void;
}): {
  flopResult: StreetSolveResult;
  turnResult?: ResolveResult;
  riverResult?: ResolveResult;
} {
  const {
    treeConfig,
    flopCards,
    oopRange,
    ipRange,
    flopIterations = 1000,
    turnCard,
    turnIterations = 500,
    riverCard,
    riverIterations = 500,
    transitionPath = 0,
    onProgress,
  } = params;

  // Solve Flop
  const flopResult = solveStreet({
    treeConfig,
    board: [...flopCards],
    street: 'FLOP',
    oopRange,
    ipRange,
    iterations: flopIterations,
    onProgress: onProgress ? (iter, elapsed) => onProgress('FLOP', iter, elapsed) : undefined,
  });

  if (turnCard === undefined) {
    return { flopResult };
  }

  // Resolve Turn
  const transitionIds = [...flopResult.boundaryData.keys()];
  const turnTransitionId = transitionIds[transitionPath] ?? transitionIds[0];

  if (turnTransitionId === undefined) {
    return { flopResult };
  }

  const turnResult = resolveSubgame({
    parentResult: flopResult,
    transitionTerminalId: turnTransitionId,
    newCard: turnCard,
    treeConfig,
    oopRange,
    ipRange,
    parentBoard: [...flopCards],
    iterations: turnIterations,
    onProgress: onProgress ? (iter, elapsed) => onProgress('TURN', iter, elapsed) : undefined,
  });

  if (riverCard === undefined) {
    return { flopResult, turnResult };
  }

  // Resolve River
  const turnTransitionIds = [...turnResult.streetResult.boundaryData.keys()];
  const riverTransitionId = turnTransitionIds[transitionPath] ?? turnTransitionIds[0];

  if (riverTransitionId === undefined) {
    return { flopResult, turnResult };
  }

  const riverResult = resolveSubgame({
    parentResult: turnResult.streetResult,
    transitionTerminalId: riverTransitionId,
    newCard: riverCard,
    treeConfig,
    oopRange,
    ipRange,
    parentBoard: turnResult.board,
    iterations: riverIterations,
    onProgress: onProgress ? (iter, elapsed) => onProgress('RIVER', iter, elapsed) : undefined,
  });

  return { flopResult, turnResult, riverResult };
}
