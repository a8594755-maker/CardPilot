// Hand → Bucket mapping service for CFR strategy viewer.
// Computes which equity bucket each hand class (AKs, QQ, etc.) falls into
// for a given board + preflop range. Results are cached in memory.

import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { evaluateBestHand } from '@cardpilot/poker-evaluator';

// ─── Card utilities ───

const RANKS = '23456789TJQKA';
const SUITS = ['c', 'd', 'h', 's'];

function indexToCard(i: number): string {
  return RANKS[Math.floor(i / 4)] + SUITS[i % 4];
}

function indexToRank(i: number): number {
  return Math.floor(i / 4);
}

function indexToSuit(i: number): number {
  return i % 4;
}

function cardToIndex(card: string): number {
  const rank = RANKS.indexOf(card[0].toUpperCase());
  const suitMap: Record<string, number> = { c: 0, d: 1, h: 2, s: 3 };
  const suit = suitMap[card[1].toLowerCase()];
  if (rank < 0 || suit === undefined) return -1;
  return rank * 4 + suit;
}

// ─── Preflop range loading (inlined from cfr-solver) ───

interface RangeEntry {
  hand: string;
  mix: Record<string, number>;
  spot: string;
}

interface PreflopRange {
  combos: Array<[number, number]>;
}

let rangeCache: Map<string, { oop: PreflopRange; ip: PreflopRange }> | null = null;

function findChartsPath(): string {
  const candidates = [
    resolve(process.cwd(), 'data/preflop_charts.json'),
    resolve(process.cwd(), '../../data/preflop_charts.json'),
    resolve(process.cwd(), '../../../data/preflop_charts.json'),
  ];
  for (const p of candidates) {
    if (existsSync(p)) return p;
  }
  return candidates[0];
}

function expandHandClassToCombos(handClass: string): Array<[number, number]> {
  const hand = handClass.toUpperCase();
  const combos: Array<[number, number]> = [];

  if (hand.length === 2 && hand[0] === hand[1]) {
    // Pair: AA, KK, etc.
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
        if (!suffix && sA === sB) continue; // default to offsuit for non-pair
        const c1 = rankA * 4 + sA;
        const c2 = rankB * 4 + sB;
        combos.push([Math.min(c1, c2), Math.max(c1, c2)]);
      }
    }
  }

  return combos;
}

function loadRanges(ipSpot: string, oopSpot: string, ipAction: string, oopAction: string): {
  oop: PreflopRange;
  ip: PreflopRange;
} {
  const cacheKey = `${ipSpot}|${oopSpot}|${ipAction}|${oopAction}`;
  if (rangeCache?.has(cacheKey)) return rangeCache.get(cacheKey)!;

  const chartsPath = findChartsPath();
  if (!existsSync(chartsPath)) {
    throw new Error(`Preflop charts not found at ${chartsPath}`);
  }

  const allEntries = JSON.parse(readFileSync(chartsPath, 'utf-8')) as RangeEntry[];
  const ipEntries = allEntries.filter(e => e.spot === ipSpot);
  const oopEntries = allEntries.filter(e => e.spot === oopSpot);

  function buildRange(entries: RangeEntry[], actionKey: string): PreflopRange {
    const combos: Array<[number, number]> = [];
    const seen = new Set<string>();
    for (const entry of entries) {
      const freq = entry.mix[actionKey];
      if (typeof freq !== 'number' || freq <= 0) continue;
      for (const combo of expandHandClassToCombos(entry.hand)) {
        const key = `${combo[0]},${combo[1]}`;
        if (seen.has(key)) continue;
        seen.add(key);
        combos.push(combo);
      }
    }
    return { combos };
  }

  const result = {
    ip: buildRange(ipEntries, ipAction),
    oop: buildRange(oopEntries, oopAction),
  };

  if (!rangeCache) rangeCache = new Map();
  rangeCache.set(cacheKey, result);
  return result;
}

