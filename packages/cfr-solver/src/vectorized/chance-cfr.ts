// Chance-Aware CFR Engine for Multi-Street Solving
//
// When the board has < 5 cards (turn/flop), the existing single-street solver
// uses an equity matrix computed from static hand evaluation. This module
// replaces that with a "realized equity matrix" that accounts for the fact
// that players will continue betting on future streets.
//
// Architecture (Turn scenario):
// 1. Pre-solve all 48 river subtrees with full-range CFR
// 2. Build a "transition equity matrix" from the pre-solved river showdown results
//    (average equity across all river cards for each pair of turn combos)
// 3. Run turn CFR using this equity matrix at showdown terminals
//
// The equity matrix captures per-pair showdown equity averaged across rivers.
// While it doesn't capture river betting dynamics directly, the pre-solved
// rivers inform future improvements (e.g., realized value extraction).

import { buildTree } from '../tree/tree-builder.js';
import { flattenTree, applyRakeToTree, isTerminal, decodeTerminalId } from './flat-tree.js';
import type { FlatTree } from './flat-tree.js';
import { ArrayStore } from './array-store.js';
import { enumerateValidCombos, buildBlockerMatrix, buildReachFromRange } from './combo-utils.js';
import type { ValidCombos } from './combo-utils.js';
import { buildShowdownMatrix } from './showdown-eval.js';
import { solveVectorized } from './vectorized-cfr.js';
import { buildComboMapping, remapReachToChild, enumerateDealableCards } from './combo-remap.js';
import type { TreeConfig } from '../types.js';
import type { WeightedCombo } from '../integration/preflop-ranges.js';

// --- Public API ---

export interface ChanceCFRParams {
  /** Board cards (3 for flop, 4 for turn) */
  board: number[];

  /** Tree config for the current street (turn/flop) */
  treeConfig: TreeConfig;

  /** Tree config for the river betting tree */
  riverTreeConfig: TreeConfig;

  /** Full OOP range */
  oopRange: WeightedCombo[];

  /** Full IP range */
  ipRange: WeightedCombo[];

  /** CFR iterations for the current street */
  iterations: number;

  /** CFR iterations for each river subtree (default: 500) */
  riverIterations?: number;

  /** Progress callback */
  onProgress?: (phase: string, detail: string, pct: number) => void;
}

export interface ChanceCFRResult {
  /** Solved turn/flop tree */
  tree: import('./flat-tree.js').FlatTree;

  /** Solved turn/flop store */
  store: ArrayStore;

  /** Valid combos on the current street */
  validCombos: ValidCombos;

  /** Number of river subtrees solved */
  numRiverSubtrees: number;

  /** Total time in ms */
  elapsedMs: number;

  /** Blocker matrix */
  blockerMatrix: Uint8Array;

  /** Transition equity matrix (averaged across river cards) */
  equityMatrix: Float32Array;
}

/**
 * Solve a turn (or future: flop) scenario with chance-aware CFR.
 *
 * Pre-solves all river subtrees to build a transition equity matrix,
 * then runs turn CFR using that equity matrix at showdown terminals.
 */
