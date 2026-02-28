#!/usr/bin/env tsx
// CLI tool for comparing CardPilot CFR strategies with external solvers.
//
// Usage:
//   # Export CardPilot strategies for a board (to compare manually with GTO Wizard)
//   npx tsx src/cli/compare-gto.ts --export --config hu_btn_bb_srp_50bb --board "Ah Ts 2c"
//
//   # Compare CardPilot vs external solver data
//   npx tsx src/cli/compare-gto.ts --compare --config hu_btn_bb_srp_50bb --file data/gto-comparison/srp50bb_AhTs2c.json
//
//   # List all solved boards for a config
//   npx tsx src/cli/compare-gto.ts --list --config hu_btn_bb_srp_50bb

import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { cardToIndex, indexToCard } from '../abstraction/card-index.js';
import { evaluateBestHand } from '@cardpilot/poker-evaluator';
import { getTreeConfig, getConfigOutputDir, getConfigLabel, type TreeConfigName } from '../tree/tree-config.js';

// ─── Project root resolution ───

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

// ─── CLI argument parsing ───

const args = process.argv.slice(2);
const hasFlag = (name: string) => args.includes(`--${name}`);
function getStringArg(name: string, defaultVal: string): string {
  const idx = args.indexOf(`--${name}`);
  if (idx !== -1 && args[idx + 1]) return args[idx + 1];
  return defaultVal;
}

const mode = hasFlag('export') ? 'export' : hasFlag('compare') ? 'compare' : hasFlag('list') ? 'list' : 'help';
const configName = getStringArg('config', 'hu_btn_bb_srp_50bb') as TreeConfigName;
const boardArg = getStringArg('board', '');
const fileArg = getStringArg('file', '');
const playerArg = getStringArg('player', 'both'); // 'oop', 'ip', or 'both'
const nodeArg = getStringArg('node', 'root'); // 'root' or action history like 'x' (after BB checks)
const dataDirOverride = getStringArg('data-dir', ''); // override data directory

// ─── Card utilities ───

const RANKS = '23456789TJQKA';
const SUITS = ['c', 'd', 'h', 's'];

function comboToHandClass(c1: number, c2: number): string {
  const r1 = Math.floor(c1 / 4);
  const r2 = Math.floor(c2 / 4);
  const s1 = c1 % 4;
  const s2 = c2 % 4;
  const high = Math.max(r1, r2);
  const low = Math.min(r1, r2);
  const highChar = RANKS[high];
  const lowChar = RANKS[low];
  if (r1 === r2) return `${highChar}${lowChar}`;
  return s1 === s2 ? `${highChar}${lowChar}s` : `${highChar}${lowChar}o`;
}

function expandHandClassToCombos(handClass: string): Array<[number, number]> {
  const hand = handClass.toUpperCase();
  const combos: Array<[number, number]> = [];

  if (hand.length === 2 && hand[0] === hand[1]) {
    const rank = RANKS.indexOf(hand[0]);
    if (rank < 0) return combos;
    for (let s1 = 0; s1 < 4; s1++) {
      for (let s2 = s1 + 1; s2 < 4; s2++) {
        combos.push([rank * 4 + s1, rank * 4 + s2]);
      }
    }
    return combos;
  }

  const suffix = hand.length === 3 ? hand[2] : '';
  const rankA = RANKS.indexOf(hand[0]);
  const rankB = RANKS.indexOf(hand[1]);
  if (rankA < 0 || rankB < 0) return combos;

  if (suffix === 'S') {
    for (let suit = 0; suit < 4; suit++) {
      const c1 = rankA * 4 + suit;
      const c2 = rankB * 4 + suit;
      combos.push([Math.min(c1, c2), Math.max(c1, c2)]);
    }
  } else {
    for (let sA = 0; sA < 4; sA++) {
      for (let sB = 0; sB < 4; sB++) {
        if (suffix === 'S' && sA !== sB) continue;
        if (suffix === 'O' && sA === sB) continue;
        if (!suffix && sA === sB) continue;
        const c1 = rankA * 4 + sA;
        const c2 = rankB * 4 + sB;
        combos.push([Math.min(c1, c2), Math.max(c1, c2)]);
      }
    }
  }

  return combos;
}

