// Per-street solving orchestration for subgame solving.
//
// This module ties together the street tree builder, vectorized CFR engine,
// and heuristic EV estimation to solve a single street.
//
// Workflow:
// 1. Build a single-street tree (e.g., Flop-only)
// 2. Flatten it into a FlatTree
// 3. At "transition" terminal nodes, use heuristic EV
// 4. Run vectorized CFR+ to convergence
// 5. Extract boundary reach probabilities for subgame resolving

import type { TreeConfig, Street } from '../types.js';
import type { WeightedCombo } from '../integration/preflop-ranges.js';
import { buildStreetTree } from './street-tree-builder.js';
import { flattenTree, isTerminal, decodeTerminalId, type FlatTree } from './flat-tree.js';
import { ArrayStore } from './array-store.js';
import {
  enumerateValidCombos,
  buildBlockerMatrix,
  buildReachFromRange,
  type ValidCombos,
} from './combo-utils.js';
import { buildShowdownMatrix, computeShowdownEV, computeFoldEV } from './showdown-eval.js';
import { estimateTransitionEVMonteCarlo } from './heuristic-ev.js';
import { assignHistoryIds } from '../tree/tree-builder.js';

/**
 * Synchronous callback for evaluating EV at street-transition terminals.
 * Drop-in replacement for estimateTransitionEVMonteCarlo.
 * If provided via StreetSolveParams.transitionEvalFn, used instead of heuristic.
 */
export type TransitionEvalFn = (
  combos: Array<[number, number]>,
  board: number[],
  pot: number,
  oopReach: Float32Array,
  ipReach: Float32Array,
  blockerMatrix: Uint8Array,
  numCombos: number,
  traverser: number,
  stacks: number[],
  outEV: Float32Array,
) => void;

export interface StreetSolveParams {
  treeConfig: TreeConfig;
  board: number[];
  street: Street;
  oopRange: WeightedCombo[];
  ipRange: WeightedCombo[];
  iterations: number;
  /** Initial reach from parent solve (for sub-street resolving) */
  initialReachOOP?: Float32Array;
  initialReachIP?: Float32Array;
  /** Number of Monte Carlo samples for transition EV heuristic */
  transitionSamples?: number;
  /**
   * Optional custom transition EV evaluator (e.g., value network).
   * If provided, replaces the default heuristic (estimateTransitionEVMonteCarlo).
   */
  transitionEvalFn?: TransitionEvalFn;
  onProgress?: (iter: number, elapsed: number) => void;
}

export interface StreetSolveResult {
  store: ArrayStore;
  tree: FlatTree;
  validCombos: ValidCombos;
  /** Boundary reach probs at each transition node (for resolving sub-streets) */
  boundaryData: Map<
    number,
    {
      oopReach: Float32Array;
      ipReach: Float32Array;
      pot: number;
      stacks: number[];
    }
  >;
}

/**
 * Solve a single street using vectorized CFR+.
 *
 * For Flop/Turn: transition terminals use heuristic EV estimation.
 * For River: all terminals are fold or showdown (exact).
 */
