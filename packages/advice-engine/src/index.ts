import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { AdvicePayload, PlayerActionType, StrategyMix } from "@cardpilot/shared-types";

type Mix = { raise: number; call: number; fold: number };

const RANKS = "AKQJT98765432";
const DEFAULT_FORMAT = "cash_6max_100bb";
const EPSILON = 1e-6;

type ChartRow = {
  format: string;
  spot: string;
  hand: string;
  mix: Mix;
  notes: string[];
};

const EXPLANATIONS: Record<string, string> = {
  IP_ADVANTAGE: "You have a positional advantage, making it easier to realize equity postflop.",
  A_BLOCKER: "The Ace blocker reduces the chance your opponent holds strong Ax combos.",
  K_BLOCKER: "The King blocker reduces the likelihood of opponent holding KK/AK.",
  WHEEL_PLAYABILITY: "This hand has wheel straight potential with decent playability.",
  SUITED_PLAYABILITY: "Suited cards give backdoor flush/straight equity, improving realizability.",
  CONNECTED: "Connected structure increases straight potential on the flop.",
  BROADWAY_STRENGTH: "Broadway combos have good hit rate on high-card boards.",
  DEFEND_RANGE: "Against a small open size, you need enough hands to defend and avoid being exploited.",
  FOLD_EQUITY: "Positional fold equity makes weaker hands worth attacking with.",
  LOW_PLAYABILITY: "Low playability and poor equity realization — theory suggests folding.",
  DOMINATION_RISK: "Risk of being dominated by stronger same-type hands — proceed with caution.",
  PAIR_VALUE: "Pocket pairs have inherent set value, good for seeing a flop.",
  PREMIUM_PAIR: "Premium pocket pair — one of the strongest preflop holdings."
};

const chartPath = resolveChartPath();
const chartRows: ChartRow[] = JSON.parse(readFileSync(chartPath, "utf-8"));
const chartIndex = new Map<string, ChartRow>();
for (const row of chartRows) {
  chartIndex.set(`${row.format}|${row.spot}|${row.hand}`, row);
}
console.log(`[advice-engine] loaded ${chartRows.length} chart rows from ${chartPath}`);

function resolveChartPath(): string {
  const fromEnv = process.env.CARDPILOT_CHART_PATH;
  if (fromEnv) return fromEnv;

  // Try full chart first, then sample
  for (const filename of ["preflop_charts.json", "preflop_charts.sample.json"]) {
    const localCwdPath = join(process.cwd(), "data", filename);
    try {
      readFileSync(localCwdPath, "utf-8");
      return localCwdPath;
    } catch {
      // fall through
    }
  }

  const thisDir = fileURLToPath(new URL(".", import.meta.url));
  return join(thisDir, "../../../data/preflop_charts.json");
}

export type BetSizing = "open2.5x" | "open3x" | "open4x" | "pot" | "half_pot" | "2x_pot" | "all_in";

export function buildSpotKey(params: {
  heroPos: string;
  villainPos: string;
  line: "unopened" | "facing_open";
  size: BetSizing;
}): string {
  if (params.line === "unopened") {
    return `${params.heroPos}_unopened_${params.size}`;
  }
  return `${params.heroPos}_vs_${params.villainPos}_facing_${params.size}`;
}

export function detectBetSizing(amount: number, bigBlind: number, potSize: number): BetSizing {
  const bbMultiple = amount / bigBlind;
  const potMultiple = potSize > 0 ? amount / potSize : 0;
  
  // Preflop sizing detection
  if (potSize <= bigBlind * 3) {
    if (bbMultiple >= 4.5) return "open4x";
    if (bbMultiple >= 3.5) return "open3x";
    if (bbMultiple >= 2.25) return "open2.5x";
  }
  
  // Postflop sizing detection
  if (potMultiple >= 1.75) return "2x_pot";
  if (potMultiple >= 0.75) return "pot";
  if (potMultiple >= 0.35) return "half_pot";
  
  return "open2.5x"; // Default
}

export function getPreflopAdvice(input: {
  tableId: string;
  handId: string;
  seat: number;
  heroPos: string;
  villainPos: string;
  line: "unopened" | "facing_open";
  heroHand: string;
  sizing?: BetSizing;
  potSize?: number;
  raiseAmount?: number;
  bigBlind?: number;
}): AdvicePayload {
  // Detect or use provided sizing
  let sizing: BetSizing = input.sizing || "open2.5x";
  if (!input.sizing && input.raiseAmount && input.bigBlind && input.potSize) {
    sizing = detectBetSizing(input.raiseAmount, input.bigBlind, input.potSize);
  }

  const spotKey = buildSpotKey({
    heroPos: input.heroPos,
    villainPos: input.villainPos,
    line: input.line,
    size: sizing
  });

  const spotCandidates = buildSpotCandidates({
    heroPos: input.heroPos,
    villainPos: input.villainPos,
    line: input.line,
    size: sizing
  });
  const heroHand = canonicalizeHandCode(input.heroHand);
  const handCandidates = [heroHand, input.heroHand].filter((v, idx, arr) => v && arr.indexOf(v) === idx);
  const row = findChartRow(DEFAULT_FORMAT, spotCandidates, handCandidates);

  const mix: Mix = row?.mix ?? fallbackMix({
    heroPos: input.heroPos,
    villainPos: input.villainPos,
    line: input.line,
    hand: heroHand
  });
  const tags = row?.notes ?? ["LOW_PLAYABILITY"];
  const explanation = tags.map((t) => EXPLANATIONS[t] ?? t).join(" ");
  const normalizedMix = normalizeMix(mix);

  // Stable pseudo-random recommendation per hand+spot, avoids UI flicker while preserving mixed frequencies.
  const rand = hashToUnitInterval(`${input.tableId}|${input.handId}|${input.seat}|${spotKey}|${heroHand}`);
  const recommended = pickByMix(normalizedMix, rand);

  return {
    tableId: input.tableId,
    handId: input.handId,
    seat: input.seat,
    spotKey: `${DEFAULT_FORMAT}_${row?.spot ?? spotKey}`,
    heroHand,
    mix: normalizedMix,
    tags,
    explanation,
    recommended,
    randomSeed: Math.round(rand * 100) / 100
  };
}

