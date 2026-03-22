// ===== Preflop GTO chart lookup for bot decision pipeline =====
// Loads GTO Wizard preflop ranges from data/preflop_charts.json and provides
// a lookup function that maps (position, facingType, raiserPos, holeCards) → Mix.

import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadGtoWizardRangeFile } from '../../../packages/cfr-solver/src/data-loaders/gto-wizard-json.js';
import type { Mix } from './types.js';

const __dirname = dirname(fileURLToPath(import.meta.url));

// ===== Rank helpers =====
const RANK_ORDER = '23456789TJQKA';

function rankChar(card: string): string {
  return card[0];
}

function rankIndex(r: string): number {
  return RANK_ORDER.indexOf(r);
}

// ===== Convert specific hole cards to hand class notation =====
// e.g. ['As', 'Kh'] → 'AKo', ['Ts', '9s'] → 'T9s', ['Jh', 'Jd'] → 'JJ'
export function toHandClass(cards: [string, string]): string {
  const r1 = rankChar(cards[0]);
  const r2 = rankChar(cards[1]);
  const s1 = cards[0][1];
  const s2 = cards[1][1];

  if (r1 === r2) return r1 + r2; // pocket pair

  const suited = s1 === s2;
  // Higher rank first
  const [high, low] = rankIndex(r1) >= rankIndex(r2) ? [r1, r2] : [r2, r1];
  return high + low + (suited ? 's' : 'o');
}

// ===== Chart data types =====
type ChartMix = { raise: number; call: number; fold: number };
type SpotChart = Map<string, ChartMix>; // handClass → mix
type ChartIndex = Map<string, SpotChart>; // spotName → chart

// ===== Module-level cache (lazy-loaded once) =====
let chartCache: ChartIndex | null = null;

function getCharts(): ChartIndex {
  if (chartCache) return chartCache;

  const chartsPath = resolve(__dirname, '../../../data/preflop_charts.json');
  try {
    const entries = loadGtoWizardRangeFile(chartsPath);
    const index: ChartIndex = new Map();

    for (const entry of entries) {
      let spotMap = index.get(entry.spot);
      if (!spotMap) {
        spotMap = new Map();
        index.set(entry.spot, spotMap);
      }
      spotMap.set(entry.hand, {
        raise: entry.mix['raise'] ?? 0,
        call: entry.mix['call'] ?? 0,
        fold: entry.mix['fold'] ?? 0,
      });
    }

    chartCache = index;
    return index;
  } catch {
    // If charts file not found or parse error, return empty index
    chartCache = new Map();
    return chartCache;
  }
}

// ===== Map game state to chart spot name =====
function resolveSpot(
  heroPosition: string,
  facingType: string,
  raiserPosition: string | null,
): string | null {
  // Opening ranges: hero is in an unopened pot
  if (facingType === 'unopened') {
    const openSpots: Record<string, string> = {
      UTG: 'UTG_unopened_open2.5x',
      HJ: 'HJ_unopened_open2.5x',
      CO: 'CO_unopened_open2.5x',
      BTN: 'BTN_unopened_open2.5x',
      SB: 'SB_unopened_open2.5x',
      // MP falls back to UTG (more conservative, safe default)
      MP: 'UTG_unopened_open2.5x',
    };
    return openSpots[heroPosition] ?? null;
  }

  // Facing open raise: any position facing an open
  if (facingType === 'facing_open' && raiserPosition) {
    // Spot format: {hero}_vs_{raiser}_facing_open
    // Fallback to old GTO Wizard spots for BB (more data points)
    if (heroPosition === 'BB') {
      const bbSpots: Record<string, string> = {
        UTG: 'BB_vs_UTG_facing_open',
        MP: 'BB_vs_UTG_facing_open',
        HJ: 'BB_vs_HJ_facing_open',
        CO: 'BB_vs_CO_facing_open',
        BTN: 'BB_vs_BTN_facing_open',
        SB: 'BB_vs_SB_facing_open',
      };
      return bbSpots[raiserPosition] ?? null;
    }
    return `${heroPosition}_vs_${raiserPosition}_facing_open`;
  }

  // Facing 3bet: hero opened, villain 3bet
  if (facingType === 'facing_3bet' && raiserPosition) {
    return `${heroPosition}_vs_${raiserPosition}_facing_3bet`;
  }

  // Facing 4bet+: hero 3bet, villain 4bet
  if ((facingType === 'facing_4bet' || facingType === 'facing_4bet_plus') && raiserPosition) {
    return `${heroPosition}_vs_${raiserPosition}_facing_4bet`;
  }

  // Uncovered spots: facing limp, squeeze, etc.
  return null;
}

// ===== Main lookup function =====
// Returns a Mix if the spot is covered by a GTO chart, or null if not.
export function lookupPreflopChart(
  heroPosition: string,
  facingType: string,
  raiserPosition: string | null,
  holeCards: [string, string],
): Mix | null {
  const spot = resolveSpot(heroPosition, facingType, raiserPosition);
  if (!spot) return null;

  const charts = getCharts();
  const spotChart = charts.get(spot);
  if (!spotChart) return null;

  const handClass = toHandClass(holeCards);
  const mix = spotChart.get(handClass);
  if (!mix) return null;

  return { raise: mix.raise, call: mix.call, fold: mix.fold };
}
