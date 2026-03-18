// Vectorized Full-Tree CFR+ Engine
//
// Processes ALL hand combos simultaneously in each traversal.
// Uses precomputed showdown/equity matrix — no hand evaluation during CFR.
// Stores regrets/strategies in contiguous ArrayStore.
//
// ZERO-ALLOCATION traversal: all buffers pre-allocated before the CFR loop.
// Recursive functions use depth-indexed offsets into flat buffers.
// NO new TypedArray allocations inside the hot path.

import type { FlatTree } from './flat-tree.js';
import { isTerminal, decodeTerminalId } from './flat-tree.js';
import { ArrayStore } from './array-store.js';
import { enumerateValidCombos, buildBlockerMatrix, buildReachFromRange } from './combo-utils.js';
import {
  buildShowdownMatrix,
  buildEquityCache,
  computeShowdownEV,
  computeFoldEV,
  computeEquityShowdownEV,
  precomputeHandValues,
  computeShowdownEVMultiWay,
  computeFoldEVMultiWay,
  getEquityCache,
  rebuildShowdownCacheForMCCFR,
} from './showdown-eval.js';
import { computeExploitability } from './exploitability.js';
import type { WeightedCombo } from '../integration/preflop-ranges.js';
import { getWasmKernels } from './wasm-kernels.js';

export interface VectorizedSolveParams {
  tree: FlatTree;
  store: ArrayStore;
  board: number[];
  oopRange: WeightedCombo[];
  ipRange: WeightedCombo[];
  iterations: number;
  onProgress?: (iter: number, elapsed: number) => void;
  /** Pre-built Int8 showdown matrix (river/turn — binary win/lose/tie). */
  showdownMatrix?: Int8Array;
  /** Pre-built Float32 equity matrix (flop — exact equity fractions).
   *  Takes precedence over showdownMatrix. */
  equityMatrix?: Float32Array;
  /** Pre-built blocker matrix. */
  blockerMatrix?: Uint8Array;
  /** Starting node ID for subgame solving (default: 0 = root). */
  startNodeId?: number;
  /** Global iteration offset for parallel workers (Linear CFR weighting). */
  globalIterOffset?: number;
  /** Fraction of iterations used as warmup (no strategy accumulation). Default: 0. */
  warmupFraction?: number;
  /** Target exploitability as % of pot. When set, solver checks every
   *  `deviationCheckInterval` iterations and stops early if below threshold. */
  targetDeviation?: number;
  /** How often to check exploitability (default: every 200 iterations). */
  deviationCheckInterval?: number;
  /** Starting pot for exploitability calculation (required if targetDeviation is set). */
  startingPot?: number;
  /** Skip expensive equity cache + WASM init. Used by parallel workers that
   *  already receive the equity matrix via SharedArrayBuffer. Falls back to
   *  JS-only equity computation (no WASM acceleration). */
  skipEquityCacheInit?: boolean;
  /** Use Linear CFR weighting instead of DCFR multiplicative discounting.
   *  Linear weighting is compatible with parallel split-iteration solving:
   *  each worker's weighted strategy sums can be simply added together.
   *  Weight for iteration i = (globalIterOffset + i + 1).
   *  DCFR's multiplicative discount is NOT splittable — parallel workers
   *  produce incorrect weights when iterations are divided. */
  useLinearWeighting?: boolean;
  /** MCCFR mode: called before each iteration to sample a new board.
   *  Receives (equityMatrix, oopInitReach, ipInitReach, iterNumber).
   *  Should fill equityMatrix with per-board exact results (1.0/0.5/0.0)
   *  and zero out reaches for dead combos (share card with sampled board). */
  mccrfSampler?: (
    equityMatrix: Float32Array,
    oopInitReach: Float32Array,
    ipInitReach: Float32Array,
    iter: number,
  ) => void;
  /** MCCFR showdown sampler: O(n log n) alternative to mccrfSampler.
   *  Called before each iteration. Should:
   *  (1) sample random turn+river, (2) compute hand values via precomputeHandValues,
   *  (3) call rebuildShowdownCacheForMCCFR to update the O(n) fast cache,
   *  (4) zero reaches for blocked combos.
   *  Uses O(n) prefix-sum showdown eval instead of O(n²) equity matrix. */
  mccrfShowdownSampler?: (
    oopInitReach: Float32Array,
    ipInitReach: Float32Array,
    iter: number,
  ) => void;
}

