#!/usr/bin/env tsx
/**
 * Benchmark: WASM C++ StreetSolver vs TypeScript CFR solver.
 *
 * Solves the same flop board with both backends and compares:
 * - Wall-clock time
 * - Strategy output (should be nearly identical)
 */
import { performance } from 'node:perf_hooks';
import {
  isWasmAvailable,
  preloadWasmModule,
  solveStreetWasmSync,
} from '../vectorized/wasm-cfr-bridge.js';
import { solveStreet, type StreetSolveParams } from '../vectorized/street-solver.js';
import { buildStreetTree } from '../vectorized/street-tree-builder.js';
import { flattenTree } from '../vectorized/flat-tree.js';
import { assignHistoryIds } from '../tree/tree-builder.js';
import {
  enumerateValidCombos,
  buildBlockerMatrix,
  buildReachFromRange,
} from '../vectorized/combo-utils.js';
import { PIPELINE_SRP_V2_CONFIG } from '../tree/tree-config.js';
import type { WeightedCombo } from '../integration/preflop-ranges.js';

const ITERATIONS = 500;
// Flop board: As Kh 7c  (indices: As=51, Kh=50-1=49... let's use cardToIndex)
// rank*4+suit: A=12, K=11, 7=5; s=0c,1d,2h,3s
// As = 12*4+3 = 51, Kh = 11*4+2 = 46, 7c = 5*4+0 = 20
const BOARD = [51, 46, 20];

// Build uniform ranges (all 1326 combos with weight 1)
function buildUniformRange(board: number[]): WeightedCombo[] {
  const blocked = new Set(board);
  const combos: WeightedCombo[] = [];
  for (let c1 = 0; c1 < 52; c1++) {
    if (blocked.has(c1)) continue;
    for (let c2 = c1 + 1; c2 < 52; c2++) {
      if (blocked.has(c2)) continue;
      combos.push({ combo: [c1, c2], weight: 1 });
    }
  }
  return combos;
}

