#!/usr/bin/env tsx
// Self-play Monte Carlo verification: simulate many hands using solved strategies
// and verify that the game value is close to 0 (Nash equilibrium property).
//
// Usage:
//   npx tsx src/cli/self-play.ts --config v1_50bb --data-dir data/cfr/v1_hu_srp_50bb --board "Tc Qc Ad" --hands 100000
//   npx tsx src/cli/self-play.ts --config hu_btn_bb_srp_50bb --board "Ah Ts 2c" --hands 500000

import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { cardToIndex, indexToCard } from '../abstraction/card-index.js';
import { evaluateBestHand, compareHands } from '@cardpilot/poker-evaluator';
import { getTreeConfig, getConfigOutputDir, type TreeConfigName } from '../tree/tree-config.js';
import { buildTree } from '../tree/tree-builder.js';
import type { GameNode, ActionNode, Street } from '../types.js';

// ─── Project root ───

const __dirname = fileURLToPath(new URL('.', import.meta.url));

function findProjectRoot(): string {
  const fromFile = resolve(__dirname, '../../../../');
  if (existsSync(resolve(fromFile, 'data/preflop_charts.json'))) return fromFile;
  if (existsSync(resolve(process.cwd(), 'data/preflop_charts.json'))) return process.cwd();
  const parent = resolve(process.cwd(), '../..');
  if (existsSync(resolve(parent, 'data/preflop_charts.json'))) return parent;
  return process.cwd();
}

const PROJECT_ROOT = findProjectRoot();

// ─── CLI args ───

const args = process.argv.slice(2);
function getStringArg(name: string, defaultVal: string): string {
  const idx = args.indexOf(`--${name}`);
  if (idx !== -1 && args[idx + 1]) return args[idx + 1];
  return defaultVal;
}

const configName = getStringArg('config', 'v1_50bb') as TreeConfigName;
const boardArg = getStringArg('board', '');
const dataDirOverride = getStringArg('data-dir', '');
const numHands = parseInt(getStringArg('hands', '100000'), 10);

// ─── Card utilities ───

const RANKS = '23456789TJQKA';

function expandHandClassToCombos(handClass: string): Array<[number, number]> {
  const hand = handClass.toUpperCase();
  const combos: Array<[number, number]> = [];
  if (hand.length === 2 && hand[0] === hand[1]) {
    const rank = RANKS.indexOf(hand[0]);
    if (rank < 0) return combos;
    for (let s1 = 0; s1 < 4; s1++)
      for (let s2 = s1 + 1; s2 < 4; s2++) combos.push([rank * 4 + s1, rank * 4 + s2]);
    return combos;
  }
  const suffix = hand.length === 3 ? hand[2] : '';
  const rankA = RANKS.indexOf(hand[0]);
  const rankB = RANKS.indexOf(hand[1]);
  if (rankA < 0 || rankB < 0) return combos;
  for (let sA = 0; sA < 4; sA++)
    for (let sB = 0; sB < 4; sB++) {
      if (suffix === 'S' && sA !== sB) continue;
      if (suffix === 'O' && sA === sB) continue;
      if (!suffix && sA === sB) continue;
      const c1 = rankA * 4 + sA;
      const c2 = rankB * 4 + sB;
      combos.push([Math.min(c1, c2), Math.max(c1, c2)]);
    }
  return combos;
}

// ─── Range loading ───

interface RangeEntry {
  hand: string;
  mix: Record<string, number>;
  spot: string;
}

const CONFIG_RANGES: Record<
  string,
  { ipSpot: string; oopSpot: string; ipAction: string; oopAction: string; minFrequency?: number }