export interface VectorizedSolveParamsMultiWay {
  tree: FlatTree;
  store: ArrayStore;
  board: number[];
  ranges: WeightedCombo[][];
  numPlayers: number;
  iterations: number;
  onProgress?: (iter: number, elapsed: number) => void;
}

// ─── Reach Pruning ───
// Threshold below which a combo's reach is considered "dead".
// Any branch/combo with ALL reaches below this is skipped entirely.
const PRUNE_THRESHOLD = 1e-6;

/**
 * Fast early-exit check: returns true if ALL elements of `reach` are below PRUNE_THRESHOLD.
 * Breaks immediately on the first live combo, so cost is O(1) for live branches.
 */
function isReachDead(reach: Float32Array, nc: number): boolean {
  for (let i = 0; i < nc; i++) {
    if (reach[i] > PRUNE_THRESHOLD) return false;
  }
  return true;
}

// ─── Pre-allocated buffer pool ───

interface BufferPool {
  /** Save/restore reach: reachSave[depth * nc .. (depth+1)*nc] */
  reachSave: Float32Array;
  /** Node EV result per depth: nodeEV[depth * nc .. (depth+1)*nc] */
  nodeEV: Float32Array;
  /** Action EVs per depth: actionEV[depth * maxAct * nc + a * nc + c] */
  actionEV: Float32Array;
  /** Strategy per depth: strategy[depth * maxAct * nc + a * nc + c] */
  strategy: Float32Array;
  /** Regret deltas per depth */
  regretDelta: Float32Array;
  /** Strategy weights per depth */
  stratWeight: Float32Array;
  maxDepth: number;
  maxActions: number;
  nc: number;
}

function computeMaxDepth(tree: FlatTree): number {
  let maxD = 0;
  const stack: number[] = [0, 0]; // pairs: [nodeId, depth]
  let sp = 0;
  // Use a manual stack to avoid array allocations
  while (sp > 0) {
    const depth = stack[--sp];
    const nodeId = stack[--sp];
    if (depth > maxD) maxD = depth;
    const numActions = tree.nodeNumActions[nodeId];
    const offset = tree.nodeActionOffset[nodeId];
    for (let a = 0; a < numActions; a++) {
      const childId = tree.childNodeId[offset + a];
      if (!isTerminal(childId)) {
        stack[sp++] = childId;
        stack[sp++] = depth + 1;
      } else {
        if (depth + 1 > maxD) maxD = depth + 1;
      }
    }
  }
  // Also handle root manually since while loop won't enter with sp=0
  // Redo with proper initialization
  maxD = 0;
  const dfsStack: Array<[number, number]> = [[0, 0]];
  while (dfsStack.length > 0) {
    const [nid, d] = dfsStack.pop()!;
    if (d > maxD) maxD = d;
    const na = tree.nodeNumActions[nid];
    const off = tree.nodeActionOffset[nid];
    for (let a = 0; a < na; a++) {
      const cid = tree.childNodeId[off + a];
      if (!isTerminal(cid)) {
        dfsStack.push([cid, d + 1]);
      } else {
        if (d + 1 > maxD) maxD = d + 1;
      }
    }
  }
  return maxD;
}

function createBufferPool(tree: FlatTree, nc: number): BufferPool {
  const maxActions = Math.max(...Array.from(tree.nodeNumActions));
  const maxDepth = computeMaxDepth(tree) + 2; // margin

  return {
    reachSave: new Float32Array(maxDepth * nc),
    nodeEV: new Float32Array(maxDepth * nc),
    actionEV: new Float32Array(maxDepth * maxActions * nc),
    strategy: new Float32Array(maxDepth * maxActions * nc),
    regretDelta: new Float32Array(maxDepth * maxActions * nc),
    stratWeight: new Float32Array(maxDepth * maxActions * nc),
    maxDepth,
    maxActions,
    nc,
  };
}

