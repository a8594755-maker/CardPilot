import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type {
  AdvicePayload,
  PlayerActionType,
  StackDepthBucket,
  StrategyMix,
} from '@cardpilot/shared-types';

type Mix = { raise: number; call: number; fold: number };

type ChartRow = {
  format: string;
  spot: string;
  hand: string;
  mix: Mix;
  notes: string[];
};

type ChartRowMatch = {
  format: string;
  row: ChartRow;
};

type StackResolution = {
  effectiveStackBb: number;
  requestedBucket: StackDepthBucket;
  targetStackBb: number;
  candidates: string[];
  inputProvided: boolean;
};

const RANKS = 'AKQJT98765432';
const DEFAULT_FORMAT = 'cash_6max_100bb';
const EPSILON = 1e-6;

const EXPLANATIONS: Record<string, string> = {
  IP_ADVANTAGE: 'You have a positional advantage, making it easier to realize equity postflop.',
  A_BLOCKER: 'The Ace blocker reduces the chance your opponent holds strong Ax combos.',
  K_BLOCKER: 'The King blocker reduces the likelihood of opponent holding KK/AK.',
  WHEEL_PLAYABILITY: 'This hand has wheel straight potential with decent playability.',
  SUITED_PLAYABILITY: 'Suited cards give backdoor flush/straight equity, improving realizability.',
  CONNECTED: 'Connected structure increases straight potential on the flop.',
  BROADWAY_STRENGTH: 'Broadway combos have good hit rate on high-card boards.',
  DEFEND_RANGE:
    'Against a small open size, you need enough hands to defend and avoid being exploited.',
  FOLD_EQUITY: 'Positional fold equity makes weaker hands worth attacking with.',
  LOW_PLAYABILITY: 'Low playability and poor equity realization - theory suggests folding.',
  DOMINATION_RISK: 'Risk of being dominated by stronger same-type hands - proceed with caution.',
  PAIR_VALUE: 'Pocket pairs have inherent set value, good for seeing a flop.',
  PREMIUM_PAIR: 'Premium pocket pair - one of the strongest preflop holdings.',
};

const STACK_BUCKET_TARGET_BB: Record<StackDepthBucket, number> = {
  short: 40,
  medium: 60,
  standard: 100,
  deep: 150,
};

const chartPath = resolveChartPath();
const chartRows: ChartRow[] = JSON.parse(readFileSync(chartPath, 'utf-8'));
const chartIndex = new Map<string, ChartRow>();
const chartFormats = new Set<string>();
const formatsByDepth = new Map<number, string[]>();

for (const row of chartRows) {
  chartIndex.set(`${row.format}|${row.spot}|${row.hand}`, row);
  chartFormats.add(row.format);

  const depth = parseFormatDepth(row.format);
  if (depth == null) continue;
  const existing = formatsByDepth.get(depth) ?? [];
  if (!existing.includes(row.format)) {
    existing.push(row.format);
    formatsByDepth.set(depth, existing);
  }
}

const availableFormatDepths = [...formatsByDepth.keys()].sort((a, b) => a - b);

console.log(`[advice-engine] loaded ${chartRows.length} chart rows from ${chartPath}`);

function resolveChartPath(): string {
  const fromEnv = process.env.CARDPILOT_CHART_PATH;
  if (fromEnv) return fromEnv;

  for (const filename of ['preflop_charts.json', 'preflop_charts.sample.json']) {
    const localCwdPath = join(process.cwd(), 'data', filename);
    try {
      readFileSync(localCwdPath, 'utf-8');
      return localCwdPath;
    } catch {
      // continue
    }
  }

  const thisDir = fileURLToPath(new URL('.', import.meta.url));
  return join(thisDir, '../../../data/preflop_charts.json');
}

export type BetSizing = 'open2.5x' | 'open3x' | 'open4x' | 'pot' | 'half_pot' | '2x_pot' | 'all_in';

export function buildSpotKey(params: {
  heroPos: string;
  villainPos: string;
  line: 'unopened' | 'facing_open';
  size: BetSizing;
}): string {
  if (params.line === 'unopened') {
    return `${params.heroPos}_unopened_${params.size}`;
  }
  return `${params.heroPos}_vs_${params.villainPos}_facing_${params.size}`;
}

