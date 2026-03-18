/**
 * Standalone test for Sample 3 with various preflop range configs.
 * Uses hard-coded params from benchmark logs — no sample files needed.
 *
 * Sample 3: Ad Qc 7c, pot=40, stack=100
 * Target: P1 at pot=69.5, stacks=[79,91.5], actions=[fold,call,raise_38.5]
 * GTO+ reference: raise=1.64%, call=72.21%, fold=26.15%
 *
 * Usage:
 *   npx tsx packages/cfr-solver/scripts/test-sample3-preflop.ts [--iterations N] [--preflopMode MODE]
 *   Modes: off (default), auto, manual-srp, manual-3bp
 */

import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { solveScenario } from '../src/benchmark/scenario-solver.js';
import type { GtoPlusParams } from '../src/benchmark/params-parser.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// ─── GTO+ reference frequencies for Sample 3 target node ───────────────────
const GTO_REF = {
  'raise_38.5': 0.016446,
  call: 0.722053,
  fold: 0.261501,
};

// ─── Parse CLI args ──────────────────────────────────────────────────────────
const args = process.argv.slice(2);
let iterations = 5000;
let preflopMode: string = 'off';
let numWorkers = 4;

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--iterations') iterations = parseInt(args[++i], 10);
  if (args[i] === '--preflopMode') preflopMode = args[++i];
  if (args[i] === '--workers') numWorkers = parseInt(args[++i], 10);
}

// ─── Sample 3 params (from benchmark logs) ──────────────────────────────────
const params: GtoPlusParams = {
  board: ['Ad', 'Qc', '7c'],
  startingPot: 40,
  effectiveStack: 100,
  rakePercent: 0,
  rakeCap: 0,
  // Absolute bet sizes from log: [8.5, 21, 38.5, 64, 100]
  betSizesAbs: [8.5, 21, 38.5, 64, 100],
  // Per-level pot fractions from log: [0.2125, 0.2193, 0.2134, 0.2179, 0.2143]
  betSizesPot: [0.2125, 0.2193, 0.2134, 0.2179, 0.2143],
  ranges: [
    { weight: 1, combos: 1128 },
    { weight: 1, combos: 1128 },
  ],
  targetDeviation: 0.001,
  threads: numWorkers,
  treeStructure: '',
  singleStreetTree: false,
};

// ─── Preflop range config ────────────────────────────────────────────────────
let preflopRangeMode: 'off' | 'auto' | 'manual' = 'off';
let preflopOopSpot: string | undefined;
let preflopOopAction: string | undefined;
let preflopIpSpot: string | undefined;
let preflopIpAction: string | undefined;

if (preflopMode === 'auto') {
  preflopRangeMode = 'auto';
} else if (preflopMode === 'manual-3bp') {
  // 3-bet pot: OOP (BB) 3-bet, IP (BTN/SB) called
  preflopRangeMode = 'manual';
  preflopOopSpot = 'BB_vs_SB_raise';
  preflopOopAction = '3B';
  preflopIpSpot = 'SB_vs_BB_strategy';
  preflopIpAction = 'RC';
} else if (preflopMode === 'manual-srp') {
  // SRP: OOP (BB) calls BTN open, IP (BTN) opens
  preflopRangeMode = 'manual';
  preflopOopSpot = 'BB_vs_SB_raise';
  preflopOopAction = 'C';
  preflopIpSpot = 'BTN_RFI';
  preflopIpAction = 'raise';
} else {
  preflopRangeMode = 'off';
}

console.log(`\n${'='.repeat(60)}`);
console.log('  Sample 3 Preflop Range Test');
console.log(`${'='.repeat(60)}`);
console.log(`  Board:       Ad Qc 7c`);
console.log(`  Pot=40  Stack=100`);
console.log(`  Target node: P1 pot=69.5 [fold/call/raise_38.5]`);
console.log(`  Iterations:  ${iterations}`);
console.log(`  Workers:     ${numWorkers}`);
console.log(`  Preflop:     ${preflopMode}`);
console.log(
  `\n  GTO+ target: raise=${(GTO_REF['raise_38.5'] * 100).toFixed(2)}%  call=${(GTO_REF['call'] * 100).toFixed(2)}%  fold=${(GTO_REF['fold'] * 100).toFixed(2)}%`,
);
console.log(`${'='.repeat(60)}\n`);

const libraryPath = resolve(
  __dirname,
  '..',
  '..',
  '..',
  'data',
  'preflop',
  'preflop_library.v1.json',
);

try {
  const startMs = Date.now();
  const result = await solveScenario({
    params,
    gtoPlusActions: ['raise_38.5', 'call', 'fold'],
    iterations,
    bucketCount: 200,
    flopMode: 'full_game',
    mccfr: true,
    numWorkers,
    minItersPerWorker: 250,
    useWasm: true,
    preflopRangeMode,
    preflopLibraryPath: libraryPath,
    preflopOopSpot,
    preflopOopAction,
    preflopIpSpot,
    preflopIpAction,
    gtoPlusContext: { pot: 69.5, stack: 91.5, toCall: 12.5 },
    onProgress: (_iter, _elapsed) => {},
  });

  const elapsedS = (Date.now() - startMs) / 1000;
  console.log(`\nSolved in ${elapsedS.toFixed(1)}s\n`);

  // ─── Results ──────────────────────────────────────────────────────────────
  console.log('  Action Frequencies at Target Node:');
  console.log('  ' + '-'.repeat(50));
  const actions = ['raise_38.5', 'call', 'fold'];
  let totalL1 = 0;
  for (const action of actions) {
    const gtoFreq = GTO_REF[action as keyof typeof GTO_REF] ?? 0;
    const ezFreq = result.overallFreqs[action] ?? 0;
    const diff = ezFreq - gtoFreq;
    totalL1 += Math.abs(diff);
    console.log(
      `  ${action.padEnd(12)}: GTO+ ${(gtoFreq * 100).toFixed(2).padStart(6)}%   EZ ${(ezFreq * 100).toFixed(2).padStart(6)}%   diff ${diff >= 0 ? '+' : ''}${(diff * 100).toFixed(2)}%`,
    );
  }
  const approxAccuracy = (1 - totalL1 / 2) * 100;
  console.log(`\n  Approximate aggregate accuracy: ${approxAccuracy.toFixed(1)}%`);
  console.log(`  (Per-hand accuracy from benchmark would differ)\n`);

  console.log(`  Top 5 deviation hands:`);
  const top5 = result.handStrategies
    .map((h) => {
      const ezRaise = h.freqs['raise_38.5'] ?? 0;
      const ezCall = h.freqs['call'] ?? 0;
      const ezFold = h.freqs['fold'] ?? 0;
      return { hand: h.handClass, ezRaise, ezCall, ezFold };
    })
    .filter((h) => h.ezRaise > 0.05)
    .sort((a, b) => b.ezRaise - a.ezRaise)
    .slice(0, 5);

  for (const h of top5) {
    console.log(
      `    ${h.hand.padEnd(6)}: raise=${(h.ezRaise * 100).toFixed(1)}%  call=${(h.ezCall * 100).toFixed(1)}%  fold=${(h.ezFold * 100).toFixed(1)}%`,
    );
  }
  console.log('');
} catch (err) {
  console.error('Error:', (err as Error).message);
  process.exit(1);
}
