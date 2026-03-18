// Extract per-combo EV from a solved tree using the converged average strategy.
//
// Performs a single read-only traversal — no regret/strategy updates.
// Used for GTO+ comparison (per-combo and per-action EV) and downstream
// street-by-street solving (transition terminal EVs).

import type { FlatTree } from './flat-tree.js';
import { isTerminal, decodeTerminalId } from './flat-tree.js';
import { ArrayStore } from './array-store.js';
import {
  computeShowdownEV,
  computeFoldEV,
  computeEquityShowdownEV,
  precomputeHandValues,
  rebuildShowdownCacheForMCCFR,
} from './showdown-eval.js';

export interface ExtractEVParams {
  tree: FlatTree;
  store: ArrayStore;
  board: number[];
  oopReach: Float32Array;
  ipReach: Float32Array;
  nc: number;
  showdownMatrix: Int8Array | null;
  equityMatrix: Float32Array | null;
  blockerMatrix: Uint8Array;
  /** Node ID to extract per-action EVs at (default: 0 = root). */
  targetNodeId?: number;
}

export interface ExtractEVResult {
  /** Per-combo EV at root for OOP (traverser=0). */
  evOOP: Float32Array;
  /** Per-combo EV at root for IP (traverser=1). */
  evIP: Float32Array;
  /** Per-action EVs at the target node (if specified). Keys are action indices. */
  actionEVs?: {
    traverser: number;
    /** actionEV[actionIndex] = Float32Array(nc) */
    perAction: Float32Array[];
    /** Overall node EV = sum(strategy * actionEV) */
    nodeEV: Float32Array;
  };
}

interface EVContext {
  tree: FlatTree;
  store: ArrayStore;
  showdownMatrix: Int8Array | null;
  equityMatrix: Float32Array | null;
  blockerMatrix: Uint8Array;
  nc: number;
  targetNodeId: number;
  /** Captured per-action EVs at the target node. */
  capturedActionEVs: Float32Array[] | null;
  capturedNodeEV: Float32Array | null;
}

const PRUNE_THRESHOLD = 1e-6;

function isReachDead(reach: Float32Array, nc: number): boolean {
  for (let i = 0; i < nc; i++) {
    if (reach[i] > PRUNE_THRESHOLD) return false;
  }
  return true;
}

/**
 * Extract per-combo EV for both players from a solved tree.
 *
 * Uses the converged average strategy (strategySums) for a single read-only
 * traversal. Does NOT modify regrets or strategy sums.
 */
export function extractEV(params: ExtractEVParams): ExtractEVResult {
  const { tree, store, nc, showdownMatrix, equityMatrix, blockerMatrix } = params;

  const targetNodeId = params.targetNodeId ?? 0;

  // Traverse for OOP (traverser=0)
  const ctxOOP: EVContext = {
    tree,
    store,
    showdownMatrix,
    equityMatrix,
    blockerMatrix,
    nc,
    targetNodeId,
    capturedActionEVs: null,
    capturedNodeEV: null,
  };
  const oopReach0 = new Float32Array(params.oopReach);
  const ipReach0 = new Float32Array(params.ipReach);
  const evOOP = evTraverseHU(ctxOOP, 0, oopReach0, ipReach0, 0);

  // Traverse for IP (traverser=1)
  const ctxIP: EVContext = {
    tree,
    store,
    showdownMatrix,
    equityMatrix,
    blockerMatrix,
    nc,
    targetNodeId,
    capturedActionEVs: null,
    capturedNodeEV: null,
  };
  const oopReach1 = new Float32Array(params.oopReach);
  const ipReach1 = new Float32Array(params.ipReach);
  const evIP = evTraverseHU(ctxIP, 0, oopReach1, ipReach1, 1);

  const result: ExtractEVResult = { evOOP, evIP };

  // Return captured action EVs at the target node (from OOP traversal).
  // The acting player at the target node determines whose perspective to use.
  const actingPlayer = tree.nodePlayer[targetNodeId];
  const capturedCtx = actingPlayer === 0 ? ctxOOP : ctxIP;
  if (capturedCtx.capturedActionEVs) {
    result.actionEVs = {
      traverser: actingPlayer,
      perAction: capturedCtx.capturedActionEVs,
      nodeEV: capturedCtx.capturedNodeEV!,
    };
  }

  return result;
}

