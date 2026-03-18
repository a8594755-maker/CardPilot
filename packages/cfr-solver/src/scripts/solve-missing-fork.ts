#!/usr/bin/env tsx
/**
 * Solves the 13 missing pipeline_srp_100bb boards using the EXACT same
 * fork() mechanism as network-worker.ts — one child process per board,
 * each with its own heap allocation.
 *
 * This matches what successfully solved the other 1,898 boards.
 *
 * Run via:
 *   node --import tsx scripts\run-fork-solver.bat
 * Or directly:
 *   node --import tsx packages\cfr-solver\src\scripts\solve-missing-fork.ts
 */

import { fork } from 'node:child_process';
import { totalmem } from 'node:os';
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

const CONFIG_NAME = 'pipeline_srp_100bb' as const;
const ITERATIONS = 200000;
const BUCKETS = 100;
const STACK_LABEL = '100bb';

// Boards that hit V8's 16.7M Map limit with 100 buckets.
// These wet connected boards generate too many unique info-set keys.
// Use 50 buckets to halve the key space and stay under the limit.
const REDUCED_BUCKET_BOARDS = new Set([1492, 1596]);

const PROJECT_ROOT = findProjectRoot();
const OUTPUT_DIR = resolve(PROJECT_ROOT, 'data/cfr', getConfigOutputDir(CONFIG_NAME));
const CHARTS_PATH = resolve(PROJECT_ROOT, 'data/preflop_charts.json');
const LOG_PATH = resolve(OUTPUT_DIR, 'fork-solver.log');

function syncLog(msg: string): void {
  const line = `[${new Date().toISOString()}] ${msg}\n`;
  appendFileSync(LOG_PATH, line);
  process.stdout.write(line);
}

/** Single-board sequential solver: give each child most of available RAM */
function autoHeapMB(): number {
  const totalMB = Math.floor(totalmem() / 1024 / 1024);
  // Reserve 4GB for OS + parent; cap at 32GB to leave headroom
  const available = Math.min(totalMB - 4096, 32768);
  // Minimum 24GB: 100bb boards need up to ~6GB CFR + ~1GB export buffer.
  // The original 4528MB was tuned for 28 parallel workers; we run one at a time.
  return Math.max(available, 24576);
}

async function solveBoardForked(
  boardId: number,
  flopCards: [number, number, number],
  label: string,
  heapMB: number,
  bucketCount: number = BUCKETS,
): Promise<WorkerResult> {
  return new Promise((resolveP, rejectP) => {
    // Use EXACT same execArgv as network-worker.ts spawnWorkers()
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
      bucketCount,
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
        if (p.iteration % 5000 === 0) {
          syncLog(`  [${boardId}] iter ${p.iteration}/${p.total}`);
        }
      } else if (msg.type === 'result') {
        child.disconnect(); // close IPC so child exits and frees its heap
        resolveP(msg as WorkerResult);
      }
    });

    child.on('exit', (code, signal) => {
      if (code !== 0 && code !== null) {
        rejectP(new Error(`Worker for board ${boardId} exited with code=${code} signal=${signal}`));
      }
    });

    child.on('error', rejectP);
  });
}

async function main(): Promise<void> {
  mkdirSync(OUTPUT_DIR, { recursive: true });

  const heapMB = autoHeapMB();
  syncLog('=== Fork Solver starting ===');
  syncLog(`  heap per child: ${heapMB}MB`);
  syncLog(`  solve-worker: ${SOLVE_WORKER_PATH}`);
  syncLog(`  output: ${OUTPUT_DIR}`);

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

  if (missing.length === 0) {
    syncLog('All boards already solved — nothing to do.');
    return;
  }

  syncLog(`Found ${missing.length} missing boards:`);
  for (const m of missing) syncLog(`  Board ${m.boardId}: ${m.label}`);
  syncLog('');

  const totalStart = Date.now();

  for (let i = 0; i < missing.length; i++) {
    const { boardId, cards, label } = missing[i];
    syncLog(`[${i + 1}/${missing.length}] Starting board ${boardId}: ${label}`);

    const t0 = Date.now();
    const buckets = REDUCED_BUCKET_BOARDS.has(boardId) ? 50 : BUCKETS;
    if (buckets !== BUCKETS) {
      syncLog(`  (board ${boardId} using reduced buckets=${buckets} to avoid Map size limit)`);
    }
    try {
      const result = await solveBoardForked(boardId, cards, label, heapMB, buckets);
      const elapsed = (Date.now() - t0) / 1000;
      syncLog(
        `[${i + 1}/${missing.length}] Board ${boardId} DONE: ` +
          `${result.infoSets?.toLocaleString() ?? '?'} info sets | ` +
          `${elapsed.toFixed(1)}s | peak ${result.peakMemoryMB ?? '?'}MB`,
      );
    } catch (err) {
      syncLog(`[${i + 1}/${missing.length}] Board ${boardId} FAILED: ${err}`);
    }
  }

  const totalElapsed = (Date.now() - totalStart) / 1000;
  const hours = (totalElapsed / 3600).toFixed(2);
  syncLog(`=== Fork Solver done: ${missing.length} boards in ${hours}h ===`);
}

main().catch((err) => {
  syncLog(`FATAL: ${err?.stack ?? err}`);
  process.exit(1);
});
