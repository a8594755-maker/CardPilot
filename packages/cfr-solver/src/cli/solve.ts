#!/usr/bin/env tsx
// CLI entry point for the CFR solver
// Usage: npx tsx src/cli/solve.ts [--flops N] [--iterations N] [--buckets N] [--use-selector] [--parallel] [--workers N]

import { buildTree, countNodes } from '../tree/tree-builder.js';
import { V1_TREE_CONFIG } from '../tree/tree-config.js';
import { InfoSetStore } from '../engine/info-set-store.js';
import { solveCFR } from '../engine/cfr-engine.js';
import { loadHUSRPRanges, getRangeCombos } from '../integration/preflop-ranges.js';
import { cardToIndex, indexToCard } from '../abstraction/card-index.js';
import { selectRepresentativeFlops, printFlopStats } from '../abstraction/flop-selector.js';
import { exportToJSONL, exportMeta } from '../storage/json-export.js';
import { solveParallel } from '../orchestration/solve-orchestrator.js';
import { resolve } from 'node:path';

// Parse CLI args
const args = process.argv.slice(2);
function getArg(name: string, defaultVal: number): number {
  const idx = args.indexOf(`--${name}`);
  if (idx !== -1 && args[idx + 1]) return parseInt(args[idx + 1], 10);
  return defaultVal;
}
const hasFlag = (name: string) => args.includes(`--${name}`);

const numFlops = getArg('flops', 1);
const iterations = getArg('iterations', 50000);
const bucketCount = getArg('buckets', 50);
const useSelector = hasFlag('use-selector');
const useParallel = hasFlag('parallel');
const numWorkers = getArg('workers', 0); // 0 = auto-detect

// Hardcoded test flops for quick runs without selector
const QUICK_FLOPS: string[][] = [
  ['As', '7d', '2c'],  // Dry A-high rainbow
  ['Kh', 'Qh', '8d'],  // Two-tone broadway
  ['Ts', '9s', '8s'],  // Monotone connected
  ['Jd', '7c', '3h'],  // Dry J-high rainbow
  ['6h', '5d', '4c'],  // Connected low rainbow
  ['Ah', 'Kd', 'Js'],  // AKJ rainbow
  ['Qc', 'Jc', 'Tc'],  // Monotone broadway
  ['2h', '2d', '7s'],  // Paired low
  ['9h', '6d', '3c'],  // Disconnected rainbow
  ['Kc', '8h', '4d'],  // K-high disconnected
];

async function main(): Promise<void> {
  console.log('=== CardPilot CFR Solver V1 ===');
  console.log(`Flops: ${numFlops} | Iterations: ${iterations} | Buckets: ${bucketCount}`);
  console.log(`Mode: ${useSelector ? 'stratified flop selection' : 'preset flops'}`);
  console.log();

  // Build the betting tree (shared across all boards)
  console.log('Building betting tree...');
  const tree = buildTree(V1_TREE_CONFIG);
  const counts = countNodes(tree);
  console.log(`Tree: ${counts.action} action nodes, ${counts.terminal} terminal nodes`);
  console.log();

  // Load preflop ranges
  console.log('Loading preflop ranges...');
  const chartsPath = resolve(process.cwd(), 'data/preflop_charts.json');
  const { oopRange, ipRange } = loadHUSRPRanges(chartsPath);
  console.log(`OOP range: ${oopRange.handClasses.size} hand classes, ${oopRange.combos.length} combos`);
  console.log(`IP range: ${ipRange.handClasses.size} hand classes, ${ipRange.combos.length} combos`);
  console.log();

  // Prepare flop list
  interface FlopEntry { cards: [number, number, number]; label: string }
  const flops: FlopEntry[] = [];

  if (useSelector) {
    console.log('Selecting representative flops...');
    const selected = selectRepresentativeFlops(numFlops);
    printFlopStats(selected);
    for (const f of selected) {
      flops.push({
        cards: f.cards,
        label: f.cards.map(indexToCard).join(' '),
      });
    }
    console.log();
  } else {
    const count = Math.min(numFlops, QUICK_FLOPS.length);
    for (let i = 0; i < count; i++) {
      const cards = QUICK_FLOPS[i].map(cardToIndex) as [number, number, number];
      flops.push({ cards, label: QUICK_FLOPS[i].join(' ') });
    }
  }

  const outputDir = resolve(process.cwd(), 'data/cfr/v1_hu_srp_50bb');
  const chartsPathResolved = chartsPath;

  // Parallel mode
  if (useParallel && flops.length > 1) {
    await solveParallel({
      flops,
      iterations,
      bucketCount,
      outputDir,
      chartsPath: chartsPathResolved,
      numWorkers: numWorkers > 0 ? numWorkers : undefined,
    });
    return;
  }

  // Serial mode
  const totalStart = Date.now();
  let totalInfoSets = 0;
  let totalExportKB = 0;

  for (let i = 0; i < flops.length; i++) {
    const { cards: flopCards, label } = flops[i];
    const deadCards = new Set(flopCards as number[]);
    const oopCombos = getRangeCombos(oopRange, deadCards);
    const ipCombos = getRangeCombos(ipRange, deadCards);

    console.log(`[${i + 1}/${flops.length}] ${label}`);

    const store = new InfoSetStore();
    const startTime = Date.now();

    solveCFR({
      root: tree,
      store,
      boardId: i,
      flopCards,
      oopRange: oopCombos,
      ipRange: ipCombos,
      iterations,
      bucketCount,
      onProgress: (iter, elapsed) => {
        process.stdout.write(
          `\r  iter ${iter}/${iterations} | ${(elapsed / 1000).toFixed(1)}s | ${store.size} info sets`
        );
      },
    });

    const elapsed = Date.now() - startTime;
    console.log();

    // Export
    const outputPath = resolve(outputDir, `flop_${String(i).padStart(3, '0')}.jsonl`);
    const exportResult = exportToJSONL(store, {
      outputPath,
      boardId: i,
      flopCards,
      iterations,
      bucketCount,
      elapsedMs: elapsed,
    });
    exportMeta({
      outputPath,
      boardId: i,
      flopCards,
      iterations,
      bucketCount,
      elapsedMs: elapsed,
      infoSets: exportResult.infoSets,
      peakMemoryMB: Math.round(process.memoryUsage().heapUsed / 1024 / 1024),
    });

    totalInfoSets += exportResult.infoSets;
    totalExportKB += exportResult.fileSize / 1024;
    console.log(`  ${(elapsed / 1000).toFixed(1)}s | ${exportResult.infoSets} info sets | ${(exportResult.fileSize / 1024).toFixed(0)}KB`);
  }

  const totalElapsed = Date.now() - totalStart;
  console.log();
  console.log('=== Summary ===');
  console.log(`Flops solved:    ${flops.length}`);
  console.log(`Total time:      ${(totalElapsed / 1000).toFixed(1)}s`);
  console.log(`Total info sets: ${totalInfoSets.toLocaleString()}`);
  console.log(`Total output:    ${(totalExportKB / 1024).toFixed(1)}MB`);
  console.log(`Output dir:      ${outputDir}`);
}

main().catch(err => {
  console.error('Error:', err);
  process.exit(1);
});
