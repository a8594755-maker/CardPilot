// Full Game Tree CFR with Chance Nodes (Optimized)
//
// Implements proper multi-street CFR that traverses the COMPLETE game tree
// (flop -> turn -> river) in each iteration. At street transitions, the solver
// iterates over ALL possible next cards (chance nodes), remaps combos, and
// uses exact 5-card showdown equity at river terminals.
//
// Key optimizations:
// - O(n) showdown eval via prefix-sum + blocker exclusion (replaces O(n^2))
// - O(n) fold eval via card-reach approach (replaces O(n^2))
// - No showdown/blocker matrices at river level (~5GB saved)
// - Pre-allocated TraversalCtx for zero-allocation inner loops
// - Lightweight combo mapping (no blocker matrix construction)

import { fork } from 'child_process';
import { cpus } from 'os';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { buildTree } from '../tree/tree-builder.js';
import { flattenTree, isTerminal, decodeTerminalId } from './flat-tree.js';
import type { FlatTree } from './flat-tree.js';
import { ArrayStore } from './array-store.js';
import { enumerateValidCombos, buildBlockerMatrix, buildReachFromRange } from './combo-utils.js';
import type { ValidCombos } from './combo-utils.js';
import { precomputeHandValues } from './showdown-eval.js';
import { enumerateDealableCards } from './combo-remap.js';
import type { TreeConfig } from '../types.js';
import type { WeightedCombo } from '../integration/preflop-ranges.js';

// --- Public API ---

export interface FullGameCFRParams {
  board: number[];
  treeConfig: TreeConfig;
  oopRange: WeightedCombo[];
  ipRange: WeightedCombo[];
  iterations: number;
  /** Use Monte Carlo chance sampling (sample 1 turn + 1 river per chance node) */
  mccfr?: boolean;
  /** Global iteration offset for parallel linear weighting */
  globalIterOffset?: number;
  onProgress?: (phase: string, detail: string, pct: number) => void;
}

export interface FullGameCFRResult {
  tree: FlatTree;
  store: ArrayStore;
  validCombos: ValidCombos;
  blockerMatrix: Uint8Array;
  nc: number;
  elapsedMs: number;
  memoryMB: number;
}

// --- Internal Data Structures ---

/** Lightweight combo mapping without blocker matrix */
interface LiteComboMapping {
  childNC: number;
  parentNC: number;
  childToParent: Int32Array;
  parentToChild: Int32Array;
  childCombos: ValidCombos;
}

/** Cache for O(n) showdown EV (prefix-sum + blocker exclusion) */
interface TerminalCache {
  combos: Array<[number, number]>;
  handValues: Float64Array;
  sortedIndices: Int32Array;
  rankStart: Int32Array;
  rankEnd: Int32Array;
  cardCombos: Int32Array[];
  nc: number;
}

/** Pre-allocated buffers for zero-allocation tree traversal */
interface TraversalCtx {
  nodeEV: Float32Array[];
  childOopReach: Float32Array[];
  childIpReach: Float32Array[];
  actionEVs: Float32Array[][];
  strategy: Float32Array[];
  regretDeltas: Float32Array[];
  stratWeights: Float32Array[];
}

/** Shared reusable buffers for a street level */
interface StreetBufs {
  prefixReach: Float64Array;
  cardReach: Float64Array;
}

interface RiverSubtree {
  riverCard: number;
  mapping: LiteComboMapping;
  tree: FlatTree;
  store: ArrayStore;
  cache: TerminalCache;
  childNC: number;
}

interface TurnSubtree {
  turnCard: number;
  mapping: LiteComboMapping;
  tree: FlatTree;
  store: ArrayStore;
  childNC: number;
  cardCombos: Int32Array[]; // for O(n) fold on turn
  rivers: RiverSubtree[];
}

// --- Constants ---
const PRUNE_THRESHOLD = 1e-8;

// Module-level state for MCCFR mode (single-threaded, set per iteration)
let _iterWeight = 1;
let _mccfr = false;
let _rakePercentage = 0;
let _rakeCap = 0;

// --- Value Network Training Data Recording ---

export interface TransitionRecord {
  /** 'flop_to_turn' (3-card board) or 'turn_to_river' (4-card board) */
  type: 'flop_to_turn' | 'turn_to_river';
  /** Board cards at the transition point */
  board: number[];
  /** Pot size at the transition */
  pot: number;
  /** Effective stacks [OOP, IP] at the transition */
  stacks: [number, number];
  /** Which player's perspective (0=OOP, 1=IP) */
  traverser: number;
  /** Number of valid combos */
  numCombos: number;
  /** OOP reach probabilities per combo */
  oopReach: Float32Array;
  /** IP reach probabilities per combo */
  ipReach: Float32Array;
  /** Averaged EV per combo (averaged over all next-street cards) */
  resultEV: Float32Array;
  /** Card pairs for each combo [card1, card2] --- for mapping to hand classes */
  combos: Array<[number, number]>;
}

export type TransitionRecorder = (record: TransitionRecord) => void;

let _transitionRecorder: TransitionRecorder | null = null;
let _shouldRecord = false;
let _recordBoard: number[] = [];

/**
 * Set a callback to record street-transition EV data during full-game CFR.
 * Used by the value network training data generator.
 */
export function setTransitionRecorder(recorder: TransitionRecorder | null): void {
  _transitionRecorder = recorder;
}

// --- Factory Functions ---

