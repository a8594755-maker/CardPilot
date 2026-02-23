// Child process entry point for solving a single flop.
// Receives flop task via IPC message, runs CFR, exports results, reports back.

import { buildTree } from '../tree/tree-builder.js';
import { V1_TREE_CONFIG } from '../tree/tree-config.js';
import { InfoSetStore } from '../engine/info-set-store.js';
import { solveCFR } from '../engine/cfr-engine.js';
import { loadHUSRPRanges, getRangeCombos } from '../integration/preflop-ranges.js';
import { exportToJSONL, exportMeta } from '../storage/json-export.js';
import { resolve } from 'node:path';

export interface FlopTask {
  type: 'solve';
  flopCards: [number, number, number];
  boardId: number;
  label: string;
  iterations: number;
  bucketCount: number;
  outputDir: string;
  chartsPath: string;
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

// Only run when executed as a child process with IPC channel
if (process.send) {
  // Build tree once per worker process
  const tree = buildTree(V1_TREE_CONFIG);
  let ranges: ReturnType<typeof loadHUSRPRanges> | null = null;

  process.on('message', (task: FlopTask) => {
    if (task.type !== 'solve') return;

    // Lazy-load ranges on first task
    if (!ranges) {
      ranges = loadHUSRPRanges(task.chartsPath);
    }

    const deadCards = new Set(task.flopCards as number[]);
    const oopCombos = getRangeCombos(ranges.oopRange, deadCards);
    const ipCombos = getRangeCombos(ranges.ipRange, deadCards);

    const store = new InfoSetStore();
    const startTime = Date.now();

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
