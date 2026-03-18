// Service for loading and querying preflop ranges.
// Ground truth path is data/preflop/preflop_library.v1.json (exact-only).

import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

// Try multiple candidate paths for the data directory
function findDataRoot(): string {
  const candidates = [resolve(process.cwd(), 'data'), resolve(process.cwd(), '..', 'data')];
  for (const c of candidates) {
    if (existsSync(c)) return c;
  }
  return resolve(process.cwd(), 'data');
}

const DATA_ROOT = findDataRoot();
const PREFLOP_LIBRARY_PATH = join(DATA_ROOT, 'preflop', 'preflop_library.v1.json');
const PREFLOP_CHARTS_PATH = join(DATA_ROOT, 'preflop_charts.json');
const PREFLOP_SOLUTIONS_DIR = join(DATA_ROOT, 'preflop');

export const EXACT_CONFIG = 'chart-exact';

export interface PreflopSpot {
  spot: string;
  heroPosition: string;
  scenario: string;
  coverage: 'exact' | 'solver';
  file?: string;
}

export interface PreflopConfigList {
  configs: string[];
  hasGtoWizardData: boolean;
  coverageByConfig: Record<string, 'exact' | 'solver'>;
}

export interface PreflopRangeEntry {
  hand: string;
  actions: Record<string, number>;
}

export interface SpotSolution {
  spot: string;
  format: string;
  coverage?: 'exact' | 'solver';
  heroPosition: string;
  villainPosition?: string;
  scenario: string;
  potSize: number;
  actions: string[];
  grid: Record<string, Record<string, number>>;
  summary: {
    totalCombos: number;
    rangeSize: number;
    actionFrequencies: Record<string, number>;
  };
  metadata: {
    iterations: number;
    exploitability: number;
    solveDate: string;
    solver: string;
  };
}

interface CanonicalSpot {
  id: string;
  format: string;
  coverage: 'exact';
  heroPosition: string;
  scenario: string;
  actions: string[];
  summary?: {
    notes?: string[];
  };
  grid: Record<string, Record<string, number>>;
}

interface CanonicalLibrary {
  version: string;
  generatedAt: string;
  source: {
    chartPath: string;
    parser: string;
  };
  spots: CanonicalSpot[];
}

// Cache loaded solutions
const solutionCache = new Map<string, SpotSolution>();
let canonicalCache: CanonicalLibrary | null | undefined;

function comboCountForHand(hand: string): number {
  if (hand.length === 2) return 6;
  return hand.endsWith('s') ? 4 : 12;
}

function computeSpotSummary(spot: CanonicalSpot): {
  totalCombos: number;
  rangeSize: number;
  actionFrequencies: Record<string, number>;
} {
  const actionCombos: Record<string, number> = {};
  for (const action of spot.actions) actionCombos[action] = 0;

  let totalCombos = 0;
  let rangeSize = 0;
  for (const [hand, mix] of Object.entries(spot.grid)) {
    const combos = comboCountForHand(hand);
    totalCombos += combos;

    let isPureFold = true;
    for (const action of spot.actions) {
      const freq = Number(mix[action] ?? 0);
      if (freq > 0 && action !== 'fold' && action !== 'F') {
        isPureFold = false;
      }
      actionCombos[action] += combos * freq;
    }

    if (!isPureFold) rangeSize += combos;
  }

  const actionFrequencies: Record<string, number> = {};
  for (const action of spot.actions) {
    actionFrequencies[action] = totalCombos > 0 ? actionCombos[action] / totalCombos : 0;
  }

  return { totalCombos, rangeSize, actionFrequencies };
}

function loadCanonicalLibrary(): CanonicalLibrary | null {
  if (canonicalCache !== undefined) return canonicalCache;
  if (!existsSync(PREFLOP_LIBRARY_PATH)) {
    canonicalCache = null;
    return canonicalCache;
  }

  try {
    const parsed = JSON.parse(readFileSync(PREFLOP_LIBRARY_PATH, 'utf-8')) as CanonicalLibrary;
    if (!parsed || !Array.isArray(parsed.spots)) {
      canonicalCache = null;
      return canonicalCache;
    }
    canonicalCache = parsed;
    return canonicalCache;
  } catch {
    canonicalCache = null;
    return canonicalCache;
  }
}

function listExactSpots(): PreflopSpot[] {
  const lib = loadCanonicalLibrary();
  if (!lib) return [];

  const order = ['LJ', 'HJ', 'CO', 'BTN', 'SB', 'BB'];
  const orderMap = new Map(order.map((pos, idx) => [pos, idx]));

  return lib.spots
    .map((spot) => ({
      spot: spot.id,
      heroPosition: spot.heroPosition,
      scenario: spot.scenario,
      coverage: 'exact' as const,
    }))
    .sort((a, b) => {
      const aOrder = orderMap.get(a.heroPosition) ?? 999;
      const bOrder = orderMap.get(b.heroPosition) ?? 999;
      if (aOrder !== bOrder) return aOrder - bOrder;
      return a.spot.localeCompare(b.spot);
    });
}