async function main() {
  console.log('=== WASM vs TS CFR Benchmark ===');
  console.log(`Board: As Kh 7c  |  Iterations: ${ITERATIONS}`);
  console.log();

  const treeConfig = PIPELINE_SRP_V2_CONFIG;
  const oopRange = buildUniformRange(BOARD);
  const ipRange = buildUniformRange(BOARD);
  console.log(`Range size: ${oopRange.length} combos`);

  // ────────────────────────────────────────
  // 1. TS Solver
  // ────────────────────────────────────────
  console.log('\n--- TypeScript CFR Solver ---');
  const tsStart = performance.now();
  const tsResult = solveStreet({
    treeConfig,
    board: BOARD,
    street: 'FLOP',
    oopRange,
    ipRange,
    iterations: ITERATIONS,
  });
  const tsTime = performance.now() - tsStart;
  console.log(`  Time: ${tsTime.toFixed(0)}ms`);
  console.log(`  Nodes: ${tsResult.tree.numNodes}, Terminals: ${tsResult.tree.numTerminals}`);
  console.log(`  Combos: ${tsResult.validCombos.numCombos}`);
  console.log(`  Boundary terminals: ${tsResult.boundaryData.size}`);

  // ────────────────────────────────────────
  // 2. WASM Solver
  // ────────────────────────────────────────
  console.log('\n--- WASM C++ CFR Solver ---');

  if (!isWasmAvailable()) {
    console.error('WASM not available! Skipping.');
    return;
  }

  const preloadStart = performance.now();
  const loaded = await preloadWasmModule();
  const preloadTime = performance.now() - preloadStart;
  console.log(`  Preload: ${preloadTime.toFixed(0)}ms (${loaded ? 'OK' : 'FAILED'})`);

  if (!loaded) {
    console.error('WASM preload failed! Skipping.');
    return;
  }

  // Build the same tree + combos that solveStreetSync would build
  const actionTree = buildStreetTree(treeConfig, 'FLOP', 2);
  assignHistoryIds(actionTree);
  const tree = flattenTree(actionTree, 2);
  const validCombos = enumerateValidCombos(BOARD);
  const nc = validCombos.numCombos;
  const blockerMatrix = buildBlockerMatrix(validCombos.combos);
  const oopInitReach = buildReachFromRange(oopRange, validCombos);
  const ipInitReach = buildReachFromRange(ipRange, validCombos);

  const comboCards = new Int32Array(nc * 2);
  for (let i = 0; i < nc; i++) {
    comboCards[i * 2] = validCombos.combos[i][0];
    comboCards[i * 2 + 1] = validCombos.combos[i][1];
  }

  const wasmStart = performance.now();
  const wasmResult = solveStreetWasmSync({
    tree,
    board: BOARD,
    comboCards,
    combos: validCombos.combos,
    numCombos: nc,
    oopReach: oopInitReach,
    ipReach: ipInitReach,
    iterations: ITERATIONS,
    blockerMatrix,
  });
  const wasmTime = performance.now() - wasmStart;

  if (!wasmResult) {
    console.error('WASM solve returned null!');
    return;
  }

  console.log(`  Time: ${wasmTime.toFixed(0)}ms`);
  console.log(`  StrategySums length: ${wasmResult.strategySums.length}`);
  console.log(`  Regrets length: ${wasmResult.regrets.length}`);

  // ────────────────────────────────────────
  // 3. Compare
  // ────────────────────────────────────────
  console.log('\n=== Results ===');
  const speedup = tsTime / wasmTime;
  console.log(`  TS:   ${tsTime.toFixed(0)}ms`);
  console.log(`  WASM: ${wasmTime.toFixed(0)}ms`);
  console.log(`  Speedup: ${speedup.toFixed(1)}x`);

  // Compare root-node average strategies (should be similar)
  const numActions = tree.nodeNumActions[0];
  const tsAvg = new Float32Array(numActions * nc);
  tsResult.store.getAverageStrategy(0, numActions, tsAvg);

  // Build WASM ArrayStore for comparison
  const { ArrayStore } = await import('../vectorized/array-store.js');
  const wasmStore = ArrayStore.fromRawBuffers(
    tree,
    nc,
    wasmResult.strategySums,
    wasmResult.regrets,
  );
  const wasmAvg = new Float32Array(numActions * nc);
  wasmStore.getAverageStrategy(0, numActions, wasmAvg);

  // Compute average KL divergence between the two strategies
  let totalKL = 0;
  let count = 0;
  for (let c = 0; c < nc; c++) {
    let klC = 0;
    for (let a = 0; a < numActions; a++) {
      const p = tsAvg[a * nc + c];
      const q = wasmAvg[a * nc + c];
      if (p > 1e-8 && q > 1e-8) {
        klC += p * Math.log(p / q);
      }
    }
    totalKL += klC;
    count++;
  }
  const avgKL = totalKL / count;
  console.log(`  Strategy KL divergence (TS vs WASM): ${avgKL.toFixed(6)}`);
  console.log(
    `  ${avgKL < 0.01 ? '✓ Strategies match closely' : '⚠ Strategies diverge (expected with different RNG)'}`,
  );

  // Show sample strategy for combo 0 (first valid combo)
  console.log(`\n  Sample strategy at root (combo #0):`);
  const labels = tree.nodeActionLabels;
  const offset = tree.nodeActionOffset[0];
  for (let a = 0; a < numActions; a++) {
    const tsP = tsAvg[a * nc + 0];
    const wasmP = wasmAvg[a * nc + 0];
    console.log(
      `    ${labels[offset + a].padEnd(8)} TS=${tsP.toFixed(4)}  WASM=${wasmP.toFixed(4)}`,
    );
  }

  console.log('\n✓ Benchmark complete');
}

main().catch((err) => {
  console.error('Benchmark failed:', err);
  process.exit(1);
});