export function solveChanceCFR(params: ChanceCFRParams): ChanceCFRResult {
  const { board, treeConfig, riverTreeConfig, oopRange, ipRange, iterations, onProgress } = params;
  const riverIterations = params.riverIterations ?? 500;

  const startTime = Date.now();

  // 1. Build current-street valid combos
  const validCombos = enumerateValidCombos(board);
  const nc = validCombos.numCombos;
  const blockerMatrix = buildBlockerMatrix(validCombos.combos);

  // 2. Build current-street tree (singleStreet --- showdown terminals = transitions)
  const currentConfig: TreeConfig = { ...treeConfig, singleStreet: true };
  const root = buildTree(currentConfig);
  const flatTree = flattenTree(root, 2);

  const store = new ArrayStore(flatTree, nc);

  // 3. Pre-solve all river subtrees and build transition equity matrix
  const dealableCards = enumerateDealableCards(board);
  const numRivers = dealableCards.length;

  if (onProgress) {
    onProgress('river', `Pre-solving ${numRivers} river subtrees...`, 0);
  }

  // Build river tree structure once (same for all river cards)
  const riverConfig: TreeConfig = { ...riverTreeConfig, singleStreet: true };
  const riverRootTemplate = buildTree(riverConfig);

  // Accumulators for transition equity matrix
  // winsMatrix[i * nc + j] = number of river runouts where combo i beats combo j
  // totalMatrix[i * nc + j] = number of river runouts where both combos survive
  const winsMatrix = new Float32Array(nc * nc);
  const totalMatrix = new Float32Array(nc * nc);

  for (let ri = 0; ri < numRivers; ri++) {
    const riverCard = dealableCards[ri];
    const riverBoard = [...board, riverCard];

    // Build combo mapping
    const mapping = buildComboMapping(validCombos, board, riverCard);
    const childNC = mapping.childNC;

    // Build river showdown matrix
    const childBlocker = mapping.childBlockerMatrix;
    const riverShowdown = buildShowdownMatrix(mapping.childCombos.combos, riverBoard, childBlocker);

    // Build river flat tree + store
    const riverFlat = flattenTree(riverRootTemplate, 2);
    if (riverConfig.rake && riverConfig.rake.percentage > 0) {
      applyRakeToTree(riverFlat, riverConfig.rake.percentage, riverConfig.rake.cap);
    }
    const riverStore = new ArrayStore(riverFlat, childNC);

    // Build full ranges for river (remap from parent reaches)
    const oopInitReach = buildReachFromRange(oopRange, validCombos);
    const ipInitReach = buildReachFromRange(ipRange, validCombos);
    const riverOOPReach = remapReachToChild(oopInitReach, mapping);
    const riverIPReach = remapReachToChild(ipInitReach, mapping);

    const riverOOPRange: WeightedCombo[] = mapping.childCombos.combos.map((combo, ci) => ({
      combo,
      weight: riverOOPReach[ci],
    }));
    const riverIPRange: WeightedCombo[] = mapping.childCombos.combos.map((combo, ci) => ({
      combo,
      weight: riverIPReach[ci],
    }));

    // Solve river CFR
    solveVectorized({
      tree: riverFlat,
      store: riverStore,
      board: riverBoard,
      oopRange: riverOOPRange,
      ipRange: riverIPRange,
      iterations: riverIterations,
      showdownMatrix: riverShowdown,
      blockerMatrix: childBlocker,
    });

    // Accumulate showdown results into transition equity matrix
    // For each pair of turn combos that survive on this river card,
    // record the showdown outcome from the river evaluation
    for (let ti = 0; ti < nc; ti++) {
      const ci = mapping.parentToChild[ti];
      if (ci < 0) continue; // blocked by river card

      for (let tj = ti + 1; tj < nc; tj++) {
        if (blockerMatrix[ti * nc + tj]) continue; // share a card

        const cj = mapping.parentToChild[tj];
        if (cj < 0) continue; // blocked by river card

        if (childBlocker[ci * childNC + cj]) continue; // blocked in river combos

        // Get showdown result for this river card
        const result = riverShowdown[ci * childNC + cj]; // +1, 0, -1
        totalMatrix[ti * nc + tj]++;
        if (result > 0) {
          winsMatrix[ti * nc + tj]++;
        } else if (result < 0) {
          winsMatrix[tj * nc + ti]++;
        }
        // ties: neither gets a win, but total is incremented
      }
    }

    if (onProgress && (ri + 1) % 4 === 0) {
      onProgress('river', `${ri + 1}/${numRivers} rivers solved`, ((ri + 1) / numRivers) * 100);
    }
  }

  if (onProgress) {
    onProgress('river', `All ${numRivers} rivers solved. Building equity matrix...`, 100);
  }

  // 4. Convert accumulators to equity matrix
  const equityMatrix = new Float32Array(nc * nc);
  for (let i = 0; i < nc; i++) {
    for (let j = i + 1; j < nc; j++) {
      if (blockerMatrix[i * nc + j]) continue;

      const total = totalMatrix[i * nc + j];
      if (total === 0) continue;

      const winsI = winsMatrix[i * nc + j];
      const winsJ = winsMatrix[j * nc + i];
      const ties = total - winsI - winsJ;

      equityMatrix[i * nc + j] = (winsI + 0.5 * ties) / total;
      equityMatrix[j * nc + i] = (winsJ + 0.5 * ties) / total;
    }
  }

  console.log(`  Transition equity matrix built: ${nc}x${nc} (${numRivers} rivers averaged)`);

  // 5. Run turn CFR with equity matrix
  if (onProgress) {
    onProgress('turn', `Solving turn CFR (${iterations} iterations)...`, 0);
  }

  solveVectorized({
    tree: flatTree,
    store,
    board,
    oopRange,
    ipRange,
    iterations,
    equityMatrix,
    blockerMatrix,
    onProgress: onProgress
      ? (iter, _elapsed) => {
          if ((iter + 1) % 50 === 0) {
            onProgress('turn', `Iter ${iter + 1}/${iterations}`, ((iter + 1) / iterations) * 100);
          }
        }
      : undefined,
  });

  const elapsedMs = Date.now() - startTime;

  return {
    tree: flatTree,
    store,
    validCombos,
    numRiverSubtrees: numRivers,
    elapsedMs,
    blockerMatrix,
    equityMatrix,
  };
}

