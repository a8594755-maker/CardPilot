// Verify BTN vs 3-bet accuracy is still intact after code changes
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = dirname(fileURLToPath(import.meta.url));

const { getPreflopConfig } = await import('./packages/cfr-solver/dist/preflop/preflop-config.js');
const { buildPreflopTree } = await import('./packages/cfr-solver/dist/preflop/preflop-tree.js');
const { solvePreflopCFR } = await import('./packages/cfr-solver/dist/preflop/preflop-cfr.js');
const { EquityTable } = await import('./packages/cfr-solver/dist/preflop/equity-table.js');
const { InfoSetStore } = await import('./packages/cfr-solver/dist/engine/info-set-store.js');
const { allHandClasses } = await import('./packages/cfr-solver/dist/preflop/preflop-types.js');

// Reference: BTN vs BB 3-bet dominant actions
const REFERENCE = {
  // Value 4-bets
  AA: '4bet',
  KK: '4bet',
  QQ: '4bet',
  AKs: '4bet',
  AKo: '4bet',
  // Fold-dominant
  22: 'fold',
  33: 'fold',
  44: 'fold',
  55: 'fold',
  66: 'fold',
  77: 'fold',
  // Call-dominant pairs
  88: 'call',
  99: 'call',
  TT: 'call',
  JJ: 'call',
  // Suited Ax
  AQs: 'call',
  AJs: 'call',
  ATs: 'call',
  A5s: '4bet',
  A4s: '4bet',
  A3s: 'mix',
  A2s: 'call',
  A9s: 'call',
  A8s: 'call',
  A7s: 'call',
  A6s: 'call',
  // Offsuit Ax
  AQo: 'call',
  AJo: 'call',
  ATo: 'call',
  // Suited connectors
  KQs: 'call',
  KJs: 'call',
  KTs: 'call',
  QJs: 'call',
  QTs: 'call',
  JTs: 'call',
};

const ALL_CLASSES = allHandClasses();
const COMBOS = ALL_CLASSES.map((hc) => (hc.length === 2 ? 6 : hc.endsWith('s') ? 4 : 12));

console.log('Loading equity table...');
const equityPath = join(__dirname, 'data', 'preflop', 'equity_169x169.bin');
const equityTable = await EquityTable.load(equityPath);
const baseConfig = getPreflopConfig('cash_6max_100bb');
const config = { ...baseConfig, players: 2, positionLabels: ['SB', 'BB'] };
const root = buildPreflopTree(config);
const store = new InfoSetStore();

console.log('Running 3M iterations (seed 42)...');
solvePreflopCFR({ root, store, equityTable, config, iterations: 3_000_000, seed: 42 });

// Find BTN vs 3-bet node (So-b3)
function findNode(node, key) {
  if (node.type === 'terminal') return null;
  if (node.historyKey === key) return node;
  for (const c of node.children.values()) {
    const r = findNode(c, key);
    if (r) return r;
  }
  return null;
}
const targetNode = findNode(root, 'So-b3');
console.log(
  `\nNode So-b3: ${targetNode.position} seat${targetNode.seat}, pot=${targetNode.pot.toFixed(2)}bb`,
);
console.log(`Actions: [${targetNode.actions.join(', ')}]`);

const ACTIONS = targetNode.actions;
const is4bet = (a) => a.startsWith('4bet_') || a === 'allin';

let aggTotal = 0,
  aggFold = 0,
  aggCall = 0,
  agg4bet = 0;
let correct = 0,
  total = 0;
const ERRORS = [];

for (let idx = 0; idx < 169; idx++) {
  const key = `${idx}|So-b3`;
  const avg = store.getAverageStrategy(key, ACTIONS.length);
  const strat = Object.fromEntries(ACTIONS.map((a, i) => [a, avg[i]]));
  const combos = COMBOS[idx];
  const hc = ALL_CLASSES[idx];

  const foldPct = (strat['fold'] || 0) * 100;
  const callPct = (strat['call'] || 0) * 100;
  const fourPct = ACTIONS.filter(is4bet).reduce((s, a) => s + (strat[a] || 0), 0) * 100;

  aggTotal += combos;
  aggFold += (foldPct / 100) * combos;
  aggCall += (callPct / 100) * combos;
  agg4bet += (fourPct / 100) * combos;

  const ref = REFERENCE[hc];
  if (!ref) continue;

  let dom;
  if (fourPct > 50) dom = '4bet';
  else if (callPct > 50) dom = 'call';
  else if (foldPct > 50) dom = 'fold';
  else dom = 'mix';

  total++;
  const match = ref === dom || (ref === 'mix' && fourPct > 20 && fourPct < 80);
  if (match) correct++;
  else ERRORS.push({ hc, dom, ref, foldPct, callPct, fourPct });
}

const pF = (aggFold / aggTotal) * 100,
  pC = (aggCall / aggTotal) * 100,
  p4 = (agg4bet / aggTotal) * 100;
console.log('\n══════════════════════════════════════════');
console.log('BTN vs 3-bet  (100BB HU, 3M iters seed 42)');
console.log('══════════════════════════════════════════');
console.log(`Aggregate: fold ${pF.toFixed(1)}%  call ${pC.toFixed(1)}%  4-bet ${p4.toFixed(1)}%`);
console.log(`Reference: fold  57.4%  call  37.5%  4-bet  5.1%`);
console.log(`\nAccuracy: ${correct}/${total} = ${((correct / total) * 100).toFixed(1)}%`);
if (ERRORS.length) {
  console.log('\nErrors:');
  for (const e of ERRORS)
    console.log(
      `  ✗ ${e.hc.padEnd(5)} solver=${e.dom} (fold:${e.foldPct.toFixed(0)}% call:${e.callPct.toFixed(0)}% 4bet:${e.fourPct.toFixed(0)}%)  ref=${e.ref}`,
    );
}
