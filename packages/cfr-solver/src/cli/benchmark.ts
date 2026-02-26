#!/usr/bin/env tsx
// Benchmark a single flop solve to measure time, memory, and output size.
// Usage: npx tsx src/cli/benchmark.ts [--config pipeline_srp] [--iterations N] [--buckets N]

import { buildTree, countNodes } from '../tree/tree-builder.js';
import {
  getTreeConfig, getSolveDefaults, getConfigLabel,
  type TreeConfigName,
} from '../tree/tree-config.js';
import { InfoSetStore } from '../engine/info-set-store.js';
import { solveCFR } from '../engine/cfr-engine.js';
import { loadHUSRPRanges, getWeightedRangeCombos } from '../integration/preflop-ranges.js';
import { cardToIndex } from '../abstraction/card-index.js';
import { resolve } from 'node:path';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
function findProjectRoot(): string {
  const fromFile = resolve(__dirname, '../../../../');
  if (existsSync(resolve(fromFile, 'data/preflop_charts.json'))) return fromFile;
  if (existsSync(resolve(process.cwd(), 'data/preflop_charts.json'))) return process.cwd();
  const parent = resolve(process.cwd(), '../..');
  if (existsSync(resolve(parent, 'data/preflop_charts.json'))) return parent;
  return process.cwd();
}
const PROJECT_ROOT = findProjectRoot();

const args = process.argv.slice(2);
function getArg(name: string, defaultVal: number): number {
  const idx = args.indexOf(`--${name}`);
  if (idx !== -1 && args[idx + 1]) return parseInt(args[idx + 1], 10);
  return defaultVal;
}
function getStringArg(name: string, defaultVal: string): string {
  const idx = args.indexOf(`--${name}`);
  if (idx !== -1 && args[idx + 1]) return args[idx + 1];
  return defaultVal;
}

const configName = getStringArg('config', 'v1_50bb') as TreeConfigName;
const defaults = getSolveDefaults(configName);
const iterations = getArg('iterations', defaults.iterations);
const bucketCount = getArg('buckets', defaults.buckets);

// Test flop: As 7d 2c (dry A-high rainbow — classic benchmark board)
const FLOP = ['As', '7d', '2c'];

async function main(): Promise<void> {
  console.log('╔══════════════════════════════════════════════╗');
  console.log('║   CFR Solver — Single Flop Benchmark         ║');
  console.log('╚══════════════════════════════════════════════╝');
  console.log();
  console.log(`Config:     ${getConfigLabel(configName)}`);
  console.log(`Iterations: ${iterations.toLocaleString()}`);
  console.log(`Buckets:    ${bucketCount}`);
  console.log();

  // 1. Build tree
  const treeConfig = getTreeConfig(configName);
  const treeStart = Date.now();
  const tree = buildTree(treeConfig);
  const counts = countNodes(tree);
  const treeMs = Date.now() - treeStart;
  console.log(`Tree build: ${treeMs}ms`);
  console.log(`  Action nodes:   ${counts.action}`);
  console.log(`  Terminal nodes:  ${counts.terminal}`);
  console.log(`  Raise cap:       ${treeConfig.raiseCapPerStreet}`);
  console.log(`  Starting pot:    ${treeConfig.startingPot}bb`);
  console.log(`  Effective stack: ${treeConfig.effectiveStack}bb`);
  console.log(`  Bet sizes:`);
  console.log(`    Flop:  [${treeConfig.betSizes.flop.join(', ')}]`);
  console.log(`    Turn:  [${treeConfig.betSizes.turn.join(', ')}]`);
  console.log(`    River: [${treeConfig.betSizes.river.join(', ')}]`);
  console.log();

  // 2. Load ranges
  const rangeStart = Date.now();
  const chartsPath = resolve(PROJECT_ROOT, 'data/preflop_charts.json');
  const { oopRange, ipRange } = loadHUSRPRanges(chartsPath);
  const rangeMs = Date.now() - rangeStart;

  const flopCards = FLOP.map(cardToIndex) as [number, number, number];
  const deadCards = new Set(flopCards as number[]);
  const oopCombos = getWeightedRangeCombos(oopRange, deadCards);
  const ipCombos = getWeightedRangeCombos(ipRange, deadCards);

  console.log(`Range load: ${rangeMs}ms`);
  console.log(`  OOP: ${oopRange.handClasses.size} classes → ${oopCombos.length} combos`);
  console.log(`  IP: ${ipRange.handClasses.size} classes → ${ipCombos.length} combos`);
  console.log(`  Board: ${FLOP.join(' ')} (indices: ${flopCards.join(',')})`);
  console.log();

  // 3. Solve
  console.log(`Solving: ${iterations.toLocaleString()} iterations, ${bucketCount} buckets`);
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
  console.log(`Config:          ${getConfigLabel(configName)}`);
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

  // 5. Projections for all 1,755 isomorphic flops
  const TOTAL_FLOPS = 1755;
  const timeAllSerial = solveMs * TOTAL_FLOPS / 1000;
  const memPerFlop = storeMemEstimate / 1024 / 1024;

  console.log(`═══ PROJECTION (${TOTAL_FLOPS} isomorphic flops) ═══`);
  console.log();
  console.log(`Per flop:        ${(solveMs / 1000).toFixed(1)}s | ${memPerFlop.toFixed(1)}MB store | ${(peakHeap / 1024 / 1024).toFixed(0)}MB peak heap`);
  console.log();

  // Machine A: 128GB RAM
  const machineA_reserve = 4096; // 4GB for OS
  const machineA_available = 128 * 1024 - machineA_reserve;
  const machineA_workers = Math.min(
    Math.floor(machineA_available / (peakHeap / 1024 / 1024)),
    24 // reasonable CPU core limit for i9
  );
  const machineA_hours = timeAllSerial / 3600 / machineA_workers;

  // Machine B/C: 32GB RAM
  const machineBC_reserve = 4096;
  const machineBC_available = 32 * 1024 - machineBC_reserve;
  const machineBC_workers = Math.min(
    Math.floor(machineBC_available / (peakHeap / 1024 / 1024)),
    16
  );
  const machineBC_hours = timeAllSerial / 3600 / machineBC_workers;

  // Combined
  const totalWorkers = machineA_workers + machineBC_workers * 2;
  const combined_hours = timeAllSerial / 3600 / totalWorkers;

  console.log('Machine A (i9 + 128GB):');
  console.log(`  Workers: ${machineA_workers} | Solo time: ${machineA_hours.toFixed(1)}h`);
  console.log();
  console.log('Machine B/C (32GB each):');
  console.log(`  Workers: ${machineBC_workers} each | Solo time: ${machineBC_hours.toFixed(1)}h each`);
  console.log();
  console.log('All 3 machines combined:');
  console.log(`  Workers: ${totalWorkers} total | Time: ${combined_hours.toFixed(1)}h`);
  console.log(`  Flops/hour: ~${Math.round(TOTAL_FLOPS / (timeAllSerial / 3600 / totalWorkers) * (timeAllSerial / 3600 / totalWorkers) / (timeAllSerial / 3600) * totalWorkers)}`);
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