// ─── HU Context ───

interface CFRContext {
  tree: FlatTree;
  store: ArrayStore;
  showdownMatrix: Int8Array | null;
  equityMatrix: Float32Array | null;
  blockerMatrix: Uint8Array;
  nc: number;
  pool: BufferPool;
}

/**
 * Run vectorized CFR+ solver for heads-up.
 */
export function solveVectorized(params: VectorizedSolveParams): void {
  const { tree, store, board, oopRange, ipRange, iterations, onProgress } = params;

  const validCombos = enumerateValidCombos(board);
  const nc = validCombos.numCombos;

  const blockerMatrix = params.blockerMatrix ?? buildBlockerMatrix(validCombos.combos);

  // ── Determine solver mode: showdown-sampler / equity-sampler / static ──
  const mccrfShowdownSampler = params.mccrfShowdownSampler;
  const mccrfSampler = params.mccrfSampler;
  const hasMCCRF = !!(mccrfShowdownSampler || mccrfSampler);

  let equityMatrix: Float32Array | null;
  let showdownMatrix: Int8Array | null;
  let mccrfEquity: Float32Array | null = null;

  if (mccrfShowdownSampler) {
    // ── Showdown sampler: O(n log n) setup + O(n) per terminal ──
    // Sampler rebuilds ShowdownCache each iter. No equity matrix needed.
    const dummyValues = new Float64Array(nc);
    showdownMatrix = rebuildShowdownCacheForMCCFR(validCombos.combos, dummyValues, blockerMatrix);
    equityMatrix = null;
  } else if (mccrfSampler) {
    // ── Equity sampler: O(n²) equity matrix fill per iter ──
    equityMatrix = params.equityMatrix ?? new Float32Array(nc * nc);
    mccrfEquity = equityMatrix;
    showdownMatrix = null;
    if (!params.skipEquityCacheInit) {
      buildEquityCache(validCombos.combos, blockerMatrix);
    }
    getWasmKernels().destroy();
  } else {
    // ── Static mode: precomputed matrix ──
    equityMatrix = params.equityMatrix ?? null;
    showdownMatrix = equityMatrix
      ? null
      : (params.showdownMatrix ?? buildShowdownMatrix(validCombos.combos, board, blockerMatrix));

    if (equityMatrix && !params.skipEquityCacheInit) {
      buildEquityCache(validCombos.combos, blockerMatrix);
      const eqCache = getEquityCache();
      if (eqCache) {
        const wk = getWasmKernels();
        wk.initSync(
          nc,
          equityMatrix,
          validCombos.combos,
          eqCache.cardCombos,
          eqCache.validIndices,
          eqCache.validOffsets,
          eqCache.validLengths,
        );
      }
    }
  }

  const oopInitReach = buildReachFromRange(oopRange, validCombos);
  const ipInitReach = buildReachFromRange(ipRange, validCombos);

  const pool = createBufferPool(tree, nc);

  // Pre-allocate iteration reach arrays (reused each iteration)
  const oopReach = new Float32Array(nc);
  const ipReach = new Float32Array(nc);

  // MCCFR: save original reaches for restoration each iteration
  const oopInitReachFull = hasMCCRF ? new Float32Array(oopInitReach) : null;
  const ipInitReachFull = hasMCCRF ? new Float32Array(ipInitReach) : null;

  const ctx: CFRContext = {
    tree,
    store,
    showdownMatrix,
    equityMatrix: mccrfSampler ? mccrfEquity : equityMatrix,
    blockerMatrix,
    nc,
    pool,
  };

  const sNodeId = params.startNodeId ?? 0;
  const startTime = Date.now();
  const totalSize = store.strategySums.length;
  const checkInterval = params.deviationCheckInterval ?? 200;
  const targetDev = params.targetDeviation;
  const sPot = params.startingPot ?? 1;
  const globalIterOffset = params.globalIterOffset ?? 0;
  const warmupIters = Math.floor(iterations * (params.warmupFraction ?? 0));
  const useLinearWeighting = params.useLinearWeighting ?? false;

  // Pre-allocate saved sums buffer for linear weighting delta computation
  const savedSums = useLinearWeighting ? new Float32Array(totalSize) : null;

  for (let iter = 0; iter < iterations; iter++) {
    // MCCFR: sample a new board and update reaches
    if (hasMCCRF && oopInitReachFull && ipInitReachFull) {
      // Restore full reaches before sampling
      oopInitReach.set(oopInitReachFull);
      ipInitReach.set(ipInitReachFull);

      if (mccrfShowdownSampler) {
        // Showdown sampler: rebuilds fast cache (O(n log n)), zeros blocked reaches
        mccrfShowdownSampler(oopInitReach, ipInitReach, iter);
      } else if (mccrfSampler && mccrfEquity) {
        // Equity sampler: fills O(n²) equity matrix, zeros blocked reaches
        mccrfSampler(mccrfEquity, oopInitReach, ipInitReach, iter);
      }
    }

    // Save strategy sums BEFORE traversal (for linear weighting delta)
    if (savedSums) {
      savedSums.set(store.strategySums);
    }

    // Traversal for player 0 (OOP)
    oopReach.set(oopInitReach);
    ipReach.set(ipInitReach);
    cfrTraverseHU(ctx, sNodeId, oopReach, ipReach, 0, 0);

    // Traversal for player 1 (IP)
    oopReach.set(oopInitReach);
    ipReach.set(ipInitReach);
    cfrTraverseHU(ctx, sNodeId, oopReach, ipReach, 1, 0);

    if (useLinearWeighting) {
      // ── Linear CFR Weighting ──
      // Weight = globalIterOffset + iter + 1 (linearly increasing).
      // Apply weight to THIS iteration's delta (new contribution).
      // This is compatible with parallel split-iteration solving:
      // sum of all workers' weighted sums = sequential weighted sum.
      const weight = globalIterOffset + iter + 1;
      for (let i = 0; i < totalSize; i++) {
        const delta = store.strategySums[i] - savedSums![i];
        store.strategySums[i] = savedSums![i] + delta * weight;
      }
    } else {
      // ── DCFR Strategy Sum Discounting ──
      // Use global iteration count (globalIterOffset + local iter) so parallel
      // workers discount relative to their position in the overall solve,
      // not from scratch.
      const t = globalIterOffset + iter + 1;
      const factor = (t * t) / ((t + 1) * (t + 1)); // (t/(t+1))^2
      for (let i = 0; i < totalSize; i++) {
        store.strategySums[i] *= factor;
      }

      // ── Warmup: clear strategy sums during warmup phase ──
      if (iter < warmupIters) {
        store.strategySums.fill(0);
      }
    }

    // ── Convergence check: exploitability ──
    if (targetDev !== undefined && (iter + 1) % checkInterval === 0 && iter >= checkInterval) {
      const devResult = computeExploitability({
        tree,
        store,
        nc,
        oopReach: oopInitReach,
        ipReach: ipInitReach,
        showdownMatrix,
        equityMatrix,
        blockerMatrix,
        startingPot: sPot,
      });
      if (devResult.exploitabilityPct <= targetDev) {
        if (onProgress) {
          onProgress(iter + 1, Date.now() - startTime);
        }
        break; // Converged — stop early
      }
    }

    // Report progress: every 10 iters for small runs (parallel workers), 100 for large
    const reportInterval = iterations <= 200 ? 10 : 100;
    if (onProgress && (iter + 1) % reportInterval === 0) {
      onProgress(iter + 1, Date.now() - startTime);
    }
  }
}

