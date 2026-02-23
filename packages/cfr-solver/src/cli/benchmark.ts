#!/usr/bin/env tsx
// Benchmark a single flop solve to measure time, memory, and output size.
// Usage: npx tsx src/cli/benchmark.ts [--iterations N] [--buckets N]

import { buildTree, countNodes } from '../tree/tree-builder.js';
import { V1_TREE_CONFIG } from '../tree/tree-config.js';
import { InfoSetStore } from '../engine/info-set-store.js';
import { solveCFR } from '../engine/cfr-engine.js';
import { loadHUSRPRanges, getRangeCombos } from '../integration/preflop-ranges.js';
import { cardToIndex } from '../abstraction/card-index.js';
import { resolve } from 'node:path';

const args = process.argv.slice(2);
function getArg(name: string, defaultVal: number): number {
  const idx = args.indexOf(`--${name}`);
  if (idx !== -1 && args[idx + 1]) return parseInt(args[idx + 1], 10);
  return defaultVal;
}

const iterations = getArg('iterations', 50000);
const bucketCount = getArg('buckets', 50);

// Test flop: As 7d 2c (dry A-high rainbow — classic benchmark board)
const FLOP = ['As', '7d', '2c'];

async function main(): Promise<void> {
  console.log('╔══════════════════════════════════════╗');
  console.log('║   CFR Solver V1 — Single Flop Bench  ║');
  console.log('╚══════════════════════════════════════╝');
  console.log();

  // 1. Build tree
  const treeStart = Date.now();
  const tree = buildTree(V1_TREE_CONFIG);
  const counts = countNodes(tree);
  const treeMs = Date.now() - treeStart;
  console.log(`Tree build: ${treeMs}ms`);
  console.log(`  Action nodes: ${counts.action}`);
  console.log(`  Terminal nodes: ${counts.terminal}`);
  console.log();

  // 2. Load ranges
  const rangeStart = Date.now();
  const chartsPath = resolve(process.cwd(), 'data/preflop_charts.json');
  const { oopRange, ipRange } = loadHUSRPRanges(chartsPath);
  const rangeMs = Date.now() - rangeStart;

  const flopCards = FLOP.map(cardToIndex) as [number, number, number];
  const deadCards = new Set(flopCards as number[]);
  const oopCombos = getRangeCombos(oopRange, deadCards);
  const ipCombos = getRangeCombos(ipRange, deadCards);

  console.log(`Range load: ${rangeMs}ms`);
  console.log(`  OOP: ${oopRange.handClasses.size} classes → ${oopCombos.length} combos`);
  console.log(`  IP: ${ipRange.handClasses.size} classes → ${ipCombos.length} combos`);
  console.log(`  Board: ${FLOP.join(' ')} (indices: ${flopCards.join(',')})`);
  console.log();

  // 3. Solve
  console.log(`Solving: ${iterations} iterations, ${bucketCount} buckets`);
  console.log();

  const store = new InfoSetStore();
  const memBefore = process.memoryUsage();
  const solveStart = Date.now();
  let peakHeap = memBefore.heapUsed;

  const checkpoints: Array<{ iter: number; elapsed: number; mem: number }> = [];

  solveCFR({
    root: tree,
    store,
    boardId: 0,
    flopCards,
    oopRange: oopCombos,
    ipRange: ipCombos,
    iterations,
    bucketCount,
    onProgress: (iter, elapsed) => {
      const heap = process.memoryUsage().heapUsed;
      if (heap > peakHeap) peakHeap = heap;
      checkpoints.push({ iter, elapsed, mem: heap });
      const iterPerSec = (iter / elapsed * 1000).toFixed(0);
      const memMB = (heap / 1024 / 1024).toFixed(1);
      process.stdout.write(
        `\r  ${iter}/${iterations} | ${(elapsed/1000).toFixed(1)}s | ${iterPerSec} iter/s | ${memMB}MB heap`
      );
    },
  });

  const solveMs = Date.now() - solveStart;
  const memAfter = process.memoryUsage();
  if (memAfter.heapUsed > peakHeap) peakHeap = memAfter.heapUsed;
  console.log();
  console.log();

  // 4. Results
  const storeMemEstimate = store.estimateMemoryBytes();
  const iterPerSec = (iterations / solveMs * 1000).toFixed(0);

  console.log('═══ BENCHMARK RESULTS ═══');
  console.log();
  console.log(`Board:           ${FLOP.join(' ')}`);
  console.log(`Iterations:      ${iterations.toLocaleString()}`);
  console.log(`Buckets:         ${bucketCount}`);
  console.log();
  console.log(`Total time:      ${(solveMs / 1000).toFixed(2)}s`);
  console.log(`Iter/sec:        ${iterPerSec}`);
  console.log(`Time/iter:       ${(solveMs / iterations).toFixed(3)}ms`);
  console.log();
  console.log(`Info sets:       ${store.size.toLocaleString()}`);
  console.log(`Store memory:    ${(storeMemEstimate / 1024 / 1024).toFixed(1)}MB (estimated)`);
  console.log(`Peak heap:       ${(peakHeap / 1024 / 1024).toFixed(1)}MB`);
  console.log(`Heap delta:      ${((memAfter.heapUsed - memBefore.heapUsed) / 1024 / 1024).toFixed(1)}MB`);
  console.log();

  // Estimate for 200 flops
  const time200Serial = solveMs * 200 / 1000;
  const time200_4workers = time200Serial / 4;
  const mem200 = storeMemEstimate * 200 / 1024 / 1024 / 1024;
  console.log('═══ PROJECTION (200 flops) ═══');
  console.log();
  console.log(`Serial time:     ${(time200Serial / 3600).toFixed(1)}h`);
  console.log(`4-worker time:   ${(time200_4workers / 3600).toFixed(1)}h`);
  console.log(`Total output:    ${(mem200 * 1024).toFixed(0)}MB (raw strategy data)`);
  console.log();

  // Print convergence trajectory
  if (checkpoints.length > 0) {
    console.log('═══ CONVERGENCE TRAJECTORY ═══');
    console.log();
    console.log(`${'Iter'.padStart(8)} | ${'Time'.padStart(8)} | ${'Iter/s'.padStart(8)} | ${'Heap MB'.padStart(8)}`);
    console.log('─'.repeat(42));
    for (const cp of checkpoints) {
      const ips = (cp.iter / cp.elapsed * 1000).toFixed(0);
      console.log(
        `${cp.iter.toString().padStart(8)} | ${(cp.elapsed/1000).toFixed(1).padStart(8)} | ${ips.padStart(8)} | ${(cp.mem/1024/1024).toFixed(1).padStart(8)}`
      );
    }
  }
}

main().catch(err => {
  console.error('Error:', err);
  process.exit(1);
});
