#!/usr/bin/env tsx
// Quick sanity check of solved strategies

import { readFileSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { InfoSetStore } from '../engine/info-set-store.js';
import { allHandClasses } from '../preflop/preflop-types.js';

function findProjectRoot(): string {
  let dir = process.cwd();
  for (let i = 0; i < 10; i++) {
    if (existsSync(join(dir, 'packages', 'cfr-solver'))) return dir;
    dir = resolve(dir, '..');
  }
  return process.cwd();
}

const ROOT = findProjectRoot();
const storePath = join(ROOT, 'data', 'preflop', 'store_cash_6max_100bb.jsonl');

if (!existsSync(storePath)) {
  console.error('Store not found:', storePath);
  process.exit(1);
}

// Load store
const store = new InfoSetStore();
const content = readFileSync(storePath, 'utf-8');
const lines = content.trim().split('\n');
for (const line of lines) {
  if (!line) continue;
  const entry = JSON.parse(line) as { key: string; numActions: number; strategy: number[] };
  for (let a = 0; a < entry.numActions; a++) {
    store.addStrategyWeight(entry.key, a, entry.strategy[a] * 1000, entry.numActions);
  }
}
console.log(`Loaded ${store.size} info sets\n`);

const hcs = allHandClasses();

// UTG RFI (historyKey = '')
console.log('=== UTG RFI (actions: fold, open_2.5) ===');
let openCount = 0,
  totalWeight = 0;
const opened: string[] = [];
const folded: string[] = [];
for (let hc = 0; hc < 169; hc++) {
  const key = `${hc}|`;
  const avg = store.getAverageStrategy(key, 2);
  const combos = hcs[hc].length === 2 ? 6 : hcs[hc][2] === 's' ? 4 : 12;
  openCount += avg[1] * combos;
  totalWeight += combos;
  if (avg[1] > 0.5) opened.push(`${hcs[hc]}:${(avg[1] * 100).toFixed(0)}%`);
  if (
    avg[0] > 0.99 &&
    (hcs[hc] === '72o' || hcs[hc] === '32o' || hcs[hc] === 'T7o' || hcs[hc] === '93o')
  ) {
    folded.push(`${hcs[hc]}:${(avg[0] * 100).toFixed(0)}%`);
  }
}
console.log(
  `Open rate (weighted): ${((openCount / totalWeight) * 100).toFixed(1)}% (target ~15-17%)`,
);
console.log(`Hands opened >50% (${opened.length}):`);
console.log(`  ${opened.slice(0, 40).join(', ')}`);
if (opened.length > 40) console.log(`  ... and ${opened.length - 40} more`);

// Check specific hands
const checkHands = ['AA', 'KK', 'AKs', 'AKo', 'QQ', 'JTs', 'T9s', '76s', '72o', '32o'];
console.log('\nKey hands:');
for (const hand of checkHands) {
  const idx = hcs.indexOf(hand);
  if (idx === -1) continue;
  const avg = store.getAverageStrategy(`${idx}|`, 2);
  console.log(
    `  ${hand.padEnd(4)}: fold=${(avg[0] * 100).toFixed(1)}%, open=${(avg[1] * 100).toFixed(1)}%`,
  );
}

// BB vs BTN open (3 actions: fold, call, 3bet — no standalone allin at this level)
console.log('\n=== BB vs BTN open (Uf-Hf-Cf-Bo-Sf) ===');
const bbKey = 'Uf-Hf-Cf-Bo-Sf';
let callC = 0,
  raiseC = 0,
  foldC = 0,
  tw2 = 0;
for (let hc = 0; hc < 169; hc++) {
  const key = `${hc}|${bbKey}`;
  const avg = store.getAverageStrategy(key, 3);
  const combos = hcs[hc].length === 2 ? 6 : hcs[hc][2] === 's' ? 4 : 12;
  foldC += avg[0] * combos;
  callC += avg[1] * combos;
  raiseC += avg[2] * combos;
  tw2 += combos;
}
console.log(
  `Fold: ${((foldC / tw2) * 100).toFixed(1)}%  Call: ${((callC / tw2) * 100).toFixed(1)}%  3bet: ${((raiseC / tw2) * 100).toFixed(1)}%`,
);

// BB key hands
console.log('\nBB key hands vs BTN:');
for (const hand of ['AA', 'KK', 'AKs', 'AKo', 'QQ', 'JTs', '76s', '72o', '32o', '53s']) {
  const idx = hcs.indexOf(hand);
  if (idx === -1) continue;
  const avg = store.getAverageStrategy(`${idx}|${bbKey}`, 3);
  console.log(
    `  ${hand.padEnd(4)}: fold=${(avg[0] * 100).toFixed(1)}%, call=${(avg[1] * 100).toFixed(1)}%, 3bet=${(avg[2] * 100).toFixed(1)}%`,
  );
}

// All position RFI rates (numActions, openIndex)
// SB has 3 actions: fold(0), complete(1), open(2)
// Others have 2 actions: fold(0), open(1)
const rfiSpots: [string, string, string, number, number][] = [
  ['UTG', '', '~15-17%', 2, 1],
  ['HJ', 'Uf', '~19-22%', 2, 1],
  ['CO', 'Uf-Hf', '~27-30%', 2, 1],
  ['BTN', 'Uf-Hf-Cf', '~45-50%', 2, 1],
  ['SB', 'Uf-Hf-Cf-Bf', '~40-50%', 3, 2], // fold/complete/open
];

console.log('\n=== All RFI Open Rates ===');
for (const [pos, history, target, numAct, openIdx] of rfiSpots) {
  let posOpen = 0,
    posLimp = 0,
    posTW = 0;
  for (let hc = 0; hc < 169; hc++) {
    const key = `${hc}|${history}`;
    const avg = store.getAverageStrategy(key, numAct);
    const combos = hcs[hc].length === 2 ? 6 : hcs[hc][2] === 's' ? 4 : 12;
    posOpen += avg[openIdx] * combos;
    if (numAct === 3) posLimp += avg[1] * combos; // complete/limp
    posTW += combos;
  }
  const openPct = ((posOpen / posTW) * 100).toFixed(1);
  if (numAct === 3) {
    const limpPct = ((posLimp / posTW) * 100).toFixed(1);
    const totalPct = (((posOpen + posLimp) / posTW) * 100).toFixed(1);
    console.log(
      `  ${pos.padEnd(3)}: open=${openPct}% limp=${limpPct}% total=${totalPct}% (target ${target})`,
    );
  } else {
    console.log(`  ${pos.padEnd(3)}: ${openPct}% (target ${target})`);
  }
}
