// Analyze BB vs BTN 4-bet strategy (100BB HU Cash)
// Target node: So-b3-S4 (BB facing BTN 4-bet)
// Reference from user: BB 5-bet = 3.7% aggregate

import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = dirname(fileURLToPath(import.meta.url));

const { getPreflopConfig } = await import('./packages/cfr-solver/dist/preflop/preflop-config.js');
const { buildPreflopTree } = await import('./packages/cfr-solver/dist/preflop/preflop-tree.js');
const { solvePreflopCFR } = await import('./packages/cfr-solver/dist/preflop/preflop-cfr.js');
const { EquityTable } = await import('./packages/cfr-solver/dist/preflop/equity-table.js');
const { InfoSetStore } = await import('./packages/cfr-solver/dist/engine/info-set-store.js');
const { allHandClasses } = await import('./packages/cfr-solver/dist/preflop/preflop-types.js');

const ITERS = 3_000_000;
const SEED = 42;
const TARGET_KEY = 'So-b3-S4';

// ─── Reference: BB 5-bet frequency per hand class ───────────────────────────
// 0 = never 5-bet, 1 = always 5-bet, 0.5 = mixed
const REF_5BET = {
  AA: 0.65,
  KK: 1.0,
  QQ: 1.0,
  JJ: 1.0,
  TT: 0.5,
  99: 0.2,
  88: 0,
  77: 0,
  66: 0,
  55: 0,
  44: 0,
  33: 0,
  22: 0,
  AKs: 1.0,
  AQs: 0,
  AJs: 0,
  ATs: 0,
  A9s: 0,
  A8s: 0.2,
  A7s: 0.2,
  A6s: 0,
  A5s: 0,
  A4s: 0,
  A3s: 0.2,
  A2s: 0.2,
  KQs: 0,
  KJs: 0,
  KTs: 0,
  K9s: 0,
  K8s: 0,
  K7s: 0,
  K6s: 0,
  K5s: 0,
  K4s: 0,
  K3s: 0,
  K2s: 0,
  QJs: 0,
  QTs: 0,
  Q9s: 0,
  Q8s: 0,
  Q7s: 0,
  Q6s: 0,
  Q5s: 0,
  Q4s: 0,
  Q3s: 0,
  Q2s: 0,
  JTs: 0,
  J9s: 0,
  J8s: 0,
  J7s: 0,
  J6s: 0,
  J5s: 0,
  J4s: 0,
  J3s: 0,
  J2s: 0,
  T9s: 0,
  T8s: 0,
  T7s: 0,
  T6s: 0,
  T5s: 0,
  T4s: 0,
  T3s: 0,
  T2s: 0,
  '98s': 0,
  '97s': 0,
  '96s': 0,
  '95s': 0,
  '94s': 0,
  '93s': 0,
  '92s': 0,
  '87s': 0,
  '86s': 0,
  '85s': 0,
  '84s': 0,
  '83s': 0,
  '82s': 0,
  '76s': 0,
  '75s': 0,
  '74s': 0,
  '73s': 0,
  '72s': 0,
  '65s': 0,
  '64s': 0,
  '63s': 0,
  '62s': 0,
  '54s': 0,
  '53s': 0,
  '52s': 0,
  '43s': 0,
  '42s': 0,
  '32s': 0,
  AKo: 1.0,
  AQo: 0,
  AJo: 0.1,
  ATo: 0.05,
  A9o: 0,
  A8o: 0,
  A7o: 0,
  A6o: 0,
  A5o: 0,
  A4o: 0,
  A3o: 0,
  A2o: 0,
  KQo: 0.05,
  KJo: 0,
  KTo: 0,
  K9o: 0,
  K8o: 0,
  K7o: 0,
  K6o: 0,
  K5o: 0,
  K4o: 0,
  K3o: 0,
  K2o: 0,
  QJo: 0,
  QTo: 0,
  Q9o: 0,
  Q8o: 0,
  Q7o: 0,
  Q6o: 0,
  Q5o: 0,
  Q4o: 0,
  Q3o: 0,
  Q2o: 0,
  JTo: 0,
  J9o: 0,
  J8o: 0,
  J7o: 0,
  J6o: 0,
  J5o: 0,
  J4o: 0,
  J3o: 0,
  J2o: 0,
  T9o: 0,
  T8o: 0,
  T7o: 0,
  T6o: 0,
  T5o: 0,
  T4o: 0,
  T3o: 0,
  T2o: 0,
  '98o': 0,
  '97o': 0,
  '96o': 0,
  '95o': 0,
  '94o': 0,
  '93o': 0,
  '92o': 0,
  '87o': 0,
  '86o': 0,
  '85o': 0,
  '84o': 0,
  '83o': 0,
  '82o': 0,
  '76o': 0,
  '75o': 0,
  '74o': 0,
  '73o': 0,
  '72o': 0,
  '65o': 0,
  '64o': 0,
  '63o': 0,
  '62o': 0,
  '54o': 0,
  '53o': 0,
  '52o': 0,
  '43o': 0,
  '42o': 0,
  '32o': 0,
};