/**
 * Zero-allocation CFR traversal for heads-up.
 *
 * Writes its nc-element EV result into pool.nodeEV[depth * nc .. (depth+1) * nc].
 * The caller reads from there before the next action's recursion overwrites it.
 */
function cfrTraverseHU(
  ctx: CFRContext,
  nodeId: number,
  oopReach: Float32Array,
  ipReach: Float32Array,
  traverser: number,
  depth: number,
): void {
  const { tree, store, nc, pool } = ctx;
  const evOff = depth * nc; // where this node's EV lives in pool.nodeEV

  // ── Terminal ──
  if (isTerminal(nodeId)) {
    computeTerminalEVHU(ctx, nodeId, oopReach, ipReach, traverser, pool.nodeEV, evOff);
    return;
  }

  // ── Whole-node reach pruning ──
  // If either player's reach is all dead, the entire subtree contributes ~0 EV.
  // Traverser dead → regret/strategy updates are ~0 weighted, EV contribution ~0.
  // Opponent dead → terminal EVs are ~0 (no opponent hands to win from).
  if (isReachDead(oopReach, nc) || isReachDead(ipReach, nc)) {
    pool.nodeEV.fill(0, evOff, evOff + nc);
    return;
  }

  const player = tree.nodePlayer[nodeId];
  const numActions = tree.nodeNumActions[nodeId];
  const actionOffset = tree.nodeActionOffset[nodeId];

  // Compute current strategy into pool.strategy[depth * maxAct * nc ..]
  const stratOff = depth * pool.maxActions * nc;
  store.getCurrentStrategyAt(nodeId, numActions, pool.strategy, stratOff);

  // Zero this node's EV
  for (let c = 0; c < nc; c++) pool.nodeEV[evOff + c] = 0;

  // Action EV base for this depth
  const actEVBase = depth * pool.maxActions * nc;

  // Reach save base for this depth
  const saveOff = depth * nc;

  for (let a = 0; a < numActions; a++) {
    const childId = tree.childNodeId[actionOffset + a];
    const sOff = stratOff + a * nc; // strategy offset for action a

    // Save reach and multiply by strategy IN PLACE
    if (player === 0) {
      for (let c = 0; c < nc; c++) {
        pool.reachSave[saveOff + c] = oopReach[c];
        oopReach[c] *= pool.strategy[sOff + c];
      }
    } else {
      for (let c = 0; c < nc; c++) {
        pool.reachSave[saveOff + c] = ipReach[c];
        ipReach[c] *= pool.strategy[sOff + c];
      }
    }

    // ── Per-action branch pruning ──
    // If acting player's reach is all dead after strategy multiplication,
    // no hands take this action → skip entire subtree.
    const actingReach = player === 0 ? oopReach : ipReach;
    if (isReachDead(actingReach, nc)) {
      // Zero action EV for this skipped branch
      const actSlot = actEVBase + a * nc;
      pool.actionEV.fill(0, actSlot, actSlot + nc);
      // Restore reach
      if (player === 0) {
        for (let c = 0; c < nc; c++) oopReach[c] = pool.reachSave[saveOff + c];
      } else {
        for (let c = 0; c < nc; c++) ipReach[c] = pool.reachSave[saveOff + c];
      }
      // nodeEV += strategy * 0 = 0, skip accumulation
      continue;
    }

    // Recurse — child writes to pool.nodeEV[(depth+1) * nc ..]
    cfrTraverseHU(ctx, childId, oopReach, ipReach, traverser, depth + 1);

    // Copy child EV into this depth's action EV slot before it's overwritten
    const childEvOff = (depth + 1) * nc;
    const actSlot = actEVBase + a * nc;
    for (let c = 0; c < nc; c++) {
      pool.actionEV[actSlot + c] = pool.nodeEV[childEvOff + c];
    }

    // Restore reach
    if (player === 0) {
      for (let c = 0; c < nc; c++) oopReach[c] = pool.reachSave[saveOff + c];
    } else {
      for (let c = 0; c < nc; c++) ipReach[c] = pool.reachSave[saveOff + c];
    }

    // Accumulate EV into nodeEV.
    // When the TRAVERSER acts: weight by their own strategy (standard CFR).
    // When the OPPONENT acts: simple sum — the opponent's strategy is already
    // incorporated via reach modification (oppReach *= strategy) before recursion.
    // Multiplying again would double-count and collapse per-combo differentiation.
    if (player === traverser) {
      for (let c = 0; c < nc; c++) {
        pool.nodeEV[evOff + c] += pool.strategy[sOff + c] * pool.actionEV[actSlot + c];
      }
    } else {
      for (let c = 0; c < nc; c++) {
        pool.nodeEV[evOff + c] += pool.actionEV[actSlot + c];
      }
    }
  }

  // Update regrets and strategy sums if this is the traverser's node
  if (player === traverser) {
    const rdOff = depth * pool.maxActions * nc;
    const swOff = depth * pool.maxActions * nc;
    const playerReach = traverser === 0 ? oopReach : ipReach;

    for (let a = 0; a < numActions; a++) {
      const actSlot = actEVBase + a * nc;
      const rdSlot = rdOff + a * nc;
      const swSlot = swOff + a * nc;
      const sOff = stratOff + a * nc;
      for (let c = 0; c < nc; c++) {
        // ── Combo-level pruning: skip dead combos ──
        if (playerReach[c] < PRUNE_THRESHOLD) {
          pool.regretDelta[rdSlot + c] = 0;
          pool.stratWeight[swSlot + c] = 0;
          continue;
        }
        pool.regretDelta[rdSlot + c] = pool.actionEV[actSlot + c] - pool.nodeEV[evOff + c];
        pool.stratWeight[swSlot + c] = playerReach[c] * pool.strategy[sOff + c];
      }
    }

    store.updateRegretsAt(nodeId, numActions, pool.regretDelta, rdOff);
    store.addStrategyWeightsAt(nodeId, numActions, pool.stratWeight, swOff);
  }
}