export function solveStreet(params: StreetSolveParams): StreetSolveResult {
  const {
    treeConfig,
    board,
    street,
    oopRange,
    ipRange,
    iterations,
    transitionEvalFn,
    initialReachOOP,
    initialReachIP,
    transitionSamples = 10,
    onProgress,
  } = params;

  const numPlayers = treeConfig.numPlayers ?? 2;

  // 1. Build single-street tree
  const actionTree = buildStreetTree(treeConfig, street, numPlayers);
  assignHistoryIds(actionTree);

  // 2. Flatten into arrays
  const tree = flattenTree(actionTree, numPlayers);

  // 3. Setup combos and matrices
  const validCombos = enumerateValidCombos(board);
  const nc = validCombos.numCombos;
  const blockerMatrix = buildBlockerMatrix(validCombos.combos);

  // Only build showdown matrix if there are showdown terminals
  // (River always has them, Flop/Turn might have all-in showdowns)
  let showdownMatrix: Int8Array | null = null;
  for (let t = 0; t < tree.numTerminals; t++) {
    if (tree.terminalIsShowdown[t]) {
      showdownMatrix = buildShowdownMatrix(validCombos.combos, board, blockerMatrix);
      break;
    }
  }

  // 4. Create store
  const store = new ArrayStore(tree, nc);

  // 5. Build initial reach
  const oopInitReach = initialReachOOP
    ? new Float32Array(initialReachOOP)
    : buildReachFromRange(oopRange, validCombos);
  const ipInitReach = initialReachIP
    ? new Float32Array(initialReachIP)
    : buildReachFromRange(ipRange, validCombos);

  // 6. Identify transition terminals
  const transitionTerminals = new Set<number>();
  for (let t = 0; t < tree.numTerminals; t++) {
    // A terminal is a transition if it's not a showdown and not a fold
    // In the flat tree, we detect transitions by checking:
    // - terminalIsShowdown[t] === 0 (not showdown)
    // - terminalFolder[t] === -1 would be showdown, but we set it to lastToAct for folds
    // Actually, we need the original tree info. Since we can't store extra fields
    // in the flat tree easily, we mark transition terminals as:
    // showdown=0 AND folder=-1 (no one folded, not a showdown = transition)
    if (!tree.terminalIsShowdown[t] && tree.terminalFolder[t] === -1) {
      // Hmm, this doesn't work because fold terminals have folder >= 0.
      // Let's use a different heuristic: transition = not showdown AND folder < 0
      transitionTerminals.add(t);
    }
  }

  // Pre-allocate buffers
  const startTime = Date.now();

  // 7. Run vectorized CFR+
  for (let iter = 0; iter < iterations; iter++) {
    // Traverse for each player as traverser
    for (let traverser = 0; traverser < 2; traverser++) {
      const oopReach = new Float32Array(oopInitReach);
      const ipReach = new Float32Array(ipInitReach);

      streetCFRTraverse(
        tree,
        store,
        blockerMatrix,
        showdownMatrix,
        validCombos,
        board,
        nc,
        0,
        oopReach,
        ipReach,
        traverser,
        transitionTerminals,
        transitionSamples,
        transitionEvalFn,
      );
    }

    if (onProgress && (iter + 1) % 100 === 0) {
      onProgress(iter + 1, Date.now() - startTime);
    }
  }

  // 8. Extract boundary data for sub-street resolving
  const boundaryData = extractBoundaryData(
    tree,
    store,
    validCombos,
    nc,
    oopInitReach,
    ipInitReach,
    transitionTerminals,
  );

  return { store, tree, validCombos, boundaryData };
}

/**
 * CFR traversal for a single-street tree.
 * Same as vectorized-cfr.ts but handles transition terminals
 * by calling heuristic EV estimation.
 */