function buildComboMappingLite(
  parentCombos: ValidCombos,
  parentBoard: number[],
  dealtCard: number,
): LiteComboMapping {
  const childBoard = [...parentBoard, dealtCard];
  const childCombos = enumerateValidCombos(childBoard);
  const childNC = childCombos.numCombos;
  const parentNC = parentCombos.numCombos;
  const parentToChild = new Int32Array(parentNC).fill(-1);
  const childToParent = new Int32Array(childNC);

  for (let pi = 0; pi < parentNC; pi++) {
    const [c1, c2] = parentCombos.combos[pi];
    if (c1 === dealtCard || c2 === dealtCard) continue;
    const globalId = parentCombos.comboIds[pi];
    const childIdx = childCombos.globalToLocal[globalId];
    if (childIdx >= 0) {
      parentToChild[pi] = childIdx;
      childToParent[childIdx] = pi;
    }
  }

  return { childNC, parentNC, childToParent, parentToChild, childCombos };
}

function buildTerminalCache(
  combos: Array<[number, number]>,
  board: number[],
  nc: number,
): TerminalCache {
  const handValues = precomputeHandValues(combos, board);
  const sortedIndices = new Int32Array(nc);
  for (let i = 0; i < nc; i++) sortedIndices[i] = i;
  sortedIndices.sort((a, b) => handValues[a] - handValues[b]);

  const rankStart = new Int32Array(nc);
  const rankEnd = new Int32Array(nc);
  let start = 0;
  while (start < nc) {
    let end = start;
    const val = handValues[sortedIndices[start]];
    while (end < nc && handValues[sortedIndices[end]] === val) end++;
    for (let k = start; k < end; k++) {
      rankStart[sortedIndices[k]] = start;
      rankEnd[sortedIndices[k]] = end - 1;
    }
    start = end;
  }

  const tempCC: number[][] = Array.from({ length: 52 }, () => []);
  for (let i = 0; i < nc; i++) {
    tempCC[combos[i][0]].push(i);
    tempCC[combos[i][1]].push(i);
  }
  const cardCombos = tempCC.map((arr) => new Int32Array(arr));

  return { combos, handValues, sortedIndices, rankStart, rankEnd, cardCombos, nc };
}

function buildCardCombos(combos: Array<[number, number]>, nc: number): Int32Array[] {
  const tempCC: number[][] = Array.from({ length: 52 }, () => []);
  for (let i = 0; i < nc; i++) {
    tempCC[combos[i][0]].push(i);
    tempCC[combos[i][1]].push(i);
  }
  return tempCC.map((arr) => new Int32Array(arr));
}

function createTraversalCtx(tree: FlatTree, nc: number): TraversalCtx {
  let maxActions = 0;
  for (let n = 0; n < tree.numNodes; n++) {
    maxActions = Math.max(maxActions, tree.nodeNumActions[n]);
  }
  const maxDepth = tree.numNodes; // conservative upper bound
  return {
    nodeEV: Array.from({ length: maxDepth }, () => new Float32Array(nc)),
    childOopReach: Array.from({ length: maxDepth }, () => new Float32Array(nc)),
    childIpReach: Array.from({ length: maxDepth }, () => new Float32Array(nc)),
    actionEVs: Array.from({ length: maxDepth }, () =>
      Array.from({ length: maxActions }, () => new Float32Array(nc)),
    ),
    strategy: Array.from({ length: maxDepth }, () => new Float32Array(maxActions * nc)),
    regretDeltas: Array.from({ length: maxDepth }, () => new Float32Array(maxActions * nc)),
    stratWeights: Array.from({ length: maxDepth }, () => new Float32Array(maxActions * nc)),
  };
}

// --- O(n) Terminal EV Computation ---

function computeShowdownEVCached(
  cache: TerminalCache,
  bufs: StreetBufs,
  pot: number,
  stacks: [number, number],
  oopReach: Float32Array,
  ipReach: Float32Array,
  traverser: number,
  outEV: Float32Array,
): void {
  const nc = cache.nc;
  const startTotal = (stacks[0] + stacks[1] + pot) / 2;
  const tStack = stacks[traverser];
  const winPayoff = tStack + pot - startTotal;
  const losePayoff = tStack - startTotal;
  const tiePayoff = tStack + pot / 2 - startTotal;
  const oppReach = traverser === 0 ? ipReach : oopReach;

  // Step 1: Prefix sums of opponent reach in sorted order
  let totalOppReach = 0;
  for (let k = 0; k < nc; k++) {
    const idx = cache.sortedIndices[k];
    totalOppReach += oppReach[idx];
    bufs.prefixReach[k] = totalOppReach;
  }

  // Step 2: Per-combo EV with blocker exclusion
  for (let i = 0; i < nc; i++) {
    const c1 = cache.combos[i][0];
    const c2 = cache.combos[i][1];
    const rs = cache.rankStart[i];
    const re = cache.rankEnd[i];
    const totalWin = rs > 0 ? bufs.prefixReach[rs - 1] : 0;
    const totalTie = bufs.prefixReach[re] - totalWin;
    const totalLose = totalOppReach - bufs.prefixReach[re];

    // Exclude blocked combos (O(~90) per combo)
    let blockedWin = 0,
      blockedTie = 0,
      blockedLose = 0;
    const myVal = cache.handValues[i];

    const list1 = cache.cardCombos[c1];
    for (let k = 0; k < list1.length; k++) {
      const j = list1[k];
      const oppR = oppReach[j];
      if (oppR === 0) continue;
      const val = cache.handValues[j];
      if (val < myVal) blockedWin += oppR;
      else if (val === myVal) blockedTie += oppR;
      else blockedLose += oppR;
    }

    const list2 = cache.cardCombos[c2];
    for (let k = 0; k < list2.length; k++) {
      const j = list2[k];
      if (j === i) continue;
      const oppR = oppReach[j];
      if (oppR === 0) continue;
      const val = cache.handValues[j];
      if (val < myVal) blockedWin += oppR;
      else if (val === myVal) blockedTie += oppR;
      else blockedLose += oppR;
    }

    outEV[i] =
      (totalWin - blockedWin) * winPayoff +
      (totalTie - blockedTie) * tiePayoff +
      (totalLose - blockedLose) * losePayoff;
  }
}