export function detectBetSizing(amount: number, bigBlind: number, potSize: number): BetSizing {
  const bbMultiple = amount / bigBlind;
  const potMultiple = potSize > 0 ? amount / potSize : 0;

  if (potSize <= bigBlind * 3) {
    if (bbMultiple >= 4.5) return 'open4x';
    if (bbMultiple >= 3.5) return 'open3x';
    if (bbMultiple >= 2.25) return 'open2.5x';
  }

  if (potMultiple >= 1.75) return '2x_pot';
  if (potMultiple >= 0.75) return 'pot';
  if (potMultiple >= 0.35) return 'half_pot';

  return 'open2.5x';
}

export function getPreflopAdvice(input: {
  tableId: string;
  handId: string;
  seat: number;
  heroPos: string;
  villainPos: string;
  line: 'unopened' | 'facing_open';
  heroHand: string;
  sizing?: BetSizing;
  potSize?: number;
  raiseAmount?: number;
  bigBlind?: number;
  effectiveStackBb?: number;
}): AdvicePayload {
  let sizing: BetSizing = input.sizing || 'open2.5x';
  if (!input.sizing && input.raiseAmount && input.bigBlind && input.potSize) {
    sizing = detectBetSizing(input.raiseAmount, input.bigBlind, input.potSize);
  }

  const spotKey = buildSpotKey({
    heroPos: input.heroPos,
    villainPos: input.villainPos,
    line: input.line,
    size: sizing,
  });

  const spotCandidates = buildSpotCandidates({
    heroPos: input.heroPos,
    villainPos: input.villainPos,
    line: input.line,
    size: sizing,
  });

  const heroHand = canonicalizeHandCode(input.heroHand);
  const handCandidates = [heroHand, input.heroHand].filter(
    (value, idx, arr) => value && arr.indexOf(value) === idx,
  );

  const stackResolution = resolveStackResolution(input.effectiveStackBb);
  const rowMatch = findChartRow(stackResolution.candidates, spotCandidates, handCandidates);
  const resolvedFormat = rowMatch?.format ?? stackResolution.candidates[0] ?? DEFAULT_FORMAT;
  const resolvedStackBb = parseFormatDepth(resolvedFormat) ?? stackResolution.targetStackBb;

  const mix: Mix =
    rowMatch?.row.mix ??
    fallbackMix({
      heroPos: input.heroPos,
      villainPos: input.villainPos,
      line: input.line,
      hand: heroHand,
    });

  const tags = rowMatch?.row.notes ?? ['LOW_PLAYABILITY'];
  const normalizedMix = normalizeMix(mix);

  const usedFallback = stackResolution.inputProvided
    ? Math.abs(stackResolution.effectiveStackBb - resolvedStackBb) > 0.5
    : false;
  const stackNote = stackResolution.inputProvided
    ? usedFallback
      ? `Stack ${round1(stackResolution.effectiveStackBb)}bb mapped to nearest ${resolvedStackBb}bb chart.`
      : `Stack depth ${round1(stackResolution.effectiveStackBb)}bb matched ${resolvedStackBb}bb chart.`
    : '';

  const explanationParts = [
    tags.map((tag) => EXPLANATIONS[tag] ?? tag).join(' '),
    stackNote,
  ].filter(Boolean);
  const explanation = explanationParts.join(' ');

  const rand = hashToUnitInterval(
    `${input.tableId}|${input.handId}|${input.seat}|${spotKey}|${heroHand}|${resolvedFormat}`,
  );
  const recommended = pickByMix(normalizedMix, rand);

  return {
    tableId: input.tableId,
    handId: input.handId,
    seat: input.seat,
    stage: 'preflop',
    spotKey: `${resolvedFormat}_${rowMatch?.row.spot ?? spotKey}`,
    heroHand,
    mix: normalizedMix,
    tags,
    explanation,
    recommended,
    randomSeed: Math.round(rand * 100) / 100,
    stackProfile: {
      effectiveStackBb: round2(stackResolution.effectiveStackBb),
      requestedBucket: stackResolution.requestedBucket,
      resolvedFormat,
      resolvedStackBb,
      usedFallback,
    },
  };
}

