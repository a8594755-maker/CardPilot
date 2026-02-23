import { resolve } from 'node:path';
import {
  expandHandClassToCombos,
  loadGtoWizardRangeFile,
  type GtoWizardRangeEntry,
} from '../data-loaders/gto-wizard-json.js';

export interface PreflopRange {
  handClasses: Map<string, number>; // hand class -> frequency
  combos: Array<{ combo: [number, number]; weight: number }>;
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
    ? allEntries.filter(entry => entry.format === options.format)
    : allEntries;
  const ipSpot = options.ipSpot ?? DEFAULT_IP_SPOT;
  const oopSpot = options.oopSpot ?? DEFAULT_OOP_SPOT;
  const ipEntries = selectedEntries.filter(entry => entry.spot === ipSpot);
  const oopEntries = selectedEntries.filter(entry => entry.spot === oopSpot);

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
 * For V1 we include every combo with weight > 0 (deterministic),
 * and only use weights later during sampling/regret updates.
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
  return result.filter(c => {
    const key = `${c[0]},${c[1]}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
