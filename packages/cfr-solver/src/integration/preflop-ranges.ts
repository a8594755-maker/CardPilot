import { resolve } from 'node:path';
import {
  expandHandClassToCombos,
  loadGtoWizardRangeFile,
  type GtoWizardRangeEntry,
} from '../data-loaders/gto-wizard-json.js';
import {
  generateEstimatedRange,
  adjustBBMultiWayDefense,
  type EstimatedSpot,
} from './range-estimator.js';

export interface WeightedCombo {
  combo: [number, number];
  weight: number; // 0.0 to 1.0, from GTO Wizard frequency
}

export interface PreflopRange {
  handClasses: Map<string, number>; // hand class -> frequency
  combos: WeightedCombo[];
}

export interface HUSRPRangesOptions {
  format?: string;
  ipSpot?: string;
  oopSpot?: string;
  ipAction?: string;
  oopAction?: string;
  minFrequency?: number;
}

const DEFAULT_IP_SPOT = 'BTN_unopened_open2.5x';
const DEFAULT_OOP_SPOT = 'BB_vs_BTN_facing_open2.5x';

/**
 * Load HU SRP ranges: BTN open range and BB calling range.
 * For SRP, we use:
 * - IP (BTN): hands that BTN opens (raise > 0)
 * - OOP (BB): hands that BB calls vs BTN (call > 0, ignoring 3-bet for SRP)
 */
export function loadHUSRPRanges(chartsPath?: string): {
  oopRange: PreflopRange;
  ipRange: PreflopRange;
};
export function loadHUSRPRanges(
  chartsPath: string | undefined,
  options: HUSRPRangesOptions,
): {
  oopRange: PreflopRange;
  ipRange: PreflopRange;
};
export function loadHUSRPRanges(
  chartsPath?: string,
  options: HUSRPRangesOptions = {},
): {
  oopRange: PreflopRange;
  ipRange: PreflopRange;
} {
  const path = chartsPath || resolve(process.cwd(), 'data/preflop_charts.json');
  const allEntries = loadGtoWizardRangeFile(path);
  const selectedEntries = options.format
    ? allEntries.filter((entry) => entry.format === options.format)
    : allEntries;
  const ipSpot = options.ipSpot ?? DEFAULT_IP_SPOT;
  const oopSpot = options.oopSpot ?? DEFAULT_OOP_SPOT;
  const ipEntries = selectedEntries.filter((entry) => entry.spot === ipSpot);
  const oopEntries = selectedEntries.filter((entry) => entry.spot === oopSpot);

  if (ipEntries.length === 0) {
    throw new Error(`No GTO Wizard entries found for IP spot: ${ipSpot}`);
  }
  if (oopEntries.length === 0) {
    throw new Error(`No GTO Wizard entries found for OOP spot: ${oopSpot}`);
  }

  // BTN opens = IP range in HU SRP
  const ipRange = buildRange(ipEntries, options.ipAction ?? 'raise', options.minFrequency);

  // BB calls = OOP range in HU SRP
  const oopRange = buildRange(oopEntries, options.oopAction ?? 'call', options.minFrequency);

  return { oopRange, ipRange };
}

function buildRange(
  entries: GtoWizardRangeEntry[],
  actionKey: string,
  minFrequency = 0,
): PreflopRange {
  const handClasses = new Map<string, number>();
  const combos: Array<{ combo: [number, number]; weight: number }> = [];

  for (const entry of entries) {
    const freq = entry.mix[actionKey];
    if (typeof freq !== 'number' || freq <= 0 || freq < minFrequency) continue;

    handClasses.set(entry.hand, Math.max(freq, handClasses.get(entry.hand) ?? 0));
    const expanded = expandHandClassToCombos(entry.hand);
    for (const combo of expanded) {
      combos.push({ combo, weight: freq });
    }
  }

  return { handClasses, combos };
}

/**
 * Get all combos from a range as flat arrays, excluding dead cards.
 * @deprecated Use getWeightedRangeCombos for V2 solver.
 */
export function getRangeCombos(
  range: PreflopRange,
  deadCards?: Set<number>,
): Array<[number, number]> {
  const result: Array<[number, number]> = [];

  for (const { combo, weight } of range.combos) {
    if (weight <= 0) continue;
    if (deadCards) {
      if (deadCards.has(combo[0]) || deadCards.has(combo[1])) continue;
    }
    result.push(combo);
  }

  // Deduplicate
  const seen = new Set<string>();
  return result.filter((c) => {
    const key = `${c[0]},${c[1]}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/**
 * Get all combos from a range with their weights, excluding dead cards.
 * V2: preserves frequency weights for weighted sampling in MCCFR.
 */
export function getWeightedRangeCombos(
  range: PreflopRange,
  deadCards?: Set<number>,
): WeightedCombo[] {
  const result: WeightedCombo[] = [];
  const seen = new Set<string>();

  for (const { combo, weight } of range.combos) {
    if (weight <= 0) continue;
    if (deadCards) {
      if (deadCards.has(combo[0]) || deadCards.has(combo[1])) continue;
    }
    const key = combo[0] < combo[1] ? `${combo[0]},${combo[1]}` : `${combo[1]},${combo[0]}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push({ combo, weight });
  }

  return result;
}

// ═══════════════════════════════════════════════════════════
// Multi-way range loading
// ═══════════════════════════════════════════════════════════

export interface MultiWayRangeConfig {
  /** Player position label (for logging) */
  position: string;
  /** GTO Wizard spot name, or 'estimated:XXX' for estimated ranges */
  spot: string;
  /** Action key in mix (e.g., 'raise', 'call') */
  action: string;
  /** Optional minimum frequency filter */
  minFrequency?: number;
  /** If true, apply multi-way speculative hand boosting */
  multiWayBoost?: boolean;
}

/**
 * Load ranges for a multi-way pot (3+ players).
 * Supports a mix of GTO Wizard data and estimated ranges.
 *
 * @param chartsPath - Path to preflop_charts.json
 * @param configs - One config per player (index 0 = first to act postflop)
 * @param numPlayers - Total players (for BB multi-way boost)
 */
export function loadMultiWayRanges(
  chartsPath: string,
  configs: MultiWayRangeConfig[],
  numPlayers: number,
): PreflopRange[] {
  const allEntries = loadGtoWizardRangeFile(chartsPath);
  const ranges: PreflopRange[] = [];

  for (const cfg of configs) {
    let entries: GtoWizardRangeEntry[];

    if (cfg.spot.startsWith('estimated:')) {
      // Use estimated range from range-estimator
      const estimatedSpot = cfg.spot.replace('estimated:', '') as EstimatedSpot;
      entries = generateEstimatedRange(estimatedSpot);
    } else {
      entries = allEntries.filter((e) => e.spot === cfg.spot);
      if (entries.length === 0) {
        throw new Error(`No entries found for spot: ${cfg.spot}`);
      }
    }

    // Apply multi-way BB defense boosting if requested
    if (cfg.multiWayBoost) {
      entries = adjustBBMultiWayDefense(entries, numPlayers);
    }

    ranges.push(buildRange(entries, cfg.action, cfg.minFrequency));
  }

  return ranges;
}
