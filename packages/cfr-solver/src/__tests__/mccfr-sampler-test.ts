// Test: solve one coaching flop with mccrfSampler on flop-only tree
import { buildTree } from '../tree/tree-builder.js';
import { getTreeConfig } from '../tree/tree-config.js';
import { flattenTree } from '../vectorized/flat-tree.js';
import { ArrayStore } from '../vectorized/array-store.js';
import { enumerateValidCombos, buildReachFromRange } from '../vectorized/combo-utils.js';
import { solveVectorized } from '../vectorized/vectorized-cfr.js';
import { precomputeHandValues } from '../vectorized/showdown-eval.js';
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

// Create store
const store = new ArrayStore(flopTree, nc);
const storeMB = store.estimateMemoryBytes() / (1024 * 1024);
console.log(`ArrayStore: ${storeMB.toFixed(1)}MB`);

// Build mccrfSampler
const dealable: number[] = [];
for (let c = 0; c < 52; c++) {
  if (!flopCards.includes(c)) dealable.push(c);
}

let sampleCount = 0;
const mccrfSampler = (
  equityMatrix: Float32Array,
  oopInit: Float32Array,
  ipInit: Float32Array,
  _iter: number,
) => {
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

  // Compute 5-card hand values
  const fullBoard = [...flopCards, turnCard, riverCard];
  const handValues = precomputeHandValues(validCombos.combos, fullBoard);

  // Fill equity matrix
  for (let i = 0; i < nc; i++) {
    for (let j = i + 1; j < nc; j++) {
      const vi = handValues[i];
      const vj = handValues[j];
      const eq = vi > vj ? 1.0 : vi === vj ? 0.5 : 0.0;
      equityMatrix[i * nc + j] = eq;
      equityMatrix[j * nc + i] = 1.0 - eq;
    }
    equityMatrix[i * nc + i] = 0.5;
  }
  sampleCount++;
};

// Solve
const ITERS = 5000;
console.log(`\nSolving ${ITERS} MCCFR iterations...`);
const t0 = Date.now();
solveVectorized({
  tree: flopTree,
  store,
  board: flopCards,
  oopRange: oopCombos,
  ipRange: ipCombos,
  iterations: ITERS,
  mccrfSampler,
  useLinearWeighting: true,
  onProgress: (iter, elapsed) => {
    if (iter % 1000 === 0) {
      console.log(`  Iter ${iter}/${ITERS} (${(elapsed / 1000).toFixed(1)}s)`);
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
const outputPath = resolve(__dirname, '../../../../data/cfr/_test_mccfr.jsonl');
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
