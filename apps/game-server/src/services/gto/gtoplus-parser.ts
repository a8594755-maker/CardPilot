/**
 * GTO+ Data Parser
 *
 * Parses GTO+ exported strategy files (.txt, tab-separated).
 * GTO+ exports one file per decision node with all 1326 hand combos.
 *
 * Format:
 *   Header: Hand  WinRate  Combos(Total) RaiseX Call Fold  Percentage Raise% Call% Fold%  EV(Total) EVRaise EVCall EVFold
 *   Data:   AdAc  96.111  1.000  0  1.000  0      0  100.000  0    96.4991  84.0347  96.4991  0
 *   Summary: Pot/Stack/ToCall/Odds/freq/TotalCombos
 */

import { readFileSync, readdirSync, existsSync } from 'fs';
import { join, basename } from 'path';

/** A single hand combo's strategy at a decision node */
export interface GtoPlusCombo {
  hand: string; // e.g. "AdAc"
  equity: number; // win rate (0-100)
  combos: number; // usually 1.0
  /** Action frequencies as fractions (0-1) */
  frequencies: Record<string, number>;
  /** EV for each action */
  evs: Record<string, number>;
  /** Overall EV for this hand */
  evTotal: number;
}

/** Parsed GTO+ node strategy */
export interface GtoPlusNodeStrategy {
  /** Source file name */
  fileName: string;
  /** Available actions at this node (e.g. ["raise_100", "call", "fold"]) */
  actions: string[];
  /** All hand combos with their strategies */
  combos: GtoPlusCombo[];
  /** Game context from summary */
  context: {
    pot: number;
    stack: number;
    toCall: number;
    odds: number;
    overallFreq: number;
  };
  /** Aggregate summary */
  summary: {
    totalCombos: number;
    actionCombos: Record<string, number>;
    actionPercentages: Record<string, number>;
    overallEquity: number;
    overallEV: number;
  };
  /** 13x13 hand class grid (aggregated from combos) */
  grid: Record<string, Record<string, number>>;
}

/** Card rank values for sorting/grouping */
const RANK_ORDER = 'AKQJT98765432';

/**
 * Parse a localized float that may use comma as decimal separator.
 * European GTO+ exports use "95,056" instead of "95.056".
 * Auto-detects: if string has comma(s) but no period, treat comma as decimal.
 */
function parseLocalizedFloat(s: string): number {
  if (!s) return 0;
  const trimmed = s.trim();
  if (trimmed === '' || trimmed === 'NA') return 0;
  // If contains comma but no period, treat comma as decimal
  if (trimmed.includes(',') && !trimmed.includes('.')) {
    return parseFloat(trimmed.replace(',', '.'));
  }
  return parseFloat(trimmed);
}

/**
 * Detect if a file uses comma as decimal separator.
 * Checks the first few data lines for the pattern.
 */
function detectCommaDecimal(lines: string[]): boolean {
  // Check first 5 data lines (skip header at index 0)
  for (let i = 1; i < Math.min(6, lines.length); i++) {
    const line = lines[i].trim();
    if (!line) continue;
    const parts = line.split('\t');
    // Check numeric columns (index 1+ should be numbers)
    for (let j = 1; j < Math.min(4, parts.length); j++) {
      const val = parts[j].trim();
      // Pattern like "95,056" (comma followed by 3 digits) = decimal comma
      if (/^\d+,\d{1,3}$/.test(val)) return true;
      // Pattern like "0,325" = decimal comma
      if (/^0,\d+$/.test(val)) return true;
    }
  }
  return false;
}

/**
 * Parse a GTO+ strategy export file
 */