const ALL_CLASSES = allHandClasses();
const COMBOS = ALL_CLASSES.map((hc) => (hc.length === 2 ? 6 : hc.endsWith('s') ? 4 : 12));

// ─── Solve ───────────────────────────────────────────────────────────────────
console.log('Loading equity table...');
const equityPath = join(__dirname, 'data', 'preflop', 'equity_169x169.bin');
const equityTable = await EquityTable.load(equityPath);
const baseConfig = getPreflopConfig('cash_6max_100bb');
const config = { ...baseConfig, players: 2, positionLabels: ['SB', 'BB'] };
const root = buildPreflopTree(config);
const store = new InfoSetStore();

console.log(`Running ${ITERS.toLocaleString()} iterations (seed ${SEED})...`);
const t0 = Date.now();
solvePreflopCFR({ root, store, equityTable, config, iterations: ITERS, seed: SEED });
console.log(`Done in ${((Date.now() - t0) / 1000).toFixed(1)}s\n`);

// ─── Find node ───────────────────────────────────────────────────────────────
function findNode(node, key) {
  if (node.type === 'terminal') return null;
  if (node.historyKey === key) return node;
  for (const c of node.children.values()) {
    const r = findNode(c, key);
    if (r) return r;
  }
  return null;
}
const targetNode = findNode(root, TARGET_KEY);
if (!targetNode) {
  console.error('Node not found');
  process.exit(1);
}

console.log(`Node: ${TARGET_KEY}  pos=${targetNode.position} seat=${targetNode.seat}`);
console.log(`Pot: ${targetNode.pot.toFixed(2)}bb  actions: [${targetNode.actions.join(', ')}]\n`);

const ACTIONS = targetNode.actions;
const is5bet = (a) => a.startsWith('5bet_') || a === 'allin';

// ─── Extract strategies ───────────────────────────────────────────────────────
let aggTotal = 0,
  aggFold = 0,
  aggCall = 0,
  agg5bet = 0;
const results = [];

for (let idx = 0; idx < 169; idx++) {
  const key = `${idx}|${TARGET_KEY}`;
  const avg = store.getAverageStrategy(key, ACTIONS.length);
  const strat = Object.fromEntries(ACTIONS.map((a, i) => [a, avg[i]]));

  const combos = COMBOS[idx];
  const hc = ALL_CLASSES[idx];
  const foldPct = (strat['fold'] || 0) * 100;
  const callPct = (strat['call'] || 0) * 100;
  const fivePct = ACTIONS.filter(is5bet).reduce((s, a) => s + (strat[a] || 0), 0) * 100;

  aggTotal += combos;
  aggFold += (foldPct / 100) * combos;
  aggCall += (callPct / 100) * combos;
  agg5bet += (fivePct / 100) * combos;

  const ref5bet = REF_5BET[hc] ?? null;
  results.push({ hc, idx, foldPct, callPct, fivePct, ref5bet, combos });
}

// ─── Print aggregate ─────────────────────────────────────────────────────────
const pF = (aggFold / aggTotal) * 100,
  pC = (aggCall / aggTotal) * 100,
  p5 = (agg5bet / aggTotal) * 100;
