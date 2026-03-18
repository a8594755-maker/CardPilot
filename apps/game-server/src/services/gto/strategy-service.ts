// Wraps the cfr-solver's LookupService for API consumption.
// Manages loading of solved strategy files and querying.

import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { evaluateBestHand } from '@cardpilot/poker-evaluator';

const __dirname = fileURLToPath(new URL('.', import.meta.url));

// Try multiple candidate paths for the data directory
function findDataDir(): string {
  const candidates = [
    resolve(__dirname, '../../../../../data/cfr'),
    resolve(__dirname, '../../../../data/cfr'),
    resolve(process.cwd(), 'data/cfr'),
  ];
  for (const c of candidates) {
    if (existsSync(c)) return c;
  }
  return resolve(process.cwd(), 'data/cfr');
}

const DATA_ROOT = findDataDir();

const RANKS = '23456789TJQKA';
const SUITS = ['c', 'd', 'h', 's'];

function indexToCard(i: number): string {
  return RANKS[Math.floor(i / 4)] + SUITS[i % 4];
}

function cardToIndex(card: string): number {
  const rank = RANKS.indexOf(card[0].toUpperCase());
  const suitMap: Record<string, number> = { c: 0, d: 1, h: 2, s: 3 };
  const suit = suitMap[card[1].toLowerCase()];
  if (rank < 0 || suit === undefined) return -1;
  return rank * 4 + suit;
}

function indexToRank(i: number): number {
  return Math.floor(i / 4);
}

function indexToSuit(i: number): number {
  return i % 4;
}

export interface FlopInfo {
  file: string;
  boardId: number;
  flopCards: number[];
  cards: string[];
  iterations: number;
  bucketCount: number;
  infoSets: number;
  elapsedMs: number;
  highCard: string;
  texture: string;
  pairing: string;
  connectivity: string;
}

export interface ConfigInfo {
  name: string;
  path: string;
  flopCount: number;
}

function classifyFlop(flopCards: number[]) {
  const ranks = flopCards.map(indexToRank).sort((a, b) => b - a);
  const suits = flopCards.map(indexToSuit);
  const uniqueSuits = new Set(suits).size;

  const highCard = RANKS[ranks[0]];
  const texture = uniqueSuits === 3 ? 'rainbow' : uniqueSuits === 2 ? 'two-tone' : 'monotone';

  let pairing = 'unpaired';
  if (ranks[0] === ranks[1] && ranks[1] === ranks[2]) pairing = 'trips';
  else if (ranks[0] === ranks[1] || ranks[1] === ranks[2]) pairing = 'paired';

  const maxGap = Math.max(ranks[0] - ranks[1], ranks[1] - ranks[2]);
  const connectivity = maxGap <= 2 ? 'connected' : maxGap <= 4 ? 'semi-connected' : 'disconnected';

  return { highCard, texture, pairing, connectivity, highRank: ranks[0] };
}

/** Get all available solve config directories */
export function getConfigs(): ConfigInfo[] {
  if (!existsSync(DATA_ROOT)) return [];
  const configs: ConfigInfo[] = [];
  for (const d of readdirSync(DATA_ROOT)) {
    const full = join(DATA_ROOT, d);
    try {
      if (!statSync(full).isDirectory()) continue;
      const flopCount = readdirSync(full).filter((f) => f.endsWith('.meta.json')).length;
      configs.push({ name: d, path: full, flopCount });
    } catch {
      /* skip */
    }
  }
  return configs;
}

/** List all solved flops for a config */
export function getFlops(configName: string): FlopInfo[] {
  const configDir = join(DATA_ROOT, configName);
  if (!existsSync(configDir)) return [];

  return readdirSync(configDir)
    .filter((f) => f.endsWith('.meta.json'))
    .sort()
    .map((f) => {
      const meta = JSON.parse(readFileSync(join(configDir, f), 'utf-8'));
      const cards = (meta.flopCards as number[]).map(indexToCard);
      const classification = classifyFlop(meta.flopCards);
      return {
        file: f.replace('.meta.json', ''),
        boardId: meta.boardId,
        flopCards: meta.flopCards,
        cards,
        iterations: meta.iterations,
        bucketCount: meta.bucketCount,
        infoSets: meta.infoSets,
        elapsedMs: meta.elapsedMs,
        ...classification,
      };
    });
}

