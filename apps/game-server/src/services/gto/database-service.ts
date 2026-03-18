import { randomUUID } from 'node:crypto';
import {
  readFileSync,
  writeFileSync,
  existsSync,
  mkdirSync,
  readdirSync,
  unlinkSync,
} from 'node:fs';
import { join, resolve } from 'node:path';
import type {
  FlopDatabase,
  FlopEntry,
  FlopResults,
  AggregateReport,
  FlopSubset,
} from '@cardpilot/shared-types';

// Try multiple candidate paths for the databases directory
function findDatabaseDir(): string {
  const candidates = [
    resolve(process.cwd(), 'data', 'databases'),
    join(process.cwd(), 'data', 'databases'),
  ];
  for (const c of candidates) {
    if (existsSync(c)) return c;
  }
  // Default: create under cwd
  const dir = resolve(process.cwd(), 'data', 'databases');
  mkdirSync(dir, { recursive: true });
  return dir;
}

const DATA_DIR = findDatabaseDir();

const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2'];
const SUITS = ['s', 'h', 'd', 'c'];

function dbPath(id: string): string {
  return join(DATA_DIR, `${id}.json`);
}

function loadDb(id: string): FlopDatabase | null {
  const path = dbPath(id);
  if (!existsSync(path)) return null;
  return JSON.parse(readFileSync(path, 'utf-8'));
}

function saveDb(db: FlopDatabase): void {
  writeFileSync(dbPath(db.id), JSON.stringify(db, null, 2));
}

export function createDatabase(name: string, config: FlopDatabase['config']): FlopDatabase {
  const db: FlopDatabase = {
    id: randomUUID(),
    name,
    createdAt: new Date().toISOString(),
    config,
    flops: [],
    status: 'idle',
  };
  saveDb(db);
  return db;
}

export function getDatabase(id: string): FlopDatabase | null {
  return loadDb(id);
}

export function listDatabases(): Array<{
  id: string;
  name: string;
  flopCount: number;
  status: string;
  createdAt: string;
}> {
  if (!existsSync(DATA_DIR)) return [];
  const files = readdirSync(DATA_DIR).filter((f: string) => f.endsWith('.json'));
  return files.map((f: string) => {
    const db = JSON.parse(readFileSync(join(DATA_DIR, f), 'utf-8')) as FlopDatabase;
    return {
      id: db.id,
      name: db.name,
      flopCount: db.flops.length,
      status: db.status,
      createdAt: db.createdAt,
    };
  });
}

export function deleteDatabase(id: string): boolean {
  const path = dbPath(id);
  if (!existsSync(path)) return false;
  unlinkSync(path);
  return true;
}

export function addFlops(
  id: string,
  flops: Array<{ cards: [string, string, string]; weight?: number }>,
): FlopDatabase | null {
  const db = loadDb(id);
  if (!db) return null;

  for (const flop of flops) {
    // Check for duplicates
    const exists = db.flops.some((f) => f.cards.join('') === flop.cards.join(''));
    if (exists) continue;

    db.flops.push({
      id: randomUUID(),
      cards: flop.cards,
      weight: flop.weight ?? 1,
      status: 'pending',
    });
  }

  saveDb(db);
  return db;
}

export function addRandomFlops(id: string, count: number): FlopDatabase | null {
  const db = loadDb(id);
  if (!db) return null;

  const allFlops = generateAllIsomorphicFlops();
  const shuffled = shuffleArray(allFlops);
  const toAdd = shuffled.slice(0, Math.min(count, shuffled.length));

  for (const cards of toAdd) {
    const exists = db.flops.some((f) => f.cards.join('') === cards.join(''));
    if (exists) continue;

    db.flops.push({
      id: randomUUID(),
      cards,
      weight: 1,
      status: 'pending',
    });
  }

  saveDb(db);
  return db;
}

export function toggleFlopIgnored(databaseId: string, flopId: string): FlopDatabase | null {
  const db = loadDb(databaseId);
  if (!db) return null;

  const flop = db.flops.find((f) => f.id === flopId);
  if (!flop) return null;

  flop.status = flop.status === 'ignored' ? 'pending' : 'ignored';
  saveDb(db);
  return db;
}

export function deleteFlop(databaseId: string, flopId: string): FlopDatabase | null {
  const db = loadDb(databaseId);
  if (!db) return null;

  db.flops = db.flops.filter((f) => f.id !== flopId);
  saveDb(db);
  return db;
}

