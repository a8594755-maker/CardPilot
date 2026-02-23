#!/usr/bin/env tsx
// CLI entry point for the CFR solver
// Usage: npx tsx src/cli/solve.ts [--flops N] [--iterations N] [--buckets N] [--use-selector] [--all-flops] [--parallel] [--workers N] [--resume]

import { buildTree, countNodes } from '../tree/tree-builder.js';
import {
  V1_TREE_CONFIG,
  getTreeConfig, getSolveDefaults, getConfigLabel, getConfigOutputDir, getStackLabel,
  type TreeConfigName,
} from '../tree/tree-config.js';
import { InfoSetStore } from '../engine/info-set-store.js';
import { solveCFR } from '../engine/cfr-engine.js';
import { loadHUSRPRanges, getWeightedRangeCombos } from '../integration/preflop-ranges.js';
import { cardToIndex, indexToCard } from '../abstraction/card-index.js';
import { selectRepresentativeFlops, printFlopStats } from '../abstraction/flop-selector.js';
import { enumerateIsomorphicFlops } from '../abstraction/suit-isomorphism.js';
import { exportToJSONL, exportMeta } from '../storage/json-export.js';
import { solveParallel } from '../orchestration/solve-orchestrator.js';
import { resolve } from 'node:path';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// Resolve project root: walk up from this file to find the monorepo root (where data/ lives)
const __dirname = fileURLToPath(new URL('.', import.meta.url));
function findProjectRoot(): string {
  // From packages/cfr-solver/src/cli/ → go up 4 levels to monorepo root
  const fromFile = resolve(__dirname, '../../../../');
  if (existsSync(resolve(fromFile, 'data/preflop_charts.json'))) return fromFile;
  // Fallback: try cwd
  if (existsSync(resolve(process.cwd(), 'data/preflop_charts.json'))) return process.cwd();
  // Fallback: try cwd parent (if running from packages/cfr-solver)
  const parent = resolve(process.cwd(), '../..');
  if (existsSync(resolve(parent, 'data/preflop_charts.json'))) return parent;
  return process.cwd();
}
const PROJECT_ROOT = findProjectRoot();

// Parse CLI args
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
const hasFlag = (name: string) => args.includes(`--${name}`);

// Config selection: v1_50bb (default), standard_50bb, standard_100bb, or "standard" (both 50bb+100bb)
const configArg = getStringArg('config', 'v1_50bb');
const isStandardBoth = configArg === 'standard'; // run both 50bb and 100bb

const numFlops = getArg('flops', 1);
const useSelector = hasFlag('use-selector');
const useAllFlops = hasFlag('all-flops');
const useParallel = hasFlag('parallel');
const useResume = hasFlag('resume');
const numWorkers = getArg('workers', 0); // 0 = auto-detect

// Resolve config(s) to run
const configNames: TreeConfigName[] = isStandardBoth
  ? ['standard_50bb', 'standard_100bb']
  : [configArg as TreeConfigName];