/** Find the nearest solved flop to a set of cards */
export function findNearestFlop(cards: string[], configName?: string): FlopInfo | null {
  const queryIndices = cards.map((c) => cardToIndex(c.trim()));
  if (queryIndices.some((c) => c < 0)) return null;

  const configs = configName ? [configName] : getConfigs().map((c) => c.name);
  let bestFlop: FlopInfo | null = null;
  let bestDist = Infinity;

  for (const cfg of configs) {
    const flops = getFlops(cfg);
    for (const flop of flops) {
      const dist = flopDistance(queryIndices, flop.flopCards);
      if (dist < bestDist) {
        bestDist = dist;
        bestFlop = flop;
      }
    }
  }

  return bestFlop;
}

function flopDistance(a: number[], b: number[]): number {
  const aRanks = a.map(indexToRank).sort((x, y) => y - x);
  const bRanks = b.map(indexToRank).sort((x, y) => y - x);
  const aSuits = new Set(a.map(indexToSuit)).size;
  const bSuits = new Set(b.map(indexToSuit)).size;
  const aPaired = aRanks[0] === aRanks[1] || aRanks[1] === aRanks[2] ? 1 : 0;
  const bPaired = bRanks[0] === bRanks[1] || bRanks[1] === bRanks[2] ? 1 : 0;

  return (
    3 * Math.abs(aRanks[0] - bRanks[0]) +
    2 * Math.abs(aRanks[1] - bRanks[1]) +
    1 * Math.abs(aRanks[2] - bRanks[2]) +
    5 * Math.abs(aSuits - bSuits) +
    4 * Math.abs(aPaired - bPaired)
  );
}

/** Load JSONL strategy data for a specific flop */
export function loadFlopStrategies(configName: string, flopFile: string): Map<string, number[]> {
  const filePath = join(DATA_ROOT, configName, `${flopFile}.jsonl`);
  if (!existsSync(filePath)) return new Map();

  const content = readFileSync(filePath, 'utf-8');
  const strategies = new Map<string, number[]>();

  for (const line of content.split('\n')) {
    if (!line.trim()) continue;
    try {
      const { key, probs } = JSON.parse(line);
      strategies.set(key, probs);
    } catch {
      /* skip malformed lines */
    }
  }

  return strategies;
}

/** Get strategy for a specific info-set key */
export function queryStrategy(configName: string, flopFile: string, key: string): number[] | null {
  const strategies = loadFlopStrategies(configName, flopFile);
  return strategies.get(key) ?? null;
}

// --- Solver Grid Builder ---

interface NodeInfo {
  player: number;
  actions: string[];
  pot: number;
  stacks: number[];
}

interface SolverMeta {
  version: string;
  configName: string;
  boardId: number;
  flopCards: number[];
  iterations: number;
  bucketCount: number;
  infoSets: number;
  elapsedMs: number;
  nodes?: Record<string, NodeInfo>;
}

export interface SolverGridResult {
  actions: string[];
  grid: Record<string, Record<string, number>>;
  context: { pot: number; stack: number; toCall: number; odds: number; overallFreq: number };
  summary: {
    totalCombos: number;
    actionCombos: Record<string, number>;
    actionPercentages: Record<string, number>;
    overallEquity: number;
    overallEV: number;
  };
  player: number;
  history: string;
  childNodes: Array<{ action: string; history: string; player: number }>;
}

/** Standard combo counts per hand class type */
function handClassComboCount(hc: string): number {
  if (hc.length === 2) return 6; // pair: AA, KK, etc.
  if (hc[2] === 's') return 4; // suited: AKs
  return 12; // offsuit: AKo
}

