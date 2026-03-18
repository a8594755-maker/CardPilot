// Test: MCCFR with O(n log n) showdown sampler vs O(n²) equity sampler
import { buildTree } from '../tree/tree-builder.js';
import { getTreeConfig } from '../tree/tree-config.js';
import { flattenTree } from '../vectorized/flat-tree.js';
import { ArrayStore } from '../vectorized/array-store.js';
import { enumerateValidCombos, buildBlockerMatrix } from '../vectorized/combo-utils.js';
import { solveVectorized } from '../vectorized/vectorized-cfr.js';
import { precomputeHandValues, rebuildShowdownCacheForMCCFR } from '../vectorized/showdown-eval.js';
import { loadHUSRPRanges, getWeightedRangeCombos } from '../integration/preflop-ranges.js';
import { exportArrayStoreToJSONL } from '../storage/json-export.js';
import { indexToCard } from '../abstraction/card-index.js';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const CHARTS_PATH = resolve(__dirname, '../../../../data/preflop_charts.json');

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

// Build single-street flop tree
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

// Build blocker matrix (stable, shared with cache)
const blockerMatrix = buildBlockerMatrix(validCombos.combos);

// Dealable cards
const dealable: number[] = [];
for (let c = 0; c < 52; c++) {
  if (!flopCards.includes(c)) dealable.push(c);
}

// Create store
const store = new ArrayStore(flopTree, nc);
const storeMB = store.estimateMemoryBytes() / (1024 * 1024);
console.log(`ArrayStore: ${storeMB.toFixed(1)}MB`);

// Build mccrfShowdownSampler (O(n log n) per iter)
let sampleCount = 0;
const mccrfShowdownSampler = (oopInit: Float32Array, ipInit: Float32Array, _iter: number) => {
  // Sample turn + river
  const ti = Math.floor(Math.random() * dealable.length);
  const turnCard = dealable[ti];
  const remaining = dealable.filter((c) => c !== turnCard);
  const ri = Math.floor(Math.random() * remaining.length);
  const riverCard = remaining[ri];

  // Zero reaches for blocked combos
  for (let i = 0; i < nc; i++) {
    const [c1, c2] = validCombos.combos[i];
    if (c1 === turnCard || c2 === turnCard || c1 === riverCard || c2 === riverCard) {
      oopInit[i] = 0;
      ipInit[i] = 0;
    }
  }

  // Compute 5-card hand values + rebuild O(n log n) showdown cache
  const fullBoard = [...flopCards, turnCard, riverCard];
  const handValues = precomputeHandValues(validCombos.combos, fullBoard);
  rebuildShowdownCacheForMCCFR(validCombos.combos, handValues, blockerMatrix);
  sampleCount++;
};

// Solve
const ITERS = 5000;
console.log(`\nSolving ${ITERS} MCCFR iterations (showdown sampler)...`);
const t0 = Date.now();
solveVectorized({
  tree: flopTree,
  store,
  board: flopCards,
  oopRange: oopCombos,
  ipRange: ipCombos,
  iterations: ITERS,
  blockerMatrix,
  mccrfShowdownSampler,
  useLinearWeighting: true,
  onProgress: (iter, elapsed) => {
    if (iter % 1000 === 0) {
      console.log(
        `  Iter ${iter}/${ITERS} (${(elapsed / 1000).toFixed(1)}s, ${(iter / (elapsed / 1000)).toFixed(0)} it/s)`,
      );
    }
  },
});
const t1 = Date.now();
const elapsed = (t1 - t0) / 1000;
console.log(`\nSolve completed in ${elapsed.toFixed(1)}s (${(ITERS / elapsed).toFixed(0)} it/s)`);
console.log(`Samples: ${sampleCount}`);

// Print root strategy
const rootActions = flopTree.nodeNumActions[0];
const out = new Float32Array(rootActions * nc);
store.getAverageStrategy(0, rootActions, out);

const offset = flopTree.nodeActionOffset[0];
console.log('\nRoot node (OOP) aggregate strategy:');
for (let a = 0; a < rootActions; a++) {
  let sum = 0;
  for (let c = 0; c < nc; c++) {
    sum += out[a * nc + c];
  }
  const label = flopTree.nodeActionLabels[offset + a];
  console.log(`  ${label}: ${(sum / nc).toFixed(3)}`);
}

// Export
const outputPath = resolve(__dirname, '../../../../data/cfr/_test_mccfr_showdown.jsonl');
const exportResult = exportArrayStoreToJSONL(store, flopTree, validCombos, {
  outputPath,
  board: flopCards,
  boardCards: flopCards.map((c) => indexToCard(c)),
  configName: cfgName,
  iterations: ITERS,
  elapsedMs: t1 - t0,
});
console.log(
  `Exported: ${exportResult.infoSets} info sets, ${(exportResult.fileSize / 1024).toFixed(1)} KB`,
);
console.log(`Peak memory: ${Math.round(process.memoryUsage().heapUsed / 1024 / 1024)}MB`);