function computeFoldEVFast(
  combos: Array<[number, number]>,
  cardCombos: Int32Array[],
  bufs: StreetBufs,
  nc: number,
  pot: number,
  stacks: [number, number],
  traverser: number,
  folder: number,
  oopReach: Float32Array,
  ipReach: Float32Array,
  outEV: Float32Array,
): void {
  const startTotal = (stacks[0] + stacks[1] + pot) / 2;
  const tStack = stacks[traverser];
  const payoff = traverser === folder ? tStack - startTotal : tStack + pot - startTotal;
  const oppReach = traverser === 0 ? ipReach : oopReach;

  let totalOppReach = 0;
  for (let i = 0; i < nc; i++) totalOppReach += oppReach[i];

  // Per-card reach
  bufs.cardReach.fill(0);
  for (let card = 0; card < 52; card++) {
    const list = cardCombos[card];
    let sum = 0;
    for (let k = 0; k < list.length; k++) sum += oppReach[list[k]];
    bufs.cardReach[card] = sum;
  }

  // Per-combo fold EV
  for (let i = 0; i < nc; i++) {
    const c1 = combos[i][0];
    const c2 = combos[i][1];
    const blocked = bufs.cardReach[c1] + bufs.cardReach[c2] - oppReach[i];
    outEV[i] = payoff * (totalOppReach - blocked);
  }
}

// --- Reach Pruning ---

function isReachDead(reach: Float32Array, nc: number): boolean {
  for (let i = 0; i < nc; i++) {
    if (reach[i] > PRUNE_THRESHOLD) return false;
  }
  return true;
}

// --- Main Solver ---