function actionCharForLabel(action: string): string {
  if (action === 'fold') return 'f';
  if (action === 'check') return 'x';
  if (action === 'call') return 'c';
  if (action === 'allin') return 'A';
  const match = action.match(/^(?:bet|raise)_(\d+)$/);
  if (match) return String(parseInt(match[1]) + 1);
  return '?';
}

/** Build a strategy grid from solver JSONL data for a specific node */
export function buildSolverGrid(
  configName: string,
  flopFile: string,
  player: number,
  history: string,
): SolverGridResult | null {
  const metaPath = join(DATA_ROOT, configName, `${flopFile}.meta.json`);
  if (!existsSync(metaPath)) return null;

  const meta: SolverMeta = JSON.parse(readFileSync(metaPath, 'utf-8'));
  if (!meta.nodes) return null;

  // Look up the target node
  const nodeInfo = meta.nodes[history];
  if (!nodeInfo) return null;

  const actions = nodeInfo.actions;
  const nodePlayer = nodeInfo.player;

  // Load JSONL strategies
  const strategies = loadFlopStrategies(configName, flopFile);

  // Filter for per-hand-class entries at this node
  const grid: Record<string, Record<string, number>> = {};
  const playerStr = String(nodePlayer);

  for (const [key, probs] of strategies) {
    const parts = key.split('|');
    // Per-hand-class lines have 5 parts: street|boardId|player|history|handClass
    if (parts.length !== 5) continue;
    if (parts[2] !== playerStr) continue;
    if (parts[3] !== history) continue;

    const handClass = parts[4];
    const entry: Record<string, number> = {};
    for (let i = 0; i < actions.length && i < probs.length; i++) {
      entry[actions[i]] = probs[i];
    }
    grid[handClass] = entry;
  }

  // Compute summary
  let totalCombos = 0;
  const actionCombos: Record<string, number> = {};
  const actionWeightedSum: Record<string, number> = {};
  for (const a of actions) {
    actionCombos[a] = 0;
    actionWeightedSum[a] = 0;
  }

  for (const [hc, freqs] of Object.entries(grid)) {
    const weight = handClassComboCount(hc);
    totalCombos += weight;
    for (const a of actions) {
      const freq = freqs[a] || 0;
      actionWeightedSum[a] += freq * weight;
      if (freq > 0.001) actionCombos[a] += weight;
    }
  }

  const actionPercentages: Record<string, number> = {};
  for (const a of actions) {
    actionPercentages[a] =
      totalCombos > 0 ? Math.round((actionWeightedSum[a] / totalCombos) * 1000) / 10 : 0;
  }

  const context = {
    pot: nodeInfo.pot,
    stack: nodeInfo.stacks[nodePlayer] ?? 0,
    toCall: 0,
    odds: 0,
    overallFreq: 1.0,
  };

  const summary = {
    totalCombos,
    actionCombos,
    actionPercentages,
    overallEquity: 0,
    overallEV: 0,
  };

  // Find child nodes for tree navigation
  const childNodes: Array<{ action: string; history: string; player: number }> = [];
  for (const action of actions) {
    const actionChar = actionCharForLabel(action);
    const childPrefix = history + actionChar;
    let bestChild: { history: string; player: number } | null = null;
    for (const [h, info] of Object.entries(meta.nodes!)) {
      if (h === childPrefix || (h.startsWith(childPrefix) && h.length <= childPrefix.length + 1)) {
        if (!bestChild || h.length < bestChild.history.length) {
          bestChild = { history: h, player: info.player };
        }
      }
    }
    if (bestChild) {
      childNodes.push({ action, ...bestChild });
    }
  }

  return { actions, grid, context, summary, player: nodePlayer, history, childNodes };
}

/** Compute hand-to-bucket mapping for a specific board */
export function computeHandBuckets(
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
    const key =
      ranked[i].c1 < ranked[i].c2
        ? `${ranked[i].c1},${ranked[i].c2}`
        : `${ranked[i].c2},${ranked[i].c1}`;
    result.set(key, bucket);
  }
  return result;
}
