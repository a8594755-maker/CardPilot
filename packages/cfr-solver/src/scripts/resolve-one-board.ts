#!/usr/bin/env tsx
/**
 * Re-solve a SINGLE flop board (for QA-flagged boards that failed convergence QA).
 * Writes to a separate output dir so the existing (suspect) artifact is never
 * overwritten until the re-solve is QA-verified. Non-destructive by design.
 *
 * Usage:
 *   node --import tsx packages/cfr-solver/src/scripts/resolve-one-board.ts \
 *     --board 66 --config pipeline_srp_v3_200bb --out data/cfr/_resolve_tmp --heap-mb 24576
 */
import { fork } from 'node:child_process';
import { resolve, dirname } from 'node:path';
import { existsSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { enumerateIsomorphicFlops } from '../abstraction/suit-isomorphism.js';
import { indexToCard } from '../abstraction/card-index.js';
import { getStackLabel } from '../tree/tree-config.js';
import type { FlopTask, WorkerResult, WorkerProgress } from '../orchestration/solve-worker.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SOLVE_WORKER_PATH = resolve(__dirname, '../orchestration/solve-worker.ts');

function arg(name: string, fallback: string): string {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

function findProjectRoot(): string {
  const fromFile = resolve(__dirname, '../../../../');
  if (existsSync(resolve(fromFile, 'data/preflop_charts.json'))) return fromFile;
  return process.cwd();
}

const BOARD_ID = parseInt(arg('--board', '-1'), 10);
const CONFIG_NAME = arg('--config', 'pipeline_srp_v3_200bb') as 'pipeline_srp_v3_200bb';
const HEAP_MB = parseInt(arg('--heap-mb', '24576'), 10);
const PROJECT_ROOT = findProjectRoot();
const OUTPUT_DIR = resolve(PROJECT_ROOT, arg('--out', 'data/cfr/_resolve_tmp'));
const CHARTS_PATH = resolve(PROJECT_ROOT, 'data/preflop_charts.json');
const ITERATIONS = 200000;
const BUCKETS = 50;

if (BOARD_ID < 0) {
  console.error(
    'usage: resolve-one-board.ts --board <id> [--config ...] [--out ...] [--heap-mb N]',
  );
  process.exit(1);
}

mkdirSync(OUTPUT_DIR, { recursive: true });

const flops = enumerateIsomorphicFlops();
const cards = flops[BOARD_ID].cards as [number, number, number];
const label = cards.map(indexToCard).join(' ');
const stackLabel = getStackLabel(CONFIG_NAME);

console.log(`[resolve] board ${BOARD_ID} = ${label} | config ${CONFIG_NAME} | out ${OUTPUT_DIR}`);

const child = fork(SOLVE_WORKER_PATH, [], {
  execArgv: ['--import', 'tsx', `--max-old-space-size=${HEAP_MB}`],
  stdio: ['inherit', 'inherit', 'inherit', 'ipc'],
});

const task: FlopTask = {
  type: 'solve',
  boardId: BOARD_ID,
  flopCards: cards,
  label,
  iterations: ITERATIONS,
  bucketCount: BUCKETS,
  outputDir: OUTPUT_DIR,
  chartsPath: CHARTS_PATH,
  configName: CONFIG_NAME,
  stackLabel,
};

const t0 = Date.now();
child.on('spawn', () => child.send(task));
child.on('message', (msg: WorkerResult | WorkerProgress) => {
  if (msg.type === 'progress') {
    const p = msg as WorkerProgress;
    if (p.iteration % 25000 === 0 && p.iteration > 0) {
      console.log(`[resolve] board ${BOARD_ID} iter ${p.iteration}/${p.total}`);
    }
  } else if (msg.type === 'result') {
    const r = msg as WorkerResult;
    const min = ((Date.now() - t0) / 60000).toFixed(1);
    console.log(
      `[resolve] board ${BOARD_ID} DONE: ${r.infoSets.toLocaleString()} info sets | ${min}min | peak ${r.peakMemoryMB}MB`,
    );
    child.disconnect();
    process.exit(0);
  }
});
child.on('error', (e) => {
  console.error(e);
  process.exit(1);
});
child.on('exit', (code, signal) => {
  if (code !== 0 && code !== null) {
    console.error(`worker exited code=${code} signal=${signal}`);
    process.exit(1);
  }
});