/**
 * Compute terminal EV into outEV[outOff .. outOff+nc].
 */
function computeTerminalEVHU(
  ctx: CFRContext,
  nodeId: number,
  oopReach: Float32Array,
  ipReach: Float32Array,
  traverser: number,
  outEV: Float32Array,
  outOff: number,
): void {
  const { tree, showdownMatrix, equityMatrix, blockerMatrix, nc } = ctx;

  // ── Opponent-reach pruning: if opponent has no live combos, EV is 0 ──
  const oppReach = traverser === 0 ? ipReach : oopReach;
  if (isReachDead(oppReach, nc)) {
    for (let c = 0; c < nc; c++) outEV[outOff + c] = 0;
    return;
  }

  const ti = decodeTerminalId(nodeId);

  const pot = tree.terminalPot[ti];
  const np = tree.numPlayers;
  const stacks: [number, number] = [tree.terminalStacks[ti * np], tree.terminalStacks[ti * np + 1]];

  // We need a contiguous nc-length view for the EV functions.
  // Use subarray — this creates a lightweight view, not a new backing buffer.
  const evSlice = outEV.subarray(outOff, outOff + nc);

  if (tree.terminalIsShowdown[ti]) {
    if (equityMatrix) {
      computeEquityShowdownEV(
        equityMatrix,
        blockerMatrix,
        oopReach,
        ipReach,
        pot,
        stacks,
        nc,
        traverser,
        evSlice,
      );
    } else {
      computeShowdownEV(
        showdownMatrix!,
        blockerMatrix,
        oopReach,
        ipReach,
        pot,
        stacks,
        nc,
        traverser,
        evSlice,
      );
    }
  } else {
    const folder = tree.terminalFolder[ti];
    const opponentReach = traverser === 0 ? ipReach : oopReach;
    computeFoldEV(blockerMatrix, opponentReach, pot, stacks, nc, traverser, folder, evSlice);
  }
}