// --- Flop Chance-CFR: Nested Pre-solve Over Turn Cards ---

export interface FlopChanceCFRParams {
  /** Board cards (3 for flop) */
  board: number[];
  /** Tree config for flop/turn betting */
  treeConfig: TreeConfig;
  /** Tree config for river betting (singleStreet) */
  riverTreeConfig: TreeConfig;
  /** Full OOP range */
  oopRange: WeightedCombo[];
  /** Full IP range */
  ipRange: WeightedCombo[];
  /** CFR iterations for the flop */
  iterations: number;
  /** CFR iterations for each turn subtree (default: 500) */
  turnIterations?: number;
  /** CFR iterations for each river subtree (default: 200) */
  riverIterations?: number;
  /**
   * Optional conditional OOP reach (Float32Array, length = nc).
   * When provided, turn subtrees are solved with this range instead of
   * the full flop range. Use the conditional check-raise/bet range at the
   * target node for more accurate per-pair payoffs.
   */
  initialOopReach?: Float32Array;
  /** Optional conditional IP reach for turn subtrees (length = nc). */
  initialIpReach?: Float32Array;
  /**
   * Override starting pot for turn subtrees.
   * Should be the actual pot at the turn entry point (e.g. after P1 calls
   * the flop check-raise). Defaults to treeConfig.startingPot.
   */
  turnStartingPot?: number;
  /** Override effective stack for turn subtrees. */
  turnEffectiveStack?: number;
  /** Progress callback */
  onProgress?: (phase: string, detail: string, pct: number) => void;
}

/**
 * Solve a flop scenario with nested chance-aware CFR.
 *
 * For each of ~47 possible turn cards:
 *   1. Pre-solve the turn using chance-CFR (which pre-solves rivers)
 *   2. Traverse the solved turn tree to extract per-pair realized payoffs
 *
 * The realized payoffs capture betting dynamics (bluffing, value betting,
 * fold equity) that static showdown equity misses.
 *
 * These payoffs are averaged across turn cards and normalized to build
 * a "realized equity matrix" for the flop solver.
 */
