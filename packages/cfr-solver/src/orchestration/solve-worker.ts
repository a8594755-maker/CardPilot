// Child process entry point for solving a single flop.
// Receives flop task via IPC message, runs CFR, exports results, reports back.
//
// For coaching HU configs (coach_hu_*):
//   Uses vectorized engine (WASM first, TS fallback) — flat TypedArrays, zero GC.
//   WASM handles full-game CFR in C++ memory (turn/river subtrees in WASM heap).
//   TS fallback uses mccrfSampler on flop-only tree (samples runout equity).
//
// For legacy configs:
//   Uses Map-based MCCFR (cfr-engine.ts) — backward compatible.

import { buildTree } from '../tree/tree-builder.js';
import { getTreeConfig, getMultiWayRangeConfigs, type TreeConfigName } from '../tree/tree-config.js';
import { InfoSetStore } from '../engine/info-set-store.js';
import { solveCFR, solveCFRMultiWay } from '../engine/cfr-engine.js';
import { loadHUSRPRanges, loadMultiWayRanges, getWeightedRangeCombos, type HUSRPRangesOptions } from '../integration/preflop-ranges.js';
import { exportToJSONL, exportMeta, exportArrayStoreToJSONL } from '../storage/json-export.js';
import { resolve } from 'node:path';

// Vectorized engine imports (for coaching configs)
import { flattenTree } from '../vectorized/flat-tree.js';
import type { FlatTree } from '../vectorized/flat-tree.js';
import { ArrayStore } from '../vectorized/array-store.js';
import { enumerateValidCombos, buildBlockerMatrix, buildReachFromRange } from '../vectorized/combo-utils.js';
import { solveVectorized } from '../vectorized/vectorized-cfr.js';
import { precomputeHandValues, rebuildShowdownCacheForMCCFR } from '../vectorized/showdown-eval.js';
import { indexToCard } from '../abstraction/card-index.js';
import { extractAllNodeQValues } from '../vectorized/ev-extractor.js';

/**
 * Config-specific preflop range options.
 * Each config maps to different position spots and actions from GTO Wizard data.
 *
 * SRP configs: IP opens (raise), OOP calls (call)
 * 3-bet configs: OOP 3-bets (raise from BB spot), IP calls the 3-bet
 *   — IP calling range approximated by filtering opener's range with minFrequency
 */
function getRangeOptions(configName: TreeConfigName): HUSRPRangesOptions {
  switch (configName) {
    // --- BTN vs BB ---
    case 'pipeline_srp':
    case 'pipeline_srp_v2':
    case 'pipeline_srp_100bb':
    case 'hu_btn_bb_srp_50bb':
    case 'hu_btn_bb_srp_100bb':
      return {
        ipSpot: 'BTN_unopened_open2.5x',
        ipAction: 'raise',
        oopSpot: 'BB_vs_BTN_facing_open2.5x',
        oopAction: 'call',
      };

    case 'pipeline_3bet':
    case 'pipeline_3bet_v2':
    case 'pipeline_3bet_100bb':
    case 'hu_btn_bb_3bp_50bb':
    case 'hu_btn_bb_3bp_100bb':
      return {
        oopSpot: 'BB_vs_BTN_facing_open2.5x',
        oopAction: 'raise',         // BB's 3-bet range
        ipSpot: 'BTN_unopened_open2.5x',
        ipAction: 'raise',
        minFrequency: 0.40,         // approximate BTN calling-3-bet range
      };

    // --- CO vs BB ---
    case 'hu_co_bb_srp_100bb':
      return {
        ipSpot: 'CO_unopened_open2.5x',
        ipAction: 'raise',
        oopSpot: 'BB_vs_CO_facing_open2.5x',
        oopAction: 'call',
      };

    case 'hu_co_bb_3bp_100bb':
      return {
        oopSpot: 'BB_vs_CO_facing_open2.5x',
        oopAction: 'raise',         // BB's 3-bet range vs CO
        ipSpot: 'CO_unopened_open2.5x',
        ipAction: 'raise',
        minFrequency: 0.50,         // CO range is tighter, so calling range is tighter
      };

    // --- UTG vs BB ---
    case 'hu_utg_bb_srp_100bb':
      return {
        ipSpot: 'UTG_unopened_open2.5x',
        ipAction: 'raise',
        oopSpot: 'BB_vs_UTG_facing_open2.5x',
        oopAction: 'call',
      };

    // --- Coaching HU SRP (BTN vs BB, all depths) ---
    case 'coach_hu_srp_30bb':
    case 'coach_hu_srp_60bb':
    case 'coach_hu_srp_100bb':
    case 'coach_hu_srp_200bb':
      return {
        ipSpot: 'BTN_unopened_open2.5x',
        ipAction: 'raise',
        oopSpot: 'BB_vs_BTN_facing_open2.5x',
        oopAction: 'call',
      };

    // --- Coaching HU 3BP (BTN vs BB 3-bet, all depths) ---
    case 'coach_hu_3bp_30bb':
    case 'coach_hu_3bp_60bb':
    case 'coach_hu_3bp_100bb':
    case 'coach_hu_3bp_200bb':
      return {
        oopSpot: 'BB_vs_BTN_facing_open2.5x',
        oopAction: 'raise',         // BB's 3-bet range
        ipSpot: 'BTN_unopened_open2.5x',
        ipAction: 'raise',
        minFrequency: 0.40,         // approximate BTN calling-3-bet range
      };

    default:
      return {}; // SRP BTN vs BB defaults
  }
}