export function parseGtoPlusFile(filePath: string): GtoPlusNodeStrategy {
  const content = readFileSync(filePath, 'utf-8');
  const lines = content.split('\n').map((l) => l.replace(/\r$/, ''));
  const useCommaDecimal = detectCommaDecimal(lines);
  const fileName = basename(filePath);

  // Parse header to detect action names
  const headerLine = lines[0];
  const actions = parseActionsFromHeader(headerLine);

  // Parse data rows (lines 1 to first empty line)
  const combos: GtoPlusCombo[] = [];
  let i = 1;
  for (; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) break;
    const combo = parseComboLine(line, actions, useCommaDecimal);
    if (combo) combos.push(combo);
  }

  // Parse summary section
  const context = parseSummary(lines.slice(i), useCommaDecimal);

  // Build aggregate summary
  const summary = buildSummary(combos, actions);

  // Build 13x13 hand class grid
  const grid = buildHandClassGrid(combos, actions);

  return { fileName, actions, combos, context, summary, grid };
}

/**
 * Parse action names from the GTO+ header (Chinese column names).
 */
function parseActionsFromHeader(header: string): string[] {
  const parts = header.split('\t').filter((p) => p.trim() !== '');
  const pctIdx = parts.indexOf('\u767e\u5206\u6bd4');
  if (pctIdx === -1) {
    return ['raise', 'call', 'fold'];
  }

  const actionNames = parts.slice(3, pctIdx);
  return actionNames.map(normalizeActionName);
}

/**
 * Normalize Chinese action names to English
 */
function normalizeActionName(name: string): string {
  if (name === '\u5f03\u724c') return 'fold';
  if (name === '\u8ddf\u6ce8') return 'call';
  if (name === '\u8fc7\u724c') return 'check';
  const raiseMatch = name.match(/\u52a0\u6ce8\s*([\d]+[.,]?\d*)/);
  if (raiseMatch) return `raise_${raiseMatch[1].replace(',', '.')}`;
  const betMatch = name.match(/\u4e0b\u6ce8\s*([\d]+[.,]?\d*)/);
  if (betMatch) return `bet_${betMatch[1].replace(',', '.')}`;
  if (name === '\u5168\u4e0b') return 'allin';
  return name;
}

/**
 * Parse a single combo data line
 */
function parseComboLine(
  line: string,
  actions: string[],
  commaDecimal: boolean = false,
): GtoPlusCombo | null {
  const parts = line.split('\t').filter((p) => p !== '');
  if (parts.length < 4) return null;

  const hand = parts[0].trim();
  if (!hand || hand.length < 4) return null;

  const pf = commaDecimal ? parseLocalizedFloat : parseFloat;

  const equity = pf(parts[1]) || 0;
  const combos = pf(parts[2]) || 0;

  const numActions = actions.length;

  // Combo counts for each action
  const frequencies: Record<string, number> = {};
  for (let j = 0; j < numActions; j++) {
    const raw = pf(parts[3 + j]) || 0;
    frequencies[actions[j]] = raw;
  }

  // Normalize frequencies to sum to 1
  const totalFreq = Object.values(frequencies).reduce((s, v) => s + v, 0);
  if (totalFreq > 0) {
    for (const a of actions) {
      frequencies[a] = frequencies[a] / totalFreq;
    }
  }

  // EVs: always the last (numActions + 1) columns
  const evOffset = parts.length - numActions - 1;
  const evTotal = evOffset >= 0 ? pf(parts[evOffset]) || 0 : 0;
  const evs: Record<string, number> = {};
  for (let j = 0; j < numActions; j++) {
    evs[actions[j]] = pf(parts[evOffset + 1 + j]) || 0;
  }

  return { hand, equity, combos, frequencies, evs, evTotal };
}

/**
 * Parse the summary section at the end of file
 */