export function getAggregateReport(id: string): AggregateReport | null {
  const db = loadDb(id);
  if (!db) return null;

  const solved = db.flops.filter(
    (f): f is FlopEntry & { results: FlopResults } => f.status === 'solved' && !!f.results,
  );

  if (solved.length === 0) {
    return {
      databaseId: db.id,
      databaseName: db.name,
      flopCount: db.flops.length,
      solvedCount: 0,
      averageOopEquity: 0,
      averageIpEquity: 0,
      averageOopEV: 0,
      averageIpEV: 0,
      averageBettingFreqs: {},
      perFlop: [],
    };
  }

  let totalWeight = 0;
  let weightedOopEq = 0;
  let weightedIpEq = 0;
  let weightedOopEv = 0;
  let weightedIpEv = 0;
  const weightedFreqs: Record<string, number> = {};

  for (const flop of solved) {
    const w = flop.weight;
    totalWeight += w;
    weightedOopEq += flop.results.oopEquity * w;
    weightedIpEq += flop.results.ipEquity * w;
    weightedOopEv += flop.results.oopEV * w;
    weightedIpEv += flop.results.ipEV * w;

    for (const [action, freq] of Object.entries(flop.results.bettingFrequency)) {
      weightedFreqs[action] = (weightedFreqs[action] || 0) + freq * w;
    }
  }

  const avgFreqs: Record<string, number> = {};
  for (const [action, total] of Object.entries(weightedFreqs)) {
    avgFreqs[action] = total / totalWeight;
  }

  return {
    databaseId: db.id,
    databaseName: db.name,
    flopCount: db.flops.length,
    solvedCount: solved.length,
    averageOopEquity: weightedOopEq / totalWeight,
    averageIpEquity: weightedIpEq / totalWeight,
    averageOopEV: weightedOopEv / totalWeight,
    averageIpEV: weightedIpEv / totalWeight,
    averageBettingFreqs: avgFreqs,
    perFlop: solved,
  };
}

export function updateFlopResults(databaseId: string, flopId: string, results: FlopResults): void {
  const db = loadDb(databaseId);
  if (!db) return;

  const flop = db.flops.find((f) => f.id === flopId);
  if (!flop) return;

  flop.results = results;
  flop.status = 'solved';

  // Check if all flops are solved
  const allSolved = db.flops.every((f) => f.status === 'solved' || f.status === 'ignored');
  if (allSolved) db.status = 'complete';

  saveDb(db);
}

/**
 * Generate all 1755 isomorphic flops.
 * Uses standardized suits (spades, diamonds, clubs).
 */
function generateAllIsomorphicFlops(): Array<[string, string, string]> {
  const flops: Array<[string, string, string]> = [];
  const seen = new Set<string>();

  for (let i = 0; i < 52; i++) {
    for (let j = i + 1; j < 52; j++) {
      for (let k = j + 1; k < 52; k++) {
        const cards = [indexToCard(i), indexToCard(j), indexToCard(k)] as [string, string, string];
        // Create a canonical form for isomorphism
        const canonical = canonicalizeFlop(cards);
        const key = canonical.join('');
        if (!seen.has(key)) {
          seen.add(key);
          flops.push(canonical);
        }
      }
    }
  }

  return flops;
}

function indexToCard(idx: number): string {
  return `${RANKS[idx % 13]}${SUITS[Math.floor(idx / 13)]}`;
}

function canonicalizeFlop(cards: [string, string, string]): [string, string, string] {
  // Sort by rank (descending)
  const parsed = cards
    .map((c) => ({
      card: c,
      rank: RANKS.indexOf(c[0]),
      suit: c[1],
    }))
    .sort((a, b) => a.rank - b.rank);

  // Standardize suits: first unique suit -> s, second -> h, third -> d
  const suitMap: Record<string, string> = {};
  const standardSuits = ['s', 'h', 'd', 'c'];
  let suitIdx = 0;

  for (const p of parsed) {
    if (!(p.suit in suitMap)) {
      suitMap[p.suit] = standardSuits[suitIdx++];
    }
  }

  return parsed.map((p) => `${p.card[0]}${suitMap[p.suit]}`) as [string, string, string];
}

function shuffleArray<T>(arr: T[]): T[] {
  const copy = [...arr];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

// Predefined weighted subsets
export const FLOP_SUBSETS: FlopSubset[] = [
  {
    name: 'subset_23',
    description: '23 representative flops (weighted)',
    count: 23,
    flops: [
      { cards: ['As', 'Kh', 'Qd'], weight: 3.2 },
      { cards: ['As', 'Ks', 'Qs'], weight: 0.8 },
      { cards: ['As', 'Kh', '7d'], weight: 4.5 },
      { cards: ['As', 'Qs', 'Jh'], weight: 3.0 },
      { cards: ['As', '8h', '3d'], weight: 5.0 },
      { cards: ['Ks', 'Qh', 'Jd'], weight: 2.8 },
      { cards: ['Ks', 'Th', '5d'], weight: 4.2 },
      { cards: ['Ks', '7h', '2d'], weight: 4.8 },
      { cards: ['Qs', 'Jh', 'Td'], weight: 2.5 },
      { cards: ['Qs', '9h', '4d'], weight: 4.0 },
      { cards: ['Js', 'Th', '9d'], weight: 2.2 },
      { cards: ['Js', '8h', '3d'], weight: 4.5 },
      { cards: ['Ts', '9h', '8d'], weight: 2.0 },
      { cards: ['Ts', '6h', '2d'], weight: 4.8 },
      { cards: ['9s', '7h', '5d'], weight: 3.5 },
      { cards: ['8s', '6h', '4d'], weight: 3.8 },
      { cards: ['7s', '5h', '3d'], weight: 4.0 },
      { cards: ['6s', '4h', '2d'], weight: 4.5 },
      { cards: ['As', 'Ah', 'Kd'], weight: 0.5 },
      { cards: ['Ks', 'Kh', '7d'], weight: 0.8 },
      { cards: ['9s', '9h', '3d'], weight: 1.2 },
      { cards: ['5s', '5h', 'Ad'], weight: 1.0 },
      { cards: ['As', '5s', '3s'], weight: 0.6 },
    ],
  },
];

export function loadSubset(name: string): FlopSubset | null {
  return FLOP_SUBSETS.find((s) => s.name === name) || null;
}