// Use config defaults for iterations/buckets, allow CLI override
const firstDefaults = getSolveDefaults(configNames[0]);
const iterations = getArg('iterations', firstDefaults.iterations);
const bucketCount = getArg('buckets', firstDefaults.buckets);

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
  console.log('=== CardPilot CFR Solver V2 ===');
  console.log(`Config: ${configNames.map(getConfigLabel).join(' + ')}`);
  console.log(`Flops: ${useAllFlops ? 'ALL (~1911)' : numFlops} | Iterations: ${iterations} | Buckets: ${bucketCount}`);
  console.log(`Mode: ${useAllFlops ? 'all isomorphic flops' : useSelector ? 'stratified flop selection' : 'preset flops'}`);
  console.log();

  // Load preflop ranges
  console.log('Loading preflop ranges...');
  const chartsPath = resolve(PROJECT_ROOT, 'data/preflop_charts.json');
  const { oopRange, ipRange } = loadHUSRPRanges(chartsPath);
  console.log(`OOP range: ${oopRange.handClasses.size} hand classes, ${oopRange.combos.length} combos`);
  console.log(`IP range: ${ipRange.handClasses.size} hand classes, ${ipRange.combos.length} combos`);
  console.log();

  // Prepare flop list
  interface FlopEntry { cards: [number, number, number]; label: string }
  const flops: FlopEntry[] = [];

  if (useAllFlops) {
    console.log('Enumerating all isomorphic flops...');
    const allIso = enumerateIsomorphicFlops();
    for (const f of allIso) {
      flops.push({
        cards: f.cards,
        label: f.cards.map(indexToCard).join(' '),
      });
    }
    console.log(`  ${flops.length} isomorphic flops loaded`);
    console.log();
  } else if (useSelector) {
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

  // Run for each config (e.g. standard = 50bb + 100bb)
  for (const configName of configNames) {
    const treeConfig = getTreeConfig(configName);
    const outputDir = resolve(PROJECT_ROOT, 'data/cfr', getConfigOutputDir(configName));
    const stackLabel = getStackLabel(configName);

    console.log(`\n${'='.repeat(50)}`);
    console.log(`Config: ${getConfigLabel(configName)}`);
    console.log(`Output: ${outputDir}`);
    console.log(`${'='.repeat(50)}\n`);

    // Build the betting tree
    console.log('Building betting tree...');
    const tree = buildTree(treeConfig);
    const counts = countNodes(tree);
    console.log(`Tree: ${counts.action} action nodes, ${counts.terminal} terminal nodes`);
    console.log();

    // Parallel mode
    if (useParallel && flops.length > 1) {
      await solveParallel({
        flops,
        iterations,
        bucketCount,
        outputDir,
        chartsPath,
        configName,
        stackLabel,
        numWorkers: numWorkers > 0 ? numWorkers : undefined,
        resume: useResume,
      });
      continue;
    }

    // Serial mode
    const totalStart = Date.now();
    let totalInfoSets = 0;
    let totalExportKB = 0;
    let skipped = 0;

    for (let i = 0; i < flops.length; i++) {
      const { cards: flopCards, label } = flops[i];

      // Checkpoint/resume: skip already-solved flops
      if (useResume) {
        const metaPath = resolve(outputDir, `flop_${String(i).padStart(3, '0')}.meta.json`);
        if (existsSync(metaPath)) {
          skipped++;
          continue;
        }
      }

      const deadCards = new Set(flopCards as number[]);
      const oopCombos = getWeightedRangeCombos(oopRange, deadCards);
      const ipCombos = getWeightedRangeCombos(ipRange, deadCards);

      console.log(`[${i + 1}/${flops.length}] ${label}${skipped > 0 ? ` (${skipped} skipped)` : ''}`);

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
        stackLabel,
        configName,
        betSizes: treeConfig.betSizes,
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
        stackLabel,
        configName,
        betSizes: treeConfig.betSizes,
      });

      totalInfoSets += exportResult.infoSets;
      totalExportKB += exportResult.fileSize / 1024;
      console.log(`  ${(elapsed / 1000).toFixed(1)}s | ${exportResult.infoSets} info sets | ${(exportResult.fileSize / 1024).toFixed(0)}KB`);
    }

    const totalElapsed = Date.now() - totalStart;
    const solved = flops.length - skipped;
    console.log();
    console.log(`=== Summary (${getConfigLabel(configName)}) ===`);
    console.log(`Flops solved:    ${solved}${skipped > 0 ? ` (${skipped} skipped/resumed)` : ''}`);
    console.log(`Total time:      ${(totalElapsed / 1000).toFixed(1)}s`);
    console.log(`Total info sets: ${totalInfoSets.toLocaleString()}`);
    console.log(`Total output:    ${(totalExportKB / 1024).toFixed(1)}MB`);
    console.log(`Output dir:      ${outputDir}`);
  }
}

main().catch(err => {
  console.error('Error:', err);
  process.exit(1);
});