// ─── Multi-Way (unchanged — not on hot path for benchmark) ───

interface CFRContextMultiWay {
  tree: FlatTree;
  store: ArrayStore;
  handValues: Float64Array;
  blockerMatrix: Uint8Array;
  numCombos: number;
  numPlayers: number;
}

export function solveVectorizedMultiWay(params: VectorizedSolveParamsMultiWay): void {
  const { tree, store, board, ranges, numPlayers, iterations, onProgress } = params;

  const validCombos = enumerateValidCombos(board);
  const nc = validCombos.numCombos;
  const blockerMatrix = buildBlockerMatrix(validCombos.combos);
  const handValues = precomputeHandValues(validCombos.combos, board);
  const initReach = ranges.map((r) => buildReachFromRange(r, validCombos));

  const mwCtx: CFRContextMultiWay = {
    tree,
    store,
    handValues,
    blockerMatrix,
    numCombos: nc,
    numPlayers,
  };

  const startTime = Date.now();

  for (let iter = 0; iter < iterations; iter++) {
    for (let traverser = 0; traverser < numPlayers; traverser++) {
      const reachProbs = initReach.map((r) => new Float32Array(r));
      cfrTraverseMultiWay(mwCtx, 0, reachProbs, traverser);
    }
    if (onProgress && (iter + 1) % 100 === 0) {
      onProgress(iter + 1, Date.now() - startTime);
    }
  }
}