export interface FlopTask {
  type: 'solve';
  flopCards: [number, number, number];
  boardId: number;
  label: string;
  iterations: number;
  bucketCount: number;
  outputDir: string;
  chartsPath: string;
  configName?: TreeConfigName; // defaults to 'v1_50bb' for backward compat
  stackLabel?: string;
}

export interface WorkerResult {
  type: 'result';
  boardId: number;
  label: string;
  infoSets: number;
  fileSize: number;
  elapsedMs: number;
  peakMemoryMB: number;
}

export interface WorkerProgress {
  type: 'progress';
  boardId: number;
  iteration: number;
  total: number;
}

// ─── Coaching HU: Vectorized/WASM solver ───

/** Module-level caches (shared between coaching and legacy paths) */
const flatTreeCache = new Map<string, FlatTree>();
const rangeCache = new Map<string, ReturnType<typeof loadHUSRPRanges>>();

function getOrBuildFlatTree(cfgName: string): FlatTree {
  if (flatTreeCache.has(cfgName)) return flatTreeCache.get(cfgName)!;
  const treeConfig = getTreeConfig(cfgName as TreeConfigName);
  const singleStreetConfig = { ...treeConfig, singleStreet: true };
  const root = buildTree(singleStreetConfig);
  const flat = flattenTree(root, treeConfig.numPlayers ?? 2);
  flatTreeCache.set(cfgName, flat);
  return flat;
}

/**
 * Solve a coaching HU flop using the vectorized engine with MCCFR showdown sampler.
 *
 * Uses O(n log n) showdown cache rebuild per iteration (not O(n²) equity matrix).
 * Terminal evaluation is O(n) via prefix sums + blocker exclusion.
 * Expected ~10ms/iter for nc≈1176 → ~10s per flop at 1000 iterations.
 */