// Config → preflop range spot mapping
const CONFIG_RANGES: Record<string, { ipSpot: string; oopSpot: string; ipAction: string; oopAction: string }> = {
  pipeline_srp: { ipSpot: 'BTN_unopened_open2.5x', oopSpot: 'BB_vs_BTN_facing_open2.5x', ipAction: 'raise', oopAction: 'call' },
  pipeline_3bet: { ipSpot: 'BTN_unopened_open2.5x', oopSpot: 'BB_vs_BTN_facing_open2.5x', ipAction: 'raise', oopAction: 'raise' },
  hu_btn_bb_srp_100bb: { ipSpot: 'BTN_unopened_open2.5x', oopSpot: 'BB_vs_BTN_facing_open2.5x', ipAction: 'raise', oopAction: 'call' },
  hu_btn_bb_3bp_100bb: { ipSpot: 'BTN_unopened_open2.5x', oopSpot: 'BB_vs_BTN_facing_open2.5x', ipAction: 'raise', oopAction: 'raise' },
  hu_btn_bb_srp_50bb: { ipSpot: 'BTN_unopened_open2.5x', oopSpot: 'BB_vs_BTN_facing_open2.5x', ipAction: 'raise', oopAction: 'call' },
  hu_btn_bb_3bp_50bb: { ipSpot: 'BTN_unopened_open2.5x', oopSpot: 'BB_vs_BTN_facing_open2.5x', ipAction: 'raise', oopAction: 'raise' },
  hu_co_bb_srp_100bb: { ipSpot: 'CO_unopened_open2.5x', oopSpot: 'BB_vs_CO_facing_open2.5x', ipAction: 'raise', oopAction: 'call' },
  hu_co_bb_3bp_100bb: { ipSpot: 'CO_unopened_open2.5x', oopSpot: 'BB_vs_CO_facing_open2.5x', ipAction: 'raise', oopAction: 'raise' },
  hu_utg_bb_srp_100bb: { ipSpot: 'UTG_unopened_open2.5x', oopSpot: 'BB_vs_UTG_facing_open2.5x', ipAction: 'raise', oopAction: 'call' },
};

// Fallback for unknown configs
const DEFAULT_RANGE = { ipSpot: 'BTN_unopened_open2.5x', oopSpot: 'BB_vs_BTN_facing_open2.5x', ipAction: 'raise', oopAction: 'call' };

// ─── Hand-map computation ───

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

// ─── LRU Cache ───

const handMapCache = new Map<string, { oop: Record<string, number>; ip: Record<string, number> }>();
const MAX_CACHE = 200;

function evictOldest() {
  if (handMapCache.size >= MAX_CACHE) {
    const firstKey = handMapCache.keys().next().value;
    if (firstKey) handMapCache.delete(firstKey);
  }
}

// ─── Public API ───

export function getHandMap(
  configName: string,
  boardCards: number[],
  bucketCount: number,
): { oop: Record<string, number>; ip: Record<string, number> } {
  const cacheKey = `${configName}:${boardCards.join(',')}:${bucketCount}`;
  if (handMapCache.has(cacheKey)) {
    const result = handMapCache.get(cacheKey)!;
    // Move to end (LRU)
    handMapCache.delete(cacheKey);
    handMapCache.set(cacheKey, result);
    return result;
  }

  const rangeConfig = CONFIG_RANGES[configName] ?? DEFAULT_RANGE;
  const ranges = loadRanges(rangeConfig.ipSpot, rangeConfig.oopSpot, rangeConfig.ipAction, rangeConfig.oopAction);
  const dead = new Set(boardCards);

  const oopCombos = ranges.oop.combos.filter(([c1, c2]) => !dead.has(c1) && !dead.has(c2));
  const ipCombos = ranges.ip.combos.filter(([c1, c2]) => !dead.has(c1) && !dead.has(c2));

  const oopBuckets = computeHandBuckets(oopCombos, boardCards, bucketCount);
  const ipBuckets = computeHandBuckets(ipCombos, boardCards, bucketCount);

  const result = {
    oop: buildHandClassMap(oopBuckets, oopCombos, boardCards),
    ip: buildHandClassMap(ipBuckets, ipCombos, boardCards),
  };

  evictOldest();
  handMapCache.set(cacheKey, result);
  return result;
}

// ─── Flop classification ───

export function classifyFlop(flopCards: number[]): {
  highCard: string;
  texture: string;
  pairing: string;
  connectivity: string;
} {
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

  return { highCard, texture, pairing, connectivity };
}

// ─── Flop distance ───

export function flopDistance(a: number[], b: number[]): number {
  const aRanks = a.map(indexToRank).sort((x, y) => y - x);
  const bRanks = b.map(indexToRank).sort((x, y) => y - x);
  const aSuits = new Set(a.map(indexToSuit)).size;
  const bSuits = new Set(b.map(indexToSuit)).size;
  const aPaired = (aRanks[0] === aRanks[1] || aRanks[1] === aRanks[2]) ? 1 : 0;
  const bPaired = (bRanks[0] === bRanks[1] || bRanks[1] === bRanks[2]) ? 1 : 0;

  return (
    3 * Math.abs(aRanks[0] - bRanks[0]) +
    2 * Math.abs(aRanks[1] - bRanks[1]) +
    1 * Math.abs(aRanks[2] - bRanks[2]) +
    5 * Math.abs(aSuits - bSuits) +
    4 * Math.abs(aPaired - bPaired)
  );
}

export { cardToIndex, indexToCard };
