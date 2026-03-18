#!/usr/bin/env tsx
/**
 * Standalone solver for the 13 remaining pipeline_srp_100bb boards.
 * Bypasses the coordinator/worker pipeline entirely — runs each board
 * serially in-process with a large heap.
 *
 * Run via:
 *   NODE_OPTIONS=--max-old-space-size=24576 npx tsx \
 *     packages/cfr-solver/src/scripts/solve-remaining-100bb.ts
 *
 * Or use the PS1 launcher: scripts/start-solve-remaining-100bb.ps1
 */

import { buildTree } from '../tree/tree-builder.js';
import { getTreeConfig, getConfigOutputDir } from '../tree/tree-config.js';
import { InfoSetStore } from '../engine/info-set-store.js';
import { solveCFR } from '../engine/cfr-engine.js';
import { loadHUSRPRanges, getWeightedRangeCombos } from '../integration/preflop-ranges.js';
import { exportToJSONL, exportMeta } from '../storage/json-export.js';
import { enumerateIsomorphicFlops } from '../abstraction/suit-isomorphism.js';
import { indexToCard } from '../abstraction/card-index.js';
import { existsSync, mkdirSync, appendFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));

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

const PROJECT_ROOT = findProjectRoot();
const OUTPUT_DIR = resolve(PROJECT_ROOT, 'data/cfr', getConfigOutputDir(CONFIG_NAME));
const CHARTS_PATH = resolve(PROJECT_ROOT, 'data/preflop_charts.json');
const COMPLETED_LOG = resolve(OUTPUT_DIR, 'completed.jsonl');
const ERR_LOG = resolve(OUTPUT_DIR, 'standalone-solver-errors.log');

function syncLog(msg: string): void {
  appendFileSync(ERR_LOG, `[${new Date().toISOString()}] ${msg}\n`);
}

// Same range options as solve-worker.ts getRangeOptions('pipeline_srp_100bb')
const RANGE_OPTIONS = {
  ipSpot: 'BTN_unopened_open2.5x',
  ipAction: 'raise' as const,
  oopSpot: 'BB_vs_BTN_facing_open2.5x',
  oopAction: 'call' as const,
};

// Synchronous error handlers — survive process.exit()
process.on('uncaughtException', (err) => {
  const msg = `UNCAUGHT EXCEPTION: ${(err as Error)?.stack || err}`;
  syncLog(msg);
  process.stderr.write(`[FATAL] ${msg}\n`);
  process.exit(1);
});
process.on('unhandledRejection', (reason) => {
  const msg = `UNHANDLED REJECTION: ${reason}`;
  syncLog(msg);
  process.stderr.write(`[FATAL] ${msg}\n`);
  process.exit(1);
});