function resolveStackResolution(effectiveStackBb?: number): StackResolution {
  const inputProvided = Number.isFinite(effectiveStackBb) && (effectiveStackBb ?? 0) > 0;
  const normalizedInput = inputProvided
    ? Number(effectiveStackBb)
    : STACK_BUCKET_TARGET_BB.standard;
  const requestedBucket = classifyStackDepth(normalizedInput);
  const targetStackBb = STACK_BUCKET_TARGET_BB[requestedBucket];

  const candidates: string[] = [];
  const preferredFormat = `cash_6max_${targetStackBb}bb`;

  pushUnique(candidates, preferredFormat);

  const nearestFormats = nearestFormatsByDepth(normalizedInput);
  for (const format of nearestFormats) {
    pushUnique(candidates, format);
  }

  pushUnique(candidates, DEFAULT_FORMAT);

  return {
    effectiveStackBb: normalizedInput,
    requestedBucket,
    targetStackBb,
    candidates,
    inputProvided,
  };
}

function classifyStackDepth(stackBb: number): StackDepthBucket {
  if (stackBb < 40) return 'short';
  if (stackBb <= 80) return 'medium';
  if (stackBb > 150) return 'deep';
  return 'standard';
}

function nearestFormatsByDepth(targetBb: number): string[] {
  if (availableFormatDepths.length === 0) {
    return chartFormats.has(DEFAULT_FORMAT) ? [DEFAULT_FORMAT] : [];
  }

  const byDistance = availableFormatDepths
    .map((depth) => ({ depth, distance: Math.abs(depth - targetBb) }))
    .sort((a, b) => a.distance - b.distance || a.depth - b.depth);

  const nearestDistance = byDistance[0]?.distance;
  if (nearestDistance == null) return [];

  const nearestDepths = byDistance
    .filter((entry) => entry.distance === nearestDistance)
    .map((entry) => entry.depth);

  const result: string[] = [];
  for (const depth of nearestDepths) {
    const formats = formatsByDepth.get(depth) ?? [];
    for (const format of formats) {
      pushUnique(result, format);
    }
  }

  return result;
}

function parseFormatDepth(format: string): number | undefined {
  const match = format.match(/(\d+)bb/i);
  if (!match) return undefined;
  return Number.parseInt(match[1], 10);
}

function pushUnique<T>(target: T[], value: T): void {
  if (!target.includes(value)) {
    target.push(value);
  }
}

function pickByMix(mix: Mix, random: number): 'raise' | 'call' | 'fold' {
  const normalized = normalizeMix(mix);
  if (random < normalized.raise) return 'raise';
  if (random < normalized.raise + normalized.call) return 'call';
  return 'fold';
}

export * from './postflop-advice.js';
export * from './board-analyzer.js';
export * from './math-engine.js';
export * from './range-estimator.js';
export * from './line-recognition.js';
export * from './audit-engine.js';

export function calculateDeviation(mix: StrategyMix, playerAction: PlayerActionType): number {
  const actionMap: Record<string, keyof StrategyMix> = {
    fold: 'fold',
    check: 'fold',
    call: 'call',
    raise: 'raise',
    all_in: 'raise',
  };

  const normalized = normalizeMix(mix);
  const key = actionMap[playerAction] ?? 'fold';
  const chosenFreq = normalized[key];

  const values = [normalized.raise, normalized.call, normalized.fold];
  const best = Math.max(...values);
  const worst = Math.min(...values);
  if (chosenFreq >= best - EPSILON) return 0;

  const relativeLoss = (best - chosenFreq) / Math.max(EPSILON, best - worst);
  const entropy = strategyEntropy(normalized);

  const entropyDiscount = 1 - entropy * 0.5;
  return round4(clamp01(relativeLoss * entropyDiscount));
}

