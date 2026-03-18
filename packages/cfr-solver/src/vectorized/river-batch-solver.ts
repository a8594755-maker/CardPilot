// Batch-solve all possible river subtrees for a given turn state.
//
// For a turn board (4 cards), there are 48 possible river cards.
// Each river card produces a different showdown matrix but the same
// betting tree structure. We solve all 48 river subtrees and store
// the resulting per-combo EVs (from the converged average strategy).
//
// These EVs are used by the chance-aware CFR engine when it encounters
// a transition terminal (end of turn betting -> deal river -> play river).

import { buildTree } from '../tree/tree-builder.js';
import { flattenTree, applyRakeToTree } from './flat-tree.js';
import { ArrayStore } from './array-store.js';
import { solveVectorized } from './vectorized-cfr.js';
import { buildReachFromRange } from './combo-utils.js';
import { buildShowdownMatrix } from './showdown-eval.js';
import { extractEV } from './ev-extractor.js';
import {
  buildComboMapping,
  remapReachToChild,
  remapEVToParent,
  enumerateDealableCards,
} from './combo-remap.js';
import type { ComboMapping } from './combo-remap.js';
import type { TreeConfig } from '../types.js';
import type { WeightedCombo } from '../integration/preflop-ranges.js';
import type { ValidCombos } from './combo-utils.js';

export interface RiverSubtreeResult {
  /** Dealt river card (0-51) */
  card: number;

  /** Per-combo EV for OOP on the river (in parent turn combo indices) */
  evOOP: Float32Array;

  /** Per-combo EV for IP on the river (in parent turn combo indices) */
  evIP: Float32Array;

  /** Combo mapping from parent (turn) to child (river) */
  mapping: ComboMapping;
}

export interface RiverBatchResult {
  /** Results per river card */
  results: RiverSubtreeResult[];

  /** Average per-combo EV across all river cards (parent indices) */
  avgEvOOP: Float32Array;

  /** Average per-combo EV across all river cards (parent indices) */
  avgEvIP: Float32Array;

  /** Number of river cards solved */
  numRivers: number;
}

export interface RiverBatchParams {
  /** Turn board (4 card indices) */
  turnBoard: number[];

  /** Tree config for the river betting tree */
  riverTreeConfig: TreeConfig;

  /** Valid combos on the turn board */
  turnCombos: ValidCombos;

  /** OOP reach at the transition point (turn combo indices) */
  oopReach: Float32Array;

  /** IP reach at the transition point (turn combo indices) */
  ipReach: Float32Array;

  /** Number of CFR iterations per river subtree */
  iterationsPerRiver: number;

  /** Progress callback: (cardsDone, totalCards) */
  onProgress?: (cardsDone: number, totalCards: number) => void;
}

/**
 * Solve all river subtrees for a given turn state.
 *
 * For each of the 48 possible river cards:
 * 1. Build combo mapping (turn -> river)
 * 2. Remap reaches to river combo space
 * 3. Build river showdown matrix
 * 4. Solve river CFR
 * 5. Extract per-combo EV
 * 6. Remap EV back to turn combo space
 *
 * Returns weighted average EV across all river cards.
 */
