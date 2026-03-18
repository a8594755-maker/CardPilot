#!/usr/bin/env tsx
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { allHandClasses } from '../../src/preflop/preflop-types.js';
import type {
  LibraryPosition,
  LibrarySpot,
  PreflopLibraryV1,
} from '../../src/preflop/preflop-library.js';
import { toLegacyChartEntries } from '../../src/preflop/preflop-library.js';

const RANKS = 'AKQJT98765432';
const HAND_CLASSES = allHandClasses();
const HAND_CLASS_SET = new Set(HAND_CLASSES);

type SummarySeed = {
  sourceLabel: string;
  raisePct?: number;
  limpPct?: number;
  foldPct?: number;
  combos?: number;
};

const SUMMARY: Record<string, SummarySeed> = {
  LJ_RFI: { sourceLabel: 'LJ Raise 17.0%', raisePct: 0.17, foldPct: 0.83, combos: 226 },
  HJ_RFI: { sourceLabel: 'HJ Raise 21.4%', raisePct: 0.214, foldPct: 0.786, combos: 284 },
  CO_RFI: { sourceLabel: 'CO Raise 27.8%', raisePct: 0.278, foldPct: 0.722, combos: 368 },
  BTN_RFI: { sourceLabel: 'BTN Raise 43.3%', raisePct: 0.433, foldPct: 0.567, combos: 574 },
  SB_vs_BB_strategy: {
    sourceLabel: 'SB Raise 24.3 / Limp 38.0 / Fold 37.7',
    raisePct: 0.243,
    limpPct: 0.38,
    foldPct: 0.377,
    combos: 1326,
  },
  BB_vs_SB_limp: {
    sourceLabel: 'BB vs SB Limp',
    raisePct: 0.404,
    foldPct: 0,
    combos: 1326,
  },
  BB_vs_SB_raise: {
    sourceLabel: 'BB vs SB Raise',
    raisePct: 0.164,
    foldPct: 0.353,
    combos: 1326,
  },
};

interface ParsedMatrix {
  actionsByHand: Record<string, string>;
}

interface ParsedActionLists {
  actionsByHand: Record<string, string>;
  conflicts: number;
}

interface BuildSpotOptions {
  id: string;
  heroPosition: LibraryPosition;
  scenario: string;
  actions: string[];
  handToAction: Record<string, string>;
  notes?: string[];
}

function getArg(name: string, fallback: string): string {
  const idx = process.argv.indexOf(`--${name}`);
  if (idx >= 0 && process.argv[idx + 1]) return process.argv[idx + 1];
  return fallback;
}

function hasFlag(name: string): boolean {
  return process.argv.includes(`--${name}`);
}

function normalizeHandClass(tokenRaw: string): string | null {
  const token = tokenRaw.trim().replace(/\s+/g, '');
  if (!token) return null;
  if (!/^[AKQJT2-9]{2}[soSO]?$/.test(token)) return null;
  if (token.length === 2) {
    if (token[0] !== token[1]) return null;
    return token;
  }
  const hi = token[0];
  const lo = token[1];
  if (hi === lo) return null;
  return `${hi}${lo}${token[2].toLowerCase()}`;
}

function splitTokens(expr: string): string[] {
  return expr
    .replace(/[（(].*?[）)]/g, '')
    .replace(/，/g, ',')
    .replace(/\s+/g, '')
    .split(',')
    .map((v) => v.trim())
    .filter(Boolean);
}

function expandExpression(expr: string): string[] {
  const out = new Set<string>();
  for (const token of splitTokens(expr)) {
    for (const hand of expandToken(token)) out.add(hand);
  }
  return [...out];
}

function expandToken(tokenRaw: string): string[] {
  const token = tokenRaw.replace(/–/g, '-').trim();
  if (!token) return [];

  const plusMatch = token.match(/^([AKQJT2-9]{2}[soSO]?)\+$/);
  if (plusMatch) {
    return expandPlus(plusMatch[1]);
  }

  const rangeMatch = token.match(/^([AKQJT2-9]{2}[soSO]?)-([AKQJT2-9]{2}[soSO]?)$/);
  if (rangeMatch) {
    return expandRange(rangeMatch[1], rangeMatch[2]);
  }

  const single = normalizeHandClass(token);
  return single ? [single] : [];
}