// ─── Preflop range loading (inlined for standalone CLI) ───

interface RangeEntry {
  hand: string;
  mix: Record<string, number>;
  spot: string;
}

const DEFAULT_BTN_BB_SRP = { ipSpot: 'BTN_unopened_open2.5x', oopSpot: 'BB_vs_BTN_facing_open2.5x', ipAction: 'raise', oopAction: 'call' };

const CONFIG_RANGES: Record<string, { ipSpot: string; oopSpot: string; ipAction: string; oopAction: string; minFrequency?: number }> = {
  v1_50bb: DEFAULT_BTN_BB_SRP,
  standard_50bb: DEFAULT_BTN_BB_SRP,
  standard_100bb: DEFAULT_BTN_BB_SRP,
  pipeline_srp: DEFAULT_BTN_BB_SRP,
  pipeline_3bet: { ipSpot: 'BTN_unopened_open2.5x', oopSpot: 'BB_vs_BTN_facing_open2.5x', ipAction: 'raise', oopAction: 'raise', minFrequency: 0.40 },
  hu_btn_bb_srp_100bb: { ipSpot: 'BTN_unopened_open2.5x', oopSpot: 'BB_vs_BTN_facing_open2.5x', ipAction: 'raise', oopAction: 'call' },
  hu_btn_bb_3bp_100bb: { ipSpot: 'BTN_unopened_open2.5x', oopSpot: 'BB_vs_BTN_facing_open2.5x', ipAction: 'raise', oopAction: 'raise', minFrequency: 0.40 },
  hu_btn_bb_srp_50bb: { ipSpot: 'BTN_unopened_open2.5x', oopSpot: 'BB_vs_BTN_facing_open2.5x', ipAction: 'raise', oopAction: 'call' },
  hu_btn_bb_3bp_50bb: { ipSpot: 'BTN_unopened_open2.5x', oopSpot: 'BB_vs_BTN_facing_open2.5x', ipAction: 'raise', oopAction: 'raise', minFrequency: 0.40 },
  hu_co_bb_srp_100bb: { ipSpot: 'CO_unopened_open2.5x', oopSpot: 'BB_vs_CO_facing_open2.5x', ipAction: 'raise', oopAction: 'call' },
  hu_co_bb_3bp_100bb: { ipSpot: 'CO_unopened_open2.5x', oopSpot: 'BB_vs_CO_facing_open2.5x', ipAction: 'raise', oopAction: 'raise', minFrequency: 0.50 },
  hu_utg_bb_srp_100bb: { ipSpot: 'UTG_unopened_open2.5x', oopSpot: 'BB_vs_UTG_facing_open2.5x', ipAction: 'raise', oopAction: 'call' },
};

function loadRange(chartsPath: string, spot: string, action: string, minFreq?: number): Array<[number, number]> {
  const allEntries = JSON.parse(readFileSync(chartsPath, 'utf-8')) as RangeEntry[];
  const entries = allEntries.filter(e => e.spot === spot);
  const combos: Array<[number, number]> = [];
  const seen = new Set<string>();

  for (const entry of entries) {
    const freq = entry.mix[action];
    if (typeof freq !== 'number' || freq <= 0) continue;
    if (minFreq !== undefined && freq < minFreq) continue;
    for (const combo of expandHandClassToCombos(entry.hand)) {
      const key = `${combo[0]},${combo[1]}`;
      if (seen.has(key)) continue;
      seen.add(key);
      combos.push(combo);
    }
  }
  return combos;
}

function loadRangesForConfig(configName: string): { oop: Array<[number, number]>; ip: Array<[number, number]> } {
  const chartsPath = resolve(PROJECT_ROOT, 'data/preflop_charts.json');
  const cfg = CONFIG_RANGES[configName];
  if (!cfg) {
    console.error(`Unknown config for range loading: ${configName}`);
    process.exit(1);
  }
  return {
    ip: loadRange(chartsPath, cfg.ipSpot, cfg.ipAction, cfg.minFrequency),
    oop: loadRange(chartsPath, cfg.oopSpot, cfg.oopAction),
  };
}

// ─── Hand bucketing (equity-based) ───