> = {
  v1_50bb: {
    ipSpot: 'BTN_unopened_open2.5x',
    oopSpot: 'BB_vs_BTN_facing_open2.5x',
    ipAction: 'raise',
    oopAction: 'call',
  },
  standard_50bb: {
    ipSpot: 'BTN_unopened_open2.5x',
    oopSpot: 'BB_vs_BTN_facing_open2.5x',
    ipAction: 'raise',
    oopAction: 'call',
  },
  pipeline_srp: {
    ipSpot: 'BTN_unopened_open2.5x',
    oopSpot: 'BB_vs_BTN_facing_open2.5x',
    ipAction: 'raise',
    oopAction: 'call',
  },
  hu_btn_bb_srp_50bb: {
    ipSpot: 'BTN_unopened_open2.5x',
    oopSpot: 'BB_vs_BTN_facing_open2.5x',
    ipAction: 'raise',
    oopAction: 'call',
  },
  hu_btn_bb_3bp_50bb: {
    ipSpot: 'BTN_unopened_open2.5x',
    oopSpot: 'BB_vs_BTN_facing_open2.5x',
    ipAction: 'raise',
    oopAction: 'raise',
    minFrequency: 0.4,
  },
  hu_btn_bb_srp_100bb: {
    ipSpot: 'BTN_unopened_open2.5x',
    oopSpot: 'BB_vs_BTN_facing_open2.5x',
    ipAction: 'raise',
    oopAction: 'call',
  },
  hu_btn_bb_3bp_100bb: {
    ipSpot: 'BTN_unopened_open2.5x',
    oopSpot: 'BB_vs_BTN_facing_open2.5x',
    ipAction: 'raise',
    oopAction: 'raise',
    minFrequency: 0.4,
  },
};

function loadRange(
  chartsPath: string,
  spot: string,
  action: string,
  minFreq?: number,
): Array<[number, number]> {
  const all = JSON.parse(readFileSync(chartsPath, 'utf-8')) as RangeEntry[];
  const entries = all.filter((e) => e.spot === spot);
  const combos: Array<[number, number]> = [];
  const seen = new Set<string>();
  for (const e of entries) {
    const freq = e.mix[action];
    if (typeof freq !== 'number' || freq <= 0) continue;
    if (minFreq !== undefined && freq < minFreq) continue;
    for (const c of expandHandClassToCombos(e.hand)) {
      const k = `${c[0]},${c[1]}`;
      if (!seen.has(k)) {
        seen.add(k);
        combos.push(c);
      }
    }
  }
  return combos;
}

// ─── Hand bucketing ───

function computeHandBuckets(
  range: Array<[number, number]>,
  boardCards: number[],
  numBuckets: number,
): Map<string, number> {
  const dead = new Set(boardCards);
  const ranked: Array<{ key: string; value: number }> = [];
  for (const [c1, c2] of range) {
    if (dead.has(c1) || dead.has(c2)) continue;
    const cards = [indexToCard(c1), indexToCard(c2), ...boardCards.map(indexToCard)];
    ranked.push({
      key: `${Math.min(c1, c2)},${Math.max(c1, c2)}`,
      value: evaluateBestHand(cards).value,
    });
  }
  ranked.sort((a, b) => a.value - b.value);
  const bucketSize = Math.max(1, Math.ceil(ranked.length / numBuckets));
  const result = new Map<string, number>();
  for (let i = 0; i < ranked.length; i++) {
    result.set(ranked[i].key, Math.min(Math.floor(i / bucketSize), numBuckets - 1));
  }
  return result;
}

// ─── JSONL / Meta loading ───

interface BoardMeta {
  boardId: number;
  flopCards: number[];
  bucketCount: number;
  iterations: number;
  betSizes?: { flop: number[]; turn: number[]; river: number[] };
}

function findDataDir(): string {
  if (dataDirOverride) {
    const abs = resolve(PROJECT_ROOT, dataDirOverride);
    return existsSync(abs) ? abs : dataDirOverride;
  }
  const outputDir = getConfigOutputDir(configName);
  return resolve(PROJECT_ROOT, 'data/cfr', outputDir);
}

function findBoardByCards(dataDir: string, targetCards: number[]): BoardMeta | null {
  const sorted = [...targetCards].sort((a, b) => a - b);
  const files = readdirSync(dataDir).filter((f) => f.endsWith('.meta.json'));
  for (const f of files) {
    const m = JSON.parse(readFileSync(join(dataDir, f), 'utf-8')) as BoardMeta;
    const ms = [...m.flopCards].sort((a, b) => a - b);
    if (ms[0] === sorted[0] && ms[1] === sorted[1] && ms[2] === sorted[2]) return m;
  }
  return null;
}