function parseSummary(
  lines: string[],
  commaDecimal: boolean = false,
): GtoPlusNodeStrategy['context'] {
  const context = { pot: 0, stack: 0, toCall: 0, odds: 0, overallFreq: 0 };
  const pf = commaDecimal ? parseLocalizedFloat : parseFloat;

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('\u5e95\u6c60:') || trimmed.startsWith('\u5e95\u6c60\uff1a')) {
      context.pot = pf(trimmed.split(/[:\uff1a]/)[1]) || 0;
    } else if (trimmed.startsWith('\u7b79\u7801:') || trimmed.startsWith('\u7b79\u7801\uff1a')) {
      context.stack = pf(trimmed.split(/[:\uff1a]/)[1]) || 0;
    } else if (
      trimmed.startsWith('\u8fdb\u884c\u8ddf\u6ce8:') ||
      trimmed.startsWith('\u8fdb\u884c\u8ddf\u6ce8\uff1a')
    ) {
      context.toCall = pf(trimmed.split(/[:\uff1a]/)[1]) || 0;
    } else if (trimmed.startsWith('\u8d54\u7387:') || trimmed.startsWith('\u8d54\u7387\uff1a')) {
      context.odds = pf(trimmed.split(/[:\uff1a]/)[1]) || 0;
    } else if (trimmed.startsWith('freq:')) {
      context.overallFreq = pf(trimmed.split(':')[1]) || 0;
    }
  }

  return context;
}

/**
 * Build aggregate summary from combos
 */
function buildSummary(combos: GtoPlusCombo[], actions: string[]): GtoPlusNodeStrategy['summary'] {
  const actionCombos: Record<string, number> = {};
  const actionPercentages: Record<string, number> = {};
  let totalCombos = 0;
  let weightedEquity = 0;
  let weightedEV = 0;

  for (const a of actions) {
    actionCombos[a] = 0;
  }

  for (const c of combos) {
    totalCombos += c.combos;
    weightedEquity += c.equity * c.combos;
    weightedEV += c.evTotal * c.combos;
    for (const a of actions) {
      actionCombos[a] += (c.frequencies[a] || 0) * c.combos;
    }
  }

  for (const a of actions) {
    actionPercentages[a] = totalCombos > 0 ? actionCombos[a] / totalCombos : 0;
  }

  return {
    totalCombos,
    actionCombos,
    actionPercentages,
    overallEquity: totalCombos > 0 ? weightedEquity / totalCombos : 0,
    overallEV: totalCombos > 0 ? weightedEV / totalCombos : 0,
  };
}

/**
 * Convert a combo hand name to a hand class
 */
function comboToHandClass(hand: string): string {
  if (hand.length < 4) return hand;
  const r1 = hand[0];
  const s1 = hand[1];
  const r2 = hand[2];
  const s2 = hand[3];

  if (r1 === r2) return `${r1}${r2}`;
  const i1 = RANK_ORDER.indexOf(r1);
  const i2 = RANK_ORDER.indexOf(r2);
  const [hi, lo] = i1 < i2 ? [r1, r2] : [r2, r1];
  const suited = s1 === s2 ? 's' : 'o';
  return `${hi}${lo}${suited}`;
}

/**
 * Build 13x13 hand class grid by averaging combo frequencies
 */
function buildHandClassGrid(
  combos: GtoPlusCombo[],
  actions: string[],
): Record<string, Record<string, number>> {
  const grid: Record<string, Record<string, number>> = {};
  const counts: Record<string, number> = {};

  for (const c of combos) {
    const hc = comboToHandClass(c.hand);
    if (!grid[hc]) {
      grid[hc] = {};
      for (const a of actions) grid[hc][a] = 0;
      counts[hc] = 0;
    }
    counts[hc] += c.combos;
    for (const a of actions) {
      grid[hc][a] += (c.frequencies[a] || 0) * c.combos;
    }
  }

  // Normalize to average frequencies
  for (const hc of Object.keys(grid)) {
    if (counts[hc] > 0) {
      for (const a of actions) {
        grid[hc][a] /= counts[hc];
      }
    }
  }

  return grid;
}

/**
 * Scan a directory for GTO+ export files
 */
export function scanGtoPlusDirectory(dirPath: string): string[] {
  if (!existsSync(dirPath)) return [];
  const files = readdirSync(dirPath, { recursive: true }) as string[];
  return files.filter((f) => f.endsWith('.txt')).map((f) => join(dirPath, f));
}