async function main(): Promise<void> {
  syncLog('=== Standalone Solver starting ===');

  console.log('╔═══════════════════════════════════════════════╗');
  console.log('║  Standalone Solver — pipeline_srp_100bb       ║');
  console.log('╚═══════════════════════════════════════════════╝');
  console.log();
  console.log(`Output dir:   ${OUTPUT_DIR}`);
  console.log(`Iterations:   ${ITERATIONS}`);
  console.log(`Buckets:      ${BUCKETS}`);
  console.log(
    `Heap:         ${Math.round(process.memoryUsage().heapTotal / 1024 / 1024)}MB current`,
  );
  console.log(`NODE_OPTIONS: ${process.env.NODE_OPTIONS ?? '(not set)'}`);
  console.log();

  mkdirSync(OUTPUT_DIR, { recursive: true });

  // Load preflop ranges (same options as pipeline worker)
  console.log('Loading preflop ranges...');
  const { oopRange, ipRange } = loadHUSRPRanges(CHARTS_PATH, RANGE_OPTIONS);
  console.log(
    `  OOP range: ${oopRange.handClasses.size} hand classes, ${oopRange.combos.length} combos`,
  );
  console.log(
    `  IP range:  ${ipRange.handClasses.size} hand classes, ${ipRange.combos.length} combos`,
  );
  console.log();

  // Build tree (same config as pipeline)
  console.log('Building betting tree...');
  const treeConfig = getTreeConfig(CONFIG_NAME);
  const tree = buildTree(treeConfig);
  console.log('Tree built.');
  console.log();

  // Enumerate all isomorphic flops
  const allFlops = enumerateIsomorphicFlops();

  // Find missing boards
  const missing: Array<{ cards: [number, number, number]; boardId: number; label: string }> = [];
  for (let i = 0; i < allFlops.length; i++) {
    const metaPath = resolve(OUTPUT_DIR, `flop_${String(i).padStart(3, '0')}.meta.json`);
    if (!existsSync(metaPath)) {
      missing.push({
        cards: allFlops[i].cards,
        boardId: i,
        label: allFlops[i].cards.map(indexToCard).join(' '),
      });
    }
  }

  if (missing.length === 0) {
    console.log('All boards already solved — nothing to do.');
    syncLog('All boards already solved — nothing to do.');
    return;
  }

  console.log(`Found ${missing.length} missing boards:`);
  for (const m of missing) {
    console.log(`  Board ${m.boardId}: ${m.label}`);
  }
  console.log();
  syncLog(`Found ${missing.length} missing boards: ${missing.map((m) => m.boardId).join(', ')}`);

  const totalStart = Date.now();

  for (let idx = 0; idx < missing.length; idx++) {
    const { cards, boardId, label } = missing[idx];

    syncLog(`[${idx + 1}/${missing.length}] Starting board ${boardId}: ${label}`);
    console.log(`[${idx + 1}/${missing.length}] Board ${boardId}: ${label}`);
    console.log(`  Started: ${new Date().toISOString()}`);

    const deadCards = new Set<number>(cards);
    const oopCombos = getWeightedRangeCombos(oopRange, deadCards);
    const ipCombos = getWeightedRangeCombos(ipRange, deadCards);

    const store = new InfoSetStore();
    const startTime = Date.now();

    try {
      solveCFR({
        root: tree,
        store,
        boardId,
        flopCards: cards,
        oopRange: oopCombos,
        ipRange: ipCombos,
        iterations: ITERATIONS,
        bucketCount: BUCKETS,
        onProgress: (iter, elapsed) => {
          const mem = process.memoryUsage();
          const heapMB = Math.round(mem.heapUsed / 1024 / 1024);
          const rssMB = Math.round(mem.rss / 1024 / 1024);
          // Log every callback (fires every 50 iters from cfr-engine)
          syncLog(
            `Board ${boardId}: iter ${iter}/${ITERATIONS} | ${(elapsed / 1000).toFixed(1)}s | ${store.size} info sets | heap: ${heapMB}MB rss: ${rssMB}MB`,
          );
          process.stdout.write(
            `\r  iter ${iter.toLocaleString()}/${ITERATIONS.toLocaleString()} | ` +
              `${(elapsed / 1000).toFixed(0)}s | ${store.size.toLocaleString()} info sets | heap: ${heapMB}MB rss: ${rssMB}MB`,
          );
        },
      });
    } catch (err) {
      const msg = `Board ${boardId} solveCFR THREW: ${(err as Error)?.stack || err}`;
      syncLog(msg);
      console.error('\n[ERROR]', msg);
      throw err;
    }

    const elapsed = Date.now() - startTime;
    const heapMB = Math.round(process.memoryUsage().heapUsed / 1024 / 1024);
    syncLog(
      `Board ${boardId} SOLVED: ${(elapsed / 1000).toFixed(1)}s | ${store.size} info sets | heap: ${heapMB}MB`,
    );
    console.log();
    console.log(
      `  Solved:  ${(elapsed / 1000).toFixed(1)}s | ${store.size.toLocaleString()} info sets | heap: ${heapMB}MB`,
    );

    // Export JSONL + meta (same format as pipeline worker)
    const outputPath = resolve(OUTPUT_DIR, `flop_${String(boardId).padStart(3, '0')}.jsonl`);
    const exportResult = exportToJSONL(store, {
      outputPath,
      boardId,
      flopCards: cards,
      iterations: ITERATIONS,
      bucketCount: BUCKETS,
      elapsedMs: elapsed,
      stackLabel: STACK_LABEL,
      configName: CONFIG_NAME,
      betSizes: treeConfig.betSizes,
    });
    exportMeta({
      outputPath,
      boardId,
      flopCards: cards,
      iterations: ITERATIONS,
      bucketCount: BUCKETS,
      elapsedMs: elapsed,
      infoSets: exportResult.infoSets,
      peakMemoryMB: heapMB,
      stackLabel: STACK_LABEL,
      configName: CONFIG_NAME,
      betSizes: treeConfig.betSizes,
    });

    // Append to completed.jsonl (so coordinator resume recognizes this board)
    const completedEntry = JSON.stringify({
      jobId: `${CONFIG_NAME}:${boardId}`,
      boardId,
      configName: CONFIG_NAME,
      elapsedMs: elapsed,
      infoSets: exportResult.infoSets,
      fileSize: exportResult.fileSize,
      completedAt: Date.now(),
      worker: 'standalone-solver',
    });
    appendFileSync(COMPLETED_LOG, completedEntry + '\n');

    syncLog(`Board ${boardId} EXPORTED: ${(exportResult.fileSize / 1024).toFixed(0)}KB`);
    console.log(
      `  Exported: ${(exportResult.fileSize / 1024).toFixed(0)}KB | ` +
        `${exportResult.infoSets.toLocaleString()} info sets`,
    );
    console.log();
  }

  const totalElapsed = (Date.now() - totalStart) / 1000;
  syncLog(`=== ALL DONE: ${missing.length} boards in ${(totalElapsed / 3600).toFixed(2)}h ===`);
  console.log('╔═══════════════════════════════════════════════╗');
  console.log(`║  All ${missing.length} boards solved!                         ║`);
  console.log('╚═══════════════════════════════════════════════╝');
  console.log(`Total time: ${(totalElapsed / 3600).toFixed(2)}h`);
}

main().catch((err) => {
  const msg = `main() CAUGHT: ${(err as Error)?.stack || err}`;
  syncLog(msg);
  process.stderr.write(`[FATAL] ${msg}\n`);
  process.exit(1);
});