/**
 * Read-only traversal using the average strategy.
 * Returns a new Float32Array(nc) of per-combo EV for the traverser.
 */
function evTraverseHU(
  ctx: EVContext,
  nodeId: number,
  oopReach: Float32Array,
  ipReach: Float32Array,
  traverser: number,
): Float32Array {
  const { tree, store, nc } = ctx;

  // Terminal node
  if (isTerminal(nodeId)) {
    return computeTerminalEV(ctx, nodeId, oopReach, ipReach, traverser);
  }

  // Reach pruning
  if (isReachDead(oopReach, nc) || isReachDead(ipReach, nc)) {
    return new Float32Array(nc);
  }

  const player = tree.nodePlayer[nodeId];
  const numActions = tree.nodeNumActions[nodeId];
  const actionOffset = tree.nodeActionOffset[nodeId];

  // Get AVERAGE strategy (not current regret-matched strategy)
  const strategy = new Float32Array(numActions * nc);
  store.getAverageStrategy(nodeId, numActions, strategy);

  const nodeEV = new Float32Array(nc);
  const isTarget = nodeId === ctx.targetNodeId;
  const actionEVList: Float32Array[] = isTarget ? [] : [];

  for (let a = 0; a < numActions; a++) {
    const childId = tree.childNodeId[actionOffset + a];

    // Create modified reaches for this action
    const childOOP = new Float32Array(oopReach);
    const childIP = new Float32Array(ipReach);

    if (player === 0) {
      for (let c = 0; c < nc; c++) {
        childOOP[c] *= strategy[a * nc + c];
      }
    } else {
      for (let c = 0; c < nc; c++) {
        childIP[c] *= strategy[a * nc + c];
      }
    }

    const actionEV = evTraverseHU(ctx, childId, childOOP, childIP, traverser);

    // Capture per-action EV at target node
    if (isTarget && traverser === player) {
      actionEVList.push(new Float32Array(actionEV));
    }

    // Accumulate EV
    if (player === traverser) {
      for (let c = 0; c < nc; c++) {
        nodeEV[c] += strategy[a * nc + c] * actionEV[c];
      }
    } else {
      for (let c = 0; c < nc; c++) {
        nodeEV[c] += actionEV[c];
      }
    }
  }

  // Capture action EVs at target node
  if (isTarget && traverser === player) {
    ctx.capturedActionEVs = actionEVList;
    ctx.capturedNodeEV = new Float32Array(nodeEV);
  }

  return nodeEV;
}

/**
 * Compute terminal EV (fold or showdown) — same logic as the CFR engine
 * but returns a new array instead of writing to a pre-allocated buffer.
 */
function computeTerminalEV(
  ctx: EVContext,
  nodeId: number,
  oopReach: Float32Array,
  ipReach: Float32Array,
  traverser: number,
): Float32Array {
  const { tree, showdownMatrix, equityMatrix, blockerMatrix, nc } = ctx;
  const ev = new Float32Array(nc);

  const oppReach = traverser === 0 ? ipReach : oopReach;
  if (isReachDead(oppReach, nc)) return ev;

  const ti = decodeTerminalId(nodeId);
  const pot = tree.terminalPot[ti];
  const np = tree.numPlayers;
  const stacks: [number, number] = [tree.terminalStacks[ti * np], tree.terminalStacks[ti * np + 1]];

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
        ev,
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
        ev,
      );
    }
  } else {
    const folder = tree.terminalFolder[ti];
    const opponentReach = traverser === 0 ? ipReach : oopReach;
    computeFoldEV(blockerMatrix, opponentReach, pot, stacks, nc, traverser, folder, ev);
  }

  return ev;
}