function loadJSONL(dataDir: string, boardId: number): Map<string, number[]> {
  const p = join(dataDir, `flop_${String(boardId).padStart(3, '0')}.jsonl`);
  const indexed = new Map<string, number[]>();
  for (const line of readFileSync(p, 'utf-8').split('\n')) {
    if (!line.trim()) continue;
    const e = JSON.parse(line);
    indexed.set(e.key, e.probs);
  }
  return indexed;
}

// ─── Self-play simulation ───

function detectV2(indexed: Map<string, number[]>): boolean {
  for (const key of indexed.keys()) {
    const parts = key.split('|');
    if (parts.length >= 5 && parts[parts.length - 1].includes('-')) return true;
  }
  return false;
}

function extractBucket(key: string): number {
  const parts = key.split('|');
  const dims = parts[parts.length - 1].split('-');
  return parseInt(dims[dims.length - 1], 10);
}

function getStrategyFromJSONL(
  indexed: Map<string, number[]>,
  prefix: string,
  bucket: number,
  isV2: boolean,
): number[] | null {
  if (!isV2) return indexed.get(prefix + bucket) || null;
  let sums: number[] | null = null;
  let count = 0;
  for (const [key, probs] of indexed) {
    if (!key.startsWith(prefix)) continue;
    if (extractBucket(key) !== bucket) continue;
    if (!sums) sums = new Array(probs.length).fill(0);
    for (let i = 0; i < probs.length; i++) sums[i] += probs[i];
    count++;
  }
  return sums && count > 0 ? sums.map((s) => s / count) : null;
}

/**
 * Simulate one hand:
 * 1. Sample OOP + IP hands from ranges
 * 2. Sample turn + river cards
 * 3. Walk the game tree, choosing actions based on solved strategies
 * 4. Return the payoff
 */
function simulateHand(
  tree: ActionNode,
  indexed: Map<string, number[]>,
  isV2: boolean,
  boardId: number,
  flopCards: number[],
  oopRange: Array<[number, number]>,
  ipRange: Array<[number, number]>,
  rng: { state: number },
  bucketCount: number,
  oopFlopBuckets: Map<string, number>,
  ipFlopBuckets: Map<string, number>,
): { oopPayoff: number; ipPayoff: number } | null {
  // 1. Sample hands
  nextRng(rng);
  const oopHand = oopRange[rng.state % oopRange.length];
  const usedCards = new Set([...flopCards, oopHand[0], oopHand[1]]);

  // Filter IP range for non-conflicting
  const validIP = ipRange.filter(([c1, c2]) => !usedCards.has(c1) && !usedCards.has(c2));
  if (validIP.length === 0) return null;
  nextRng(rng);
  const ipHand = validIP[rng.state % validIP.length];
  usedCards.add(ipHand[0]);
  usedCards.add(ipHand[1]);

  // 2. Sample turn + river
  const available: number[] = [];
  for (let c = 0; c < 52; c++) if (!usedCards.has(c)) available.push(c);
  nextRng(rng);
  const tIdx = rng.state % available.length;
  const turnCard = available[tIdx];
  const availRiver = available.filter((_, i) => i !== tIdx);
  nextRng(rng);
  const riverCard = availRiver[rng.state % availRiver.length];

  // 3. Compute buckets per street (flop precomputed, turn/river computed per hand)
  const turnBoard = [...flopCards, turnCard];
  const riverBoard = [...flopCards, turnCard, riverCard];

  const oopKey = `${Math.min(oopHand[0], oopHand[1])},${Math.max(oopHand[0], oopHand[1])}`;
  const ipKey = `${Math.min(ipHand[0], ipHand[1])},${Math.max(ipHand[0], ipHand[1])}`;
  const oopFlopB = oopFlopBuckets.get(oopKey);
  const ipFlopB = ipFlopBuckets.get(ipKey);
  if (oopFlopB === undefined || ipFlopB === undefined) return null;

  // For turn/river, compute percentile buckets
  const oopTurnB = quickPercentileBucket(oopHand, turnBoard, oopRange, bucketCount);
  const ipTurnB = quickPercentileBucket(ipHand, turnBoard, ipRange, bucketCount);
  const oopRiverB = quickPercentileBucket(oopHand, riverBoard, oopRange, bucketCount);
  const ipRiverB = quickPercentileBucket(ipHand, riverBoard, ipRange, bucketCount);

  // 4. Showdown
  const oopCards = [
    indexToCard(oopHand[0]),
    indexToCard(oopHand[1]),
    ...riverBoard.map(indexToCard),
  ];
  const ipCards = [indexToCard(ipHand[0]), indexToCard(ipHand[1]), ...riverBoard.map(indexToCard)];
  const oopEval = evaluateBestHand(oopCards);
  const ipEval = evaluateBestHand(ipCards);
  const cmp = compareHands(oopEval, ipEval);
  const showdownResult = cmp > 0 ? 1 : cmp < 0 ? -1 : 0;

  // 5. Walk tree
  const buckets = {
    FLOP: [oopFlopB, ipFlopB],
    TURN: [oopTurnB, ipTurnB],
    RIVER: [oopRiverB, ipRiverB],
  };

  const result = walkTree(tree, indexed, isV2, boardId, buckets, showdownResult, rng, bucketCount);
  return result;
}