/**
 * Pick action by cumulative distribution of mix frequencies.
 * r ∈ [0,1) → action with matching probability band.
 */
function pickByMix(mix: Mix, r: number): "raise" | "call" | "fold" {
  const normalized = normalizeMix(mix);
  if (r < normalized.raise) return "raise";
  if (r < normalized.raise + normalized.call) return "call";
  return "fold";
}

/**
 * Calculate deviation score between player action and GTO mix.
 * 0 = perfect (chose the highest-frequency action), 1 = worst possible.
 */
export * from './postflop-advice.js';
export * from './range-estimator.js';

export function calculateDeviation(
  mix: StrategyMix,
  playerAction: PlayerActionType
): number {
  const actionMap: Record<string, keyof StrategyMix> = {
    fold: "fold",
    check: "fold", // check ≈ passive / fold equivalent for preflop
    call: "call",
    raise: "raise",
    all_in: "raise"
  };

  const normalized = normalizeMix(mix);
  const key = actionMap[playerAction] ?? "fold";
  const chosenFreq = normalized[key];

  const values = [normalized.raise, normalized.call, normalized.fold];
  const best = Math.max(...values);
  const worst = Math.min(...values);
  if (chosenFreq >= best - EPSILON) return 0;

  const relativeLoss = (best - chosenFreq) / Math.max(EPSILON, best - worst);
  const entropy = strategyEntropy(normalized);

  // In mixed spots (high entropy), several actions are close in EV, so penalize less.
  const entropyDiscount = 1 - entropy * 0.5;
  return round4(clamp01(relativeLoss * entropyDiscount));
}

function fallbackMix(input: {
  heroPos: string;
  villainPos: string;
  line: "unopened" | "facing_open";
  hand: string;
}): Mix {
  const hand = canonicalizeHandCode(input.hand);
  if (!hand) return { raise: 0, call: 0.1, fold: 0.9 };

  const rankA = hand[0];
  const rankB = hand[1];
  const suited = hand.length === 3 && hand[2] === "s";
  const pair = rankA === rankB;
  const idxA = RANKS.indexOf(rankA);
  const idxB = RANKS.indexOf(rankB);
  const gap = Math.abs(idxA - idxB);
  const highCards = Number(idxA <= 3) + Number(idxB <= 3);
  const connectorLike = !pair && gap <= 2;

  let strength = 0;
  if (pair) strength += 3.2 - (idxA / 12) * 1.6;
  if (rankA === "A") strength += 1.2;
  if (rankA === "K" && rankB !== "2") strength += 0.6;
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
    BB: -0.25
  };

  const openerTightness: Record<string, number> = {
    UTG: -0.3,
    MP: -0.18,
    HJ: -0.1,
    CO: 0.02,
    BTN: 0.18,
    SB: 0.1,
    BB: 0
  };

  if (input.line === "unopened") {
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
  line: "unopened" | "facing_open";
  size: BetSizing;
}): string[] {
  const primary = buildSpotKey(params);
  const candidates = [primary];
  
  // Backward compatibility: some chart files include explicit BB in unopened spot key
  if (params.line === "unopened") {
    const withExplicitBlind = `${params.heroPos}_vs_BB_unopened_${params.size}`;
    if (primary !== withExplicitBlind) {
      candidates.push(withExplicitBlind);
    }
  }
  
  // Fallback to default 2.5x sizing if specific size not found
  if (params.size !== "open2.5x") {
    const fallbackKey = buildSpotKey({ ...params, size: "open2.5x" });
    if (!candidates.includes(fallbackKey)) {
      candidates.push(fallbackKey);
    }
  }
  
  return candidates;
}

function findChartRow(format: string, spotCandidates: string[], handCandidates: string[]): ChartRow | undefined {
  for (const spot of spotCandidates) {
    for (const hand of handCandidates) {
      const key = `${format}|${spot}|${hand}`;
      const row = chartIndex.get(key);
      if (row) return row;
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
    fold: round4(fold / sum)
  };
}

function canonicalizeHandCode(raw: string): string {
  const hand = raw.trim().toUpperCase();
  if (hand.length !== 2 && hand.length !== 3) return hand;

  const r1 = hand[0];
  const r2 = hand[1];
  if (!RANKS.includes(r1) || !RANKS.includes(r2)) return hand;

  if (r1 === r2) return `${r1}${r2}`;

  const suitFlag = hand.length === 3 ? hand[2].toLowerCase() : "o";
  const normalizedSuit = suitFlag === "S".toLowerCase() ? "s" : "o";

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
  const p = [mix.raise, mix.call, mix.fold].filter((v) => v > EPSILON);
  if (p.length === 0) return 0;
  const entropy = -p.reduce((sum, v) => sum + v * Math.log2(v), 0);
  const maxEntropy = Math.log2(3);
  return maxEntropy > 0 ? clamp01(entropy / maxEntropy) : 0;
}

function sigmoid(x: number): number {
  return 1 / (1 + Math.exp(-x));
}

function clamp01(v: number): number {
  return Math.max(0, Math.min(1, v));
}

function round4(v: number): number {
  return Math.round(v * 10000) / 10000;
}