// ─── Fast EV Extractor (zero-allocation, single-traverser) ───

/**
 * Pre-allocated buffer pool for fastExtractEV.
 * Eliminates GC pressure when called repeatedly (e.g., 48 rivers × 200 iters).
 */
export interface FastEVPool {
  maxDepth: number;
  maxActions: number;
  nc: number;
  /** Per-depth node EV: [depth * nc ... (depth+1) * nc) */
  nodeEV: Float32Array;
  /** Per-depth strategy: [depth * maxActions * nc ...] */
  strategy: Float32Array;
  /** Per-depth per-action reach saves for OOP */
  oopSave: Float32Array;
  /** Per-depth per-action reach saves for IP */
  ipSave: Float32Array;
}

/**
 * Create a buffer pool for fastExtractEV.
 */
export function createFastEVPool(tree: FlatTree, nc: number): FastEVPool {
  const maxActions = Math.max(...Array.from(tree.nodeNumActions));
  // Compute max depth via iterative DFS
  let maxD = 0;
  const stack: Array<[number, number]> = [[0, 0]];
  while (stack.length > 0) {
    const [nid, d] = stack.pop()!;
    if (d > maxD) maxD = d;
    const na = tree.nodeNumActions[nid];
    const off = tree.nodeActionOffset[nid];
    for (let a = 0; a < na; a++) {
      const cid = tree.childNodeId[off + a];
      if (!isTerminal(cid)) stack.push([cid, d + 1]);
      else if (d + 1 > maxD) maxD = d + 1;
    }
  }
  const maxDepth = maxD + 2;

  return {
    maxDepth,
    maxActions,
    nc,
    nodeEV: new Float32Array(maxDepth * nc),
    strategy: new Float32Array(maxDepth * maxActions * nc),
    oopSave: new Float32Array(maxDepth * nc),
    ipSave: new Float32Array(maxDepth * nc),
  };
}

/**
 * Fast single-traverser EV extraction with zero allocations in the hot loop.
 *
 * Writes traverser's per-combo EV into `outEV` (caller-allocated Float32Array(nc)).
 * Uses pre-allocated `pool` buffers. Does NOT capture per-action EVs.
 *
 * This is designed for the chance-cfr inner loop where extractEV is called
 * thousands of times per turn iteration.
 */
export function fastExtractEV(
  tree: FlatTree,
  store: ArrayStore,
  showdownMatrix: Int8Array,
  blockerMatrix: Uint8Array,
  oopReach: Float32Array,
  ipReach: Float32Array,
  traverser: number,
  nc: number,
  pool: FastEVPool,
  outEV: Float32Array,
): void {
  fastTraverse(
    tree,
    store,
    showdownMatrix,
    blockerMatrix,
    oopReach,
    ipReach,
    traverser,
    nc,
    pool,
    0,
    0,
  );
  // Copy result from pool to output
  outEV.set(pool.nodeEV.subarray(0, nc));
}

