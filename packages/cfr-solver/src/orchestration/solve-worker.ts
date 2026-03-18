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
import {
  getTreeConfig,
  getMultiWayRangeConfigs,
  type TreeConfigName,
} from '../tree/tree-config.js';
import { InfoSetStore } from '../engine/info-set-store.js';
import { solveCFR, solveCFRMultiWay } from '../engine/cfr-engine.js';
import {
  loadHUSRPRanges,
  loadMultiWayRanges,
  getWeightedRangeCombos,
  type HUSRPRangesOptions,
} from '../integration/preflop-ranges.js';
import { exportToJSONL, exportMeta } from '../storage/json-export.js';
import { resolve } from 'node:path';

// Vectorized engine imports are loaded dynamically in solveCoachingHU()
// to avoid ERR_MODULE_NOT_FOUND when vectorized/ directory doesn't exist yet.

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
        oopAction: 'raise', // BB's 3-bet range
        ipSpot: 'BTN_unopened_open2.5x',
        ipAction: 'raise',
        minFrequency: 0.4, // approximate BTN calling-3-bet range
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
        oopAction: 'raise', // BB's 3-bet range vs CO
        ipSpot: 'CO_unopened_open2.5x',
        ipAction: 'raise',
        minFrequency: 0.5, // CO range is tighter, so calling range is tighter
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
        oopAction: 'raise', // BB's 3-bet range
        ipSpot: 'BTN_unopened_open2.5x',
        ipAction: 'raise',
        minFrequency: 0.4, // approximate BTN calling-3-bet range
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

// ─── Coaching HU: Vectorized/WASM solver (stub) ───
// Vectorized engine modules (flat-tree, array-store, etc.) are not yet ported.
// Coaching configs (coach_hu_*) will fail with a clear error.
// Pipeline configs use the legacy Map-based MCCFR path below.

const rangeCache = new Map<string, ReturnType<typeof loadHUSRPRanges>>();

function solveCoachingHU(_task: FlopTask, cfgName: string): void {
  throw new Error(
    `Coaching config "${cfgName}" requires the vectorized engine (packages/cfr-solver/src/vectorized/) ` +
      `which has not been ported yet. Use pipeline or HU configs instead.`,
  );
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
      const playerRanges = mwRanges.map((r) => getWeightedRangeCombos(r, deadCards));

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
    const outputPath = resolve(
      task.outputDir,
      `flop_${String(task.boardId).padStart(3, '0')}.jsonl`,
    );
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
