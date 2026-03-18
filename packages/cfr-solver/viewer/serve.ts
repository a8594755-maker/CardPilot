#!/usr/bin/env tsx
// Simple HTTP server to serve the CFR viewer and data files (V2).
// Usage: npx tsx viewer/serve.ts [port]
// Opens http://localhost:3456 with the viewer pre-loaded.

import { createServer, request as httpRequest } from 'node:http';
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { resolve, join, extname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { evaluateBestHand } from '@cardpilot/poker-evaluator';
import { loadHUSRPRanges, getRangeCombos } from '../src/integration/preflop-ranges.js';
import { loadGtoWizardRangeFile } from '../src/data-loaders/gto-wizard-json.js';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const PORT = parseInt(process.argv[2] || '3456', 10);

// Scan for all available config data directories
const CFR_ROOT = resolve(__dirname, '../../../data/cfr');
const DATA_DIRS: Record<string, string> = {};
if (existsSync(CFR_ROOT)) {
  for (const d of readdirSync(CFR_ROOT)) {
    const full = join(CFR_ROOT, d);
    try {
      if (statSync(full).isDirectory()) DATA_DIRS[d] = full;
    } catch {}
  }
}
// Default data dir: prefer standard_*, then v2_*, then v1_*
const DATA_DIR_PRIORITY = [
  'standard_hu_srp_50bb',
  'standard_hu_srp_100bb',
  'v2_hu_srp_50bb',
  'v1_hu_srp_50bb',
];
let DEFAULT_DATA_DIR = '';
for (const p of DATA_DIR_PRIORITY) {
  if (DATA_DIRS[p]) {
    DEFAULT_DATA_DIR = DATA_DIRS[p];
    break;
  }
}
if (!DEFAULT_DATA_DIR && Object.keys(DATA_DIRS).length > 0) {
  DEFAULT_DATA_DIR = Object.values(DATA_DIRS)[0];
}
const DATA_DIR = DEFAULT_DATA_DIR;

const VIEWER_HTML = resolve(__dirname, 'index.html');
const PREFLOP_HTML = resolve(__dirname, 'preflop.html');

const MIME: Record<string, string> = {
  '.html': 'text/html',
  '.json': 'application/json',
  '.jsonl': 'application/jsonlines+json',
};

const RANKS = '23456789TJQKA';
const SUITS = ['c', 'd', 'h', 's'];

function indexToCard(i: number): string {
  const rank = Math.floor(i / 4);
  const suit = i % 4;
  return RANKS[rank] + SUITS[suit];
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

function classifyFlop(flopCards: number[]): {
  highCard: string;
  texture: string;
  pairing: string;
  connectivity: string;
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
    const key =
      ranked[i].c1 < ranked[i].c2
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
    result[cls] = bkts[Math.floor(bkts.length / 2)];
  }
  return result;
}

function getHandMap(
  file: string,
): { oop: Record<string, number>; ip: Record<string, number> } | null {
  if (handMapCache.has(file)) return handMapCache.get(file)!;

  const metaPath = join(DATA_DIR, `${file}.meta.json`);
  if (!existsSync(metaPath)) return null;

  const meta = JSON.parse(readFileSync(metaPath, 'utf-8'));
  const boardCards: number[] = meta.flopCards;
  const bucketCount: number = meta.bucketCount || 50;
  const ranges = getRanges();
  const dead = new Set(boardCards);

  const oopCombos = getRangeCombos(ranges.oopRange, dead);
  const ipCombos = getRangeCombos(ranges.ipRange, dead);

  const oopBuckets = computeHandBuckets(oopCombos, boardCards, bucketCount);
  const ipBuckets = computeHandBuckets(ipCombos, boardCards, bucketCount);

  const result = {
    oop: buildHandClassMap(oopBuckets, oopCombos, boardCards),
    ip: buildHandClassMap(ipBuckets, ipCombos, boardCards),
  };

  handMapCache.set(file, result);
  return result;
}

// ─── Flop distance matching ───

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

// ─── Server ───

const server = createServer((req, res) => {
  const url = new URL(req.url!, `http://localhost:${PORT}`);
  const path = url.pathname;

  res.setHeader('Access-Control-Allow-Origin', '*');

  // Main viewer
  if (path === '/' || path === '/index.html') {
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(readFileSync(VIEWER_HTML));
    return;
  }

  // Preflop knowledge base page
  if (path === '/preflop' || path === '/preflop.html') {
    if (existsSync(PREFLOP_HTML)) {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(readFileSync(PREFLOP_HTML));
    } else {
      res.writeHead(404);
      res.end('Preflop page not found');
    }
    return;
  }

  // List available configs
  if (path === '/api/configs') {
    const configs = Object.entries(DATA_DIRS).map(([name, dir]) => {
      const metaFiles = existsSync(dir)
        ? readdirSync(dir).filter((f) => f.endsWith('.meta.json'))
        : [];
      return { name, flopCount: metaFiles.length, isDefault: dir === DATA_DIR };
    });
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(configs));
    return;
  }

  // Resolve data dir: allow ?config= query param to override
  const configParam = url.searchParams.get('config');
  const activeDataDir = (configParam && DATA_DIRS[configParam]) || DATA_DIR;

  // List available flops with texture classification
  if (path === '/api/flops') {
    if (!existsSync(activeDataDir)) {
      res.writeHead(404);
      res.end(JSON.stringify({ error: 'Data directory not found' }));
      return;
    }
    const metas = readdirSync(activeDataDir)
      .filter((f) => f.endsWith('.meta.json'))
      .sort()
      .map((f) => {
        const meta = JSON.parse(readFileSync(join(activeDataDir, f), 'utf-8'));
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

  // Find nearest solved flop
  if (path === '/api/nearest-flop') {
    const cardsParam = url.searchParams.get('cards');
    if (!cardsParam) {
      res.writeHead(400);
      res.end(JSON.stringify({ error: 'Missing cards parameter' }));
      return;
    }
    const queryCards = cardsParam.split(',').map((c) => cardToIndex(c.trim()));
    if (queryCards.some((c) => c < 0)) {
      res.writeHead(400);
      res.end(JSON.stringify({ error: 'Invalid card format' }));
      return;
    }

    if (!existsSync(DATA_DIR)) {
      res.writeHead(404);
      res.end(JSON.stringify({ error: 'No data' }));
      return;
    }

    let bestFile = '';
    let bestDist = Infinity;
    const metaFiles = readdirSync(DATA_DIR)
      .filter((f) => f.endsWith('.meta.json'))
      .sort();
    for (const f of metaFiles) {
      const meta = JSON.parse(readFileSync(join(DATA_DIR, f), 'utf-8'));
      const dist = flopDistance(queryCards, meta.flopCards);
      if (dist < bestDist) {
        bestDist = dist;
        bestFile = f.replace('.meta.json', '');
      }
    }

    if (bestFile) {
      const meta = JSON.parse(readFileSync(join(DATA_DIR, `${bestFile}.meta.json`), 'utf-8'));
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(
        JSON.stringify({
          file: bestFile,
          distance: bestDist,
          cards: (meta.flopCards as number[]).map(indexToCard),
          ...meta,
          ...classifyFlop(meta.flopCards),
        }),
      );
    } else {
      res.writeHead(404);
      res.end(JSON.stringify({ error: 'No boards found' }));
    }
    return;
  }

  // Preflop API: list all spots
  if (path === '/api/preflop-spots') {
    try {
      const chartsPath = resolve(__dirname, '../../../data/preflop_charts.json');
      const entries = loadGtoWizardRangeFile(chartsPath);
      const spots = [...new Set(entries.map((e) => e.spot))];
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(spots));
    } catch {
      res.writeHead(500);
      res.end(JSON.stringify({ error: 'Failed to load preflop charts' }));
    }
    return;
  }

  // Preflop API: get range data for a specific spot
  if (path.startsWith('/api/preflop-range/')) {
    try {
      const spot = decodeURIComponent(path.replace('/api/preflop-range/', ''));
      const chartsPath = resolve(__dirname, '../../../data/preflop_charts.json');
      const entries = loadGtoWizardRangeFile(chartsPath);
      const filtered = entries.filter((e) => e.spot === spot);
      if (filtered.length === 0) {
        res.writeHead(404);
        res.end(JSON.stringify({ error: `Spot not found: ${spot}` }));
        return;
      }
      const matrix: Record<
        string,
        { raise: number; call: number; fold: number; notes?: string[] }
      > = {};
      for (const entry of filtered) {
        matrix[entry.hand] = {
          raise: entry.mix.raise || 0,
          call: entry.mix.call || 0,
          fold: entry.mix.fold || 0,
          notes: entry.notes,
        };
      }
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(matrix));
    } catch {
      res.writeHead(500);
      res.end(JSON.stringify({ error: 'Failed to load preflop charts' }));
    }
    return;
  }

  // Solve progress monitoring API
  if (path === '/api/solve-progress') {
    try {
      const progressDataDir = (configParam && DATA_DIRS[configParam]) || DATA_DIR;
      const totalExpected = 1911; // all isomorphic flops
      const metaFiles = existsSync(progressDataDir)
        ? readdirSync(progressDataDir)
            .filter((f) => f.endsWith('.meta.json'))
            .sort()
        : [];

      const completed = metaFiles.length;
      const metas = metaFiles
        .map((f) => {
          try {
            return JSON.parse(readFileSync(join(progressDataDir, f), 'utf-8'));
          } catch {
            return null;
          }
        })
        .filter(Boolean);

      let totalInfoSets = 0;
      let totalElapsedMs = 0;
      let totalSizeMB = 0;
      let peakMemoryMB = 0;
      let latestTimestamp = '';

      for (const m of metas) {
        totalInfoSets += m.infoSets || 0;
        totalElapsedMs += m.elapsedMs || 0;
        if (m.peakMemoryMB > peakMemoryMB) peakMemoryMB = m.peakMemoryMB;
        if (m.timestamp > latestTimestamp) latestTimestamp = m.timestamp;
      }

      // Calculate file sizes
      const jsonlFiles = existsSync(progressDataDir)
        ? readdirSync(progressDataDir).filter((f) => f.endsWith('.jsonl'))
        : [];
      for (const f of jsonlFiles) {
        try {
          const fstat = statSync(join(progressDataDir, f));
          totalSizeMB += fstat.size / (1024 * 1024);
        } catch {}
      }

      // Sort by timestamp for chronological log
      const sortedMetas = [...metas].sort((a, b) =>
        (a.timestamp || '').localeCompare(b.timestamp || ''),
      );

      // Recent completions (last 50 for log view, reversed = newest first)
      const recentMetas = sortedMetas
        .slice(-50)
        .reverse()
        .map((m) => ({
          boardId: m.boardId,
          file: `flop_${String(m.boardId).padStart(3, '0')}`,
          flopCards: (m.flopCards as number[]).map(indexToCard).join(' '),
          infoSets: m.infoSets,
          elapsedMs: m.elapsedMs,
          peakMemoryMB: m.peakMemoryMB || 0,
          timestamp: m.timestamp,
        }));

      // Estimate remaining time
      const avgTimePerFlop = completed > 0 ? totalElapsedMs / completed : 0;
      const remaining = totalExpected - completed;
      // Workers run in parallel, estimate based on wall-clock
      const firstTimestamp = metas.length > 0 ? metas[0].timestamp : '';
      let wallClockMs = 0;
      if (firstTimestamp && latestTimestamp) {
        wallClockMs = new Date(latestTimestamp).getTime() - new Date(firstTimestamp).getTime();
      }
      const wallClockPerFlop = completed > 1 ? wallClockMs / (completed - 1) : avgTimePerFlop;
      const etaMs = remaining * wallClockPerFlop;

      // Check progress file from orchestrator
      const progressPath = join(progressDataDir, '_progress.json');
      let progressFile = null;
      if (existsSync(progressPath)) {
        try {
          progressFile = JSON.parse(readFileSync(progressPath, 'utf-8'));
        } catch {}
      }

      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(
        JSON.stringify({
          totalExpected,
          completed,
          remaining,
          percentDone: ((completed / totalExpected) * 100).toFixed(2),
          totalInfoSets,
          totalElapsedMs,
          totalSizeMB: totalSizeMB.toFixed(1),
          peakMemoryMB,
          avgTimePerFlopSec: (avgTimePerFlop / 1000).toFixed(1),
          wallClockPerFlopSec: (wallClockPerFlop / 1000).toFixed(1),
          etaMinutes: (etaMs / 60000).toFixed(0),
          etaHours: (etaMs / 3600000).toFixed(1),
          latestTimestamp,
          recentCompletions: recentMetas,
          progressFile,
        }),
      );
    } catch (err) {
      res.writeHead(500);
      res.end(JSON.stringify({ error: String(err) }));
    }
    return;
  }

  // Pipeline status proxy — forward to coordinator queue server
  if (path === '/api/pipeline-status') {
    const pipelinePort = url.searchParams.get('port') || '3500';
    const proxy = httpRequest(
      {
        hostname: '127.0.0.1',
        port: parseInt(pipelinePort, 10),
        path: '/status',
        method: 'GET',
        timeout: 3000,
      },
      (proxyRes) => {
        const chunks: Buffer[] = [];
        proxyRes.on('data', (c: Buffer) => chunks.push(c));
        proxyRes.on('end', () => {
          res.writeHead(proxyRes.statusCode ?? 502, { 'Content-Type': 'application/json' });
          res.end(Buffer.concat(chunks));
        });
      },
    );
    proxy.on('error', () => {
      res.writeHead(502, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Pipeline coordinator not reachable' }));
    });
    proxy.on('timeout', () => {
      proxy.destroy();
    });
    proxy.end();
    return;
  }

  // Monitor page
  if (path === '/monitor' || path === '/monitor.html') {
    const monitorPath = resolve(__dirname, 'monitor.html');
    if (existsSync(monitorPath)) {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(readFileSync(monitorPath));
    } else {
      res.writeHead(404);
      res.end('Monitor page not found');
    }
    return;
  }

  // Serve a specific flop file (supports ?config= param)
  if (path.startsWith('/data/')) {
    const filename = path.replace('/data/', '');
    const filePath = join(activeDataDir, filename);
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
  console.log(`\n  CFR Strategy Viewer V2: http://localhost:${PORT}`);
  console.log(`  Preflop Knowledge Base: http://localhost:${PORT}/preflop\n`);
  console.log(`  Default data: ${DATA_DIR}`);
  const configList = Object.entries(DATA_DIRS);
  if (configList.length > 0) {
    console.log(`  Available configs:`);
    for (const [name, dir] of configList) {
      const count = existsSync(dir)
        ? readdirSync(dir).filter((f) => f.endsWith('.jsonl')).length
        : 0;
      console.log(`    ${name}: ${count} flops${dir === DATA_DIR ? ' (default)' : ''}`);
    }
  }
  console.log();
});