function fastTraverse(
  tree: FlatTree,
  store: ArrayStore,
  showdownMatrix: Int8Array,
  blockerMatrix: Uint8Array,
  oopReach: Float32Array,
  ipReach: Float32Array,
  traverser: number,
  nc: number,
  pool: FastEVPool,
  nodeId: number,
  depth: number,
): void {
  const evOff = depth * nc;

  // Terminal node
  if (isTerminal(nodeId)) {
    const ti = decodeTerminalId(nodeId);
    const pot = tree.terminalPot[ti];
    const np = tree.numPlayers;
    const stacks: [number, number] = [
      tree.terminalStacks[ti * np],
      tree.terminalStacks[ti * np + 1],
    ];

    const oppReach = traverser === 0 ? ipReach : oopReach;
    let dead = true;
    for (let c = 0; c < nc; c++) {
      if (oppReach[c] > PRUNE_THRESHOLD) {
        dead = false;
        break;
      }
    }
    if (dead) {
      pool.nodeEV.fill(0, evOff, evOff + nc);
      return;
    }

    const evSlice = pool.nodeEV.subarray(evOff, evOff + nc);
    if (tree.terminalIsShowdown[ti]) {
      computeShowdownEV(
        showdownMatrix,
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
      const folder = tree.terminalFolder[ti];
      const opponentReach = traverser === 0 ? ipReach : oopReach;
      computeFoldEV(blockerMatrix, opponentReach, pot, stacks, nc, traverser, folder, evSlice);
    }
    return;
  }

  // Reach pruning
  let oopDead = true,
    ipDead = true;
  for (let c = 0; c < nc; c++) {
    if (oopReach[c] > PRUNE_THRESHOLD) oopDead = false;
    if (ipReach[c] > PRUNE_THRESHOLD) ipDead = false;
    if (!oopDead && !ipDead) break;
  }
  if (oopDead || ipDead) {
    pool.nodeEV.fill(0, evOff, evOff + nc);
    return;
  }

  const player = tree.nodePlayer[nodeId];
  const numActions = tree.nodeNumActions[nodeId];
  const actionOffset = tree.nodeActionOffset[nodeId];

  // Get average strategy into pool buffer
  const stratOff = depth * pool.maxActions * nc;
  store.getAverageStrategy(nodeId, numActions, pool.strategy.subarray(stratOff));

  // Zero node EV
  pool.nodeEV.fill(0, evOff, evOff + nc);

  const saveOff = depth * nc;
  const childEvOff = (depth + 1) * nc;

  for (let a = 0; a < numActions; a++) {
    const childId = tree.childNodeId[actionOffset + a];
    const sOff = stratOff + a * nc;

    // Save and multiply reach
    if (player === 0) {
      for (let c = 0; c < nc; c++) {
        pool.oopSave[saveOff + c] = oopReach[c];
        oopReach[c] *= pool.strategy[sOff + c];
      }
    } else {
      for (let c = 0; c < nc; c++) {
        pool.ipSave[saveOff + c] = ipReach[c];
        ipReach[c] *= pool.strategy[sOff + c];
      }
    }

    // Recurse
    fastTraverse(
      tree,
      store,
      showdownMatrix,
      blockerMatrix,
      oopReach,
      ipReach,
      traverser,
      nc,
      pool,
      childId,
      depth + 1,
    );

    // Restore reach
    if (player === 0) {
      for (let c = 0; c < nc; c++) oopReach[c] = pool.oopSave[saveOff + c];
    } else {
      for (let c = 0; c < nc; c++) ipReach[c] = pool.ipSave[saveOff + c];
    }

    // Accumulate EV
    if (player === traverser) {
      for (let c = 0; c < nc; c++) {
        pool.nodeEV[evOff + c] += pool.strategy[sOff + c] * pool.nodeEV[childEvOff + c];
      }
    } else {
      for (let c = 0; c < nc; c++) {
        pool.nodeEV[evOff + c] += pool.nodeEV[childEvOff + c];
      }
    }
  }
}

/**
 * Compute win rate (equity %) for each combo against all opponent combos.
 *
 * For river (showdownMatrix): equity = (wins + ties*0.5) / valid_opponents
 * For non-river (equityMatrix): equity = avg(equityMatrix[i,j]) over valid j
 *
 * Returns Float32Array(nc) where each value is equity as a fraction (0-1).
 */
export function computeWinRates(
  nc: number,
  showdownMatrix: Int8Array | null,
  equityMatrix: Float32Array | null,
  blockerMatrix: Uint8Array,
): Float32Array {
  const winRates = new Float32Array(nc);

  if (equityMatrix) {
    // Non-river: equity matrix provides direct equity fractions
    for (let i = 0; i < nc; i++) {
      let sum = 0;
      let count = 0;
      for (let j = 0; j < nc; j++) {
        if (i === j) continue;
        if (blockerMatrix[i * nc + j]) continue;
        sum += equityMatrix[i * nc + j];
        count++;
      }
      winRates[i] = count > 0 ? sum / count : 0.5;
    }
  } else if (showdownMatrix) {
    // River: showdown matrix gives +1 (win), 0 (tie), -1 (loss)
    for (let i = 0; i < nc; i++) {
      let wins = 0;
      let ties = 0;
      let count = 0;
      for (let j = 0; j < nc; j++) {
        if (i === j) continue;
        if (blockerMatrix[i * nc + j]) continue;
        const result = showdownMatrix[i * nc + j];
        if (result > 0) wins++;
        else if (result === 0) ties++;
        count++;
      }
      winRates[i] = count > 0 ? (wins + ties * 0.5) / count : 0.5;
    }
  }

  return winRates;
}

// ─── All-Node Q-Value Extraction (post-solve, per-runout) ───

export interface AllQValuesParams {
  tree: FlatTree;
  store: ArrayStore;
  board: number[]; // flop cards (3 card indices)
  oopReach: Float32Array; // initial OOP reach (from preflop range)
  ipReach: Float32Array; // initial IP reach (from preflop range)
  nc: number; // number of combos
  combos: Array<[number, number]>; // combo card pairs
  blockerMatrix: Uint8Array;
  /** Progress callback: (runout, totalRunouts) */
  onProgress?: (runout: number, total: number) => void;
}

export interface AllQValuesResult {
  /**
   * Per-node per-action per-combo counterfactual values, averaged over all runouts.
   * qValues.get(nodeId)[actionIdx] = Float32Array(nc) of per-combo Q-values.
   * Only populated for nodes where player === traverser (each node has ONE player).
   */
  qValues: Map<number, Float32Array[]>;
  /** Number of runouts averaged over. */
  runoutCount: number;
}

/**
 * Extract Q-values at ALL decision nodes by averaging over all turn+river runouts.
 *
 * For each of the ~1176 runouts:
 *   1. Rebuild the O(n log n) showdown cache
 *   2. Traverse twice (OOP + IP) using the averaged strategy
 *   3. Accumulate per-action counterfactual values
 *
 * Performance: ~0.5-1 second per flop with nc ≈ 1176.
 */
export function extractAllNodeQValues(params: AllQValuesParams): AllQValuesResult {
  const { tree, store, board, nc, combos, blockerMatrix, onProgress } = params;

  // Pre-allocate Float64 accumulators for numerical stability across many runouts
  const actionAccum = new Map<number, Float64Array[]>();
  for (let nodeId = 0; nodeId < tree.numNodes; nodeId++) {
    const na = tree.nodeNumActions[nodeId];
    if (na === 0) continue;
    const arrays: Float64Array[] = [];
    for (let a = 0; a < na; a++) {
      arrays.push(new Float64Array(nc));
    }
    actionAccum.set(nodeId, arrays);
  }

  // Enumerate dealable cards (52 - 3 flop cards = 49)
  const dealable: number[] = [];
  for (let c = 0; c < 52; c++) {
    if (!board.includes(c)) dealable.push(c);
  }

  // Pre-allocate reach buffers (reused per runout to avoid GC pressure)
  const oopBuf = new Float32Array(nc);
  const ipBuf = new Float32Array(nc);
  // Pre-allocate traversal buffers per depth
  const maxDepth = 20;
  const maxAct = 8;
  const reachPool = {
    oopSave: Array.from({ length: maxDepth }, () => new Float32Array(nc)),
    ipSave: Array.from({ length: maxDepth }, () => new Float32Array(nc)),
    childOOP: Array.from({ length: maxDepth }, () => new Float32Array(nc)),
    childIP: Array.from({ length: maxDepth }, () => new Float32Array(nc)),
    nodeEV: Array.from({ length: maxDepth }, () => new Float32Array(nc)),
    strategy: Array.from({ length: maxDepth }, () => new Float32Array(maxAct * nc)),
    actionEV: new Float32Array(nc), // temp for terminal results
  };

  let runoutCount = 0;
  const totalRunouts = (dealable.length * (dealable.length - 1)) / 2;

  for (let ti = 0; ti < dealable.length; ti++) {
    const turnCard = dealable[ti];
    for (let ri = ti + 1; ri < dealable.length; ri++) {
      const riverCard = dealable[ri];

      // Prepare reaches: copy initial, zero blocked combos
      oopBuf.set(params.oopReach);
      ipBuf.set(params.ipReach);
      for (let c = 0; c < nc; c++) {
        const [c1, c2] = combos[c];
        if (c1 === turnCard || c2 === turnCard || c1 === riverCard || c2 === riverCard) {
          oopBuf[c] = 0;
          ipBuf[c] = 0;
        }
      }

      // Compute hand values and rebuild showdown cache
      const fullBoard = [board[0], board[1], board[2], turnCard, riverCard];
      const handValues = precomputeHandValues(combos, fullBoard);
      const showdownMatrix = rebuildShowdownCacheForMCCFR(combos, handValues, blockerMatrix);

      // Traverse for OOP (captures Q-values at player=0 nodes)
      qvTraverse(
        tree,
        store,
        showdownMatrix,
        blockerMatrix,
        nc,
        oopBuf,
        ipBuf,
        0,
        0,
        actionAccum,
        reachPool,
        0,
      );

      // Reset reaches for IP traversal
      oopBuf.set(params.oopReach);
      ipBuf.set(params.ipReach);
      for (let c = 0; c < nc; c++) {
        const [c1, c2] = combos[c];
        if (c1 === turnCard || c2 === turnCard || c1 === riverCard || c2 === riverCard) {
          oopBuf[c] = 0;
          ipBuf[c] = 0;
        }
      }

      // Traverse for IP (captures Q-values at player=1 nodes)
      qvTraverse(
        tree,
        store,
        showdownMatrix,
        blockerMatrix,
        nc,
        oopBuf,
        ipBuf,
        1,
        0,
        actionAccum,
        reachPool,
        0,
      );

      runoutCount++;
      if (onProgress && runoutCount % 100 === 0) {
        onProgress(runoutCount, totalRunouts);
      }
    }
  }

  // Compute per-combo opponent reach mass for normalization.
  // For OOP combos (player=0 nodes): opponent is IP → use ipReach.
  // For IP combos (player=1 nodes): opponent is OOP → use oopReach.
  // This converts counterfactual values to expected chip values (≈ BB).
  const oopMass = new Float32Array(nc);
  const ipMass = new Float32Array(nc);
  for (let c = 0; c < nc; c++) {
    let sm0 = 0,
      sm1 = 0;
    for (let j = 0; j < nc; j++) {
      if (c === j || blockerMatrix[c * nc + j]) continue;
      sm0 += params.oopReach[j]; // OOP mass (for IP player's nodes)
      sm1 += params.ipReach[j]; // IP mass (for OOP player's nodes)
    }
    oopMass[c] = sm0 || 1; // avoid division by zero
    ipMass[c] = sm1 || 1;
  }

  // Average accumulators → Float32 result, normalized to chip EV
  const qValues = new Map<number, Float32Array[]>();
  for (const [nodeId, accums] of actionAccum) {
    const player = tree.nodePlayer[nodeId];
    const mass = player === 0 ? ipMass : oopMass; // opponent's reach mass
    const averaged: Float32Array[] = [];
    for (const accum of accums) {
      const f32 = new Float32Array(nc);
      for (let c = 0; c < nc; c++) {
        f32[c] = accum[c] / (runoutCount * mass[c]);
      }
      averaged.push(f32);
    }
    qValues.set(nodeId, averaged);
  }

  return { qValues, runoutCount };
}

interface ReachPool {
  oopSave: Float32Array[];
  ipSave: Float32Array[];
  childOOP: Float32Array[];
  childIP: Float32Array[];
  nodeEV: Float32Array[];
  strategy: Float32Array[];
  actionEV: Float32Array;
}

/**
 * Modified EV traversal that accumulates per-action counterfactual values
 * at ALL traverser nodes (not just a target node).
 *
 * Uses pooled buffers to avoid GC pressure across ~2400 traversals.
 * Writes traverser's per-combo EV into reachPool.nodeEV[depth].
 */
function qvTraverse(
  tree: FlatTree,
  store: ArrayStore,
  showdownMatrix: Int8Array,
  blockerMatrix: Uint8Array,
  nc: number,
  oopReach: Float32Array,
  ipReach: Float32Array,
  traverser: number,
  nodeId: number,
  accumulators: Map<number, Float64Array[]>,
  pool: ReachPool,
  depth: number,
): void {
  const ev = pool.nodeEV[depth];

  // Terminal node
  if (isTerminal(nodeId)) {
    const oppReach = traverser === 0 ? ipReach : oopReach;
    let dead = true;
    for (let c = 0; c < nc; c++) {
      if (oppReach[c] > PRUNE_THRESHOLD) {
        dead = false;
        break;
      }
    }
    if (dead) {
      ev.fill(0);
      return;
    }

    const ti = decodeTerminalId(nodeId);
    const pot = tree.terminalPot[ti];
    const np = tree.numPlayers;
    const stacks: [number, number] = [
      tree.terminalStacks[ti * np],
      tree.terminalStacks[ti * np + 1],
    ];

    if (tree.terminalIsShowdown[ti]) {
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
    return;
  }

  // Reach pruning
  let oopDead = true,
    ipDead = true;
  for (let c = 0; c < nc; c++) {
    if (oopReach[c] > PRUNE_THRESHOLD) oopDead = false;
    if (ipReach[c] > PRUNE_THRESHOLD) ipDead = false;
    if (!oopDead && !ipDead) break;
  }
  if (oopDead || ipDead) {
    ev.fill(0);
    return;
  }

  const player = tree.nodePlayer[nodeId];
  const numActions = tree.nodeNumActions[nodeId];
  const actionOffset = tree.nodeActionOffset[nodeId];

  // Get average strategy into pool buffer
  const strat = pool.strategy[depth];
  store.getAverageStrategy(nodeId, numActions, strat);

  // Zero node EV
  ev.fill(0);

  const oopSave = pool.oopSave[depth];
  const ipSave = pool.ipSave[depth];
  const childEV = pool.nodeEV[depth + 1]; // child writes here

  const nodeAccums = player === traverser ? accumulators.get(nodeId) : null;

  for (let a = 0; a < numActions; a++) {
    const childId = tree.childNodeId[actionOffset + a];

    // Save and multiply reach
    if (player === 0) {
      for (let c = 0; c < nc; c++) {
        oopSave[c] = oopReach[c];
        oopReach[c] *= strat[a * nc + c];
      }
    } else {
      for (let c = 0; c < nc; c++) {
        ipSave[c] = ipReach[c];
        ipReach[c] *= strat[a * nc + c];
      }
    }

    // Recurse — child writes EV to pool.nodeEV[depth+1]
    qvTraverse(
      tree,
      store,
      showdownMatrix,
      blockerMatrix,
      nc,
      oopReach,
      ipReach,
      traverser,
      childId,
      accumulators,
      pool,
      depth + 1,
    );

    // Restore reach
    if (player === 0) {
      for (let c = 0; c < nc; c++) oopReach[c] = oopSave[c];
    } else {
      for (let c = 0; c < nc; c++) ipReach[c] = ipSave[c];
    }

    // Accumulate Q-value at traverser's node
    if (nodeAccums) {
      const accum = nodeAccums[a];
      for (let c = 0; c < nc; c++) {
        accum[c] += childEV[c];
      }
    }

    // Accumulate node EV
    if (player === traverser) {
      for (let c = 0; c < nc; c++) {
        ev[c] += strat[a * nc + c] * childEV[c];
      }
    } else {
      for (let c = 0; c < nc; c++) {
        ev[c] += childEV[c];
      }
    }
  }
}
