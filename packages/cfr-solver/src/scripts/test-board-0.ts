#!/usr/bin/env tsx
/**
 * Test board 0 (a known-good board) to compare timing/crash behavior with board 1144.
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
const LOG = resolve(PROJECT_ROOT, 'data/cfr/pipeline_v2_hu_srp_100bb/test-board-0.log');

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
const CONFIG_NAME = 'pipeline_srp_100bb' as const;
const BUCKETS = 100;
const RANGE_OPTIONS = {
  ipSpot: 'BTN_unopened_open2.5x',
  ipAction: 'raise' as const,
  oopSpot: 'BB_vs_BTN_facing_open2.5x',
  oopAction: 'call' as const,
};

async function main() {
  syncLog('=== Test Board 0 Starting ===');
  const { oopRange, ipRange } = loadHUSRPRanges(CHARTS_PATH, RANGE_OPTIONS);
  const treeConfig = getTreeConfig(CONFIG_NAME);
  const tree = buildTree(treeConfig);

  const allFlops = enumerateIsomorphicFlops();
  // Test board 0 AND board 500 (mid-range, known-good)
  for (const boardId of [0, 500, 1000]) {
    const flop = allFlops[boardId];
    const label = flop.cards.map(indexToCard).join(' ');
    syncLog(`--- Board ${boardId}: ${label} ---`);

    const deadCards = new Set<number>(flop.cards);
    const oopCombos = getWeightedRangeCombos(oopRange, deadCards);
    const ipCombos = getWeightedRangeCombos(ipRange, deadCards);

    const store = new InfoSetStore();
    const t0 = Date.now();
    try {
      solveCFR({
        root: tree,
        store,
        boardId,
        flopCards: flop.cards,
        oopRange: oopCombos,
        ipRange: ipCombos,
        iterations: 1000,
        bucketCount: BUCKETS,
        onProgress: (iter, elapsed) => {
          const heapMB = Math.round(process.memoryUsage().heapUsed / 1024 / 1024);
          syncLog(
            `  iter=${iter} ${(elapsed / 1000).toFixed(1)}s heap=${heapMB}MB infoSets=${store.size}`,
          );
        },
      });
      const ms = Date.now() - t0;
      syncLog(`  PASSED board ${boardId}: ${ms}ms, ${store.size} infoSets`);
    } catch (err) {
      syncLog(`  THREW board ${boardId}: ${(err as Error)?.stack || err}`);
    }
  }
  syncLog('=== DONE ===');
}

main().catch((err) => {
  syncLog(`main CAUGHT: ${(err as Error)?.stack || err}`);
  process.exit(1);
});
