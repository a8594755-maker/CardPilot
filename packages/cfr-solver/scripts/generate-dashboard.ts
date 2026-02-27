#!/usr/bin/env tsx
/**
 * Generates dashboard-data.json from all solved .meta.json files.
 * Usage: npx tsx scripts/generate-dashboard.ts [--config pipeline_hu_3bet_50bb]
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Card encoding (same as card-index.ts)
const RANK_CHARS = '23456789TJQKA';
const SUIT_CHARS = 'cdhs';
const SUIT_SYMBOLS: Record<string, string> = { c: '\u2663', d: '\u2666', h: '\u2665', s: '\u2660' };

function indexToCard(index: number): string {
  return RANK_CHARS[index >> 2] + SUIT_CHARS[index & 3];
}

function indexToRank(index: number): number {
  return index >> 2;
}

function indexToSuit(index: number): number {
  return index & 3;
}

function indexToReadable(index: number): string {
  return RANK_CHARS[index >> 2] + SUIT_SYMBOLS[SUIT_CHARS[index & 3]];
}

interface FlopTexture {
  suitedness: 'monotone' | 'two-tone' | 'rainbow';
  pairing: 'trips' | 'paired' | 'unpaired';
  highCard: string; // rank char: A, K, Q, etc.
  connected: boolean; // all 3 cards within 4 ranks
}

function classifyFlop(cards: number[]): FlopTexture {
  const ranks = cards.map(indexToRank).sort((a, b) => b - a);
  const suits = cards.map(indexToSuit);

  // Suitedness
  const uniqueSuits = new Set(suits).size;
  const suitedness = uniqueSuits === 1 ? 'monotone' : uniqueSuits === 2 ? 'two-tone' : 'rainbow';

  // Pairing
  const uniqueRanks = new Set(ranks).size;
  const pairing = uniqueRanks === 1 ? 'trips' : uniqueRanks === 2 ? 'paired' : 'unpaired';

  // High card
  const highCard = RANK_CHARS[ranks[0]];

  // Connectedness: max rank spread <= 4 (e.g., 5-6-7, 8-9-T)
  const spread = ranks[0] - ranks[ranks.length - 1];
  const connected = spread <= 4 && uniqueRanks === 3;

  return { suitedness, pairing, highCard, connected };
}

interface MetaFile {
  version: string;
  keyFormat: string;
  game: string;
  stack: string;
  config: string;
  boardId: number;
  flopCards: number[];
  iterations: number;
  bucketCount: number;
  infoSets: number;
  elapsedMs: number;
  peakMemoryMB: number;
  timestamp: string;
  betSizes: { flop: number[]; turn: number[]; river: number[] };
}

// --- Main ---
const args = process.argv.slice(2);
let configName = 'pipeline_hu_3bet_50bb';
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--config' && args[i + 1]) configName = args[i + 1];
}

const projectRoot = path.resolve(__dirname, '../../..');
const dataDir = path.join(projectRoot, 'data', 'cfr', configName);
const outFile = path.join(__dirname, '..', 'viewer', 'dashboard-data.json');

if (!fs.existsSync(dataDir)) {
  console.error(`Data directory not found: ${dataDir}`);
  process.exit(1);
}

console.log(`Scanning ${dataDir} ...`);

const files = fs.readdirSync(dataDir).filter(f => f.endsWith('.meta.json'));
console.log(`Found ${files.length} meta files`);

const flops: any[] = [];
let totalInfoSets = 0;
let totalElapsedMs = 0;
let totalMemory = 0;
let minElapsed = Infinity;
let maxElapsed = 0;
let minInfoSets = Infinity;
let maxInfoSets = 0;

const textureCounts = {
  monotone: 0, 'two-tone': 0, rainbow: 0,
  trips: 0, paired: 0, unpaired: 0,
  connected: 0,
};

const highCardCounts: Record<string, number> = {};

/** Extract root-node strategy from a JSONL file.
 *  OOP opening: F|boardId|0||bucket → [check, bet, allin]
 *  IP after check: F|boardId|1|x|bucket → [check, bet, allin]
 *  Returns averaged probs across all buckets. */
function extractStrategy(jsonlPath: string, boardId: number) {
  const oopPrefix = `"F|${boardId}|0||`;
  const ipPrefix = `"F|${boardId}|1|x|`;
  const oopProbs: number[][] = [];
  const ipProbs: number[][] = [];

  const content = fs.readFileSync(jsonlPath, 'utf-8');
  for (const line of content.split('\n')) {
    if (!line) continue;
    if (line.includes(oopPrefix)) {
      const entry = JSON.parse(line);
      oopProbs.push(entry.probs);
    } else if (line.includes(ipPrefix)) {
      const entry = JSON.parse(line);
      ipProbs.push(entry.probs);
    }
  }

  function avg(arr: number[][]): number[] | null {
    if (arr.length === 0) return null;
    const n = arr[0].length;
    const sums = new Array(n).fill(0);
    for (const row of arr) for (let i = 0; i < n; i++) sums[i] += row[i];
    return sums.map(s => Math.round(s / arr.length * 1000) / 1000);
  }

  return { oop: avg(oopProbs), ip: avg(ipProbs) };
}

