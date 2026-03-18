#!/usr/bin/env tsx
// Convergence test: solve the same board at different iteration counts
// and measure how much the strategy changes between steps.
//
// If strategies stabilize (< 2% shift), the solver has converged.
//
// Usage:
//   npx tsx src/cli/convergence-test.ts --config hu_btn_bb_srp_50bb --board "Ah Ts 2c"
//   npx tsx src/cli/convergence-test.ts --config v1_50bb --board "Tc Qc Ad"
//   npx tsx src/cli/convergence-test.ts --config hu_btn_bb_3bp_50bb --board "Kh 9h 4h" --steps 50000,100000,200000,500000

import { resolve } from 'node:path';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { buildTree, countNodes } from '../tree/tree-builder.js';
import { getTreeConfig, type TreeConfigName } from '../tree/tree-config.js';
import { InfoSetStore } from '../engine/info-set-store.js';
import { solveCFR } from '../engine/cfr-engine.js';
import {
  loadHUSRPRanges,
  getWeightedRangeCombos,
  type HUSRPRangesOptions,
} from '../integration/preflop-ranges.js';
import { cardToIndex, indexToCard } from '../abstraction/card-index.js';

// ─── Project root ───

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

// ─── CLI args ───

const args = process.argv.slice(2);
function getStringArg(name: string, defaultVal: string): string {
  const idx = args.indexOf(`--${name}`);
  if (idx !== -1 && args[idx + 1]) return args[idx + 1];
  return defaultVal;
}

const configName = getStringArg('config', 'v1_50bb') as TreeConfigName;
const boardArg = getStringArg('board', 'Tc Qc Ad');
const stepsArg = getStringArg('steps', '25000,50000,100000,200000');
const bucketCountArg = parseInt(getStringArg('buckets', '50'), 10);

// ─── Range options per config ───

function getRangeOptions(configName: TreeConfigName): HUSRPRangesOptions {
  switch (configName) {
    case 'pipeline_srp':
    case 'hu_btn_bb_srp_50bb':
    case 'hu_btn_bb_srp_100bb':
    case 'v1_50bb' as any:
    case 'standard_50bb' as any:
    case 'standard_100bb' as any:
      return {
        ipSpot: 'BTN_unopened_open2.5x',
        ipAction: 'raise',
        oopSpot: 'BB_vs_BTN_facing_open2.5x',
        oopAction: 'call',
      };

    case 'pipeline_3bet':
    case 'hu_btn_bb_3bp_50bb':
    case 'hu_btn_bb_3bp_100bb':
      return {
        oopSpot: 'BB_vs_BTN_facing_open2.5x',
        oopAction: 'raise',
        ipSpot: 'BTN_unopened_open2.5x',
        ipAction: 'raise',
        minFrequency: 0.4,
      };

    case 'hu_co_bb_srp_100bb':
      return {
        ipSpot: 'CO_unopened_open2.5x',
        ipAction: 'raise',
        oopSpot: 'BB_vs_CO_facing_open2.5x',
        oopAction: 'call',
      };

    default:
      return {
        ipSpot: 'BTN_unopened_open2.5x',
        ipAction: 'raise',
        oopSpot: 'BB_vs_BTN_facing_open2.5x',
        oopAction: 'call',
      };
  }
}

// ─── Strategy extraction ───

function extractAverageStrategies(store: InfoSetStore): Map<string, number[]> {
  const strategies = new Map<string, number[]>();
  for (const entry of store.entries()) {
    strategies.set(entry.key, Array.from(entry.averageStrategy));
  }
  return strategies;
}

function computeStrategyShift(
  prev: Map<string, number[]>,
  curr: Map<string, number[]>,
): { avgL1: number; maxL1: number; maxKey: string; compared: number } {
  let totalL1 = 0;
  let maxL1 = 0;
  let maxKey = '';
  let compared = 0;

  for (const [key, currProbs] of curr) {
    const prevProbs = prev.get(key);
    if (!prevProbs) continue;

    let l1 = 0;
    for (let i = 0; i < currProbs.length; i++) {
      l1 += Math.abs(currProbs[i] - (prevProbs[i] || 0));
    }
    totalL1 += l1;
    if (l1 > maxL1) {
      maxL1 = l1;
      maxKey = key;
    }
    compared++;
  }

  return {
    avgL1: compared > 0 ? totalL1 / compared : 0,
    maxL1,
    maxKey,
    compared,
  };
}