function streetCFRTraverse(
  tree: FlatTree,
  store: ArrayStore,
  blockerMatrix: Uint8Array,
  showdownMatrix: Int8Array | null,
  validCombos: ValidCombos,
  board: number[],
  nc: number,
  nodeId: number,
  oopReach: Float32Array,
  ipReach: Float32Array,
  traverser: number,
  transitionTerminals: Set<number>,
  transitionSamples: number,
  transitionEvalFn?: TransitionEvalFn,
): Float32Array {
  if (isTerminal(nodeId)) {
    const ti = decodeTerminalId(nodeId);
    const ev = new Float32Array(nc);
    const pot = tree.terminalPot[ti];
    const stacks: [number, number] = [tree.terminalStacks[ti * 2], tree.terminalStacks[ti * 2 + 1]];

    if (transitionTerminals.has(ti)) {
      // Transition terminal: use custom eval (value network) or heuristic
      const evalFn = transitionEvalFn ?? estimateTransitionEVMonteCarlo;
      evalFn(
        validCombos.combos,
        board,
        pot,
        oopReach,
        ipReach,
        blockerMatrix,
        nc,
        traverser,
        [...stacks],
        ev,
      );
      return ev;
    }

    if (tree.terminalIsShowdown[ti] && showdownMatrix) {
      computeShowdownEV(
        showdownMatrix,
        blockerMatrix,
        oopReach,
        ipReach,
        pot,
        stacks,
        nc,
        traverser,
        ev,
      );
    } else {
      const folder = tree.terminalFolder[ti];
      const opponentReach = traverser === 0 ? ipReach : oopReach;
      computeFoldEV(blockerMatrix, opponentReach, pot, stacks, nc, traverser, folder, ev);
    }
    return ev;
  }

  const player = tree.nodePlayer[nodeId];
  const numActions = tree.nodeNumActions[nodeId];
  const actionOffset = tree.nodeActionOffset[nodeId];

  const strategy = new Float32Array(numActions * nc);
  store.getCurrentStrategy(nodeId, numActions, strategy);

  const actionEVs = new Array<Float32Array>(numActions);
  const nodeEV = new Float32Array(nc);

  for (let a = 0; a < numActions; a++) {
    const childId = tree.childNodeId[actionOffset + a];

    const newOopReach = player === 0 ? new Float32Array(nc) : oopReach;
    const newIpReach = player === 1 ? new Float32Array(nc) : ipReach;

    if (player === 0) {
      for (let c = 0; c < nc; c++) {
        newOopReach[c] = oopReach[c] * strategy[a * nc + c];
      }
    } else {
      for (let c = 0; c < nc; c++) {
        newIpReach[c] = ipReach[c] * strategy[a * nc + c];
      }
    }

    actionEVs[a] = streetCFRTraverse(
      tree,
      store,
      blockerMatrix,
      showdownMatrix,
      validCombos,
      board,
      nc,
      childId,
      newOopReach,
      newIpReach,
      traverser,
      transitionTerminals,
      transitionSamples,
      transitionEvalFn,
    );

    for (let c = 0; c < nc; c++) {
      nodeEV[c] += strategy[a * nc + c] * actionEVs[a][c];
    }
  }

  if (player === traverser) {
    const regretDeltas = new Float32Array(numActions * nc);
    const stratWeights = new Float32Array(numActions * nc);
    const playerReach = traverser === 0 ? oopReach : ipReach;

    for (let a = 0; a < numActions; a++) {
      for (let c = 0; c < nc; c++) {
        regretDeltas[a * nc + c] = actionEVs[a][c] - nodeEV[c];
        stratWeights[a * nc + c] = playerReach[c] * strategy[a * nc + c];
      }
    }

    store.updateRegrets(nodeId, numActions, regretDeltas);
    store.addStrategyWeights(nodeId, numActions, stratWeights);
  }

  return nodeEV;
}

/**
 * Extract boundary reach probabilities at transition terminals.
 *
 * After solving, we can reconstruct the reach probabilities at each
 * transition point by playing the average strategy from the root.
 */
function extractBoundaryData(
  tree: FlatTree,
  store: ArrayStore,
  validCombos: ValidCombos,
  nc: number,
  oopInitReach: Float32Array,
  ipInitReach: Float32Array,
  transitionTerminals: Set<number>,
): Map<number, { oopReach: Float32Array; ipReach: Float32Array; pot: number; stacks: number[] }> {
  const result = new Map<
    number,
    {
      oopReach: Float32Array;
      ipReach: Float32Array;
      pot: number;
      stacks: number[];
    }
  >();

  // Walk the tree with average strategy to compute reach at transitions
  function walkForReach(nodeId: number, oopReach: Float32Array, ipReach: Float32Array): void {
    if (isTerminal(nodeId)) {
      const ti = decodeTerminalId(nodeId);
      if (transitionTerminals.has(ti)) {
        const pot = tree.terminalPot[ti];
        const stacks = [tree.terminalStacks[ti * 2], tree.terminalStacks[ti * 2 + 1]];
        result.set(ti, {
          oopReach: new Float32Array(oopReach),
          ipReach: new Float32Array(ipReach),
          pot,
          stacks,
        });
      }
      return;
    }

    const player = tree.nodePlayer[nodeId];
    const numActions = tree.nodeNumActions[nodeId];
    const actionOffset = tree.nodeActionOffset[nodeId];

    const avgStrategy = new Float32Array(numActions * nc);
    store.getAverageStrategy(nodeId, numActions, avgStrategy);

    for (let a = 0; a < numActions; a++) {
      const childId = tree.childNodeId[actionOffset + a];

      const newOopReach = player === 0 ? new Float32Array(nc) : new Float32Array(oopReach);
      const newIpReach = player === 1 ? new Float32Array(nc) : new Float32Array(ipReach);

      if (player === 0) {
        for (let c = 0; c < nc; c++) {
          newOopReach[c] = oopReach[c] * avgStrategy[a * nc + c];
        }
      } else {
        for (let c = 0; c < nc; c++) {
          newIpReach[c] = ipReach[c] * avgStrategy[a * nc + c];
        }
      }

      walkForReach(childId, newOopReach, newIpReach);
    }
  }

  walkForReach(0, oopInitReach, ipInitReach);
  return result;
}