function solveCoachingHU(task: FlopTask, cfgName: string): void {
  const startTime = Date.now();

  // Build/cache single-street flat tree
  const flopTree = getOrBuildFlatTree(cfgName);

  // Load ranges (cached)
  const rangeOpts = getRangeOptions(cfgName as TreeConfigName);
  if (!rangeCache.has(cfgName)) {
    rangeCache.set(cfgName, loadHUSRPRanges(task.chartsPath, rangeOpts));
  }
  const ranges = rangeCache.get(cfgName)!;

  const deadCards = new Set(task.flopCards as number[]);
  const oopCombos = getWeightedRangeCombos(ranges.oopRange, deadCards);
  const ipCombos = getWeightedRangeCombos(ranges.ipRange, deadCards);

  // Enumerate valid combos for this flop
  const validCombos = enumerateValidCombos(task.flopCards);
  const nc = validCombos.numCombos;

  // Build blocker matrix (stable across iterations)
  const blockerMatrix = buildBlockerMatrix(validCombos.combos);

  // Build dealable cards (52 minus flop)
  const flopCards = Array.from(task.flopCards);
  const dealable: number[] = [];
  const deadSet = new Set(flopCards);
  for (let c = 0; c < 52; c++) {
    if (!deadSet.has(c)) dealable.push(c);
  }

  // Create store
  const store = new ArrayStore(flopTree, nc);

  // ── MCCFR Showdown Sampler ──
  // Samples random turn+river, rebuilds O(n log n) showdown cache.
  // Terminal eval uses O(n) prefix-sum fast path.
  const mccrfShowdownSampler = (
    oopInit: Float32Array,
    ipInit: Float32Array,
    _iter: number,
  ) => {
    // Sample random turn + river cards
    const ti = Math.floor(Math.random() * dealable.length);
    const turnCard = dealable[ti];
    const remaining = dealable.filter(c => c !== turnCard);
    const ri = Math.floor(Math.random() * remaining.length);
    const riverCard = remaining[ri];

    // Zero reaches for combos blocked by turn/river
    for (let i = 0; i < nc; i++) {
      const [c1, c2] = validCombos.combos[i];
      if (c1 === turnCard || c2 === turnCard || c1 === riverCard || c2 === riverCard) {
        oopInit[i] = 0;
        ipInit[i] = 0;
      }
    }

    // Compute 5-card hand values and rebuild O(n log n) showdown cache
    const fullBoard = [...flopCards, turnCard, riverCard];
    const handValues = precomputeHandValues(validCombos.combos, fullBoard);
    rebuildShowdownCacheForMCCFR(validCombos.combos, handValues, blockerMatrix);
  };

  solveVectorized({
    tree: flopTree,
    store,
    board: flopCards,
    oopRange: oopCombos,
    ipRange: ipCombos,
    iterations: task.iterations,
    blockerMatrix,
    mccrfShowdownSampler,
    useLinearWeighting: true,
    onProgress: (iter, _elapsed) => {
      if (iter % Math.max(1, Math.floor(task.iterations / 20)) === 0) {
        process.send!({
          type: 'progress',
          boardId: task.boardId,
          iteration: iter,
          total: task.iterations,
        } satisfies WorkerProgress);
      }
    },
  });

  const solveElapsed = Date.now() - startTime;

  // Extract per-node Q-values by averaging over all turn+river runouts
  const oopReachInit = buildReachFromRange(oopCombos, validCombos);
  const ipReachInit = buildReachFromRange(ipCombos, validCombos);
  const qvResult = extractAllNodeQValues({
    tree: flopTree,
    store,
    board: Array.from(task.flopCards),
    oopReach: oopReachInit,
    ipReach: ipReachInit,
    nc,
    combos: validCombos.combos,
    blockerMatrix,
  });

  const elapsed = Date.now() - startTime;

  // Export using vectorized export format (with Q-values)
  const outputPath = resolve(task.outputDir, `flop_${String(task.boardId).padStart(3, '0')}.jsonl`);
  const boardCards = task.flopCards.map((c: number) => indexToCard(c));
  const exportResult = exportArrayStoreToJSONL(store, flopTree, validCombos, {
    outputPath,
    board: Array.from(task.flopCards),
    boardCards,
    configName: cfgName,
    iterations: task.iterations,
    elapsedMs: elapsed,
    qValues: qvResult.qValues,
  });

  process.send!({
    type: 'result',
    boardId: task.boardId,
    label: task.label,
    infoSets: exportResult.infoSets,
    fileSize: exportResult.fileSize,
    elapsedMs: elapsed,
    peakMemoryMB: Math.round(process.memoryUsage().heapUsed / 1024 / 1024),
  } satisfies WorkerResult);
}

// ─── IPC message handler ───

