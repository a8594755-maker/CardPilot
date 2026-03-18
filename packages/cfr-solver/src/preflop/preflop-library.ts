import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { allHandClasses } from './preflop-types.js';

export type LibraryCoverage = 'exact';

export type LibraryPosition = 'LJ' | 'HJ' | 'CO' | 'BTN' | 'SB' | 'BB';

export interface LibrarySpotSummary {
  sourceLabel?: string;
  raisePct?: number;
  limpPct?: number;
  foldPct?: number;
  combos?: number;
  notes?: string[];
}

export interface LibrarySpot {
  id: string;
  format: string;
  coverage: LibraryCoverage;
  heroPosition: LibraryPosition;
  scenario: string;
  actions: string[];
  summary: LibrarySpotSummary;
  grid: Record<string, Record<string, number>>;
}

export interface PreflopLibraryV1 {
  version: '1.0';
  generatedAt: string;
  source: {
    chartPath: string;
    parser: string;
  };
  spots: LibrarySpot[];
}

export interface LegacyChartEntry {
  format: string;
  spot: string;
  hand: string;
  mix: Record<string, number>;
  notes?: string[];
}

const HAND_CLASSES = new Set(allHandClasses());

export function loadPreflopLibrary(filePath?: string): PreflopLibraryV1 | null {
  const path = filePath ?? resolve(process.cwd(), 'data', 'preflop', 'preflop_library.v1.json');

  if (!existsSync(path)) return null;
  const raw = JSON.parse(readFileSync(path, 'utf-8')) as unknown;
  return parsePreflopLibrary(raw);
}

export function parsePreflopLibrary(raw: unknown): PreflopLibraryV1 {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    throw new Error('preflop library must be an object');
  }
  const root = raw as Record<string, unknown>;
  if (root.version !== '1.0') {
    throw new Error(`unsupported preflop library version: ${String(root.version)}`);
  }
  if (!Array.isArray(root.spots)) {
    throw new Error('preflop library spots must be an array');
  }

  const spots = root.spots.map(parseSpot);
  return {
    version: '1.0',
    generatedAt: String(root.generatedAt ?? ''),
    source: parseSource(root.source),
    spots,
  };
}

function parseSource(value: unknown): { chartPath: string; parser: string } {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return { chartPath: '', parser: '' };
  }
  const source = value as Record<string, unknown>;
  return {
    chartPath: String(source.chartPath ?? ''),
    parser: String(source.parser ?? ''),
  };
}

function parseSpot(raw: unknown): LibrarySpot {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    throw new Error('library spot must be an object');
  }
  const spot = raw as Record<string, unknown>;
  if (!Array.isArray(spot.actions) || spot.actions.length === 0) {
    throw new Error(`spot ${String(spot.id)} has no actions`);
  }
  if (typeof spot.grid !== 'object' || spot.grid === null || Array.isArray(spot.grid)) {
    throw new Error(`spot ${String(spot.id)} has invalid grid`);
  }

  const actions = spot.actions.map((a) => String(a));
  const grid = parseGrid(spot.grid, actions, String(spot.id ?? ''));

  return {
    id: String(spot.id ?? ''),
    format: String(spot.format ?? ''),
    coverage: 'exact',
    heroPosition: String(spot.heroPosition ?? '') as LibraryPosition,
    scenario: String(spot.scenario ?? ''),
    actions,
    summary: parseSummary(spot.summary),
    grid,
  };
}

function parseSummary(value: unknown): LibrarySpotSummary {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return {};
  }
  const summary = value as Record<string, unknown>;
  return {
    sourceLabel: summary.sourceLabel ? String(summary.sourceLabel) : undefined,
    raisePct: toOptionalNumber(summary.raisePct),
    limpPct: toOptionalNumber(summary.limpPct),
    foldPct: toOptionalNumber(summary.foldPct),
    combos: toOptionalNumber(summary.combos),
    notes: Array.isArray(summary.notes) ? summary.notes.map((n) => String(n)) : undefined,
  };
}

function parseGrid(
  rawGrid: unknown,
  actions: string[],
  spotId: string,
): Record<string, Record<string, number>> {
  const gridObj = rawGrid as Record<string, unknown>;
  const grid: Record<string, Record<string, number>> = {};

  for (const [handClass, rawMix] of Object.entries(gridObj)) {
    if (!HAND_CLASSES.has(handClass)) {
      throw new Error(`spot ${spotId} has unknown hand class: ${handClass}`);
    }
    if (typeof rawMix !== 'object' || rawMix === null || Array.isArray(rawMix)) {
      throw new Error(`spot ${spotId} hand ${handClass} has invalid mix`);
    }
    const mixObj = rawMix as Record<string, unknown>;
    const mix: Record<string, number> = {};
    let sum = 0;
    for (const action of actions) {
      const value = Number(mixObj[action] ?? 0);
      if (!Number.isFinite(value) || value < 0 || value > 1) {
        throw new Error(`spot ${spotId} hand ${handClass} action ${action} out of range`);
      }
      mix[action] = value;
      sum += value;
    }
    if (Math.abs(sum - 1) > 1e-4) {
      throw new Error(
        `spot ${spotId} hand ${handClass} mix does not sum to 1 (sum=${sum.toFixed(6)})`,
      );
    }
    grid[handClass] = mix;
  }

  for (const handClass of HAND_CLASSES) {
    if (!grid[handClass]) {
      throw new Error(`spot ${spotId} missing hand class ${handClass}`);
    }
  }

  return grid;
}

function toOptionalNumber(value: unknown): number | undefined {
  if (value === undefined || value === null) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export function getLibrarySpot(library: PreflopLibraryV1, spotId: string): LibrarySpot | null {
  for (const spot of library.spots) {
    if (spot.id === spotId) return spot;
  }
  return null;
}

export function listLibrarySpots(library: PreflopLibraryV1): Array<{
  id: string;
  heroPosition: LibraryPosition;
  scenario: string;
  coverage: LibraryCoverage;
}> {
  return library.spots.map((spot) => ({
    id: spot.id,
    heroPosition: spot.heroPosition,
    scenario: spot.scenario,
    coverage: spot.coverage,
  }));
}

export function toLegacyChartEntries(library: PreflopLibraryV1): LegacyChartEntry[] {
  const entries: LegacyChartEntry[] = [];
  for (const spot of library.spots) {
    for (const handClass of Object.keys(spot.grid)) {
      entries.push({
        format: spot.format,
        spot: spot.id,
        hand: handClass,
        mix: { ...spot.grid[handClass] },
        notes: spot.summary.notes,
      });
    }
  }
  return entries;
}