function buildInfoKeyLocal(
  street: Street,
  boardId: number,
  player: number,
  historyKey: string,
  buckets: Record<string, number[]>,
): string {
  const streetChar = street === 'FLOP' ? 'F' : street === 'TURN' ? 'T' : 'R';
  const flopB = buckets.FLOP[player];
  switch (street) {
    case 'FLOP':
      return `${streetChar}|${boardId}|${player}|${historyKey}|${flopB}`;
    case 'TURN':
      return `${streetChar}|${boardId}|${player}|${historyKey}|${flopB}-${buckets.TURN[player]}`;
    case 'RIVER':
      return `${streetChar}|${boardId}|${player}|${historyKey}|${flopB}-${buckets.TURN[player]}-${buckets.RIVER[player]}`;
  }
}

function walkTree(
  node: GameNode,
  indexed: Map<string, number[]>,
  isV2: boolean,
  boardId: number,
  buckets: Record<string, number[]>,
  showdownResult: number,
  rng: { state: number },
  bucketCount: number,
): { oopPayoff: number; ipPayoff: number } {
  if (node.type === 'terminal') {
    const startTotal = (node.playerStacks[0] + node.playerStacks[1] + node.pot) / 2;

    if (!node.showdown) {
      const folder = node.lastToAct;
      const oopPayoff =
        folder === 0
          ? node.playerStacks[0] - startTotal
          : node.playerStacks[0] + node.pot - startTotal;
      return { oopPayoff, ipPayoff: -oopPayoff };
    }

    if (showdownResult === 0) {
      const oopPayoff = node.playerStacks[0] + node.pot / 2 - startTotal;
      return { oopPayoff, ipPayoff: -oopPayoff };
    }

    const oopWins = showdownResult > 0;
    const oopPayoff = oopWins
      ? node.playerStacks[0] + node.pot - startTotal
      : node.playerStacks[0] - startTotal;
    return { oopPayoff, ipPayoff: -oopPayoff };
  }

  const act = node as ActionNode;
  const player = act.player;
  const numActions = act.actions.length;

  // Build info key and get strategy
  const infoKey = buildInfoKeyLocal(act.street, boardId, player, act.historyKey, buckets);
  const prefix = infoKey.substring(0, infoKey.lastIndexOf('|') + 1);
  const bucketVal = parseInt(
    infoKey
      .substring(infoKey.lastIndexOf('|') + 1)
      .split('-')
      .pop()!,
    10,
  );

  const probs = getStrategyFromJSONL(indexed, prefix, bucketVal, isV2);

  // Choose action based on strategy
  let chosenAction = 0;
  if (probs && probs.length === numActions) {
    nextRng(rng);
    const r = rng.state / 0x7fffffff;
    let cum = 0;
    for (let a = 0; a < numActions; a++) {
      cum += probs[a];
      if (r <= cum) {
        chosenAction = a;
        break;
      }
    }
  } else {
    // Fallback: uniform random
    nextRng(rng);
    chosenAction = rng.state % numActions;
  }

  const child = act.children.get(act.actions[chosenAction])!;
  return walkTree(child, indexed, isV2, boardId, buckets, showdownResult, rng, bucketCount);
}