export function solveFlopChanceCFR(params: FlopChanceCFRParams): ChanceCFRResult {
  const { board, treeConfig, riverTreeConfig, oopRange, ipRange, iterations, onProgress } = params;
  const turnIterations = params.turnIterations ?? 500;
  const riverIterations = params.riverIterations ?? 200;

  const startTime = Date.now();

  // 1. Build flop valid combos
  const validCombos = enumerateValidCombos(board);
  const nc = validCombos.numCombos;
  const blockerMatrix = buildBlockerMatrix(validCombos.combos);

  // 2. Build flop tree (single-street: flop betting only)
  const flopConfig: TreeConfig = { ...treeConfig, singleStreet: true };
  const flopRoot = buildTree(flopConfig);
  const flopFlatTree = flattenTree(flopRoot, 2);
  const flopStore = new ArrayStore(flopFlatTree, nc);

  // 3. Build initial reaches for turn subtrees.
  // Use conditional reaches if provided (captures the actual range at the
  // turn entry point after the target action sequence), otherwise fall back
  // to the full input range.
  const oopReach = params.initialOopReach ?? buildReachFromRange(oopRange, validCombos);
  const ipReach = params.initialIpReach ?? buildReachFromRange(ipRange, validCombos);

  // 4. Pre-solve all turn positions
  const dealableTurns = enumerateDealableCards(board);
  const numTurns = dealableTurns.length;

  if (onProgress) {
    onProgress('turn', `Pre-solving ${numTurns} turn positions...`, 0);
  }

  // Accumulators for realized equity
  const payoffSum = new Float64Array(nc * nc);
  const payoffCount = new Float32Array(nc * nc);

  // Turn config: override pot/stack if the caller specified the actual turn
  // entry conditions (e.g. pot=82, effectiveStack=79 after a flop check-raise call).
  const turnConfig: TreeConfig = {
    ...treeConfig,
    singleStreet: true,
    ...(params.turnStartingPot !== undefined && { startingPot: params.turnStartingPot }),
    ...(params.turnEffectiveStack !== undefined && { effectiveStack: params.turnEffectiveStack }),
  };

  for (let ti = 0; ti < numTurns; ti++) {
    const turnCard = dealableTurns[ti];
    const turnBoard = [...board, turnCard];

    // Build combo mapping for this turn card
    const mapping = buildComboMapping(validCombos, board, turnCard);
    const childNC = mapping.childNC;

    // Remap ranges for turn
    const turnOopReach = remapReachToChild(oopReach, mapping);
    const turnIpReach = remapReachToChild(ipReach, mapping);
    const turnOopRange: WeightedCombo[] = mapping.childCombos.combos.map((combo, ci) => ({
      combo,
      weight: turnOopReach[ci],
    }));
    const turnIpRange: WeightedCombo[] = mapping.childCombos.combos.map((combo, ci) => ({
      combo,
      weight: turnIpReach[ci],
    }));

    // Solve turn using chance-CFR (which pre-solves rivers)
    const turnResult = solveChanceCFR({
      board: turnBoard,
      treeConfig: turnConfig,
      riverTreeConfig,
      oopRange: turnOopRange,
      ipRange: turnIpRange,
      iterations: turnIterations,
      riverIterations,
    });

    // Extract per-pair realized payoffs from the solved turn tree
    const pairPayoffs = computeAllPairPayoffs(
      turnResult.tree,
      turnResult.store,
      turnResult.equityMatrix,
      turnResult.blockerMatrix,
      childNC,
    );

    // Accumulate into flop equity (mapping child combos back to parent)
    for (let pi = 0; pi < nc; pi++) {
      const ci = mapping.parentToChild[pi];
      if (ci < 0) continue;

      for (let pj = pi + 1; pj < nc; pj++) {
        if (blockerMatrix[pi * nc + pj]) continue;

        const cj = mapping.parentToChild[pj];
        if (cj < 0) continue;

        if (turnResult.blockerMatrix[ci * childNC + cj]) continue;

        const payoff = pairPayoffs[ci * childNC + cj];
        payoffSum[pi * nc + pj] += payoff;
        payoffSum[pj * nc + pi] -= payoff; // zero-sum
        payoffCount[pi * nc + pj]++;
        payoffCount[pj * nc + pi]++;
      }
    }

    if (onProgress) {
      onProgress('turn', `Turn ${ti + 1}/${numTurns} solved`, ((ti + 1) / numTurns) * 100);
    }
  }

  if (onProgress) {
    onProgress('turn', `All ${numTurns} turns solved. Building realized equity...`, 100);
  }

  // 5. Convert realized payoffs to equity matrix [0,1]
  // Compute average payoff per pair and normalize using data-driven scaling
  const avgPayoffs = new Float32Array(nc * nc);
  let minPayoff = Infinity,
    maxPayoff = -Infinity;

  for (let i = 0; i < nc; i++) {
    for (let j = i + 1; j < nc; j++) {
      const count = payoffCount[i * nc + j];
      if (count === 0) continue;
      const avg = payoffSum[i * nc + j] / count;
      avgPayoffs[i * nc + j] = avg;
      avgPayoffs[j * nc + i] = -avg;
      if (avg < minPayoff) minPayoff = avg;
      if (avg > maxPayoff) maxPayoff = avg;
      if (-avg < minPayoff) minPayoff = -avg;
      if (-avg > maxPayoff) maxPayoff = -avg;
    }
  }

  // Convert turn game payoffs to equity scale used by computeEquityShowdownEV.
  // Formula: outEV[i] = validOppReach * losePayoff + eqSum * payoffSpread
  // So: equity[i][j] = (payoff[i][j] - losePayoff) / payoffSpread
  // The formula is purely linear --- values outside [0,1] are valid and necessary
  // when turn+river betting creates pots larger than the flop terminal pot.
  // DO NOT clamp to [0,1]: e.g. payoff=98.8 -> equity=1.706 correctly rounds to
  // max EV at that terminal, whereas clamping to 1.0 would understate it.
  const equityMatrix = new Float32Array(nc * nc);

  if (params.turnStartingPot !== undefined && params.turnEffectiveStack !== undefined) {
    // Terminal-specific normalization anchored to the target node's call terminal.
    // losePayoff = -41 (P0 loses all of the 82-chip turn pot)
    // payoffSpread = 82 (full turn pot)
    const startTotalFlop = treeConfig.effectiveStack + treeConfig.startingPot / 2;
    const losePayoff = params.turnEffectiveStack - startTotalFlop;
    const payoffSpread = params.turnStartingPot;

    for (let i = 0; i < nc; i++) {
      for (let j = i + 1; j < nc; j++) {
        const count = payoffCount[i * nc + j];
        if (count === 0) continue;
        const avg = payoffSum[i * nc + j] / count;
        // No clamping: values outside [0,1] represent larger-than-pot wins/losses
        // from turn/river bets, and the linear EV formula handles them correctly.
        equityMatrix[i * nc + j] = (avg - losePayoff) / payoffSpread;
        equityMatrix[j * nc + i] = (-avg - losePayoff) / payoffSpread;
      }
    }
    console.log(
      `  Realized equity matrix: payoff range [${minPayoff.toFixed(4)}, ${maxPayoff.toFixed(4)}], terminal-normalized (losePayoff=${losePayoff.toFixed(1)}, spread=${payoffSpread.toFixed(1)})`,
    );
  } else {
    // Fallback: data-driven min-max normalization
    const payoffRange = maxPayoff - minPayoff;
    if (payoffRange > 1e-10) {
      for (let i = 0; i < nc; i++) {
        for (let j = i + 1; j < nc; j++) {
          if (payoffCount[i * nc + j] === 0) continue;
          equityMatrix[i * nc + j] = (avgPayoffs[i * nc + j] - minPayoff) / payoffRange;
          equityMatrix[j * nc + i] = (avgPayoffs[j * nc + i] - minPayoff) / payoffRange;
        }
      }
    }
    console.log(
      `  Realized equity matrix: payoff range [${minPayoff.toFixed(4)}, ${maxPayoff.toFixed(4)}], ${numTurns} turns`,
    );
  }

  // 6. Solve flop single-street tree with realized equity
  if (onProgress) {
    onProgress('flop', `Solving flop CFR (${iterations} iterations)...`, 0);
  }

  solveVectorized({
    tree: flopFlatTree,
    store: flopStore,
    board,
    oopRange,
    ipRange,
    iterations,
    equityMatrix,
    blockerMatrix,
    onProgress: onProgress
      ? (iter, _elapsed) => {
          if ((iter + 1) % 50 === 0) {
            onProgress('flop', `Iter ${iter + 1}/${iterations}`, ((iter + 1) / iterations) * 100);
          }
        }
      : undefined,
  });

  const elapsedMs = Date.now() - startTime;

  return {
    tree: flopFlatTree,
    store: flopStore,
    validCombos,
    numRiverSubtrees: numTurns,
    elapsedMs,
    blockerMatrix,
    equityMatrix,
  };
}