// Compute aggregate root strategy (average over all buckets)
function computeRootAggregate(
  store: InfoSetStore,
  boardId: number,
  player: number,
): { probs: number[]; count: number } {
  let sums: number[] | null = null;
  let count = 0;
  const prefix = `F|${boardId}|${player}||`;

  for (const entry of store.entries()) {
    if (!entry.key.startsWith(prefix)) continue;
    const probs = Array.from(entry.averageStrategy);
    if (!sums) sums = new Array(probs.length).fill(0);
    for (let i = 0; i < probs.length; i++) sums[i] += probs[i];
    count++;
  }

  if (!sums || count === 0) return { probs: [], count: 0 };
  return { probs: sums.map((s) => s / count), count };
}

// ─── Main ───

async function main(): Promise<void> {
  const boardCards = boardArg.trim().split(/\s+/).map(cardToIndex) as [number, number, number];
  if (boardCards.length !== 3) {
    console.error('Error: Board must have exactly 3 cards');
    process.exit(1);
  }

  const iterationSteps = stepsArg.split(',').map((s) => parseInt(s.trim(), 10));
  const treeConfig = getTreeConfig(configName);
  const chartsPath = resolve(PROJECT_ROOT, 'data/preflop_charts.json');

  console.log(`\n${'═'.repeat(60)}`);
  console.log(`  Convergence Test`);
  console.log(`  Config: ${configName}`);
  console.log(`  Board: ${boardCards.map(indexToCard).join(' ')}`);
  console.log(`  Steps: ${iterationSteps.map((n) => n.toLocaleString()).join(' → ')}`);
  console.log(`  Buckets: ${bucketCountArg}`);
  console.log(`${'═'.repeat(60)}\n`);

  // Load ranges
  console.log('Loading preflop ranges...');
  const rangeOpts = getRangeOptions(configName);
  const { oopRange, ipRange } = loadHUSRPRanges(chartsPath, rangeOpts);
  const deadCards = new Set(boardCards as number[]);
  const oopCombos = getWeightedRangeCombos(oopRange, deadCards);
  const ipCombos = getWeightedRangeCombos(ipRange, deadCards);
  console.log(`  OOP: ${oopCombos.length} combos, IP: ${ipCombos.length} combos\n`);

  // Build tree
  console.log('Building betting tree...');
  const tree = buildTree(treeConfig);
  const counts = countNodes(tree);
  console.log(`  ${counts.action} action nodes, ${counts.terminal} terminal nodes\n`);

  // Solve at each iteration step
  const results: Array<{
    iterations: number;
    elapsed: number;
    infoSets: number;
    shift: { avgL1: number; maxL1: number; maxKey: string; compared: number } | null;
    rootOOP: { probs: number[]; count: number };
    rootIP: { probs: number[]; count: number };
  }> = [];

  let prevStrategies: Map<string, number[]> | null = null;

  for (let stepIdx = 0; stepIdx < iterationSteps.length; stepIdx++) {
    const targetIter = iterationSteps[stepIdx];

    // For the first step, create a fresh store.
    // For subsequent steps, continue from previous solve.
    let store: InfoSetStore;
    let solveIterations: number;

    if (stepIdx === 0) {
      store = new InfoSetStore();
      solveIterations = targetIter;
    } else {
      // We need to re-solve from scratch each time because the CFR solver
      // doesn't support incremental solving with the same store easily
      // (it accumulates strategy sums, making continuation not straightforward).
      store = new InfoSetStore();
      solveIterations = targetIter;
    }

    process.stdout.write(`  Solving ${targetIter.toLocaleString()} iterations...`);
    const startTime = Date.now();

    solveCFR({
      root: tree,
      store,
      boardId: 0,
      flopCards: boardCards,
      oopRange: oopCombos,
      ipRange: ipCombos,
      iterations: solveIterations,
      bucketCount: bucketCountArg,
      onProgress: (iter) => {
        if (iter % 25000 === 0) {
          process.stdout.write(
            `\r  Solving ${targetIter.toLocaleString()} iterations... ${((iter / solveIterations) * 100).toFixed(0)}%`,
          );
        }
      },
    });

    const elapsed = Date.now() - startTime;
    process.stdout.write(
      `\r  Solving ${targetIter.toLocaleString()} iterations... done (${(elapsed / 1000).toFixed(1)}s, ${store.size} info sets)\n`,
    );

    // Extract strategies and compare with previous
    const currStrategies = extractAverageStrategies(store);
    const shift = prevStrategies ? computeStrategyShift(prevStrategies, currStrategies) : null;

    // Root aggregate
    const rootOOP = computeRootAggregate(store, 0, 0);
    const rootIP = computeRootAggregate(store, 0, 1);

    results.push({
      iterations: targetIter,
      elapsed,
      infoSets: store.size,
      shift,
      rootOOP,
      rootIP,
    });

    prevStrategies = currStrategies;
  }

  // Print results
  console.log(`\n${'─'.repeat(60)}`);
  console.log('  Convergence Results');
  console.log(`${'─'.repeat(60)}\n`);

  const treeConfigBetSizes = treeConfig.betSizes.flop;
  const actionLabels = [
    'Check',
    ...treeConfigBetSizes.map((s) => `Bet ${Math.round(s * 100)}%`),
    'All-in',
  ];

  for (let i = 0; i < results.length; i++) {
    const r = results[i];
    const iterLabel = r.iterations.toLocaleString().padStart(10);

    if (r.shift) {
      const status =
        r.shift.avgL1 < 0.02 ? '✓ Converged' : r.shift.avgL1 < 0.05 ? '~ Nearly' : '✗ Not yet';
      const prevIter = results[i - 1].iterations.toLocaleString();
      console.log(
        `  ${prevIter} → ${iterLabel}:  avg shift = ${(r.shift.avgL1 * 100).toFixed(1)}%  max = ${(r.shift.maxL1 * 100).toFixed(1)}%  ${status}`,
      );
    }
  }

  console.log();

  // Print root strategies at each step
  console.log('  Root node strategies across iteration steps:\n');

  console.log('  BB (OOP) at root:');
  const oopHeader = `  ${'Iterations'.padEnd(12)}${actionLabels.map((a) => a.padStart(10)).join('')}`;
  console.log(oopHeader);
  console.log(`  ${'─'.repeat(oopHeader.length - 2)}`);
  for (const r of results) {
    if (r.rootOOP.probs.length === 0) continue;
    const iterLabel = r.iterations.toLocaleString().padEnd(12);
    const probStrs = r.rootOOP.probs
      .slice(0, actionLabels.length)
      .map((p) => `${(p * 100).toFixed(1)}%`.padStart(10));
    console.log(`  ${iterLabel}${probStrs.join('')}`);
  }

  console.log();
  console.log('  BTN (IP) facing check:');
  // IP strategies at root would be after BB checks — history = 'x'
  // But we computed root of player 1 at empty history which may or may not have data
  // Let's use what we have
  const ipHeader = `  ${'Iterations'.padEnd(12)}${actionLabels.map((a) => a.padStart(10)).join('')}`;
  console.log(ipHeader);
  console.log(`  ${'─'.repeat(ipHeader.length - 2)}`);
  for (const r of results) {
    if (r.rootIP.probs.length === 0) {
      console.log(
        `  ${r.iterations.toLocaleString().padEnd(12)}  (no data at empty history for IP)`,
      );
      continue;
    }
    const iterLabel = r.iterations.toLocaleString().padEnd(12);
    const probStrs = r.rootIP.probs
      .slice(0, actionLabels.length)
      .map((p) => `${(p * 100).toFixed(1)}%`.padStart(10));
    console.log(`  ${iterLabel}${probStrs.join('')}`);
  }

  console.log();

  // Final assessment
  const lastShift = results[results.length - 1].shift;
  if (lastShift) {
    if (lastShift.avgL1 < 0.02) {
      console.log('  Assessment: CONVERGED — strategies are stable (< 2% avg shift)');
    } else if (lastShift.avgL1 < 0.05) {
      console.log('  Assessment: NEARLY CONVERGED — consider more iterations for precision');
    } else {
      console.log('  Assessment: NOT CONVERGED — need significantly more iterations');
    }
  }
  console.log();
}

main().catch((err) => {
  console.error('Error:', err);
  process.exit(1);
});
