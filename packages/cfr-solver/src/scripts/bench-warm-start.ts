#!/usr/bin/env tsx
/**
 * Benchmark: VNet warm-start vs cold-start CFR convergence.
 * Compares solve quality at various iteration counts.
 */

import { solveStreet, solveStreetSync } from '../vectorized/street-solver.js';
import { preloadWasmModule } from '../vectorized/wasm-cfr-bridge.js';
import { REALTIME_SRP_50BB_CONFIG } from '../tree/tree-config.js';
import { loadHUSRPRanges, getWeightedRangeCombos } from '../integration/preflop-ranges.js';
import { loadModel } from '@cardpilot/fast-model';
import { resolve } from 'node:path';

async function main() {
  await preloadWasmModule();

  const projectRoot = resolve(import.meta.dirname ?? '.', '../../../../');
  const ranges = loadHUSRPRanges(resolve(projectRoot, 'data/preflop_charts.json'), {});
  const oopRange = getWeightedRangeCombos(ranges.oopRange);
  const ipRange = getWeightedRangeCombos(ranges.ipRange);

  const vnet = loadModel(resolve(projectRoot, 'models/vnet-v10-v3data.json'));
  if (!vnet) {
    console.error('Failed to load VNet model');
    process.exit(1);
  }

  const board = [0, 4, 8]; // 2c 3c 4c
  const config = REALTIME_SRP_50BB_CONFIG;

  console.log('=== Benchmark: VNet Warm-Start vs Cold-Start ===');
  console.log(`Board: 2c 3c 4c | Config: REALTIME_SRP_50BB`);
  console.log('');

  // Reference: high-iteration cold solve (ground truth)
  console.log('Computing reference solve (10000 iter, cold, WASM)...');
  const refT0 = Date.now();
  const refResult = solveStreetSync({
    treeConfig: config,
    board,
    street: 'FLOP',
    oopRange,
    ipRange,
    iterations: 10000,
  });
  console.log(`  Reference: ${Date.now() - refT0}ms, ${refResult.tree.numNodes} nodes`);

  // Extract reference strategies for comparison
  const refStrategies = extractNodeStrategies(refResult);

  console.log(
    `\n${'Iter'.padStart(6)} | ${'Mode'.padEnd(12)} | ${'Time'.padStart(8)} | Strategy Diff`,
  );
  console.log('-'.repeat(55));

  for (const iters of [200, 500, 1000, 2000, 5000]) {
    // Cold start (WASM)
    const coldT0 = Date.now();
    const coldResult = solveStreetSync({
      treeConfig: config,
      board,
      street: 'FLOP',
      oopRange,
      ipRange,
      iterations: iters,
    });
    const coldMs = Date.now() - coldT0;
    const coldDiff = compareStrategies(refStrategies, extractNodeStrategies(coldResult));

    // Warm start (TS with VNet)
    const warmT0 = Date.now();
    const warmResult = solveStreet({
      treeConfig: config,
      board,
      street: 'FLOP',
      oopRange,
      ipRange,
      iterations: iters,
      vnetModel: vnet,
      vnetWeight: 10,
    });
    const warmMs = Date.now() - warmT0;
    const warmDiff = compareStrategies(refStrategies, extractNodeStrategies(warmResult));

    console.log(
      `${String(iters).padStart(6)} | ${'cold(WASM)'.padEnd(12)} | ${String(coldMs + 'ms').padStart(8)} | ${coldDiff.toFixed(4)}`,
    );
    console.log(
      `${String(iters).padStart(6)} | ${'warm(VNet)'.padEnd(12)} | ${String(warmMs + 'ms').padStart(8)} | ${warmDiff.toFixed(4)}`,
    );
  }
}

/** Extract average strategy per action at root node */
function extractNodeStrategies(result: { store: any; tree: any }): Map<number, number[]> {
  const { store, tree } = result;
  const nc = store.numCombos;
  const strategies = new Map<number, number[]>();

  for (let nodeId = 0; nodeId < Math.min(tree.numNodes, 10); nodeId++) {
    const numActions = tree.nodeNumActions[nodeId];
    const base = store.nodeOffset[nodeId];
    const avgProbs: number[] = [];

    for (let a = 0; a < numActions; a++) {
      let sum = 0;
      let count = 0;
      for (let c = 0; c < nc; c++) {
        const val = store.strategySums[base + a * nc + c];
        if (val > 0) {
          sum += val;
          count++;
        }
      }
      avgProbs.push(count > 0 ? sum / count : 0);
    }

    // Normalize
    const total = avgProbs.reduce((a, b) => a + b, 0);
    if (total > 0) {
      for (let i = 0; i < avgProbs.length; i++) avgProbs[i] /= total;
    }
    strategies.set(nodeId, avgProbs);
  }

  return strategies;
}

/** Compute average L1 distance between two strategy maps */
function compareStrategies(ref: Map<number, number[]>, test: Map<number, number[]>): number {
  let totalDiff = 0;
  let count = 0;

  for (const [nodeId, refProbs] of ref) {
    const testProbs = test.get(nodeId);
    if (!testProbs) continue;
    const len = Math.min(refProbs.length, testProbs.length);
    for (let i = 0; i < len; i++) {
      totalDiff += Math.abs(refProbs[i] - testProbs[i]);
    }
    count++;
  }

  return count > 0 ? totalDiff / count : 0;
}

main().catch(console.error);
