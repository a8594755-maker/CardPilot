#!/usr/bin/env tsx
// Simple HTTP server to serve the CFR viewer and data files.
// Usage: npx tsx viewer/serve.ts [port]
// Opens http://localhost:3456 with the viewer pre-loaded.

import { createServer } from 'node:http';
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { resolve, join, extname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { evaluateBestHand } from '@cardpilot/poker-evaluator';
import { loadHUSRPRanges, getRangeCombos } from '../src/integration/preflop-ranges.js';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const PORT = parseInt(process.argv[2] || '3456', 10);
const DATA_DIR = resolve(__dirname, '../../../data/cfr/v1_hu_srp_50bb');
const VIEWER_HTML = resolve(__dirname, 'index.html');

const MIME: Record<string, string> = {
  '.html': 'text/html',
  '.json': 'application/json',
  '.jsonl': 'application/jsonlines+json',
};

const RANKS = '23456789TJQKA';
const SUITS = ['c', 'd', 'h', 's'];
const RANK_NAMES: Record<string, string> = {
  '2': '2', '3': '3', '4': '4', '5': '5', '6': '6', '7': '7',
  '8': '8', '9': '9', 'T': 'T', 'J': 'J', 'Q': 'Q', 'K': 'K', 'A': 'A',
};

function indexToCard(i: number): string {
  const rank = Math.floor(i / 4);
  const suit = i % 4;
  return RANKS[rank] + SUITS[suit];
}

function indexToRank(i: number): number {
  return Math.floor(i / 4);
}

function indexToSuit(i: number): number {
  return i % 4;
}

function classifyFlop(flopCards: number[]): {
  highCard: string;
  texture: string;   // 'rainbow' | 'two-tone' | 'monotone'
  pairing: string;   // 'unpaired' | 'paired' | 'trips'
  connectivity: string; // 'connected' | 'semi-connected' | 'disconnected'
  highRank: number;
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

  return { highCard, texture, pairing, connectivity, highRank: ranks[0] };
}

// ─── Hand → Bucket mapping ───

const RANK_ORDER = 'AKQJT98765432';
const handMapCache = new Map<string, { oop: Record<string, number>; ip: Record<string, number> }>();

let preflopRanges: ReturnType<typeof loadHUSRPRanges> | null = null;
function getRanges() {
  if (!preflopRanges) {
    const chartsPath = resolve(__dirname, '../../../data/preflop_charts.json');
    preflopRanges = loadHUSRPRanges(chartsPath);
  }
  return preflopRanges;
}

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
    // Use median bucket for the hand class
    bkts.sort((a, b) => a - b);
    result[cls] = bkts[Math.floor(bkts.length / 2)];
  }
  return result;
}

function getHandMap(file: string): { oop: Record<string, number>; ip: Record<string, number> } | null {
  if (handMapCache.has(file)) return handMapCache.get(file)!;

  const metaPath = join(DATA_DIR, `${file}.meta.json`);
  if (!existsSync(metaPath)) return null;

  const meta = JSON.parse(readFileSync(metaPath, 'utf-8'));
  const boardCards: number[] = meta.flopCards;
  const ranges = getRanges();
  const dead = new Set(boardCards);

  const oopCombos = getRangeCombos(ranges.oopRange, dead);
  const ipCombos = getRangeCombos(ranges.ipRange, dead);

  const oopBuckets = computeHandBuckets(oopCombos, boardCards, 50);
  const ipBuckets = computeHandBuckets(ipCombos, boardCards, 50);

  const result = {
    oop: buildHandClassMap(oopBuckets, oopCombos, boardCards),
    ip: buildHandClassMap(ipBuckets, ipCombos, boardCards),
  };

  handMapCache.set(file, result);
  return result;
}

const server = createServer((req, res) => {
  const url = new URL(req.url!, `http://localhost:${PORT}`);
  const path = url.pathname;

  // CORS
  res.setHeader('Access-Control-Allow-Origin', '*');

  if (path === '/' || path === '/index.html') {
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(readFileSync(VIEWER_HTML));
    return;
  }

  // List available flops with texture classification
  if (path === '/api/flops') {
    if (!existsSync(DATA_DIR)) {
      res.writeHead(404);
      res.end(JSON.stringify({ error: 'Data directory not found' }));
      return;
    }
    const metas = readdirSync(DATA_DIR)
      .filter(f => f.endsWith('.meta.json'))
      .sort()
      .map(f => {
        const meta = JSON.parse(readFileSync(join(DATA_DIR, f), 'utf-8'));
        const cards = (meta.flopCards as number[]).map(indexToCard);
        const classification = classifyFlop(meta.flopCards);
        return {
          file: f.replace('.meta.json', ''),
          ...meta,
          cards,
          ...classification,
        };
      });
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(metas));
    return;
  }

  // Hand → bucket mapping for a specific board
  if (path.startsWith('/api/hand-map/')) {
    const file = path.replace('/api/hand-map/', '');
    const handMap = getHandMap(file);
    if (!handMap) {
      res.writeHead(404);
      res.end(JSON.stringify({ error: 'Board not found' }));
      return;
    }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(handMap));
    return;
  }

  // Serve a specific flop file
  if (path.startsWith('/data/')) {
    const filename = path.replace('/data/', '');
    const filePath = join(DATA_DIR, filename);
    if (existsSync(filePath) && !filename.includes('..')) {
      const ext = extname(filename);
      res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
      res.end(readFileSync(filePath));
      return;
    }
    res.writeHead(404);
    res.end('Not found');
    return;
  }

  res.writeHead(404);
  res.end('Not found');
});

server.listen(PORT, () => {
  console.log(`\n  CFR Strategy Viewer: http://localhost:${PORT}\n`);
  console.log(`  Data directory: ${DATA_DIR}`);
  console.log(`  Available flops: ${existsSync(DATA_DIR) ? readdirSync(DATA_DIR).filter(f => f.endsWith('.jsonl')).length : 0}`);
  console.log();
});