function expandPlus(baseRaw: string): string[] {
  const base = normalizeHandClass(baseRaw);
  if (!base) return [];
  const out: string[] = [];

  if (base.length === 2) {
    const start = RANKS.indexOf(base[0]);
    for (let i = start; i >= 0; i--) out.push(`${RANKS[i]}${RANKS[i]}`);
    return out;
  }

  const a = base[0];
  const b = base[1];
  const suffix = base[2];
  const ia = RANKS.indexOf(a);
  const ib = RANKS.indexOf(b);
  if (ia < 0 || ib < 0 || ia >= ib) return [];
  for (let i = ib; i > ia; i--) out.push(`${a}${RANKS[i]}${suffix}`);
  return out;
}

function expandRange(startRaw: string, endRaw: string): string[] {
  const start = normalizeHandClass(startRaw);
  const end = normalizeHandClass(endRaw);
  if (!start || !end) return [];
  const out: string[] = [];

  if (start.length === 2 && end.length === 2) {
    const is = RANKS.indexOf(start[0]);
    const ie = RANKS.indexOf(end[0]);
    if (is < 0 || ie < 0) return [];
    const lo = Math.min(is, ie);
    const hi = Math.max(is, ie);
    for (let i = hi; i >= lo; i--) out.push(`${RANKS[i]}${RANKS[i]}`);
    return out;
  }

  if (start.length !== 3 || end.length !== 3 || start[2] !== end[2]) return [];

  const s1 = RANKS.indexOf(start[0]);
  const s2 = RANKS.indexOf(start[1]);
  const e1 = RANKS.indexOf(end[0]);
  const e2 = RANKS.indexOf(end[1]);
  if (s1 < 0 || s2 < 0 || e1 < 0 || e2 < 0) return [];

  if (start[0] === end[0]) {
    const lo = Math.min(s2, e2);
    const hi = Math.max(s2, e2);
    for (let i = hi; i >= lo; i--) out.push(`${start[0]}${RANKS[i]}${start[2]}`);
    return out;
  }

  if (start[1] === end[1]) {
    const lo = Math.min(s1, e1);
    const hi = Math.max(s1, e1);
    for (let i = hi; i >= lo; i--) out.push(`${RANKS[i]}${start[1]}${start[2]}`);
    return out;
  }

  return [];
}

function section(content: string, marker: RegExp): string {
  const match = content.match(marker);
  return match ? (match[1] ?? match[0]) : '';
}

function parseRfiSection(sectionText: string): Set<string> {
  const hands = new Set<string>();
  const rowRegex = /^\|\s*\*\*[^|]+\*\*\s*\|\s*([^|]+?)\s*\|/gm;
  let row: RegExpExecArray | null;
  while ((row = rowRegex.exec(sectionText)) !== null) {
    const expr = row[1].trim();
    if (!expr || expr.includes('範圍') || expr === '—') continue;
    for (const hand of expandExpression(expr)) {
      if (HAND_CLASS_SET.has(hand)) hands.add(hand);
    }
  }
  return hands;
}

function parseMatrix(sectionText: string): ParsedMatrix {
  const blockMatch = sectionText.match(/###\s*13[×x]13[\s\S]*?```([\s\S]*?)```/);
  if (!blockMatch) throw new Error('matrix block not found');
  const lines = blockMatch[1]
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);

  const actionsByHand: Record<string, string> = {};
  const rowRanks: string[] = [];
  for (const line of lines) {
    if (/^[A KQJT98765432]{20,}$/.test(line.replace(/\s+/g, ''))) continue;
    const parts = line.split(/\s+/);
    if (!/^[AKQJT2-9]$/.test(parts[0])) continue;
    if (parts.length < 14) continue;
    rowRanks.push(parts[0]);
    const row = rowRanks.length - 1;
    for (let col = 0; col < 13; col++) {
      const colRank = RANKS[col];
      const action = parts[col + 1];
      const handClass = matrixCellToHandClass(row, col, parts[0], colRank);
      actionsByHand[handClass] = action;
    }
  }

  if (Object.keys(actionsByHand).length !== 169) {
    throw new Error(`matrix parsed ${Object.keys(actionsByHand).length} hands, expected 169`);
  }
  return { actionsByHand };
}