function computeHandBuckets(
  range: Array<[number, number]>,
  boardCards: number[],
  numBuckets: number,
): Map<string, number> {
  const dead = new Set(boardCards);
  const ranked: Array<{ c1: number; c2: number; value: number }> = [];

  for (const [c1, c2] of range) {
    if (dead.has(c1) || dead.has(c2)) continue;
    const cards = [indexToCard(c1), indexToCard(c2), ...boardCards.map(indexToCard)];
    const ev = evaluateBestHand(cards);
    ranked.push({ c1, c2, value: ev.value });
  }

  ranked.sort((a, b) => a.value - b.value);
  const bucketSize = Math.max(1, Math.ceil(ranked.length / numBuckets));
  const result = new Map<string, number>();

  for (let i = 0; i < ranked.length; i++) {
    const bucket = Math.min(Math.floor(i / bucketSize), numBuckets - 1);
    const key = ranked[i].c1 < ranked[i].c2
      ? `${ranked[i].c1},${ranked[i].c2}`
      : `${ranked[i].c2},${ranked[i].c1}`;
    result.set(key, bucket);
  }
  return result;
}

function buildHandClassMap(
  buckets: Map<string, number>,
  range: Array<[number, number]>,
  boardCards: number[],
): Record<string, number> {
  const dead = new Set(boardCards);
  const classBuckets = new Map<string, number[]>();

  for (const [c1, c2] of range) {
    if (dead.has(c1) || dead.has(c2)) continue;
    const key = c1 < c2 ? `${c1},${c2}` : `${c2},${c1}`;
    const bucket = buckets.get(key);
    if (bucket === undefined) continue;
    const handClass = comboToHandClass(c1, c2);
    if (!classBuckets.has(handClass)) classBuckets.set(handClass, []);
    classBuckets.get(handClass)!.push(bucket);
  }

  const result: Record<string, number> = {};
  for (const [cls, bkts] of classBuckets) {
    bkts.sort((a, b) => a - b);
    result[cls] = bkts[Math.floor(bkts.length / 2)]; // median bucket
  }
  return result;
}

// ─── JSONL data loading ───

interface BoardMeta {
  boardId: number;
  flopCards: number[];
  bucketCount: number;
  iterations: number;
  infoSets: number;
  elapsedMs: number;
  betSizes?: { flop: number[]; turn: number[]; river: number[] };
}

function findDataDir(configName: string): string {
  if (dataDirOverride) {
    const abs = resolve(PROJECT_ROOT, dataDirOverride);
    if (existsSync(abs)) return abs;
    if (existsSync(dataDirOverride)) return dataDirOverride;
    return abs;
  }
  const outputDir = getConfigOutputDir(configName as TreeConfigName);
  const candidates = [
    resolve(PROJECT_ROOT, 'data/cfr', outputDir),
    resolve(process.cwd(), 'data/cfr', outputDir),
  ];
  for (const p of candidates) {
    if (existsSync(p)) return p;
  }
  return candidates[0];
}

function listSolvedBoards(dataDir: string): BoardMeta[] {
  if (!existsSync(dataDir)) return [];
  const files = readdirSync(dataDir).filter(f => f.endsWith('.meta.json'));
  const boards: BoardMeta[] = [];
  for (const f of files) {
    const meta = JSON.parse(readFileSync(join(dataDir, f), 'utf-8'));
    boards.push(meta);
  }
  return boards.sort((a, b) => a.boardId - b.boardId);
}

function findBoardByCards(dataDir: string, targetCards: number[]): BoardMeta | null {
  const sorted = [...targetCards].sort((a, b) => a - b);
  const boards = listSolvedBoards(dataDir);
  for (const board of boards) {
    const boardSorted = [...board.flopCards].sort((a, b) => a - b);
    if (boardSorted[0] === sorted[0] && boardSorted[1] === sorted[1] && boardSorted[2] === sorted[2]) {
      return board;
    }
  }
  return null;
}