// --- Per-Pair Realized Payoff Extraction ---

/**
 * Compute realized payoff for ALL pairs (i,j) by traversing the solved tree.
 *
 * For each pair, the realized payoff is the expected chips OOP gains when
 * both players follow the equilibrium strategy (average strategy from CFR).
 *
 * This captures fold equity, value betting, and bluffing dynamics that
 * raw showdown equity misses.
 *
 * @returns Float32Array(nc * nc) where payoffs[i*nc+j] = OOP's expected payoff for pair (i,j)
 */
function computeAllPairPayoffs(
  tree: FlatTree,
  store: ArrayStore,
  equityMatrix: Float32Array,
  blockerMatrix: Uint8Array,
  nc: number,
): Float32Array {
  // 1. Pre-compute average strategy for all nodes
  const numNodes = tree.numNodes;
  const strategies: Float32Array[] = [];
  for (let nid = 0; nid < numNodes; nid++) {
    const numActions = tree.nodeNumActions[nid];
    const strat = new Float32Array(numActions * nc);
    store.getAverageStrategy(nid, numActions, strat);
    strategies[nid] = strat;
  }

  // 2. DFS to find all terminals and compute per-combo reach to each terminal
  interface TerminalInfo {
    oopReach: Float32Array;
    ipReach: Float32Array;
    isShowdown: boolean;
    pot: number;
    stacks: [number, number];
    folder: number; // which player folds (0=OOP, 1=IP), only for fold terminals
  }

  const terminals: TerminalInfo[] = [];

  function dfs(nodeId: number, oopReach: Float32Array, ipReach: Float32Array): void {
    if (isTerminal(nodeId)) {
      const ti = decodeTerminalId(nodeId);
      terminals.push({
        oopReach: new Float32Array(oopReach),
        ipReach: new Float32Array(ipReach),
        isShowdown: !!tree.terminalIsShowdown[ti],
        pot: tree.terminalPot[ti],
        stacks: [tree.terminalStacks[ti * 2], tree.terminalStacks[ti * 2 + 1]],
        folder: tree.terminalFolder[ti],
      });
      return;
    }

    const player = tree.nodePlayer[nodeId];
    const numActions = tree.nodeNumActions[nodeId];
    const actionOffset = tree.nodeActionOffset[nodeId];
    const strat = strategies[nodeId];

    for (let a = 0; a < numActions; a++) {
      const childId = tree.childNodeId[actionOffset + a];
      const childOop = new Float32Array(oopReach);
      const childIp = new Float32Array(ipReach);

      if (player === 0) {
        for (let c = 0; c < nc; c++) childOop[c] *= strat[a * nc + c];
      } else {
        for (let c = 0; c < nc; c++) childIp[c] *= strat[a * nc + c];
      }

      dfs(childId, childOop, childIp);
    }
  }

  // Start DFS with uniform reach
  const initOop = new Float32Array(nc).fill(1);
  const initIp = new Float32Array(nc).fill(1);
  dfs(0, initOop, initIp);

  // 3. Compute startTotal (same for all terminals in a balanced tree)
  const t0 = terminals[0];
  const startTotal = (t0.stacks[0] + t0.stacks[1] + t0.pot) / 2;

  // 4. Compute per-pair payoffs
  const payoffs = new Float32Array(nc * nc);

  for (let i = 0; i < nc; i++) {
    for (let j = i + 1; j < nc; j++) {
      if (blockerMatrix[i * nc + j]) continue;

      let totalPayoff = 0;

      for (const term of terminals) {
        const oopR = term.oopReach[i];
        const ipR = term.ipReach[j];
        const reachProb = oopR * ipR;

        if (reachProb < 1e-12) continue;

        if (term.isShowdown) {
          const winPayoff = term.stacks[0] + term.pot - startTotal;
          const losePayoff = term.stacks[0] - startTotal;
          const spread = winPayoff - losePayoff;
          const eq = equityMatrix[i * nc + j];
          totalPayoff += reachProb * (losePayoff + eq * spread);
        } else {
          // Fold terminal
          if (term.folder === 0) {
            // OOP folds
            totalPayoff += reachProb * (term.stacks[0] - startTotal);
          } else {
            // IP folds
            totalPayoff += reachProb * (term.stacks[0] + term.pot - startTotal);
          }
        }
      }

      payoffs[i * nc + j] = totalPayoff;
      payoffs[j * nc + i] = -totalPayoff;
    }
  }

  return payoffs;
}
