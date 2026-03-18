#!/usr/bin/env tsx
/**
 * Binary search for the iteration count where board 1144 crashes.
 * Tests: 200, 300, 400, 500, 600, 700 iterations.
 */
import { buildTree } from '../tree/tree-builder.js';
import { getTreeConfig } from '../tree/tree-config.js';
import { InfoSetStore } from '../engine/info-set-store.js';
import { solveCFR } from '../engine/cfr-engine.js';
import { loadHUSRPRanges, getWeightedRangeCombos } from '../integration/preflop-ranges.js';
import { enumerateIsomorphicFlops } from '../abstraction/suit-isomorphism.js';
import { indexToCard } from '../abstraction/card-index.js';
import { appendFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const PROJECT_ROOT = resolve(__dirname, '../../../../');
const LOG = resolve(PROJECT_ROOT, 'data/cfr/pipeline_v2_hu_srp_100bb/test-iter-threshold.log');

const syncLog = (msg: string) => {
  const line = `[${new Date().toISOString()}] ${msg}\n`;
  appendFileSync(LOG, line);
  process.stdout.write(line);
};

process.on('uncaughtException', (err) => {
  syncLog(`UNCAUGHT: ${(err as Error)?.stack || err}`);
  process.exit(1);
});

const CHARTS_PATH = resolve(PROJECT_ROOT, 'data/preflop_charts.json');
const RANGE_OPTIONS = {
  ipSpot: 'BTN_unopened_open2.5x',
  ipAction: 'raise' as const,
  oopSpot: 'BB_vs_BTN_facing_open2.5x',
  oopAction: 'call' as const,
};

async function main() {
  syncLog('=== Iter threshold test ===');
  const { oopRange, ipRange } = loadHUSRPRanges(CHARTS_PATH, RANGE_OPTIONS);
  const tree = buildTree(getTreeConfig('pipeline_srp_100bb'));
  const allFlops = enumerateIsomorphicFlops();
  const flop = allFlops[1144];
  const deadCards = new Set<number>(flop.cards);
  const oopCombos = getWeightedRangeCombos(oopRange, deadCards);
  const ipCombos = getWeightedRangeCombos(ipRange, deadCards);
  syncLog(
    `Board 1144: ${flop.cards.map(indexToCard).join(' ')} | OOP=${oopCombos.length} IP=${ipCombos.length}`,
  );

  for (const iters of [200, 300, 400, 500, 600, 700, 800]) {
    syncLog(`--- Testing ${iters} iterations ---`);
    const store = new InfoSetStore();
    const t0 = Date.now();
    try {
      solveCFR({
        root: tree,
        store,
        boardId: 1144,
        flopCards: flop.cards,
        oopRange: oopCombos,
        ipRange: ipCombos,
        iterations: iters,
        bucketCount: 100,
        onProgress: (iter, elapsed) => {
          const heapMB = Math.round(process.memoryUsage().heapUsed / 1024 / 1024);
          syncLog(`  iter=${iter} ${(elapsed / 1000).toFixed(1)}s heap=${heapMB}MB`);
        },
      });
      syncLog(
        `  PASSED ${iters} iters: ${Date.now() - t0}ms heap=${Math.round(process.memoryUsage().heapUsed / 1024 / 1024)}MB`,
      );
    } catch (err) {
      syncLog(`  THREW: ${(err as Error)?.stack || err}`);
    }
  }
  syncLog('=== DONE ===');
}

main().catch((err) => {
  syncLog(`CAUGHT: ${(err as Error)?.stack || err}`);
  process.exit(1);
});