// Only run when executed as a child process with IPC channel
if (process.send) {
  // Cache trees and ranges per config name (different configs need different ranges)
  const treeCache = new Map<string, ReturnType<typeof buildTree>>();
  // rangeCache is at module scope (shared with solveCoachingHU)
  const multiWayRangeCache = new Map<string, ReturnType<typeof loadMultiWayRanges>>();

  process.on('message', async (task: FlopTask) => {
    if (task.type !== 'solve') return;

    const cfgName = task.configName || 'v1_50bb';
    const treeConfig = getTreeConfig(cfgName);
    const numPlayers = treeConfig.numPlayers ?? 2;

    // ── Coaching HU: use vectorized MCCFR showdown sampler ──
    const isCoachingHU = cfgName.startsWith('coach_hu_') && numPlayers === 2;
    if (isCoachingHU) {
      try {
        solveCoachingHU(task, cfgName);
      } catch (err) {
        console.error(`[Worker] Coaching solve failed for board ${task.boardId}:`, err);
        process.send!({
          type: 'result',
          boardId: task.boardId,
          label: task.label,
          infoSets: 0,
          fileSize: 0,
          elapsedMs: 0,
          peakMemoryMB: Math.round(process.memoryUsage().heapUsed / 1024 / 1024),
        } satisfies WorkerResult);
      }
      return;
    }

    // ── Legacy path: Map-based MCCFR ──
    // Build/cache tree for this config
    if (!treeCache.has(cfgName)) {
      treeCache.set(cfgName, buildTree(treeConfig));
    }
    const tree = treeCache.get(cfgName)!;

    const store = new InfoSetStore();
    const startTime = Date.now();

    if (numPlayers > 2) {
      // ---- Multi-way solve ----
      if (!multiWayRangeCache.has(cfgName)) {
        const mwConfigs = getMultiWayRangeConfigs(cfgName);
        multiWayRangeCache.set(cfgName, loadMultiWayRanges(task.chartsPath, mwConfigs, numPlayers));
      }
      const mwRanges = multiWayRangeCache.get(cfgName)!;

      const deadCards = new Set(task.flopCards as number[]);
      const playerRanges = mwRanges.map(r => getWeightedRangeCombos(r, deadCards));

      solveCFRMultiWay({
        root: tree,
        store,
        boardId: task.boardId,
        flopCards: task.flopCards,
        ranges: playerRanges,
        numPlayers,
        iterations: task.iterations,
        bucketCount: task.bucketCount,
        onProgress: (iter, _elapsed) => {
          process.send!({
            type: 'progress',
            boardId: task.boardId,
            iteration: iter,
            total: task.iterations,
          } satisfies WorkerProgress);
        },
      });
    } else {
      // ---- HU solve (existing path) ----
      if (!rangeCache.has(cfgName)) {
        const rangeOpts = getRangeOptions(cfgName);
        rangeCache.set(cfgName, loadHUSRPRanges(task.chartsPath, rangeOpts));
      }
      const ranges = rangeCache.get(cfgName)!;

      const deadCards = new Set(task.flopCards as number[]);
      const oopCombos = getWeightedRangeCombos(ranges.oopRange, deadCards);
      const ipCombos = getWeightedRangeCombos(ranges.ipRange, deadCards);

      solveCFR({
        root: tree,
        store,
        boardId: task.boardId,
        flopCards: task.flopCards,
        oopRange: oopCombos,
        ipRange: ipCombos,
        iterations: task.iterations,
        bucketCount: task.bucketCount,
        onProgress: (iter, _elapsed) => {
          process.send!({
            type: 'progress',
            boardId: task.boardId,
            iteration: iter,
            total: task.iterations,
          } satisfies WorkerProgress);
        },
      });
    }

    const elapsed = Date.now() - startTime;

    // Export
    const outputPath = resolve(task.outputDir, `flop_${String(task.boardId).padStart(3, '0')}.jsonl`);
    const exportResult = exportToJSONL(store, {
      outputPath,
      boardId: task.boardId,
      flopCards: task.flopCards,
      iterations: task.iterations,
      bucketCount: task.bucketCount,
      elapsedMs: elapsed,
      stackLabel: task.stackLabel,
      configName: cfgName,
      betSizes: treeConfig.betSizes,
    });
    exportMeta({
      outputPath,
      boardId: task.boardId,
      flopCards: task.flopCards,
      iterations: task.iterations,
      bucketCount: task.bucketCount,
      elapsedMs: elapsed,
      infoSets: exportResult.infoSets,
      peakMemoryMB: Math.round(process.memoryUsage().heapUsed / 1024 / 1024),
      stackLabel: task.stackLabel,
      configName: cfgName,
      betSizes: treeConfig.betSizes,
    });

    process.send!({
      type: 'result',
      boardId: task.boardId,
      label: task.label,
      infoSets: exportResult.infoSets,
      fileSize: exportResult.fileSize,
      elapsedMs: elapsed,
      peakMemoryMB: Math.round(process.memoryUsage().heapUsed / 1024 / 1024),
    } satisfies WorkerResult);
  });
}
