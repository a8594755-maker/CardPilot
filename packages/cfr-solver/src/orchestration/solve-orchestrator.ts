// Orchestrates solving multiple flops in parallel using worker pool.
// V2: supports checkpoint/resume for long-running full-board solves.

import { WorkerPool } from './worker-pool.js';
import type { FlopTask, WorkerResult } from './solve-worker.js';
import { indexToCard } from '../abstraction/card-index.js';
import { resolve, join } from 'node:path';
import { cpus } from 'node:os';
import { existsSync, readFileSync, writeFileSync, mkdirSync, readdirSync } from 'node:fs';

export interface OrchestratorConfig {
  flops: Array<{ cards: [number, number, number]; label: string }>;
  iterations: number;
  bucketCount: number;
  outputDir: string;
  chartsPath: string;
  configName?: string;  // tree config name for workers
  stackLabel?: string;  // e.g. '50bb', '100bb'
  numWorkers?: number;  // defaults to min(cpus, flops.length)
  resume?: boolean;     // if true, skip flops that already have output files
}

export interface OrchestratorResult {
  totalFlops: number;
  totalInfoSets: number;
  totalOutputKB: number;
  totalElapsedMs: number;
  flopResults: WorkerResult[];
  skippedFlops: number;
}

interface ProgressFile {
  completedBoardIds: number[];
  lastUpdated: string;
  iterations: number;
  bucketCount: number;
}

/**
 * Solve multiple flops in parallel using a worker pool.
 * Supports checkpoint/resume: skips already-solved flops on restart.
 */
export async function solveParallel(config: OrchestratorConfig): Promise<OrchestratorResult> {
  const numWorkers = config.numWorkers ?? Math.min(cpus().length, config.flops.length);

  // Ensure output directory exists
  mkdirSync(config.outputDir, { recursive: true });

  // Load checkpoint if resuming
  const progressPath = join(config.outputDir, '_progress.json');
  let completedIds = new Set<number>();
  let skippedFlops = 0;

  if (config.resume) {
    completedIds = loadCheckpoint(progressPath, config.outputDir);
    if (completedIds.size > 0) {
      console.log(`Resuming: ${completedIds.size} flops already solved, skipping them.`);
    }
  }

  // Filter out already-completed flops
  const pendingFlops = config.flops.filter((_, i) => !completedIds.has(i));
  skippedFlops = config.flops.length - pendingFlops.length;

  console.log(`=== CardPilot CFR Solver V2 (Parallel) ===`);
  console.log(`Flops: ${pendingFlops.length} pending (${skippedFlops} skipped) of ${config.flops.length} total`);
  console.log(`Iterations: ${config.iterations} | Buckets: ${config.bucketCount}`);
  console.log(`Workers: ${numWorkers}`);
  console.log();

  if (pendingFlops.length === 0) {
    console.log('All flops already solved. Nothing to do.');
    return {
      totalFlops: 0,
      totalInfoSets: 0,
      totalOutputKB: 0,
      totalElapsedMs: 0,
      flopResults: [],
      skippedFlops,
    };
  }

  const results: WorkerResult[] = [];
  let completed = 0;
  const totalStart = Date.now();

  const pool = new WorkerPool({
    numWorkers,
    onResult: (result) => {
      completed++;
      results.push(result);
      completedIds.add(result.boardId);

      const elapsed = (result.elapsedMs / 1000).toFixed(1);
      const fileKB = (result.fileSize / 1024).toFixed(0);
      console.log(
        `[${completed + skippedFlops}/${config.flops.length}] ${result.label} | ${elapsed}s | ${result.infoSets} info sets | ${fileKB}KB`
      );

      // Save checkpoint after each completed flop
      saveCheckpoint(progressPath, completedIds, config.iterations, config.bucketCount);
    },
    onProgress: (_progress) => {
      // Could display per-worker progress bars here
    },
  });

  // Submit pending tasks (use original board IDs)
  for (const flop of pendingFlops) {
    const originalIndex = config.flops.indexOf(flop);
    const { cards, label } = flop;
    pool.submit({
      type: 'solve',
      flopCards: cards,
      boardId: originalIndex,
      label,
      iterations: config.iterations,
      bucketCount: config.bucketCount,
      outputDir: config.outputDir,
      chartsPath: config.chartsPath,
      configName: config.configName as any,
      stackLabel: config.stackLabel,
    });
  }

  // Wait for all to complete
  await pool.waitAll();
  await pool.shutdown();

  const totalElapsed = Date.now() - totalStart;
  const totalInfoSets = results.reduce((s, r) => s + r.infoSets, 0);
  const totalOutputKB = results.reduce((s, r) => s + r.fileSize / 1024, 0);

  console.log();
  console.log('=== Summary ===');
  console.log(`Flops solved:    ${results.length} (${skippedFlops} skipped/resumed)`);
  console.log(`Total time:      ${(totalElapsed / 1000).toFixed(1)}s (wall clock)`);
  console.log(`Total info sets: ${totalInfoSets.toLocaleString()}`);
  console.log(`Total output:    ${(totalOutputKB / 1024).toFixed(1)}MB`);
  console.log(`Output dir:      ${config.outputDir}`);

  return {
    totalFlops: results.length,
    totalInfoSets,
    totalOutputKB,
    totalElapsedMs: totalElapsed,
    flopResults: results,
    skippedFlops,
  };
}

// --- Checkpoint helpers ---

function loadCheckpoint(progressPath: string, outputDir: string): Set<number> {
  const completed = new Set<number>();

  // Method 1: Read progress file
  if (existsSync(progressPath)) {
    try {
      const data = JSON.parse(readFileSync(progressPath, 'utf-8')) as ProgressFile;
      for (const id of data.completedBoardIds) completed.add(id);
    } catch {
      // Corrupted progress file, scan output dir instead
    }
  }

  // Method 2: Also scan for existing output files (in case progress file was lost)
  if (existsSync(outputDir)) {
    const files = readdirSync(outputDir);
    for (const f of files) {
      const match = f.match(/^flop_(\d+)\.meta\.json$/);
      if (match) {
        completed.add(parseInt(match[1], 10));
      }
    }
  }

  return completed;
}

function saveCheckpoint(
  progressPath: string,
  completedIds: Set<number>,
  iterations: number,
  bucketCount: number,
): void {
  const data: ProgressFile = {
    completedBoardIds: [...completedIds].sort((a, b) => a - b),
    lastUpdated: new Date().toISOString(),
    iterations,
    bucketCount,
  };
  writeFileSync(progressPath, JSON.stringify(data, null, 2));
}