function matrixCellToHandClass(row: number, col: number, rowRank: string, colRank: string): string {
  if (row === col) return `${rowRank}${rowRank}`;
  if (row < col) return `${rowRank}${colRank}s`;
  return `${colRank}${rowRank}o`;
}

function parseActionLists(sectionText: string): ParsedActionLists {
  const actionsByHand: Record<string, string> = {};
  let conflicts = 0;

  const blockRegex = /\*\*([^*]+?)\*\*[\s\S]*?```([\s\S]*?)```/g;
  let match: RegExpExecArray | null;
  while ((match = blockRegex.exec(sectionText)) !== null) {
    const header = match[1];
    const codeBlock = match[2];
    const actionCodeMatch = header.match(/(?:—|-)\s*([A-Z0-9]+)/i);
    if (!actionCodeMatch) continue;
    const action = actionCodeMatch[1].toUpperCase();
    const tokens = codeBlock
      .replace(/\n/g, ',')
      .split(',')
      .map((v) => normalizeHandClass(v))
      .filter((v): v is string => Boolean(v));

    for (const hand of tokens) {
      if (!HAND_CLASS_SET.has(hand)) continue;
      if (actionsByHand[hand] && actionsByHand[hand] !== action) conflicts++;
      actionsByHand[hand] = action;
    }
  }

  return { actionsByHand, conflicts };
}

function buildSpot(options: BuildSpotOptions): LibrarySpot {
  const { id, heroPosition, scenario, actions, handToAction, notes } = options;
  const grid: Record<string, Record<string, number>> = {};
  for (const handClass of HAND_CLASSES) {
    const action = handToAction[handClass];
    if (!action) {
      throw new Error(`spot ${id} missing action for hand ${handClass}`);
    }
    const mix: Record<string, number> = {};
    for (const a of actions) mix[a] = a === action ? 1 : 0;
    grid[handClass] = mix;
  }

  const summarySeed = SUMMARY[id] ?? { sourceLabel: id };
  return {
    id,
    format: 'chart_exact_v1',
    coverage: 'exact',
    heroPosition,
    scenario,
    actions,
    summary: {
      ...summarySeed,
      notes,
    },
    grid,
  };
}

function buildRfiSpot(id: string, heroPosition: LibraryPosition, sectionText: string): LibrarySpot {
  const raises = parseRfiSection(sectionText);
  const handToAction: Record<string, string> = {};
  for (const handClass of HAND_CLASSES) {
    handToAction[handClass] = raises.has(handClass) ? 'raise' : 'fold';
  }
  return buildSpot({
    id,
    heroPosition,
    scenario: 'RFI',
    actions: ['raise', 'fold'],
    handToAction,
  });
}

function buildMatrixSpot(
  id: string,
  heroPosition: LibraryPosition,
  scenario: string,
  sectionText: string,
  actions: string[],
): LibrarySpot {
  const matrix = parseMatrix(sectionText);
  const lists = parseActionLists(sectionText);

  const handToAction: Record<string, string> = {};
  for (const handClass of HAND_CLASSES) {
    const fromMatrix = matrix.actionsByHand[handClass];
    const fromList = lists.actionsByHand[handClass];
    handToAction[handClass] = fromMatrix ?? fromList ?? '';
  }

  return buildSpot({
    id,
    heroPosition,
    scenario,
    actions,
    handToAction,
    notes: [`matrix_list_conflicts=${lists.conflicts}`, 'matrix_priority=enabled'],
  });
}