function loadJSONL(dataDir: string, boardId: number): Map<string, number[]> {
  const padded = String(boardId).padStart(3, '0');
  const jsonlPath = join(dataDir, `flop_${padded}.jsonl`);
  if (!existsSync(jsonlPath)) {
    console.error(`JSONL file not found: ${jsonlPath}`);
    process.exit(1);
  }

  const indexed = new Map<string, number[]>();
  const lines = readFileSync(jsonlPath, 'utf-8').split('\n');
  for (const line of lines) {
    if (!line.trim()) continue;
    const entry = JSON.parse(line);
    indexed.set(entry.key, entry.probs);
  }
  return indexed;
}

// ─── Strategy extraction ───

function getActionLabels(betSizes: number[], facingBet: boolean): string[] {
  if (facingBet) {
    const labels = ['Fold', 'Call'];
    for (const size of betSizes) {
      labels.push(`Raise ${Math.round(size * 100)}%`);
    }
    labels.push('All-in');
    return labels;
  }
  const labels = ['Check'];
  for (const size of betSizes) {
    labels.push(`Bet ${Math.round(size * 100)}%`);
  }
  labels.push('All-in');
  return labels;
}

function detectKeyFormat(indexed: Map<string, number[]>): boolean {
  for (const key of indexed.keys()) {
    const parts = key.split('|');
    if (parts.length >= 5) {
      const suffix = parts[parts.length - 1];
      if (suffix.includes('-')) return true;
    }
  }
  return false;
}

function extractPrimaryBucket(key: string): number {
  const parts = key.split('|');
  const suffix = parts[parts.length - 1];
  const dims = suffix.split('-');
  return parseInt(dims[dims.length - 1], 10);
}

function getProbs(
  indexed: Map<string, number[]>,
  prefix: string,
  bucket: number,
  isV2: boolean,
  bucketCount: number,
): number[] | null {
  if (!isV2) {
    return indexed.get(prefix + bucket) || null;
  }

  // V2: aggregate all entries matching prefix where primary bucket matches
  let sums: number[] | null = null;
  let count = 0;
  for (const [key, probs] of indexed) {
    if (!key.startsWith(prefix)) continue;
    if (extractPrimaryBucket(key) !== bucket) continue;
    if (!sums) sums = new Array(probs.length).fill(0);
    for (let i = 0; i < probs.length; i++) sums[i] += probs[i];
    count++;
  }
  if (!sums || count === 0) return null;
  return sums.map(s => s / count);
}

function extractStrategiesForPlayer(
  indexed: Map<string, number[]>,
  handMap: Record<string, number>,
  boardId: number,
  player: number,
  historyKey: string,
  betSizes: number[],
  bucketCount: number,
): {
  strategies: Record<string, number[]>;
  actions: string[];
  aggregate: Record<string, number>;
  handCount: number;
} {
  const street = historyKey.includes('/') ? (historyKey.split('/').length === 2 ? 'T' : 'R') : 'F';
  const prefix = `${street}|${boardId}|${player}|${historyKey}|`;
  const isV2 = detectKeyFormat(indexed);

  // Detect whether we're facing a bet (simplified: check last char of history)
  const lastChar = historyKey.length > 0 ? historyKey[historyKey.length - 1] : '';
  const facingBet = ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'A'].includes(lastChar);
  const streetBetSizes = betSizes; // already filtered to current street

  const actions = getActionLabels(streetBetSizes, facingBet);

  // Find a sample entry to determine actual number of actions
  let numActions = 0;
  for (const [key, probs] of indexed) {
    if (key.startsWith(prefix)) {
      numActions = probs.length;
      break;
    }
  }

  if (numActions === 0) {
    return { strategies: {}, actions, aggregate: {}, handCount: 0 };
  }

  // Trim action labels to match actual number of actions
  const actualActions = actions.slice(0, numActions);
  if (actualActions.length < numActions) {
    for (let i = actualActions.length; i < numActions; i++) {
      actualActions.push(`Action_${i}`);
    }
  }

  const strategies: Record<string, number[]> = {};
  const aggregateSums = new Array(numActions).fill(0);
  let totalHands = 0;

  for (const [handClass, bucket] of Object.entries(handMap)) {
    const probs = getProbs(indexed, prefix, bucket, isV2, bucketCount);
    if (!probs) continue;
    strategies[handClass] = probs.map(p => Math.round(p * 1000) / 1000);
    for (let i = 0; i < probs.length; i++) aggregateSums[i] += probs[i];
    totalHands++;
  }

  const aggregate: Record<string, number> = {};
  for (let i = 0; i < numActions; i++) {
    aggregate[actualActions[i]] = totalHands > 0
      ? Math.round((aggregateSums[i] / totalHands) * 1000) / 1000
      : 0;
  }

  return { strategies, actions: actualActions, aggregate, handCount: totalHands };
}