export function solveFullGameCFR(params: FullGameCFRParams): FullGameCFRResult {
  const { board, treeConfig, oopRange, ipRange, iterations, onProgress } = params;
  const mccfr = params.mccfr ?? false;
  const startTime = Date.now();
  _rakePercentage = Math.max(0, treeConfig.rake?.percentage ?? 0);
  _rakeCap = Math.max(0, treeConfig.rake?.cap ?? 0);

  // -- Phase 1: Build flop data --
  const flopCombos = enumerateValidCombos(board);
  const flopNC = flopCombos.numCombos;
  const flopBlocker = buildBlockerMatrix(flopCombos.combos);
  const flopCardCombos = buildCardCombos(flopCombos.combos, flopNC);

  const flopConfig: TreeConfig = {
    ...treeConfig,
    singleStreet: true,
    // Prefer absoluteBetSizes for fixed amounts; clear pot-relative fractions
    perLevelBetFractions: treeConfig.absoluteBetSizes ? undefined : treeConfig.perLevelBetFractions,
  };
  const flopRoot = buildTree(flopConfig);
  const flopTree = flattenTree(flopRoot, 2);
  const flopStore = new ArrayStore(flopTree, flopNC);

  const flopOopReach = buildReachFromRange(oopRange, flopCombos);
  const flopIpReach = buildReachFromRange(ipRange, flopCombos);

  if (onProgress) onProgress('init', `Flop: ${flopNC} combos, ${flopTree.numNodes} nodes`, 0);

  // -- Phase 2: Build all turn + river subtrees --
  const turnCards = enumerateDealableCards(board);
  const numTurns = turnCards.length;

  if (onProgress) onProgress('init', `Building ${numTurns} turn subtrees...`, 5);

  const turnSubtrees: TurnSubtree[] = [];
  let totalRivers = 0;
  let totalMemory = flopStore.estimateMemoryBytes();
  let maxTurnNC = 0;
  let maxRiverNC = 0;

  // Build template trees for turn/river subtrees.
  // Both MCCFR and full-enum modes use the FULL tree complexity to match GTO+.
  // Using simplified trees (raiseCapPerStreet=0) was tried but produces wrong
  // equilibria --- the turn/river raise dynamics significantly affect flop strategy.
  //
  // IMPORTANT: Inner trees use absoluteBetSizes (fixed amounts) instead of
  // perLevelBetFractions (pot-relative). GTO+ uses the SAME absolute bet sizes
  // on every street regardless of pot. With pot-relative fractions, bet sizes
  // scale with pot (e.g., after flop bet-call doubling the pot, turn bets
  // would double too), producing wrong equilibria. The potOffset mechanism
  // adjusts terminal payoffs to account for the pot difference.
  const innerConfig: TreeConfig = {
    ...treeConfig,
    singleStreet: true,
    // Prefer absoluteBetSizes for fixed amounts; clear pot-relative fractions
    perLevelBetFractions: treeConfig.absoluteBetSizes ? undefined : treeConfig.perLevelBetFractions,
  };
  const innerRoot = buildTree(innerConfig);
  const innerTree = flattenTree(innerRoot, 2);

  if (onProgress)
    onProgress(
      'init',
      `Inner tree: ${innerTree.numNodes} nodes, ${innerTree.numTerminals} terminals`,
      5,
    );

  for (let ti = 0; ti < numTurns; ti++) {
    const turnCard = turnCards[ti];
    const turnBoard = [...board, turnCard];
    const turnMapping = buildComboMappingLite(flopCombos, board, turnCard);
    const turnNC = turnMapping.childNC;
    if (turnNC > maxTurnNC) maxTurnNC = turnNC;

    const turnTree = flattenTree(innerRoot, 2);
    const turnStore = new ArrayStore(turnTree, turnNC);
    totalMemory += turnStore.estimateMemoryBytes();

    const turnCC = buildCardCombos(turnMapping.childCombos.combos, turnNC);

    const riverCards = enumerateDealableCards(turnBoard);
    const rivers: RiverSubtree[] = [];

    for (let ri = 0; ri < riverCards.length; ri++) {
      const riverCard = riverCards[ri];
      const riverBoard = [...turnBoard, riverCard];
      const riverMapping = buildComboMappingLite(turnMapping.childCombos, turnBoard, riverCard);
      const riverNC = riverMapping.childNC;
      if (riverNC > maxRiverNC) maxRiverNC = riverNC;

      const riverTree = flattenTree(innerRoot, 2);
      const riverStore = new ArrayStore(riverTree, riverNC);
      totalMemory += riverStore.estimateMemoryBytes();

      // Build O(n) terminal cache (replaces showdown matrix + blocker matrix)
      const cache = buildTerminalCache(riverMapping.childCombos.combos, riverBoard, riverNC);

      rivers.push({
        riverCard,
        mapping: riverMapping,
        tree: riverTree,
        store: riverStore,
        cache,
        childNC: riverNC,
      });
      totalRivers++;
    }

    turnSubtrees.push({
      turnCard,
      mapping: turnMapping,
      tree: turnTree,
      store: turnStore,
      childNC: turnNC,
      cardCombos: turnCC,
      rivers,
    });

    if (onProgress && (ti + 1) % 5 === 0) {
      onProgress(
        'init',
        `Turn ${ti + 1}/${numTurns} built (${totalRivers} rivers)`,
        5 + ((ti + 1) / numTurns) * 20,
      );
    }
  }

  const memoryMB = Math.round(totalMemory / (1024 * 1024));
  if (onProgress)
    onProgress(
      'init',
      `All subtrees built: ${numTurns} turns, ${totalRivers} rivers, ${memoryMB} MB`,
      25,
    );

  // -- Create shared traversal contexts (one per street level) --
  const flopCtx = createTraversalCtx(flopTree, flopNC);
  const turnCtx = createTraversalCtx(innerTree, maxTurnNC);
  const riverCtx = createTraversalCtx(innerTree, maxRiverNC);

  // Pre-allocate shared chance node buffers
  const turnChanceOop = new Float32Array(maxTurnNC);
  const turnChanceIp = new Float32Array(maxTurnNC);
  const turnChanceEV = new Float32Array(maxTurnNC);
  const riverChanceOop = new Float32Array(maxRiverNC);
  const riverChanceIp = new Float32Array(maxRiverNC);
  const riverChanceEV = new Float32Array(maxRiverNC);

  // Shared reusable buffers per street level (for O(n) terminal eval)
  const flopBufs: StreetBufs = {
    prefixReach: new Float64Array(flopNC),
    cardReach: new Float64Array(52),
  };
  const turnBufs: StreetBufs = {
    prefixReach: new Float64Array(maxTurnNC),
    cardReach: new Float64Array(52),
  };
  const riverBufs: StreetBufs = {
    prefixReach: new Float64Array(maxRiverNC),
    cardReach: new Float64Array(52),
  };

  _mccfr = mccfr;

  if (onProgress) {
    const mode = mccfr ? 'MCCFR (chance sampling)' : 'full enumeration';
    onProgress('init', `Contexts ready. Starting ${iterations} iterations [${mode}]...`, 28);
  }

  // -- Phase 3: CFR iterations --
  const iterStart = Date.now();
  const flopResultEV = new Float32Array(flopNC);

  // Pre-allocate reach buffers to avoid per-iteration GC pressure
  const reachOopBuf = new Float32Array(flopNC);
  const reachIpBuf = new Float32Array(flopNC);

  // Parallel workers use linear CFR weighting for correct aggregation.
  // Serial full-enum uses DCFR discounting (uniform weight + discount old strategy sums).
  // MCCFR always uses linear weighting.
  const isParallelWorker = params.globalIterOffset !== undefined;
  const useLinearWeighting = mccfr || isParallelWorker;

  // Value network data recording: set board context
  _recordBoard = board;
  _shouldRecord = false;

  for (let iter = 0; iter < iterations; iter++) {
    // Enable recording on the last iteration (converged strategies)
    _shouldRecord = _transitionRecorder != null && iter === iterations - 1;
    const t = iter + 1;
    const globalT = (params.globalIterOffset ?? 0) + t;
    _iterWeight = useLinearWeighting ? globalT : 1;

    // Traversal for player 0 (OOP)
    reachOopBuf.set(flopOopReach);
    reachIpBuf.set(flopIpReach);
    cfrTraverseFlop(
      flopTree,
      flopStore,
      flopNC,
      flopCombos.combos,
      flopCardCombos,
      flopBufs,
      turnSubtrees,
      numTurns,
      reachOopBuf,
      reachIpBuf,
      0,
      flopCtx,
      turnCtx,
      riverCtx,
      turnChanceOop,
      turnChanceIp,
      turnChanceEV,
      riverChanceOop,
      riverChanceIp,
      riverChanceEV,
      turnBufs,
      riverBufs,
      flopResultEV,
      treeConfig.startingPot,
    );

    // Traversal for player 1 (IP)
    reachOopBuf.set(flopOopReach);
    reachIpBuf.set(flopIpReach);
    cfrTraverseFlop(
      flopTree,
      flopStore,
      flopNC,
      flopCombos.combos,
      flopCardCombos,
      flopBufs,
      turnSubtrees,
      numTurns,
      reachOopBuf,
      reachIpBuf,
      1,
      flopCtx,
      turnCtx,
      riverCtx,
      turnChanceOop,
      turnChanceIp,
      turnChanceEV,
      riverChanceOop,
      riverChanceIp,
      riverChanceEV,
      turnBufs,
      riverBufs,
      flopResultEV,
      treeConfig.startingPot,
    );

    // DCFR strategy sum discounting (serial full-enum only).
    // Parallel workers + MCCFR use linear weighting instead --- no discounting needed.
    if (!useLinearWeighting) {
      const factor = (t * t) / ((t + 1) * (t + 1));
      applyDCFRDiscount(flopStore, factor);
      for (const ts of turnSubtrees) {
        applyDCFRDiscount(ts.store, factor);
        for (const rs of ts.rivers) {
          applyDCFRDiscount(rs.store, factor);
        }
      }
    }

    if (onProgress && (iter + 1) % Math.max(1, Math.floor(iterations / 20)) === 0) {
      const elapsed = (Date.now() - iterStart) / 1000;
      const iterPerSec = (iter + 1) / elapsed;
      const pct = 25 + ((iter + 1) / iterations) * 75;
      onProgress(
        'cfr',
        `Iter ${iter + 1}/${iterations} (${elapsed.toFixed(1)}s, ${iterPerSec.toFixed(0)} it/s)`,
        pct,
      );
    }
  }

  _shouldRecord = false;

  return {
    tree: flopTree,
    store: flopStore,
    validCombos: flopCombos,
    blockerMatrix: flopBlocker,
    nc: flopNC,
    elapsedMs: Date.now() - startTime,
    memoryMB,
  };
}