/**
 * Load all GTO+ samples from a directory
 */
export function loadGtoPlusSamples(dirPath: string): GtoPlusNodeStrategy[] {
  const files = scanGtoPlusDirectory(dirPath);
  return files.map((f) => parseGtoPlusFile(f));
}

/**
 * Compare EZ-GTO strategy against GTO+ ground truth at hand-class level.
 */
export interface StrategyComparison {
  accuracy: number;
  meanDeviation: number;
  maxDeviation: number;
  worstHand: string;
  perHand: Record<
    string,
    {
      handClass: string;
      gtoPlusFreqs: Record<string, number>;
      ezGtoFreqs: Record<string, number>;
      deviation: number;
    }
  >;
  perAction: Record<
    string,
    {
      meanDeviation: number;
      correlation: number;
    }
  >;
}

export function compareStrategies(
  gtoPlusGrid: Record<string, Record<string, number>>,
  ezGtoGrid: Record<string, Record<string, number>>,
  actions: string[],
): StrategyComparison {
  const perHand: StrategyComparison['perHand'] = {};
  const perAction: StrategyComparison['perAction'] = {};
  let totalDeviation = 0;
  let maxDeviation = 0;
  let worstHand = '';
  let handCount = 0;

  const actionDeviations: Record<string, number[]> = {};
  const actionGtoPlus: Record<string, number[]> = {};
  const actionEzGto: Record<string, number[]> = {};
  for (const a of actions) {
    actionDeviations[a] = [];
    actionGtoPlus[a] = [];
    actionEzGto[a] = [];
  }

  const allHands = new Set([...Object.keys(gtoPlusGrid), ...Object.keys(ezGtoGrid)]);
  for (const hc of allHands) {
    const gp = gtoPlusGrid[hc] || {};
    const ez = ezGtoGrid[hc] || {};

    let handDeviation = 0;
    for (const a of actions) {
      const gpFreq = gp[a] || 0;
      const ezFreq = ez[a] || 0;
      const diff = Math.abs(gpFreq - ezFreq);
      handDeviation += diff;
      actionDeviations[a].push(diff);
      actionGtoPlus[a].push(gpFreq);
      actionEzGto[a].push(ezFreq);
    }
    handDeviation /= actions.length;

    perHand[hc] = {
      handClass: hc,
      gtoPlusFreqs: gp,
      ezGtoFreqs: ez,
      deviation: handDeviation,
    };

    totalDeviation += handDeviation;
    handCount++;

    if (handDeviation > maxDeviation) {
      maxDeviation = handDeviation;
      worstHand = hc;
    }
  }

  for (const a of actions) {
    const devs = actionDeviations[a];
    const meanDev = devs.length > 0 ? devs.reduce((s, v) => s + v, 0) / devs.length : 0;
    const corr = pearsonCorrelation(actionGtoPlus[a], actionEzGto[a]);
    perAction[a] = { meanDeviation: meanDev, correlation: corr };
  }

  const meanDeviation = handCount > 0 ? totalDeviation / handCount : 0;
  const accuracy = Math.max(0, (1 - meanDeviation) * 100);

  return { accuracy, meanDeviation, maxDeviation, worstHand, perHand, perAction };
}

function pearsonCorrelation(x: number[], y: number[]): number {
  const n = x.length;
  if (n < 2) return 0;

  const meanX = x.reduce((s, v) => s + v, 0) / n;
  const meanY = y.reduce((s, v) => s + v, 0) / n;

  let num = 0,
    denX = 0,
    denY = 0;
  for (let i = 0; i < n; i++) {
    const dx = x[i] - meanX;
    const dy = y[i] - meanY;
    num += dx * dy;
    denX += dx * dx;
    denY += dy * dy;
  }

  const den = Math.sqrt(denX * denY);
  return den === 0 ? 0 : num / den;
}