// ─── Comparison logic ───

interface ComparisonResult {
  handClass: string;
  cardpilot: number[];
  external: number[];
  l1: number;
  checkVsBetDiff: number;
}

function compareStrategies(
  cpStrategies: Record<string, number[]>,
  extStrategies: Record<string, number[]>,
): {
  results: ComparisonResult[];
  avgL1: number;
  maxL1: ComparisonResult | null;
  avgCheckDiff: number;
  compared: number;
} {
  const results: ComparisonResult[] = [];

  for (const [handClass, extProbs] of Object.entries(extStrategies)) {
    const cpProbs = cpStrategies[handClass];
    if (!cpProbs) continue;

    // Ensure same length by padding
    const maxLen = Math.max(cpProbs.length, extProbs.length);
    const cp = [...cpProbs];
    const ext = [...extProbs];
    while (cp.length < maxLen) cp.push(0);
    while (ext.length < maxLen) ext.push(0);

    let l1 = 0;
    for (let i = 0; i < maxLen; i++) {
      l1 += Math.abs(cp[i] - ext[i]);
    }

    // Check vs bet difference (first action is check/fold, rest are bets)
    const cpCheck = cp[0];
    const extCheck = ext[0];
    const checkVsBetDiff = Math.abs(cpCheck - extCheck);

    results.push({ handClass, cardpilot: cp, external: ext, l1, checkVsBetDiff });
  }

  results.sort((a, b) => b.l1 - a.l1);
  const avgL1 = results.length > 0 ? results.reduce((s, r) => s + r.l1, 0) / results.length : 0;
  const avgCheckDiff = results.length > 0 ? results.reduce((s, r) => s + r.checkVsBetDiff, 0) / results.length : 0;
  const maxL1 = results.length > 0 ? results[0] : null;

  return { results, avgL1, maxL1, avgCheckDiff, compared: results.length };
}

// ─── Commands ───

function cmdList(): void {
  const dataDir = findDataDir(configName);
  console.log(`Config: ${getConfigLabel(configName as TreeConfigName)}`);
  console.log(`Data dir: ${dataDir}\n`);

  const boards = listSolvedBoards(dataDir);
  if (boards.length === 0) {
    console.log('No solved boards found.');
    return;
  }

  console.log(`Solved boards: ${boards.length}\n`);
  console.log('  ID   Board           Iterations  InfoSets  Time');
  console.log('  ───  ──────────────  ──────────  ────────  ────');
  for (const b of boards.slice(0, 30)) {
    const label = b.flopCards.map(indexToCard).join(' ');
    const time = (b.elapsedMs / 1000).toFixed(0);
    console.log(`  ${String(b.boardId).padStart(3)}  ${label.padEnd(14)}  ${String(b.iterations).padStart(10)}  ${String(b.infoSets).padStart(8)}  ${time}s`);
  }
  if (boards.length > 30) {
    console.log(`  ... and ${boards.length - 30} more`);
  }
}