let processed = 0;
for (const file of files) {
  const meta: MetaFile = JSON.parse(fs.readFileSync(path.join(dataDir, file), 'utf-8'));
  const texture = classifyFlop(meta.flopCards);

  const cardsReadable = meta.flopCards.map(indexToReadable).join(' ');
  const cardsShort = meta.flopCards.map(indexToCard).join(' ');

  // Extract strategy from corresponding JSONL
  const jsonlFile = file.replace('.meta.json', '.jsonl');
  const jsonlPath = path.join(dataDir, jsonlFile);
  let strategy: { oop: number[] | null; ip: number[] | null } = { oop: null, ip: null };
  if (fs.existsSync(jsonlPath)) {
    strategy = extractStrategy(jsonlPath, meta.boardId);
  }

  flops.push({
    boardId: meta.boardId,
    cards: cardsShort,
    cardsReadable,
    flopCards: meta.flopCards,
    texture,
    infoSets: meta.infoSets,
    elapsedMs: meta.elapsedMs,
    peakMemoryMB: meta.peakMemoryMB,
    timestamp: meta.timestamp,
    // Strategy: OOP opening [check, bet, allin], IP after check [check, bet, allin]
    oopStrategy: strategy.oop,  // [check%, bet%, allin%]
    ipStrategy: strategy.ip,    // [checkBack%, bet%, allin%]
  });

  totalInfoSets += meta.infoSets;
  totalElapsedMs += meta.elapsedMs;
  totalMemory += meta.peakMemoryMB;
  minElapsed = Math.min(minElapsed, meta.elapsedMs);
  maxElapsed = Math.max(maxElapsed, meta.elapsedMs);
  minInfoSets = Math.min(minInfoSets, meta.infoSets);
  maxInfoSets = Math.max(maxInfoSets, meta.infoSets);

  textureCounts[texture.suitedness]++;
  textureCounts[texture.pairing]++;
  if (texture.connected) textureCounts.connected++;
  highCardCounts[texture.highCard] = (highCardCounts[texture.highCard] || 0) + 1;

  processed++;
  if (processed % 100 === 0) process.stdout.write(`\r  Processing ${processed}/${files.length}...`);
}
console.log(`\r  Processed ${processed}/${files.length} flops (with strategy extraction)`);

// Sort by boardId
flops.sort((a, b) => a.boardId - b.boardId);

// Use first meta for config info
const sampleMeta: MetaFile = JSON.parse(fs.readFileSync(path.join(dataDir, files[0]), 'utf-8'));

const dashboard = {
  generatedAt: new Date().toISOString(),
  config: {
    name: configName,
    game: sampleMeta.game,
    stack: sampleMeta.stack,
    configLabel: sampleMeta.config,
    iterations: sampleMeta.iterations,
    bucketCount: sampleMeta.bucketCount,
    betSizes: sampleMeta.betSizes,
  },
  summary: {
    totalFlops: flops.length,
    totalInfoSets,
    totalElapsedMs,
    avgElapsedMs: Math.round(totalElapsedMs / flops.length),
    minElapsedMs: minElapsed,
    maxElapsedMs: maxElapsed,
    avgInfoSets: Math.round(totalInfoSets / flops.length),
    minInfoSets,
    maxInfoSets,
    avgMemoryMB: Math.round(totalMemory / flops.length),
  },
  textures: textureCounts,
  highCardCounts,
  flops,
};

fs.writeFileSync(outFile, JSON.stringify(dashboard));
const sizeMB = (fs.statSync(outFile).size / 1024 / 1024).toFixed(1);

// Also generate self-contained HTML with embedded data
const htmlTemplate = fs.readFileSync(path.join(__dirname, '..', 'viewer', 'dashboard.html'), 'utf-8');
const embedScript = `<script>window.DASHBOARD_DATA = ${JSON.stringify(dashboard)};</script>`;
const embeddedHtml = htmlTemplate.replace('</head>', embedScript + '\n</head>');
const embedOutFile = path.join(__dirname, '..', 'viewer', 'dashboard-standalone.html');
fs.writeFileSync(embedOutFile, embeddedHtml);
const embedSizeMB = (fs.statSync(embedOutFile).size / 1024 / 1024).toFixed(1);

console.log(`\nWritten ${outFile} (${sizeMB} MB)`);
console.log(`Written ${embedOutFile} (${embedSizeMB} MB) [standalone, no server needed]`);
console.log(`  Flops: ${flops.length}`);
console.log(`  Total info sets: ${(totalInfoSets / 1e6).toFixed(1)}M`);
console.log(`  Total solve time: ${(totalElapsedMs / 3600000).toFixed(1)}h`);
console.log(`  Avg solve time: ${(dashboard.summary.avgElapsedMs / 1000).toFixed(0)}s`);
console.log(`  Textures: rainbow=${textureCounts.rainbow} two-tone=${textureCounts['two-tone']} monotone=${textureCounts.monotone}`);
console.log(`  Pairing: unpaired=${textureCounts.unpaired} paired=${textureCounts.paired} trips=${textureCounts.trips}`);
