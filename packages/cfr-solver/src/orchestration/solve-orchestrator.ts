// Orchestrates solving multiple flops in parallel using worker pool.

import { WorkerPool } from './worker-pool.js';
import type { FlopTask, WorkerResult } from './solve-worker.js';
import { indexToCard } from '../abstraction/card-index.js';
import { resolve } from 'node:path';
import { cpus } from 'node:os';

export interface OrchestratorConfig {
  flops: Array<{ cards: [number, number, number]; label: string }>;
  iterations: number;
  bucketCount: number;
  outputDir: string;
  chartsPath: string;
  numWorkers?: number; // defaults to min(cpus, flops.length)
}

export interface OrchestratorResult {
  totalFlops: number;
  totalInfoSets: number;
  totalOutputKB: number;
  totalElapsedMs: number;
  flopResults: WorkerResult[];
}

/**
 * Solve multiple flops in parallel using a worker pool.
 */
export async function solveParallel(config: OrchestratorConfig): Promise<OrchestratorResult> {
  const numWorkers = config.numWorkers ?? Math.min(cpus().length, config.flops.length);

  console.log(`=== CardPilot CFR Solver V1 (Parallel) ===`);
  console.log(`Flops: ${config.flops.length} | Iterations: ${config.iterations} | Buckets: ${config.bucketCount}`);
  console.log(`Workers: ${numWorkers}`);
  console.log();

  const results: WorkerResult[] = [];
  let completed = 0;
  const totalStart = Date.now();

  const pool = new WorkerPool({
    numWorkers,
    onResult: (result) => {
      completed++;
      results.push(result);
      const elapsed = (result.elapsedMs / 1000).toFixed(1);
      const fileKB = (result.fileSize / 1024).toFixed(0);
      console.log(
        `[${completed}/${config.flops.length}] ${result.label} | ${elapsed}s | ${result.infoSets} info sets | ${fileKB}KB`
      );
    },
    onProgress: (_progress) => {
      // Could display per-worker progress bars here
    },
  });

  // Submit all tasks
  for (let i = 0; i < config.flops.length; i++) {
    const { cards, label } = config.flops[i];
    pool.submit({
      type: 'solve',
      flopCards: cards,
      boardId: i,
      label,
      iterations: config.iterations,
      bucketCount: config.bucketCount,
      outputDir: config.outputDir,
      chartsPath: config.chartsPath,
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
  console.log(`Flops solved:    ${results.length}`);
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
  };
}