function cmdExport(): void {
  if (!boardArg) {
    console.error('Error: --board is required (e.g., --board "Ah Ts 2c")');
    process.exit(1);
  }

  const boardCards = boardArg.trim().split(/\s+/).map(cardToIndex);
  if (boardCards.length !== 3) {
    console.error('Error: Board must have exactly 3 cards');
    process.exit(1);
  }

  const dataDir = findDataDir(configName);
  const board = findBoardByCards(dataDir, boardCards);
  if (!board) {
    console.error(`Board ${boardArg} not found in ${configName}.`);
    console.error('Use --list to see available boards.');
    process.exit(1);
  }

  const treeConfig = getTreeConfig(configName as TreeConfigName);
  const indexed = loadJSONL(dataDir, board.boardId);
  const ranges = loadRangesForConfig(configName);
  const bucketCount = board.bucketCount;

  // Determine which node/history to export
  const historyKey = nodeArg === 'root' ? '' : nodeArg;

  // Detect the street from history
  const streetSeparators = (historyKey.match(/\//g) || []).length;
  const streetBetSizes = streetSeparators === 0
    ? treeConfig.betSizes.flop
    : streetSeparators === 1
      ? treeConfig.betSizes.turn
      : treeConfig.betSizes.river;

  const players = playerArg === 'oop' ? [0] : playerArg === 'ip' ? [1] : [0, 1];
  const playerLabels = ['OOP (BB)', 'IP (BTN)'];

  const exportData: Record<string, any> = {
    config: configName,
    configLabel: getConfigLabel(configName as TreeConfigName),
    board: boardCards.map(indexToCard).join(' '),
    boardId: board.boardId,
    node: nodeArg,
    historyKey,
    iterations: board.iterations,
    bucketCount,
    betSizes: treeConfig.betSizes,
    players: {} as Record<string, any>,
  };

  for (const player of players) {
    const range = player === 0 ? ranges.oop : ranges.ip;
    const oopBuckets = computeHandBuckets(range, boardCards, bucketCount);
    const handMap = buildHandClassMap(oopBuckets, range, boardCards);

    // Determine which player is acting at this node
    // At root (empty history), player 0 (OOP/BB) acts first
    // After each action, player alternates (simplified)
    const result = extractStrategiesForPlayer(
      indexed, handMap, board.boardId, player, historyKey, streetBetSizes, bucketCount,
    );

    const label = playerLabels[player];
    exportData.players[label] = {
      player,
      actions: result.actions,
      aggregate: result.aggregate,
      handCount: result.handCount,
      strategies: result.strategies,
    };
  }

  // Print summary to console
  console.log(`\n${'═'.repeat(60)}`);
  console.log(`  CardPilot Strategy Export`);
  console.log(`  Config: ${getConfigLabel(configName as TreeConfigName)}`);
  console.log(`  Board: ${boardCards.map(indexToCard).join(' ')} (ID: ${board.boardId})`);
  console.log(`  Node: ${nodeArg} | Iterations: ${board.iterations.toLocaleString()}`);
  console.log(`${'═'.repeat(60)}\n`);

  for (const player of players) {
    const label = playerLabels[player];
    const data = exportData.players[label];
    if (data.handCount === 0) {
      console.log(`  ${label}: No data at this node\n`);
      continue;
    }

    console.log(`  ${label} (${data.handCount} hand classes):`);
    console.log(`  Actions: ${data.actions.join(' | ')}`);
    console.log(`  Aggregate: ${Object.entries(data.aggregate).map(([k, v]) => `${k} ${((v as number) * 100).toFixed(1)}%`).join(' | ')}`);
    console.log();

    // Print top hands as a table
    const entries = Object.entries(data.strategies as Record<string, number[]>);
    entries.sort((a, b) => {
      // Sort by hand strength: pairs first, then suited, then offsuit
      const rankOrder = (h: string) => {
        const r1 = RANKS.indexOf(h[0]);
        const r2 = RANKS.indexOf(h[1]);
        return -(r1 * 14 + r2) + (h.endsWith('s') ? 0.5 : h.length === 2 ? 1 : 0);
      };
      return rankOrder(a[0]) - rankOrder(b[0]);
    });

    console.log(`  ${'Hand'.padEnd(6)}${data.actions.map((a: string) => a.padStart(10)).join('')}`);
    console.log(`  ${'─'.repeat(6)}${data.actions.map(() => '─'.repeat(10)).join('')}`);
    for (const [hand, probs] of entries) {
      const probStrs = (probs as number[]).map(p => `${(p * 100).toFixed(1)}%`.padStart(10));
      console.log(`  ${hand.padEnd(6)}${probStrs.join('')}`);
    }
    console.log();
  }

  // Save to file
  const outputDir = resolve(PROJECT_ROOT, 'data/gto-comparison');
  mkdirSync(outputDir, { recursive: true });

  const boardLabel = boardCards.map(indexToCard).join('');
  const outputPath = join(outputDir, `export_${configName}_${boardLabel}.json`);
  writeFileSync(outputPath, JSON.stringify(exportData, null, 2), 'utf-8');
  console.log(`  Saved to: ${outputPath}`);
}

function cmdCompare(): void {
  if (!fileArg) {
    console.error('Error: --file is required (path to external solver JSON)');
    process.exit(1);
  }

  if (!existsSync(fileArg)) {
    console.error(`File not found: ${fileArg}`);
    process.exit(1);
  }

  // Load external data
  const extData = JSON.parse(readFileSync(fileArg, 'utf-8'));
  const extBoard = extData.board as string;
  const extStrategies = extData.strategies as Record<string, number[]>;
  const extActions = extData.actions as string[] | undefined;
  const extPlayer = extData.player as string | undefined;
  const extSource = extData.source as string || 'External';

  if (!extStrategies || Object.keys(extStrategies).length === 0) {
    console.error('Error: External file has no strategies data');
    process.exit(1);
  }

  // Resolve board
  const boardCards = extBoard
    ? extBoard.trim().split(/\s+/).map(cardToIndex)
    : boardArg.trim().split(/\s+/).map(cardToIndex);

  if (boardCards.length !== 3) {
    console.error('Error: Board must have exactly 3 cards');
    process.exit(1);
  }

  const dataDir = findDataDir(configName);
  const board = findBoardByCards(dataDir, boardCards);
  if (!board) {
    console.error(`Board ${boardCards.map(indexToCard).join(' ')} not found in ${configName}`);
    process.exit(1);
  }

  const treeConfig = getTreeConfig(configName as TreeConfigName);
  const indexed = loadJSONL(dataDir, board.boardId);
  const ranges = loadRangesForConfig(configName);
  const bucketCount = board.bucketCount;

  const historyKey = nodeArg === 'root' ? '' : nodeArg;
  const streetSeparators = (historyKey.match(/\//g) || []).length;
  const streetBetSizes = streetSeparators === 0
    ? treeConfig.betSizes.flop
    : streetSeparators === 1
      ? treeConfig.betSizes.turn
      : treeConfig.betSizes.river;

  // Determine player
  const player = (extPlayer === 'IP' || extPlayer === 'ip') ? 1 : 0;
  const range = player === 0 ? ranges.oop : ranges.ip;
  const playerLabel = player === 0 ? 'OOP (BB)' : 'IP (BTN)';

  const buckets = computeHandBuckets(range, boardCards, bucketCount);
  const handMap = buildHandClassMap(buckets, range, boardCards);

  const cpResult = extractStrategiesForPlayer(
    indexed, handMap, board.boardId, player, historyKey, streetBetSizes, bucketCount,
  );

  // Compare
  const comparison = compareStrategies(cpResult.strategies, extStrategies);

  // Print report
  console.log(`\n${'═'.repeat(70)}`);
  console.log(`  CFR Comparison: ${configName} | Board: ${boardCards.map(indexToCard).join(' ')}`);
  console.log(`  Node: ${nodeArg} (${playerLabel}) | Source: ${extSource}`);
  console.log(`  Compared: ${comparison.compared}/${Object.keys(extStrategies).length} hand classes`);
  console.log(`${'═'.repeat(70)}\n`);

  // Overall metrics
  const status = comparison.avgL1 < 0.10 ? 'GOOD' : comparison.avgL1 < 0.20 ? 'ACCEPTABLE' : 'SIGNIFICANT DEVIATION';
  console.log(`  Overall:`);
  console.log(`    Mean L1 deviation:    ${(comparison.avgL1 * 100).toFixed(1)}% — ${status}`);
  console.log(`    Check freq deviation: ${(comparison.avgCheckDiff * 100).toFixed(1)}%`);
  if (comparison.maxL1) {
    console.log(`    Max deviation:        ${comparison.maxL1.handClass} (${(comparison.maxL1.l1 * 100).toFixed(1)}%)`);
  }
  console.log();

  // Aggregate comparison
  if (cpResult.aggregate && extActions) {
    console.log(`  Aggregate frequencies:`);
    console.log(`  ${''.padEnd(12)}${'CardPilot'.padStart(12)}${'External'.padStart(12)}${'Diff'.padStart(10)}`);
    console.log(`  ${'─'.repeat(46)}`);
    for (let i = 0; i < cpResult.actions.length; i++) {
      const cpFreq = cpResult.aggregate[cpResult.actions[i]] || 0;
      // Try to find matching external action
      const extLabel = i < extActions.length ? extActions[i] : cpResult.actions[i];
      const label = cpResult.actions[i];
      console.log(`  ${label.padEnd(12)}${((cpFreq) * 100).toFixed(1).padStart(11)}%${'?'.padStart(12)}${'N/A'.padStart(10)}`);
    }
    console.log();
  }

  // Top deviations
  const topN = Math.min(15, comparison.results.length);
  console.log(`  Top ${topN} deviations:`);
  console.log(`  ${'Hand'.padEnd(6)}${'CP'.padStart(30)}${'External'.padStart(30)}${'L1'.padStart(8)}`);
  console.log(`  ${'─'.repeat(74)}`);

  for (let i = 0; i < topN; i++) {
    const r = comparison.results[i];
    const cpStr = r.cardpilot.map(p => `${(p * 100).toFixed(0)}%`).join('/');
    const extStr = r.external.map(p => `${(p * 100).toFixed(0)}%`).join('/');
    console.log(`  ${r.handClass.padEnd(6)}${cpStr.padStart(30)}${extStr.padStart(30)}${((r.l1 * 100).toFixed(1) + '%').padStart(8)}`);
  }
  console.log();

  // Best matches
  const sorted = [...comparison.results].sort((a, b) => a.l1 - b.l1);
  const bestN = Math.min(5, sorted.length);
  console.log(`  Best ${bestN} matches:`);
  for (let i = 0; i < bestN; i++) {
    const r = sorted[i];
    const cpStr = r.cardpilot.map(p => `${(p * 100).toFixed(0)}%`).join('/');
    const extStr = r.external.map(p => `${(p * 100).toFixed(0)}%`).join('/');
    console.log(`  ${r.handClass.padEnd(6)}${cpStr.padStart(30)}${extStr.padStart(30)}${((r.l1 * 100).toFixed(1) + '%').padStart(8)}`);
  }
  console.log();

  // Rating
  console.log(`  Rating: ${comparison.avgL1 < 0.05 ? 'EXCELLENT (<5%)' : comparison.avgL1 < 0.10 ? 'GOOD (<10%)' : comparison.avgL1 < 0.20 ? 'ACCEPTABLE (<20%)' : 'NEEDS IMPROVEMENT (>20%)'}`);
  console.log(`  Threshold: <5% EXCELLENT | <10% GOOD | <20% ACCEPTABLE | >20% SIGNIFICANT\n`);
}

function cmdHelp(): void {
  console.log(`
CardPilot CFR Comparison Tool

Usage:
  npx tsx src/cli/compare-gto.ts --export --config <config> --board "<cards>"
  npx tsx src/cli/compare-gto.ts --compare --config <config> --file <json>
  npx tsx src/cli/compare-gto.ts --list --config <config>

Options:
  --export        Export CardPilot strategies to JSON for manual comparison
  --compare       Compare CardPilot vs external solver data
  --list          List all solved boards for a config
  --config <name> Config name (e.g., hu_btn_bb_srp_50bb, hu_btn_bb_3bp_50bb)
  --board <cards> Board cards (e.g., "Ah Ts 2c")
  --file <path>   Path to external solver JSON file
  --player <p>    Player: oop, ip, or both (default: both)
  --node <n>      Node: root (default) or action history (e.g., "x" for after BB checks)

External JSON format:
  {
    "source": "GTO Wizard",
    "board": "Ah Ts 2c",
    "player": "OOP",
    "actions": ["Check", "Bet 33%", "Bet 75%"],
    "strategies": {
      "AA": [0.45, 0.30, 0.25],
      "AKs": [0.10, 0.50, 0.40],
      ...
    }
  }
`);
}

// ─── Main ───

switch (mode) {
  case 'list': cmdList(); break;
  case 'export': cmdExport(); break;
  case 'compare': cmdCompare(); break;
  default: cmdHelp(); break;
}
