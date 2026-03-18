// Quick test: solve one coaching flop with TS full-game MCCFR engine
import { getTreeConfig } from '../tree/tree-config.js';
import { solveFullGameCFR } from '../vectorized/full-game-cfr.js';
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

console.log(`OOP combos: ${oopCombos.length}, IP combos: ${ipCombos.length}`);
console.log(
  `Config: startingPot=${treeConfig.startingPot}, effectiveStack=${treeConfig.effectiveStack}`,
);

const t0 = Date.now();
const result = solveFullGameCFR({
  board: flopCards,
  treeConfig,
  oopRange: oopCombos,
  ipRange: ipCombos,
  iterations: 1000,
  mccfr: true,
  onProgress: (phase, detail, pct) => {
    console.log(`[${phase}] ${detail} (${pct.toFixed(0)}%)`);
  },
});
const t1 = Date.now();

console.log(`\nSolve completed in ${((t1 - t0) / 1000).toFixed(1)}s`);
console.log(`Memory: ${result.memoryMB}MB`);
console.log(`Flop tree: ${result.tree.numNodes} nodes, ${result.nc} combos`);

// Print root node strategy
const rootActions = result.tree.nodeNumActions[0];
const out = new Float32Array(rootActions * result.nc);
result.store.getAverageStrategy(0, rootActions, out);

const offset = result.tree.nodeActionOffset[0];
console.log('\nRoot node (OOP) aggregate strategy:');
for (let a = 0; a < rootActions; a++) {
  let sum = 0;
  for (let c = 0; c < result.nc; c++) {
    sum += out[a * result.nc + c];
  }
  const label = result.tree.nodeActionLabels[offset + a];
  console.log(`  ${label}: ${(sum / result.nc).toFixed(3)}`);
}

// Export to temp file
const outputPath = resolve(__dirname, '../../../../data/cfr/_test_coaching.jsonl');
const exportResult = exportArrayStoreToJSONL(result.store, result.tree, result.validCombos, {
  outputPath,
  board: flopCards,
  boardCards: flopCards.map((c) => indexToCard(c)),
  configName: cfgName,
  iterations: 1000,
  elapsedMs: t1 - t0,
});
console.log(
  `\nExported: ${exportResult.infoSets} info sets, ${(exportResult.fileSize / 1024).toFixed(1)} KB`,
);