export function parseChartToLibrary(markdown: string, chartPath: string): PreflopLibraryV1 {
  const ljSection = section(markdown, /##\s*1️⃣[\s\S]*?Lojack[\s\S]*?(?=\n##\s*2️⃣|\n##\s*2️⃣|$)/);
  const hjSection = section(markdown, /##\s*2️⃣[\s\S]*?Hijack[\s\S]*?(?=\n##\s*3️⃣|$)/);
  const coSection = section(markdown, /##\s*3️⃣[\s\S]*?Cutoff[\s\S]*?(?=\n##\s*4️⃣|$)/);
  const btnSection = section(markdown, /##\s*4️⃣[\s\S]*?Button[\s\S]*?(?=\n##\s*5️⃣|$)/);
  const sbSection = section(markdown, /##\s*5️⃣[\s\S]*?Small Blind[\s\S]*?(?=\n##\s*6️⃣|$)/);
  const bbLimpSection = section(
    markdown,
    /##\s*6️⃣[\s\S]*?Big Blind vs SB Limp[\s\S]*?(?=\n##\s*7️⃣|$)/,
  );
  const bbRaiseSection = section(markdown, /##\s*7️⃣[\s\S]*?Big Blind vs SB Raise[\s\S]*$/);

  const spots: LibrarySpot[] = [
    buildRfiSpot('LJ_RFI', 'LJ', ljSection),
    buildRfiSpot('HJ_RFI', 'HJ', hjSection),
    buildRfiSpot('CO_RFI', 'CO', coSection),
    buildRfiSpot('BTN_RFI', 'BTN', btnSection),
    buildMatrixSpot('SB_vs_BB_strategy', 'SB', 'vs_bb_unopened', sbSection, [
      'R4',
      'RC',
      'RF',
      'LR',
      'LC',
      'LF',
      'F',
    ]),
    buildMatrixSpot('BB_vs_SB_limp', 'BB', 'vs_sb_limp', bbLimpSection, ['R', 'X']),
    buildMatrixSpot('BB_vs_SB_raise', 'BB', 'vs_sb_raise', bbRaiseSection, ['3B', 'C', 'F']),
  ];

  return {
    version: '1.0',
    generatedAt: new Date().toISOString(),
    source: {
      chartPath,
      parser: 'preflop-chart-parser/v1',
    },
    spots,
  };
}

export function runParseChart(options: {
  chartPath: string;
  outputPath: string;
  legacyOutputPath: string;
  generatedAt?: string;
  quiet?: boolean;
}): { library: PreflopLibraryV1; spotCount: number; legacyEntries: number } {
  const markdown = readFileSync(options.chartPath, 'utf-8');
  const library = parseChartToLibrary(markdown, options.chartPath);
  if (options.generatedAt) {
    library.generatedAt = options.generatedAt;
  }
  const legacy = toLegacyChartEntries(library);

  mkdirSync(dirname(options.outputPath), { recursive: true });
  mkdirSync(dirname(options.legacyOutputPath), { recursive: true });
  writeFileSync(options.outputPath, JSON.stringify(library, null, 2));
  writeFileSync(options.legacyOutputPath, JSON.stringify(legacy, null, 2));

  if (!options.quiet) {
    console.log(`Wrote canonical library: ${options.outputPath}`);
    console.log(`Wrote legacy chart data: ${options.legacyOutputPath}`);
    console.log(`Spots: ${library.spots.length}, legacy entries: ${legacy.length}`);
  }

  return {
    library,
    spotCount: library.spots.length,
    legacyEntries: legacy.length,
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const chartPath = resolve(
    getArg('chart', resolve(process.cwd(), 'GTO + sample', 'Preflop Strategy Chart.md')),
  );
  const outputPath = resolve(
    getArg('out', resolve(process.cwd(), 'data', 'preflop', 'preflop_library.v1.json')),
  );
  const legacyOutputPath = resolve(
    getArg('legacy-out', resolve(process.cwd(), 'data', 'preflop_charts.json')),
  );
  const generatedAt = getArg('generated-at', '');

  runParseChart({
    chartPath,
    outputPath,
    legacyOutputPath,
    generatedAt: generatedAt || undefined,
    quiet: hasFlag('quiet'),
  });
}