console.log('══════════════════════════════════════════════════════');
console.log('BB vs 4-bet  (100BB HU, 3M iterations, seed 42)');
console.log('══════════════════════════════════════════════════════');
console.log(`Aggregate:  fold ${pF.toFixed(1)}%  call ${pC.toFixed(1)}%  5-bet ${p5.toFixed(1)}%`);
console.log(`Reference:  fold  ?    call  ?    5-bet 3.7%\n`);

// ─── Accuracy: compare 5-bet% vs reference ───────────────────────────────────
// Tolerance: |solver - ref| <= 0.20 for match
// For mixed hands (0 < ref < 1), accept if same direction (both nonzero)
let correct = 0,
  total = 0,
  errors = 0;
const ERR_THRESHOLD = 0.2; // 20% tolerance

console.log('Key hand comparison (5-bet frequency):');
console.log('  Hand   Solver  Ref    Δ      Match?');
console.log('  ─────────────────────────────────────');

const nonzeroRef = results.filter((r) => r.ref5bet !== null && r.ref5bet > 0);
const zeroRef = results.filter((r) => r.ref5bet !== null && r.ref5bet === 0);

// Show all non-zero reference hands
for (const r of nonzeroRef.sort((a, b) => b.ref5bet - a.ref5bet)) {
  const solverFrac = r.fivePct / 100;
  const delta = solverFrac - r.ref5bet;
  const match = Math.abs(delta) <= ERR_THRESHOLD;
  const marker = match ? '✓' : '✗';
  if (!match) errors++;
  correct += match ? 1 : 0;
  total++;
  console.log(
    `  ${marker} ${r.hc.padEnd(5)} ${r.fivePct.toFixed(0).padStart(4)}%  ${(r.ref5bet * 100).toFixed(0).padStart(3)}%  ${(delta * 100 > 0 ? '+' : '') + (delta * 100).toFixed(0).padStart(3)}%`,
  );
}

console.log('\n  --- Hands that should NOT 5-bet (ref=0) ---');
const wrongCall = zeroRef
  .filter((r) => r.fivePct > 20)
  .sort((a, b) => b.fivePct - a.fivePct)
  .slice(0, 15);
for (const r of wrongCall) {
  console.log(
    `  ✗ ${r.hc.padEnd(5)} ${r.fivePct.toFixed(0).padStart(4)}%  ref 0%  (should NOT 5-bet)`,
  );
  errors++;
}

// Count zero-ref accuracy (hands that 5-bet <= 20%)
let zeroCorrect = 0;
for (const r of zeroRef) {
  const match = r.fivePct <= 20;
  if (match) zeroCorrect++;
  total++;
  correct += match ? 1 : 0;
}
console.log(`\n  Zero-ref hands: ${zeroCorrect}/${zeroRef.length} within 20% threshold`);

console.log('\n══════════════════════════════════════════════════════');
console.log(`Overall accuracy: ${correct}/${total} = ${((correct / total) * 100).toFixed(1)}%`);
console.log(`Errors: ${errors}`);

// ─── Full grid for main hands ─────────────────────────────────────────────────
console.log('\n─── Full strategy for premium/notable hands ───');
const notable = [
  'AA',
  'KK',
  'QQ',
  'JJ',
  'TT',
  '99',
  '88',
  '77',
  'AKs',
  'AQs',
  'AJs',
  'ATs',
  'A8s',
  'A7s',
  'A6s',
  'A5s',
  'A4s',
  'A3s',
  'A2s',
  'AKo',
  'AQo',
  'AJo',
  'ATo',
  'KQs',
  'KQo',
];
for (const hc of notable) {
  const r = results.find((x) => x.hc === hc);
  if (!r) continue;
  const ref5 = REF_5BET[hc] ?? 0;
  const delta = (r.fivePct / 100 - ref5) * 100;
  const ok = Math.abs(delta) <= 20 ? '✓' : '✗';
  console.log(
    `  ${ok} ${hc.padEnd(5)} fold:${r.foldPct.toFixed(0).padStart(3)}% call:${r.callPct.toFixed(0).padStart(3)}% 5bet:${r.fivePct.toFixed(0).padStart(3)}%  (ref 5bet: ${(ref5 * 100).toFixed(0).padStart(3)}%)`,
  );
}