function fallbackMix(input: {
  heroPos: string;
  villainPos: string;
  line: 'unopened' | 'facing_open';
  hand: string;
}): Mix {
  const hand = canonicalizeHandCode(input.hand);
  if (!hand) return { raise: 0, call: 0.1, fold: 0.9 };

  const rankA = hand[0];
  const rankB = hand[1];
  const suited = hand.length === 3 && hand[2] === 's';
  const pair = rankA === rankB;
  const idxA = RANKS.indexOf(rankA);
  const idxB = RANKS.indexOf(rankB);
  const gap = Math.abs(idxA - idxB);
  const highCards = Number(idxA <= 3) + Number(idxB <= 3);
  const connectorLike = !pair && gap <= 2;

  let strength = 0;
  if (pair) strength += 3.2 - (idxA / 12) * 1.6;
  if (rankA === 'A') strength += 1.2;
  if (rankA === 'K' && rankB !== '2') strength += 0.6;
  if (suited) strength += 0.55;
  if (connectorLike) strength += 0.35;
  strength += highCards * 0.35;

  const openPressure: Record<string, number> = {
    UTG: -0.35,
    MP: -0.2,
    HJ: -0.1,
    CO: 0.05,
    BTN: 0.2,
    SB: 0.1,
    BB: -0.25,
  };

  const openerTightness: Record<string, number> = {
    UTG: -0.3,
    MP: -0.18,
    HJ: -0.1,
    CO: 0.02,
    BTN: 0.18,
    SB: 0.1,
    BB: 0,
  };

  if (input.line === 'unopened') {
    strength += openPressure[input.heroPos] ?? 0;
    const raise = clamp01(0.02 + sigmoid((strength - 1.2) / 0.85) * 0.94);
    const call = 0;
    const fold = clamp01(1 - raise);
    return normalizeMix({ raise, call, fold });
  }

  strength += (openPressure[input.heroPos] ?? 0) * 0.5;
  strength += openerTightness[input.villainPos] ?? 0;

  const raise = clamp01(sigmoid((strength - 2.2) / 0.9) * 0.38);
  const defend = clamp01(sigmoid((strength - 0.95) / 0.85) * 0.95);
  const call = clamp01(defend - raise);
  const fold = clamp01(1 - defend);
  return normalizeMix({ raise, call, fold });
}

function buildSpotCandidates(params: {
  heroPos: string;
  villainPos: string;
  line: 'unopened' | 'facing_open';
  size: BetSizing;
}): string[] {
  const primary = buildSpotKey(params);
  const candidates = [primary];

  if (params.line === 'unopened') {
    const withExplicitBlind = `${params.heroPos}_vs_BB_unopened_${params.size}`;
    if (primary !== withExplicitBlind) {
      candidates.push(withExplicitBlind);
    }
  }

  if (params.size !== 'open2.5x') {
    const fallbackKey = buildSpotKey({ ...params, size: 'open2.5x' });
    if (!candidates.includes(fallbackKey)) {
      candidates.push(fallbackKey);
    }
  }

  return candidates;
}

function findChartRow(
  formatCandidates: string[],
  spotCandidates: string[],
  handCandidates: string[],
): ChartRowMatch | undefined {
  for (const format of formatCandidates) {
    for (const spot of spotCandidates) {
      for (const hand of handCandidates) {
        const key = `${format}|${spot}|${hand}`;
        const row = chartIndex.get(key);
        if (row) {
          return { format, row };
        }
      }
    }
  }
  return undefined;
}

function normalizeMix(mix: StrategyMix): Mix {
  const raise = Math.max(0, Number.isFinite(mix.raise) ? mix.raise : 0);
  const call = Math.max(0, Number.isFinite(mix.call) ? mix.call : 0);
  const fold = Math.max(0, Number.isFinite(mix.fold) ? mix.fold : 0);
  const sum = raise + call + fold;
  if (sum < EPSILON) return { raise: 0, call: 0, fold: 1 };
  return {
    raise: round4(raise / sum),
    call: round4(call / sum),
    fold: round4(fold / sum),
  };
}

function canonicalizeHandCode(raw: string): string {
  const hand = raw.trim().toUpperCase();
  if (hand.length !== 2 && hand.length !== 3) return hand;

  const r1 = hand[0];
  const r2 = hand[1];
  if (!RANKS.includes(r1) || !RANKS.includes(r2)) return hand;

  if (r1 === r2) return `${r1}${r2}`;

  const suitFlag = hand.length === 3 ? hand[2].toLowerCase() : 'o';
  const normalizedSuit = suitFlag === 's' ? 's' : 'o';

  const i1 = RANKS.indexOf(r1);
  const i2 = RANKS.indexOf(r2);
  const [hi, lo] = i1 <= i2 ? [r1, r2] : [r2, r1];
  return `${hi}${lo}${normalizedSuit}`;
}

function hashToUnitInterval(seed: string): number {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  const unsigned = h >>> 0;
  return unsigned / 0x100000000;
}

function strategyEntropy(mix: StrategyMix): number {
  const p = [mix.raise, mix.call, mix.fold].filter((value) => value > EPSILON);
  if (p.length === 0) return 0;
  const entropy = -p.reduce((sum, value) => sum + value * Math.log2(value), 0);
  const maxEntropy = Math.log2(3);
  return maxEntropy > 0 ? clamp01(entropy / maxEntropy) : 0;
}

function sigmoid(value: number): number {
  return 1 / (1 + Math.exp(-value));
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

function round4(value: number): number {
  return Math.round(value * 10000) / 10000;
}