function getExactRange(spotName: string): SpotSolution | null {
  const lib = loadCanonicalLibrary();
  if (!lib) return null;

  const spot = lib.spots.find((s) => s.id === spotName);
  if (!spot) return null;

  const summary = computeSpotSummary(spot);

  return {
    spot: spot.id,
    format: spot.format,
    coverage: 'exact',
    heroPosition: spot.heroPosition,
    scenario: spot.scenario,
    potSize: 0,
    actions: [...spot.actions],
    grid: spot.grid,
    summary,
    metadata: {
      iterations: 0,
      exploitability: 0,
      solveDate: lib.generatedAt,
      solver: 'chart-ground-truth-v1',
    },
  };
}

export function getExactSpotIds(): string[] {
  return listExactSpots().map((s) => s.spot);
}

/** List available preflop solution configs */
export function getPreflopConfigs(): PreflopConfigList {
  const solverConfigs: string[] = [];
  const coverageByConfig: Record<string, 'exact' | 'solver'> = {};

  if (existsSync(PREFLOP_SOLUTIONS_DIR)) {
    for (const d of readdirSync(PREFLOP_SOLUTIONS_DIR)) {
      try {
        const indexPath = join(PREFLOP_SOLUTIONS_DIR, d, 'index.json');
        if (existsSync(indexPath)) {
          solverConfigs.push(d);
          coverageByConfig[d] = 'solver';
        }
      } catch {
        // ignore malformed subdirectories
      }
    }
  }

  const exactAvailable = existsSync(PREFLOP_LIBRARY_PATH);
  const configs = exactAvailable ? [EXACT_CONFIG, ...solverConfigs] : solverConfigs;
  if (exactAvailable) coverageByConfig[EXACT_CONFIG] = 'exact';

  return {
    configs,
    hasGtoWizardData: existsSync(PREFLOP_CHARTS_PATH),
    coverageByConfig,
  };
}

/** List all spots for a given preflop config */
export function getPreflopSpots(config: string): PreflopSpot[] {
  if (config === EXACT_CONFIG) {
    return listExactSpots();
  }

  const indexPath = join(PREFLOP_SOLUTIONS_DIR, config, 'index.json');
  if (!existsSync(indexPath)) return [];

  try {
    const index = JSON.parse(readFileSync(indexPath, 'utf-8'));
    return (
      index.spots as Array<{ file: string; spot: string; heroPosition: string; scenario: string }>
    ).map((s) => ({
      spot: s.spot,
      heroPosition: s.heroPosition,
      scenario: s.scenario,
      coverage: 'solver',
      file: s.file,
    }));
  } catch {
    return [];
  }
}

/** Get the full solution grid for a specific spot */
export function getPreflopRange(config: string, spotName: string): SpotSolution | null {
  if (config === EXACT_CONFIG) {
    return getExactRange(spotName);
  }

  const cacheKey = `${config}/${spotName}`;
  if (solutionCache.has(cacheKey)) return solutionCache.get(cacheKey)!;

  const filePath = join(PREFLOP_SOLUTIONS_DIR, config, `${spotName}.json`);
  if (!existsSync(filePath)) return null;

  try {
    const solution: SpotSolution = JSON.parse(readFileSync(filePath, 'utf-8'));
    solution.coverage = solution.coverage ?? 'solver';
    solutionCache.set(cacheKey, solution);
    return solution;
  } catch {
    return null;
  }
}

/** Load preflop charts from legacy format */
export function getGtoWizardSpots(): string[] {
  if (!existsSync(PREFLOP_CHARTS_PATH)) return [];
  try {
    const data = JSON.parse(readFileSync(PREFLOP_CHARTS_PATH, 'utf-8'));
    const spots = new Set<string>();
    for (const entry of data) {
      spots.add(entry.spot);
    }
    return [...spots].sort();
  } catch {
    return [];
  }
}

/** Get legacy range for a specific spot */
export function getGtoWizardRange(spot: string): PreflopRangeEntry[] | null {
  if (!existsSync(PREFLOP_CHARTS_PATH)) return null;
  try {
    const data = JSON.parse(readFileSync(PREFLOP_CHARTS_PATH, 'utf-8'));
    const filtered = data.filter((e: { spot: string }) => e.spot === spot);
    if (filtered.length === 0) return null;

    return filtered.map((e: { hand: string; mix: Record<string, number> }) => ({
      hand: e.hand,
      actions: { ...e.mix },
    }));
  } catch {
    return null;
  }
}