export function solveRiverBatch(params: RiverBatchParams): RiverBatchResult {
  const {
    turnBoard,
    riverTreeConfig,
    turnCombos,
    oopReach,
    ipReach,
    iterationsPerRiver,
    onProgress,
  } = params;

  const dealableCards = enumerateDealableCards(turnBoard);
  const numRivers = dealableCards.length;
  const turnNC = turnCombos.numCombos;

  // Accumulate weighted average EV
  const avgEvOOP = new Float32Array(turnNC);
  const avgEvIP = new Float32Array(turnNC);
  // Track how many river cards each turn combo survives (for proper averaging)
  const comboSurvivalCount = new Float32Array(turnNC);

  const results: RiverSubtreeResult[] = [];

  // Build the river betting tree once (same structure for all river cards)
  const riverConfig: TreeConfig = {
    ...riverTreeConfig,
    singleStreet: true, // river is always single-street
  };
  const riverRoot = buildTree(riverConfig);

  for (let ri = 0; ri < numRivers; ri++) {
    const riverCard = dealableCards[ri];
    const riverBoard = [...turnBoard, riverCard];

    // 1. Build combo mapping
    const mapping = buildComboMapping(turnCombos, turnBoard, riverCard);

    // 2. Remap reaches to river combo space
    const riverOOPReach = remapReachToChild(oopReach, mapping);
    const riverIPReach = remapReachToChild(ipReach, mapping);

    // 3. Build river infrastructure
    const riverBlocker = mapping.childBlockerMatrix;
    const riverShowdown = buildShowdownMatrix(mapping.childCombos.combos, riverBoard, riverBlocker);

    // 4. Flatten tree and create store
    const riverFlat = flattenTree(riverRoot, 2);

    // Apply rake if configured
    if (riverConfig.rake && riverConfig.rake.percentage > 0) {
      applyRakeToTree(riverFlat, riverConfig.rake.percentage, riverConfig.rake.cap);
    }

    const riverNC = mapping.childNC;
    const riverStore = new ArrayStore(riverFlat, riverNC);

    // Build full ranges from remapped reaches
    const riverOOPRange: WeightedCombo[] = [];
    const riverIPRange: WeightedCombo[] = [];
    for (let ci = 0; ci < riverNC; ci++) {
      const combo = mapping.childCombos.combos[ci];
      riverOOPRange.push({ combo, weight: riverOOPReach[ci] });
      riverIPRange.push({ combo, weight: riverIPReach[ci] });
    }

    // 5. Solve river CFR
    solveVectorized({
      tree: riverFlat,
      store: riverStore,
      board: riverBoard,
      oopRange: riverOOPRange,
      ipRange: riverIPRange,
      iterations: iterationsPerRiver,
      showdownMatrix: riverShowdown,
      blockerMatrix: riverBlocker,
    });

    // 6. Extract per-combo EV from solved river
    const evResult = extractEV({
      tree: riverFlat,
      store: riverStore,
      board: riverBoard,
      oopReach: buildReachFromRange(riverOOPRange, mapping.childCombos),
      ipReach: buildReachFromRange(riverIPRange, mapping.childCombos),
      nc: riverNC,
      showdownMatrix: riverShowdown,
      equityMatrix: null,
      blockerMatrix: riverBlocker,
    });

    // 7. Remap EV back to turn combo space
    const turnEvOOP = remapEVToParent(evResult.evOOP, mapping);
    const turnEvIP = remapEVToParent(evResult.evIP, mapping);

    // Accumulate
    for (let pi = 0; pi < turnNC; pi++) {
      if (mapping.parentToChild[pi] >= 0) {
        avgEvOOP[pi] += turnEvOOP[pi];
        avgEvIP[pi] += turnEvIP[pi];
        comboSurvivalCount[pi]++;
      }
    }

    results.push({ card: riverCard, evOOP: turnEvOOP, evIP: turnEvIP, mapping });

    if (onProgress) {
      onProgress(ri + 1, numRivers);
    }
  }

  // Compute average: divide by survival count
  // Each turn combo survives in (48 - number_of_blocking_river_cards) rivers.
  // Blocking river cards = cards that overlap with the hand.
  // For a 2-card hand on a 4-card board, each hand card blocks 1 river,
  // so each combo survives in 46 out of 48 rivers.
  for (let pi = 0; pi < turnNC; pi++) {
    if (comboSurvivalCount[pi] > 0) {
      avgEvOOP[pi] /= comboSurvivalCount[pi];
      avgEvIP[pi] /= comboSurvivalCount[pi];
    }
  }

  return { results, avgEvOOP, avgEvIP, numRivers };
}
