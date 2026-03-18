// Quick test: solve one coaching flop with WASM engine
import { buildTree } from '../tree/tree-builder.js';
import { getTreeConfig } from '../tree/tree-config.js';
import { flattenTree } from '../vectorized/flat-tree.js';
import { ArrayStore } from '../vectorized/array-store.js';
import { enumerateValidCombos, buildReachFromRange } from '../vectorized/combo-utils.js';
import { solveWithWasm, isWasmAvailable } from '../vectorized/wasm-cfr-bridge.js';
import { solveFullGameCFR } from '../vectorized/full-game-cfr.js';
import { loadHUSRPRanges, getWeightedRangeCombos } from '../integration/preflop-ranges.js';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const CHARTS_PATH = resolve(__dirname, '../../../../data/preflop_charts.json');

async function main() {
  const cfgName = 'coach_hu_srp_100bb';
  const treeConfig = getTreeConfig(cfgName);
  const flopCards = [0, 4, 8]; // 2c 3c 4c

  // Load ranges
  const ranges = loadHUSRPRanges(CHARTS_PATH, {
    ipSpot: 'BTN_unopened_open2.5x',
    ipAction: 'raise',
    oopSpot: 'BB_vs_BTN_facing_open2.5x',
    oopAction: 'call',
  });
  const deadCards = new Set(flopCards);
  const oopCombos = getWeightedRangeCombos(ranges.oopRange, deadCards);
  const ipCombos = getWeightedRangeCombos(ranges.ipRange, deadCards);

  // Build single-street tree
  const singleStreetConfig = { ...treeConfig, singleStreet: true };
  const root = buildTree(singleStreetConfig);
  const flopTree = flattenTree(root, 2);
  console.log(
    `Flop tree: ${flopTree.numNodes} nodes, ${flopTree.numTerminals} terminals, ${flopTree.totalActions} actions`,
  );

  // Enumerate combos
  const validCombos = enumerateValidCombos(flopCards);
  const nc = validCombos.numCombos;
  console.log(`Valid combos: ${nc}`);

  // Build reaches
  const oopReach = buildReachFromRange(oopCombos, validCombos);
  const ipReach = buildReachFromRange(ipCombos, validCombos);

  console.log(`WASM available: ${isWasmAvailable()}`);

  // Test 1: WASM solve with 100 iterations
  console.log('\n--- WASM MCCFR solve (100 iters) ---');
  const comboCards = new Int32Array(nc * 2);
  for (let i = 0; i < nc; i++) {
    comboCards[i * 2] = validCombos.combos[i][0];
    comboCards[i * 2 + 1] = validCombos.combos[i][1];
  }

  const t0 = Date.now();
  const wasmResult = await solveWithWasm({
    flopTree,
    flopNumCombos: nc,
    flopComboCards: comboCards,
    flopOopReach: new Float32Array(oopReach),
    flopIpReach: new Float32Array(ipReach),
    startingPot: treeConfig.startingPot,
    effectiveStack: treeConfig.effectiveStack,
    innerTree: flopTree,
    board: flopCards,
    rakePercentage: 0,
    rakeCap: 0,
    iterations: 100,
    mccfr: true,
  });
  const t1 = Date.now();

  if (wasmResult) {
    console.log(`WASM solve completed in ${t1 - t0}ms`);
    console.log(`Strategy sums length: ${wasmResult.strategySums.length}`);
    console.log(`Flop NC: ${wasmResult.flopNC}`);

    // Create ArrayStore and check first few strategies
    const store = new ArrayStore(flopTree, wasmResult.flopNC);
    store.strategySums.set(wasmResult.strategySums);

    // Check root node strategy
    const rootActions = flopTree.nodeNumActions[0];
    const out = new Float32Array(rootActions * wasmResult.flopNC);
    store.getAverageStrategy(0, rootActions, out);

    // Print aggregate root strategy
    const actionLabels: string[] = [];
    const offset = flopTree.nodeActionOffset[0];
    for (let a = 0; a < rootActions; a++) {
      actionLabels.push(flopTree.nodeActionLabels[offset + a]);
    }

    console.log('\nRoot node (OOP) strategy:');
    for (let a = 0; a < rootActions; a++) {
      let sum = 0;
      for (let c = 0; c < wasmResult.flopNC; c++) {
        sum += out[a * wasmResult.flopNC + c];
      }
      console.log(`  ${actionLabels[a]}: ${(sum / wasmResult.flopNC).toFixed(3)}`);
    }
  } else {
    console.log('WASM returned null (not available)');
  }

  // Test 2: TS full-game CFR with MCCFR for comparison
  console.log('\n--- TS FullGameCFR MCCFR (100 iters) ---');
  const t2 = Date.now();
  const tsResult = solveFullGameCFR({
    board: flopCards,
    treeConfig,
    oopRange: oopCombos,
    ipRange: ipCombos,
    iterations: 100,
    mccfr: true,
    onProgress: (phase, detail, pct) => {
      if (phase === 'init') console.log(`  ${detail}`);
    },
  });
  const t3 = Date.now();
  console.log(`TS solve completed in ${t3 - t2}ms (${tsResult.memoryMB}MB)`);

  // Compare root strategies
  const tsRootActions = tsResult.tree.nodeNumActions[0];
  const tsOut = new Float32Array(tsRootActions * tsResult.nc);
  tsResult.store.getAverageStrategy(0, tsRootActions, tsOut);

  const tsOffset = tsResult.tree.nodeActionOffset[0];
  console.log('\nRoot node (OOP) strategy:');
  for (let a = 0; a < tsRootActions; a++) {
    let sum = 0;
    for (let c = 0; c < tsResult.nc; c++) {
      sum += tsOut[a * tsResult.nc + c];
    }
    const label = tsResult.tree.nodeActionLabels[tsOffset + a];
    console.log(`  ${label}: ${(sum / tsResult.nc).toFixed(3)}`);
  }
}

main().catch(console.error);