// --- DCFR Discount ---

function applyDCFRDiscount(store: ArrayStore, factor: number): void {
  const sums = store.strategySums;
  for (let i = 0; i < sums.length; i++) {
    sums[i] *= factor;
  }
}

// --- Handler Types ---

type ShowdownHandler = (
  pot: number,
  stacks: [number, number],
  oopReach: Float32Array,
  ipReach: Float32Array,
  traverser: number,
  outEV: Float32Array,
) => void;

type FoldHandler = (
  pot: number,
  stacks: [number, number],
  oopReach: Float32Array,
  ipReach: Float32Array,
  traverser: number,
  folder: number,
  outEV: Float32Array,
) => void;

// --- Generic CFR Node Traversal (Zero-allocation) ---

function cfrTraverseNode(
  tree: FlatTree,
  store: ArrayStore,
  nc: number,
  oopReach: Float32Array,
  ipReach: Float32Array,
  traverser: number,
  nodeId: number,
  depth: number,
  ctx: TraversalCtx,
  onShowdown: ShowdownHandler,
  onFold: FoldHandler,
  outEV: Float32Array,
  potOffset: number = 0,
): void {
  // -- Terminal --
  if (isTerminal(nodeId)) {
    const ti = decodeTerminalId(nodeId);
    // Adjust terminal pot/stacks by potOffset to account for chips invested
    // on previous streets. With absoluteBetSizes, bet amounts are fixed but
    // the base pot varies by flop/turn action path. The offset correctly
    // shifts payoffs: winner gets +potOffset/2, loser gets -potOffset/2.
    const pot = tree.terminalPot[ti] + potOffset;
    const stacks: [number, number] = [
      tree.terminalStacks[ti * 2] - potOffset / 2,
      tree.terminalStacks[ti * 2 + 1] - potOffset / 2,
    ];
    const rake = _rakePercentage > 0 ? Math.min(pot * _rakePercentage, _rakeCap) : 0;
    const potAfterRake = pot - rake;
    if (tree.terminalIsShowdown[ti]) {
      onShowdown(potAfterRake, stacks, oopReach, ipReach, traverser, outEV);
    } else {
      const folder = tree.terminalFolder[ti];
      onFold(potAfterRake, stacks, oopReach, ipReach, traverser, folder, outEV);
    }
    return;
  }

  // -- Pruning --
  if (isReachDead(oopReach, nc) || isReachDead(ipReach, nc)) {
    outEV.fill(0, 0, nc);
    return;
  }

  const player = tree.nodePlayer[nodeId];
  const numActions = tree.nodeNumActions[nodeId];
  const actionOffset = tree.nodeActionOffset[nodeId];

  // Get current strategy via regret matching (into pre-allocated buffer)
  const strategy = ctx.strategy[depth];
  store.getCurrentStrategy(nodeId, numActions, strategy);

  // Local node EV accumulator
  const nodeEV = ctx.nodeEV[depth];
  nodeEV.fill(0, 0, nc);

  for (let a = 0; a < numActions; a++) {
    const childId = tree.childNodeId[actionOffset + a];

    // Build child reaches into depth-local buffers
    const childOop = ctx.childOopReach[depth];
    const childIp = ctx.childIpReach[depth];
    if (player === 0) {
      for (let c = 0; c < nc; c++) {
        childOop[c] = oopReach[c] * strategy[a * nc + c];
        childIp[c] = ipReach[c];
      }
    } else {
      for (let c = 0; c < nc; c++) {
        childOop[c] = oopReach[c];
        childIp[c] = ipReach[c] * strategy[a * nc + c];
      }
    }

    // Skip dead branches
    const actingReach = player === 0 ? childOop : childIp;
    if (isReachDead(actingReach, nc)) {
      ctx.actionEVs[depth][a].fill(0, 0, nc);
      continue;
    }

    // Recurse --- result written into ctx.actionEVs[depth][a]
    const actionEV = ctx.actionEVs[depth][a];
    cfrTraverseNode(
      tree,
      store,
      nc,
      childOop,
      childIp,
      traverser,
      childId,
      depth + 1,
      ctx,
      onShowdown,
      onFold,
      actionEV,
      potOffset,
    );

    // Accumulate node EV
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

  // Update regrets and strategy sums
  if (player === traverser) {
    const playerReach = traverser === 0 ? oopReach : ipReach;
    const regretDeltas = ctx.regretDeltas[depth];
    const stratWeights = ctx.stratWeights[depth];

    for (let a = 0; a < numActions; a++) {
      const actionEV = ctx.actionEVs[depth][a];
      for (let c = 0; c < nc; c++) {
        if (playerReach[c] < PRUNE_THRESHOLD) continue;
        regretDeltas[a * nc + c] = actionEV[c] - nodeEV[c];
        stratWeights[a * nc + c] = _iterWeight * playerReach[c] * strategy[a * nc + c];
      }
    }

    store.updateRegrets(nodeId, numActions, regretDeltas);
    store.addStrategyWeights(nodeId, numActions, stratWeights);
  }

  // Copy result to output
  for (let c = 0; c < nc; c++) {
    outEV[c] = nodeEV[c];
  }
}

// --- Street-Level CFR Traversal ---

function cfrTraverseFlop(
  tree: FlatTree,
  store: ArrayStore,
  nc: number,
  flopCombos: Array<[number, number]>,
  flopCardCombos: Int32Array[],
  flopBufs: StreetBufs,
  turnSubtrees: TurnSubtree[],
  numTurns: number,
  oopReach: Float32Array,
  ipReach: Float32Array,
  traverser: number,
  flopCtx: TraversalCtx,
  turnCtx: TraversalCtx,
  riverCtx: TraversalCtx,
  turnChanceOop: Float32Array,
  turnChanceIp: Float32Array,
  turnChanceEV: Float32Array,
  riverChanceOop: Float32Array,
  riverChanceIp: Float32Array,
  riverChanceEV: Float32Array,
  turnBufs: StreetBufs,
  riverBufs: StreetBufs,
  outEV: Float32Array,
  startingPot: number,
): void {
  cfrTraverseNode(
    tree,
    store,
    nc,
    oopReach,
    ipReach,
    traverser,
    0,
    0,
    flopCtx,
    // Showdown = street transition to turn
    (pot, stacks, oR, iR, trav, out) => {
      // pot is the actual flop terminal pot (flop tree has potOffset=0).
      // Inner trees use absoluteBetSizes (fixed amounts), so we pass a potOffset
      // to adjust terminal payoffs instead of scaling. The offset = actual pot
      // minus the inner tree's startingPot (the template base).
      const turnPotOffset = pot - startingPot;
      computeTurnChanceValue(
        turnSubtrees,
        numTurns,
        nc,
        oR,
        iR,
        trav,
        turnCtx,
        riverCtx,
        turnChanceOop,
        turnChanceIp,
        turnChanceEV,
        riverChanceOop,
        riverChanceIp,
        riverChanceEV,
        turnBufs,
        riverBufs,
        out,
        turnPotOffset,
        startingPot,
      );
      // Record flop->turn transition for value network training
      if (_shouldRecord && _transitionRecorder) {
        _transitionRecorder({
          type: 'flop_to_turn',
          board: [..._recordBoard],
          pot,
          stacks: [stacks[0], stacks[1]],
          traverser: trav,
          numCombos: nc,
          oopReach: new Float32Array(oR.subarray(0, nc)),
          ipReach: new Float32Array(iR.subarray(0, nc)),
          resultEV: new Float32Array(out.subarray(0, nc)),
          combos: flopCombos.slice(0, nc),
        });
      }
    },
    // Fold on flop
    (pot, stacks, oR, iR, trav, folder, out) => {
      computeFoldEVFast(
        flopCombos,
        flopCardCombos,
        flopBufs,
        nc,
        pot,
        stacks,
        trav,
        folder,
        oR,
        iR,
        out,
      );
    },
    outEV,
  );
}

function cfrTraverseTurn(
  ts: TurnSubtree,
  oopReach: Float32Array,
  ipReach: Float32Array,
  traverser: number,
  turnCtx: TraversalCtx,
  turnBufs: StreetBufs,
  riverCtx: TraversalCtx,
  riverChanceOop: Float32Array,
  riverChanceIp: Float32Array,
  riverChanceEV: Float32Array,
  riverBufs: StreetBufs,
  outEV: Float32Array,
  potOffset: number = 0,
  startingPot: number = 0,
): void {
  const { tree, store, childNC: nc, cardCombos, rivers } = ts;

  cfrTraverseNode(
    tree,
    store,
    nc,
    oopReach,
    ipReach,
    traverser,
    0,
    0,
    turnCtx,
    // Showdown = street transition to river
    (pot, stacks, oR, iR, trav, out) => {
      // pot is the adjusted turn terminal pot (turnTemplatePot + turnPotOffset).
      // The river template starts at startingPot, so the river's offset is
      // the total chips from flop+turn betting = pot - startingPot.
      const riverPotOffset = pot - startingPot;
      computeRiverChanceValue(
        rivers,
        nc,
        oR,
        iR,
        trav,
        riverCtx,
        riverChanceOop,
        riverChanceIp,
        riverChanceEV,
        riverBufs,
        out,
        riverPotOffset,
      );
      // Record turn->river transition for value network training
      if (_shouldRecord && _transitionRecorder) {
        _transitionRecorder({
          type: 'turn_to_river',
          board: [..._recordBoard, ts.turnCard],
          pot,
          stacks: [stacks[0], stacks[1]],
          traverser: trav,
          numCombos: nc,
          oopReach: new Float32Array(oR.subarray(0, nc)),
          ipReach: new Float32Array(iR.subarray(0, nc)),
          resultEV: new Float32Array(out.subarray(0, nc)),
          combos: ts.mapping.childCombos.combos.slice(0, nc),
        });
      }
    },
    // Fold on turn --- pot/stacks already adjusted by potOffset in cfrTraverseNode
    (pot, stacks, oR, iR, trav, folder, out) => {
      computeFoldEVFast(
        ts.mapping.childCombos.combos,
        cardCombos,
        turnBufs,
        nc,
        pot,
        stacks,
        trav,
        folder,
        oR,
        iR,
        out,
      );
    },
    outEV,
    potOffset,
  );
}

function cfrTraverseRiver(
  rs: RiverSubtree,
  oopReach: Float32Array,
  ipReach: Float32Array,
  traverser: number,
  riverCtx: TraversalCtx,
  riverBufs: StreetBufs,
  outEV: Float32Array,
  potOffset: number = 0,
): void {
  const { tree, store, childNC: nc, cache } = rs;

  cfrTraverseNode(
    tree,
    store,
    nc,
    oopReach,
    ipReach,
    traverser,
    0,
    0,
    riverCtx,
    // Actual showdown --- exact 5-card equity (pot/stacks already adjusted by potOffset)
    (pot, stacks, oR, iR, trav, out) => {
      computeShowdownEVCached(cache, riverBufs, pot, stacks, oR, iR, trav, out);
    },
    // Fold on river (pot/stacks already adjusted by potOffset)
    (pot, stacks, oR, iR, trav, folder, out) => {
      computeFoldEVFast(
        cache.combos,
        cache.cardCombos,
        riverBufs,
        nc,
        pot,
        stacks,
        trav,
        folder,
        oR,
        iR,
        out,
      );
    },
    outEV,
    potOffset,
  );
}

// --- Chance Nodes ---

function computeTurnChanceValue(
  turnSubtrees: TurnSubtree[],
  numTurns: number,
  flopNC: number,
  oopReach: Float32Array,
  ipReach: Float32Array,
  traverser: number,
  turnCtx: TraversalCtx,
  riverCtx: TraversalCtx,
  turnChanceOop: Float32Array,
  turnChanceIp: Float32Array,
  turnChanceEV: Float32Array,
  riverChanceOop: Float32Array,
  riverChanceIp: Float32Array,
  riverChanceEV: Float32Array,
  turnBufs: StreetBufs,
  riverBufs: StreetBufs,
  outEV: Float32Array,
  potOffset: number = 0,
  startingPot: number = 0,
): void {
  outEV.fill(0, 0, flopNC);

  if (_mccfr) {
    const ti = Math.floor(Math.random() * numTurns);
    const ts = turnSubtrees[ti];
    const { mapping, childNC: turnNC } = ts;
    for (let ci = 0; ci < turnNC; ci++) {
      turnChanceOop[ci] = oopReach[mapping.childToParent[ci]];
      turnChanceIp[ci] = ipReach[mapping.childToParent[ci]];
    }
    cfrTraverseTurn(
      ts,
      turnChanceOop,
      turnChanceIp,
      traverser,
      turnCtx,
      turnBufs,
      riverCtx,
      riverChanceOop,
      riverChanceIp,
      riverChanceEV,
      riverBufs,
      turnChanceEV,
      potOffset,
      startingPot,
    );
    // Direct assignment (no averaging) --- unbiased estimator of E[V]
    for (let ci = 0; ci < turnNC; ci++) {
      outEV[mapping.childToParent[ci]] = turnChanceEV[ci];
    }
    return;
  }

  for (let ti = 0; ti < numTurns; ti++) {
    const ts = turnSubtrees[ti];
    const { mapping, childNC: turnNC } = ts;

    // Inline remap reaches from flop to turn (no allocation)
    for (let ci = 0; ci < turnNC; ci++) {
      turnChanceOop[ci] = oopReach[mapping.childToParent[ci]];
      turnChanceIp[ci] = ipReach[mapping.childToParent[ci]];
    }

    // Skip dead turns
    if (isReachDead(turnChanceOop, turnNC) || isReachDead(turnChanceIp, turnNC)) {
      continue;
    }

    // Traverse the turn subtree
    cfrTraverseTurn(
      ts,
      turnChanceOop,
      turnChanceIp,
      traverser,
      turnCtx,
      turnBufs,
      riverCtx,
      riverChanceOop,
      riverChanceIp,
      riverChanceEV,
      riverBufs,
      turnChanceEV,
      potOffset,
      startingPot,
    );

    // Inline remap EV back to flop space and accumulate
    for (let ci = 0; ci < turnNC; ci++) {
      outEV[mapping.childToParent[ci]] += turnChanceEV[ci];
    }
  }

  // Average across turn cards
  const invNumTurns = 1 / numTurns;
  for (let c = 0; c < flopNC; c++) {
    outEV[c] *= invNumTurns;
  }
}

function computeRiverChanceValue(
  rivers: RiverSubtree[],
  turnNC: number,
  oopReach: Float32Array,
  ipReach: Float32Array,
  traverser: number,
  riverCtx: TraversalCtx,
  riverChanceOop: Float32Array,
  riverChanceIp: Float32Array,
  riverChanceEV: Float32Array,
  riverBufs: StreetBufs,
  outEV: Float32Array,
  potOffset: number = 0,
): void {
  const numRivers = rivers.length;
  outEV.fill(0, 0, turnNC);

  if (_mccfr) {
    const ri = Math.floor(Math.random() * numRivers);
    const rs = rivers[ri];
    const { mapping, childNC: riverNC } = rs;
    for (let ci = 0; ci < riverNC; ci++) {
      riverChanceOop[ci] = oopReach[mapping.childToParent[ci]];
      riverChanceIp[ci] = ipReach[mapping.childToParent[ci]];
    }
    cfrTraverseRiver(
      rs,
      riverChanceOop,
      riverChanceIp,
      traverser,
      riverCtx,
      riverBufs,
      riverChanceEV,
      potOffset,
    );
    for (let ci = 0; ci < riverNC; ci++) {
      outEV[mapping.childToParent[ci]] = riverChanceEV[ci];
    }
    return;
  }

  for (let ri = 0; ri < numRivers; ri++) {
    const rs = rivers[ri];
    const { mapping, childNC: riverNC } = rs;

    // Inline remap reaches
    for (let ci = 0; ci < riverNC; ci++) {
      riverChanceOop[ci] = oopReach[mapping.childToParent[ci]];
      riverChanceIp[ci] = ipReach[mapping.childToParent[ci]];
    }

    if (isReachDead(riverChanceOop, riverNC) || isReachDead(riverChanceIp, riverNC)) {
      continue;
    }

    // Traverse river subtree
    cfrTraverseRiver(
      rs,
      riverChanceOop,
      riverChanceIp,
      traverser,
      riverCtx,
      riverBufs,
      riverChanceEV,
      potOffset,
    );

    // Inline remap EV and accumulate
    for (let ci = 0; ci < riverNC; ci++) {
      outEV[mapping.childToParent[ci]] += riverChanceEV[ci];
    }
  }

  // Average across river cards
  const invNumRivers = 1 / numRivers;
  for (let c = 0; c < turnNC; c++) {
    outEV[c] *= invNumRivers;
  }
}

// --- Parallel CFR Solver ---

export interface ParallelFullGameParams extends FullGameCFRParams {
  numWorkers?: number;
}

/**
 * Parallel CFR solver: forks N child processes, each independently
 * building the game tree and running its share of iterations.
 * Workers' flop strategySums are aggregated via IPC.
 *
 * Supports both MCCFR (mccfr=true) and full enumeration (mccfr=false).
 * Uses Linear CFR weighting for correct parallel aggregation.
 */
export async function solveFullGameCFRParallel(
  params: ParallelFullGameParams,
): Promise<FullGameCFRResult> {
  const numWorkers = Math.min(params.numWorkers ?? cpus().length, params.iterations);

  if (numWorkers <= 1) {
    return solveFullGameCFR({ ...params, mccfr: params.mccfr ?? false });
  }

  const { board, treeConfig, oopRange, ipRange, iterations, onProgress } = params;
  const startTime = Date.now();

  // Build game tree on main thread (for result structure + flop store shape)
  const flopCombos = enumerateValidCombos(board);
  const flopNC = flopCombos.numCombos;
  const flopBlocker = buildBlockerMatrix(flopCombos.combos);
  const flopConfig: TreeConfig = {
    ...treeConfig,
    singleStreet: true,
    perLevelBetFractions: treeConfig.absoluteBetSizes ? undefined : treeConfig.perLevelBetFractions,
  };
  const flopRoot = buildTree(flopConfig);
  const flopTree = flattenTree(flopRoot, 2);
  const flopStore = new ArrayStore(flopTree, flopNC);

  const mccfr = params.mccfr ?? false;

  if (onProgress) {
    const mode = mccfr ? 'MCCFR' : 'Full-Enum';
    onProgress('init', `Launching ${numWorkers} parallel ${mode} workers...`, 5);
  }

  // Worker script path --- use compiled .js from dist/ (avoids tsx loader issues in workers)
  const __dirname = dirname(fileURLToPath(import.meta.url));
  const workerPath = join(__dirname, '..', '..', 'dist', 'vectorized', 'full-game-worker.js');

  // Distribute iterations with linear weighting offsets
  const baseIters = Math.floor(iterations / numWorkers);
  const extraIters = iterations % numWorkers;
  const workerProgress = new Array(numWorkers).fill(0);

  interface WorkerResult {
    strategySums: number[];
    elapsedMs: number;
    memoryMB: number;
  }

  const workerPromises: Promise<WorkerResult>[] = [];
  let cumulativeIters = 0;

  for (let w = 0; w < numWorkers; w++) {
    const workerIters = baseIters + (w < extraIters ? 1 : 0);
    if (workerIters <= 0) continue;

    const globalIterOffset = cumulativeIters;
    cumulativeIters += workerIters;

    workerPromises.push(
      new Promise<WorkerResult>((resolve, reject) => {
        const child = fork(workerPath, [], {
          execArgv: [...process.execArgv],
          serialization: 'advanced',
          stdio: ['pipe', 'pipe', 'pipe', 'ipc'],
        });

        child.on('message', (msg: any) => {
          if (msg.type === 'progress') {
            workerProgress[w] = msg.pct ?? 0;
          } else if (msg.type === 'done') {
            resolve({
              strategySums: msg.strategySums,
              elapsedMs: msg.elapsedMs,
              memoryMB: msg.memoryMB,
            });
          }
        });

        child.on('error', reject);
        child.on('exit', (code) => {
          if (code !== 0 && code !== null) {
            reject(new Error(`Worker ${w} exited with code ${code}`));
          }
        });

        // Send work to the child process
        child.send({
          workerId: w,
          board,
          treeConfig,
          oopRange,
          ipRange,
          iterations: workerIters,
          globalIterOffset,
          mccfr,
        });
      }),
    );
  }

  // Poll progress
  let timer: ReturnType<typeof setInterval> | null = null;
  if (onProgress) {
    timer = setInterval(() => {
      const avgPct = workerProgress.reduce((a, b) => a + b, 0) / numWorkers;
      const elapsed = (Date.now() - startTime) / 1000;
      onProgress(
        'parallel',
        `${numWorkers} workers (${elapsed.toFixed(0)}s, avg ${avgPct.toFixed(0)}%)`,
        avgPct,
      );
    }, 2000);
  }

  try {
    const results = await Promise.all(workerPromises);

    // Aggregate flop strategySums from all workers
    flopStore.strategySums.fill(0);
    for (const result of results) {
      const sums = result.strategySums;
      for (let i = 0; i < sums.length; i++) {
        flopStore.strategySums[i] += sums[i];
      }
    }

    const maxMemory = Math.max(...results.map((r) => r.memoryMB));
    const totalElapsed = Date.now() - startTime;

    if (onProgress) {
      onProgress(
        'done',
        `All ${numWorkers} workers finished (${(totalElapsed / 1000).toFixed(1)}s)`,
        100,
      );
    }

    return {
      tree: flopTree,
      store: flopStore,
      validCombos: flopCombos,
      blockerMatrix: flopBlocker,
      nc: flopNC,
      elapsedMs: totalElapsed,
      memoryMB: maxMemory * numWorkers,
    };
  } finally {
    if (timer) clearInterval(timer);
  }
}