function quickPercentileBucket(
  hand: [number, number],
  board: number[],
  range: Array<[number, number]>,
  numBuckets: number,
): number {
  const handCards = [indexToCard(hand[0]), indexToCard(hand[1]), ...board.map(indexToCard)];
  const handValue = evaluateBestHand(handCards).value;
  let weaker = 0;
  let total = 0;
  for (const [c1, c2] of range) {
    if (c1 === hand[0] || c1 === hand[1] || c2 === hand[0] || c2 === hand[1]) continue;
    let conflict = false;
    for (const bc of board) {
      if (c1 === bc || c2 === bc) {
        conflict = true;
        break;
      }
    }
    if (conflict) continue;
    const cards = [indexToCard(c1), indexToCard(c2), ...board.map(indexToCard)];
    const v = evaluateBestHand(cards).value;
    total++;
    if (v < handValue) weaker++;
    else if (v === handValue) weaker += 0.5;
  }
  if (total === 0) return Math.floor(numBuckets / 2);
  return Math.min(numBuckets - 1, Math.floor((weaker / total) * numBuckets));
}

function nextRng(rng: { state: number }): number {
  rng.state = (rng.state * 1103515245 + 12345) & 0x7fffffff;
  return rng.state;
}

// ─── Main ───

async function main(): Promise<void> {
  if (!boardArg) {
    console.error('Error: --board is required (e.g., --board "Tc Qc Ad")');
    process.exit(1);
  }

  const flopCards = boardArg.trim().split(/\s+/).map(cardToIndex);
  if (flopCards.length !== 3) {
    console.error('Error: Board must have exactly 3 cards');
    process.exit(1);
  }

  const dataDir = findDataDir();
  const board = findBoardByCards(dataDir, flopCards);
  if (!board) {
    console.error(`Board ${boardArg} not found. Check data directory.`);
    process.exit(1);
  }

  const treeConfig = getTreeConfig(configName);
  const tree = buildTree(treeConfig);
  const indexed = loadJSONL(dataDir, board.boardId);
  const isV2 = detectV2(indexed);
  const bucketCount = board.bucketCount;

  // Load ranges
  const chartsPath = resolve(PROJECT_ROOT, 'data/preflop_charts.json');
  const cfg = CONFIG_RANGES[configName] || CONFIG_RANGES['v1_50bb'];
  const oopRange = loadRange(chartsPath, cfg.oopSpot, cfg.oopAction, cfg.minFrequency);
  const ipRange = loadRange(chartsPath, cfg.ipSpot, cfg.ipAction);

  // Filter out dead cards
  const dead = new Set(flopCards);
  const oopFiltered = oopRange.filter(([c1, c2]) => !dead.has(c1) && !dead.has(c2));
  const ipFiltered = ipRange.filter(([c1, c2]) => !dead.has(c1) && !dead.has(c2));

  // Precompute flop buckets (expensive - do once)
  console.log(`\n${'═'.repeat(60)}`);
  console.log(`  Self-Play Monte Carlo Verification`);
  console.log(`  Config: ${configName}`);
  console.log(`  Board: ${flopCards.map(indexToCard).join(' ')} (ID: ${board.boardId})`);
  console.log(`  Hands: ${numHands.toLocaleString()}`);
  console.log(`  Buckets: ${bucketCount} | Iterations: ${board.iterations.toLocaleString()}`);
  console.log(`${'═'.repeat(60)}\n`);

  console.log(`  OOP range: ${oopFiltered.length} combos`);
  console.log(`  IP range: ${ipFiltered.length} combos`);
  console.log(`  JSONL entries: ${indexed.size}`);
  console.log(`  Key format: ${isV2 ? 'V2 (multi-dim)' : 'V1 (flat)'}\n`);

  console.log('  Precomputing flop buckets...');
  const oopFlopBuckets = computeHandBuckets(oopFiltered, flopCards, bucketCount);
  const ipFlopBuckets = computeHandBuckets(ipFiltered, flopCards, bucketCount);
  console.log(
    `  OOP flop buckets: ${oopFlopBuckets.size}, IP flop buckets: ${ipFlopBuckets.size}\n`,
  );

  console.log('  Simulating...');
  const startTime = Date.now();
  const rng = { state: Date.now() & 0x7fffffff };

  let sumOOP = 0;
  let sumIP = 0;
  let sumOOP2 = 0; // for variance
  let validHands = 0;
  for (let h = 0; h < numHands; h++) {
    const result = simulateHand(
      tree,
      indexed,
      isV2,
      board.boardId,
      flopCards,
      oopFiltered,
      ipFiltered,
      rng,
      bucketCount,
      oopFlopBuckets,
      ipFlopBuckets,
    );

    if (!result) continue;

    sumOOP += result.oopPayoff;
    sumIP += result.ipPayoff;
    sumOOP2 += result.oopPayoff * result.oopPayoff;
    validHands++;

    if ((h + 1) % 10000 === 0) {
      const avg = sumOOP / validHands;
      process.stdout.write(
        `\r  ${(h + 1).toLocaleString()} hands... OOP avg = ${avg.toFixed(4)} bb/hand`,
      );
    }
  }

  const elapsed = Date.now() - startTime;
  console.log();

  // Results
  const avgOOP = validHands > 0 ? sumOOP / validHands : 0;
  const avgIP = validHands > 0 ? sumIP / validHands : 0;
  const variance = validHands > 1 ? sumOOP2 / validHands - avgOOP * avgOOP : 0;
  const stddev = Math.sqrt(variance);
  const stderr = validHands > 0 ? stddev / Math.sqrt(validHands) : 0;

  console.log(`\n${'─'.repeat(60)}`);
  console.log('  Results');
  console.log(`${'─'.repeat(60)}\n`);

  console.log(`  Valid hands:     ${validHands.toLocaleString()} / ${numHands.toLocaleString()}`);
  console.log(`  Elapsed:         ${(elapsed / 1000).toFixed(1)}s`);
  console.log(`  Speed:           ${Math.round(validHands / (elapsed / 1000))} hands/sec\n`);

  console.log(
    `  OOP avg profit:  ${avgOOP >= 0 ? '+' : ''}${avgOOP.toFixed(4)} bb/hand  (±${(stderr * 1.96).toFixed(4)})`,
  );
  console.log(
    `  IP avg profit:   ${avgIP >= 0 ? '+' : ''}${avgIP.toFixed(4)} bb/hand  (±${(stderr * 1.96).toFixed(4)})`,
  );
  console.log(`  Game value:      ${(avgOOP + avgIP).toFixed(6)} bb/hand (should be ~0)\n`);

  // Assessment
  const absGameValue = Math.abs(avgOOP);
  const potFrac = absGameValue / treeConfig.startingPot;
  if (potFrac < 0.01) {
    console.log(`  Assessment: EXCELLENT — game value < 1% of pot`);
  } else if (potFrac < 0.05) {
    console.log(`  Assessment: GOOD — game value < 5% of pot`);
  } else if (potFrac < 0.1) {
    console.log(`  Assessment: ACCEPTABLE — game value < 10% of pot`);
  } else {
    console.log(`  Assessment: POTENTIAL ISSUE — game value > 10% of pot`);
  }
  console.log(`  (Game value as % of pot: ${(potFrac * 100).toFixed(2)}%)\n`);
}

main().catch((err) => {
  console.error('Error:', err);
  process.exit(1);
});
