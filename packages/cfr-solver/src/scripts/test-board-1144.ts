#!/usr/bin/env tsx
/**
 * Minimal diagnostic: test if board 1144 (5c 8c Jd) can be solved at all.
 * Tests with progressive iteration counts to find where the crash occurs.
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
const LOG = resolve(PROJECT_ROOT, 'data/cfr/pipeline_v2_hu_srp_100bb/test-board-1144.log');

const syncLog = (msg: string) => {
  const line = `[${new Date().toISOString()}] ${msg}\n`;
  appendFileSync(LOG, line);
  process.stdout.write(line);
};

process.on('uncaughtException', (err) => {
  syncLog(`UNCAUGHT: ${(err as Error)?.stack || err}`);
  process.exit(1);
});
process.on('unhandledRejection', (reason) => {
  syncLog(`REJECTION: ${reason}`);
  process.exit(1);
});

const CHARTS_PATH = resolve(PROJECT_ROOT, 'data/preflop_charts.json');
const CONFIG_NAME = 'pipeline_srp_100bb' as const;
const BUCKETS = 100;

const RANGE_OPTIONS = {
  ipSpot: 'BTN_unopened_open2.5x',
  ipAction: 'raise' as const,
  oopSpot: 'BB_vs_BTN_facing_open2.5x',
  oopAction: 'call' as const,
};

async function main() {
  syncLog('=== Test Board 1144 Starting ===');
  syncLog(
    `Heap: ${Math.round(process.memoryUsage().heapTotal / 1024 / 1024)}MB, limit approx ${process.env.NODE_OPTIONS ?? '(flags)'}`,
  );

  syncLog('Loading ranges...');
  const { oopRange, ipRange } = loadHUSRPRanges(CHARTS_PATH, RANGE_OPTIONS);
  syncLog(`Ranges loaded: OOP=${oopRange.combos.length} IP=${ipRange.combos.length}`);

  syncLog('Building tree...');
  const treeConfig = getTreeConfig(CONFIG_NAME);
  const tree = buildTree(treeConfig);
  syncLog('Tree built.');

  // Find board 1144
  const allFlops = enumerateIsomorphicFlops();
  const flop1144 = allFlops[1144];
  const label = flop1144.cards.map(indexToCard).join(' ');
  syncLog(`Board 1144: ${label}`);

  const deadCards = new Set<number>(flop1144.cards);
  syncLog('Computing dead cards...');
  const oopCombos = getWeightedRangeCombos(oopRange, deadCards);
  const ipCombos = getWeightedRangeCombos(ipRange, deadCards);
  syncLog(`Live combos: OOP=${oopCombos.length} IP=${ipCombos.length}`);

  // Test with progressive iteration counts
  const iterCounts = [1, 10, 100, 1000, 5000, 10000, 50000];

  for (const iters of iterCounts) {
    syncLog(`--- Testing ${iters} iterations ---`);
    const store = new InfoSetStore();
    const t0 = Date.now();

    try {
      solveCFR({
        root: tree,
        store,
        boardId: 1144,
        flopCards: flop1144.cards,
        oopRange: oopCombos,
        ipRange: ipCombos,
        iterations: iters,
        bucketCount: BUCKETS,
        onProgress: (iter, elapsed) => {
          const heapMB = Math.round(process.memoryUsage().heapUsed / 1024 / 1024);
          syncLog(
            `  iter=${iter} elapsed=${(elapsed / 1000).toFixed(1)}s heap=${heapMB}MB infoSets=${store.size}`,
          );
          if (typeof (global as any).gc === 'function') (global as any).gc();
        },
      });
      const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
      const heapMB = Math.round(process.memoryUsage().heapUsed / 1024 / 1024);
      syncLog(`  PASSED ${iters} iters in ${elapsed}s | heap=${heapMB}MB | infoSets=${store.size}`);
    } catch (err) {
      syncLog(`  THREW at ${iters} iters: ${(err as Error)?.stack || err}`);
      throw err;
    }
  }

  syncLog('=== ALL TESTS PASSED ===');
}

main().catch((err) => {
  syncLog(`main() CAUGHT: ${(err as Error)?.stack || err}`);
  process.exit(1);
});
