#!/usr/bin/env tsx
/**
 * Parallel V3 pipeline solver.
 * Runs N concurrent child processes, each solving one board at a time.
 * Boards are assigned from a shared queue with resume support.
 *
 * Usage:
 *   node --import tsx packages/cfr-solver/src/scripts/solve-v3-parallel.ts
 *   node --import tsx packages/cfr-solver/src/scripts/solve-v3-parallel.ts --workers 8
 */

import { fork, type ChildProcess } from 'node:child_process';
import { cpus, totalmem } from 'node:os';
import { resolve, dirname } from 'node:path';
import { existsSync, mkdirSync, appendFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { enumerateIsomorphicFlops } from '../abstraction/suit-isomorphism.js';
import { indexToCard } from '../abstraction/card-index.js';
import { getConfigOutputDir } from '../tree/tree-config.js';
import type { FlopTask, WorkerResult, WorkerProgress } from '../orchestration/solve-worker.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SOLVE_WORKER_PATH = resolve(__dirname, '../orchestration/solve-worker.ts');

function findProjectRoot(): string {
  const fromFile = resolve(__dirname, '../../../../');
  if (existsSync(resolve(fromFile, 'data/preflop_charts.json'))) return fromFile;
  if (existsSync(resolve(process.cwd(), 'data/preflop_charts.json'))) return process.cwd();
  return process.cwd();
}

const CONFIG_NAME = 'pipeline_srp_v3' as const;
const ITERATIONS = 200000;
const BUCKETS = 50;
const STACK_LABEL = '50bb';

const PROJECT_ROOT = findProjectRoot();
const OUTPUT_DIR = resolve(PROJECT_ROOT, 'data/cfr', getConfigOutputDir(CONFIG_NAME));
const CHARTS_PATH = resolve(PROJECT_ROOT, 'data/preflop_charts.json');
const LOG_PATH = resolve(OUTPUT_DIR, 'parallel-solver.log');

// CLI args
const argv = process.argv.slice(2);
function getArgNum(name: string, fallback: number): number {
  const idx = argv.indexOf(name);
  return idx >= 0 && argv[idx + 1] ? parseInt(argv[idx + 1], 10) : fallback;
}

function syncLog(msg: string): void {
  const line = `[${new Date().toISOString()}] ${msg}\n`;
  appendFileSync(LOG_PATH, line);
  process.stdout.write(line);
}

/** Calculate heap per worker and max workers based on available RAM */
function autoConfig(requestedWorkers: number): { workers: number; heapMB: number } {
  const totalMB = Math.floor(totalmem() / 1024 / 1024);
  const reservedMB = 8192; // OS + parent + safety margin
  const perWorkerMB = 6144; // V3 50bb peaks at ~4.4GB, 6GB is safe
  const maxByRam = Math.floor((totalMB - reservedMB) / perWorkerMB);
  const maxByCpu = Math.max(1, cpus().length - 2);
  const workers = Math.min(requestedWorkers, maxByRam, maxByCpu);
  return { workers, heapMB: perWorkerMB };
}

/** Solve a single board in a forked child process */
function solveBoardForked(
  boardId: number,
  flopCards: [number, number, number],
  label: string,
  heapMB: number,
): Promise<WorkerResult> {
  return new Promise((resolveP, rejectP) => {
    const child = fork(SOLVE_WORKER_PATH, [], {
      execArgv: ['--import', 'tsx', `--max-old-space-size=${heapMB}`],
      stdio: ['inherit', 'inherit', 'inherit', 'ipc'],
    });

    const task: FlopTask = {
      type: 'solve',
      boardId,
      flopCards,
      label,
      iterations: ITERATIONS,
      bucketCount: BUCKETS,
      outputDir: OUTPUT_DIR,
      chartsPath: CHARTS_PATH,
      configName: CONFIG_NAME,
      stackLabel: STACK_LABEL,
    };

    child.on('spawn', () => {
      child.send(task);
    });

    child.on('message', (msg: WorkerResult | WorkerProgress) => {
      if (msg.type === 'progress') {
        const p = msg as WorkerProgress;
        if (p.iteration % 25000 === 0 && p.iteration > 0) {
          syncLog(`  [board ${boardId}] iter ${p.iteration}/${p.total}`);
        }
      } else if (msg.type === 'result') {
        child.disconnect();
        resolveP(msg as WorkerResult);
      }
    });

    child.on('exit', (code, signal) => {
      if (code !== 0 && code !== null) {
        rejectP(new Error(`Worker for board ${boardId} exited code=${code} signal=${signal}`));
      }
    });

    child.on('error', rejectP);
  });
}

async function main(): Promise<void> {
  mkdirSync(OUTPUT_DIR, { recursive: true });

  const requestedWorkers = getArgNum('--workers', 12);
  const { workers, heapMB } = autoConfig(requestedWorkers);

  // Find missing boards
  const allFlops = enumerateIsomorphicFlops();
  const missing: Array<{ boardId: number; cards: [number, number, number]; label: string }> = [];
  for (let i = 0; i < allFlops.length; i++) {
    const metaPath = resolve(OUTPUT_DIR, `flop_${String(i).padStart(3, '0')}.meta.json`);
    if (!existsSync(metaPath)) {
      missing.push({
        boardId: i,
        cards: allFlops[i].cards,
        label: allFlops[i].cards.map(indexToCard).join(' '),
      });
    }
  }

  syncLog('=== V3 Parallel Solver starting ===');
  syncLog(`  config: ${CONFIG_NAME} (${BUCKETS} buckets, ${ITERATIONS} iter)`);
  syncLog(`  workers: ${workers} (${heapMB}MB heap each)`);
  syncLog(`  output: ${OUTPUT_DIR}`);
  syncLog(`  missing: ${missing.length} / ${allFlops.length} boards`);

  if (missing.length === 0) {
    syncLog('All boards already solved!');
    return;
  }

  const totalStart = Date.now();
  let completed = 0;
  let failed = 0;
  let queueIdx = 0; // Next board to assign

  /** Launch a worker, resolve when it finishes and picks up next task */
  async function runWorker(workerId: number): Promise<void> {
    while (queueIdx < missing.length) {
      const idx = queueIdx++;
      const { boardId, cards, label } = missing[idx];
      const progress = `[${completed + 1 + workers}/${missing.length}]`;

      syncLog(`W${workerId} ${progress} Starting board ${boardId}: ${label}`);
      const t0 = Date.now();

      try {
        const result = await solveBoardForked(boardId, cards, label, heapMB);
        const elapsed = (Date.now() - t0) / 1000;
        completed++;
        const eta =
          missing.length > completed
            ? (
                (((Date.now() - totalStart) / completed) * (missing.length - completed)) /
                3600000
              ).toFixed(1)
            : '0';
        syncLog(
          `W${workerId} Board ${boardId} DONE: ` +
            `${result.infoSets?.toLocaleString() ?? '?'} info sets | ` +
            `${(elapsed / 60).toFixed(1)}min | peak ${result.peakMemoryMB ?? '?'}MB | ` +
            `${completed}/${missing.length} done | ETA ${eta}h`,
        );
      } catch (err) {
        failed++;
        syncLog(`W${workerId} Board ${boardId} FAILED: ${err}`);
      }
    }
  }

  // Launch N workers in parallel
  const workerPromises: Promise<void>[] = [];
  for (let w = 0; w < workers; w++) {
    workerPromises.push(runWorker(w));
  }

  await Promise.all(workerPromises);

  const totalElapsed = (Date.now() - totalStart) / 1000;
  const hours = (totalElapsed / 3600).toFixed(2);
  syncLog(`=== V3 Parallel Solver done ===`);
  syncLog(`  completed: ${completed}, failed: ${failed}`);
  syncLog(`  total time: ${hours}h`);
  syncLog(`  avg per board: ${(totalElapsed / Math.max(completed, 1) / 60).toFixed(1)}min`);
}

main().catch((err) => {
  syncLog(`FATAL: ${err?.stack ?? err}`);
  process.exit(1);
});