function cfrTraverseMultiWay(
  ctx: CFRContextMultiWay,
  nodeId: number,
  reachProbs: Float32Array[],
  traverser: number,
): Float32Array {
  const { tree, store, numCombos: nc } = ctx;

  if (isTerminal(nodeId)) {
    return computeTerminalEVMultiWay(ctx, nodeId, reachProbs, traverser);
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
    const newReach = reachProbs.map((r) => new Float32Array(r));
    for (let c = 0; c < nc; c++) {
      newReach[player][c] *= strategy[a * nc + c];
    }
    actionEVs[a] = cfrTraverseMultiWay(ctx, childId, newReach, traverser);
    if (player === traverser) {
      for (let c = 0; c < nc; c++) {
        nodeEV[c] += strategy[a * nc + c] * actionEVs[a][c];
      }
    } else {
      for (let c = 0; c < nc; c++) {
        nodeEV[c] += actionEVs[a][c];
      }
    }
  }

  if (player === traverser) {
    const regretDeltas = new Float32Array(numActions * nc);
    const stratWeights = new Float32Array(numActions * nc);
    for (let a = 0; a < numActions; a++) {
      for (let c = 0; c < nc; c++) {
        regretDeltas[a * nc + c] = actionEVs[a][c] - nodeEV[c];
        stratWeights[a * nc + c] = reachProbs[traverser][c] * strategy[a * nc + c];
      }
    }
    store.updateRegrets(nodeId, numActions, regretDeltas);
    store.addStrategyWeights(nodeId, numActions, stratWeights);
  }

  return nodeEV;
}

function computeTerminalEVMultiWay(
  ctx: CFRContextMultiWay,
  nodeId: number,
  reachProbs: Float32Array[],
  traverser: number,
): Float32Array {
  const { tree, handValues, blockerMatrix, numCombos: nc, numPlayers } = ctx;
  const ti = decodeTerminalId(nodeId);
  const ev = new Float32Array(nc);

  const pot = tree.terminalPot[ti];
  const stacks: number[] = [];
  for (let p = 0; p < numPlayers; p++) {
    stacks.push(tree.terminalStacks[ti * numPlayers + p]);
  }
  const foldedMask = tree.terminalFolded[ti];

  if (tree.terminalIsShowdown[ti]) {
    computeShowdownEVMultiWay(
      handValues,
      reachProbs,
      blockerMatrix,
      pot,
      stacks,
      nc,
      numPlayers,
      foldedMask,
      traverser,
      ev,
    );
  } else {
    const winner = tree.terminalWinner[ti];
    computeFoldEVMultiWay(
      reachProbs,
      blockerMatrix,
      pot,
      stacks,
      nc,
      numPlayers,
      winner,
      traverser,
      ev,
    );
  }

  return ev;
}
