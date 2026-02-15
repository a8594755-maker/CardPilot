import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { classifyHandOnBoard, type Card, type EquityResult } from "@cardpilot/poker-evaluator";
import type {
  AdvicePayload,
  BoardTextureProfile,
  HandAction,
  MathBreakdown,
  PostflopFrequency,
  PostflopPreferredAction,
  StrategyMix,
} from "@cardpilot/shared-types";
import { BoardAnalyzer } from "./board-analyzer.js";
import { MathEngine } from "./math-engine.js";
import { RangeEstimator, type HandRange } from "./range-estimator.js";
import { WorkerService } from "./WorkerService.js";

const EPSILON = 1e-6;
const ONE_HOUR_MS = 60 * 60 * 1000;
const MAX_EQUITY_CACHE_ENTRIES = 2000;
const DEFAULT_POSTFLOP_SIMULATIONS = 300;

const equityCache = createTimedLruCache<string, EquityResult>(MAX_EQUITY_CACHE_ENTRIES, ONE_HOUR_MS);
const rangeEstimator = new RangeEstimator();
let workerService: WorkerService | null = null;

process.once("beforeExit", () => {
  if (workerService) {
    void workerService.destroy();
  }
});

export interface PostflopContext {
  tableId: string;
  handId: string;
  seat: number;
  street: "FLOP" | "TURN" | "RIVER";
  heroHand: [Card, Card];
  board: Card[];
  heroPosition: string;
  villainPosition: string;
  potSize: number;
  toCall: number;
  effectiveStack: number;
  effectiveStackBb?: number;
  aggressor: "hero" | "villain" | "none";
  preflopAggressor: "hero" | "villain" | "none";
  heroInPosition: boolean;
  numVillains: number;
  actionHistory?: HandAction[];
  potType?: "SRP" | "3BP" | "4BP";
}

type PreflopChartRow = {
  format: string;
  spot: string;
  hand: string;
  mix: { raise: number; call: number; fold: number };
};

let preflopChartRowsCache: PreflopChartRow[] | null = null;

async function resolvePostflopEquity(input: {
  context: PostflopContext;
  handClass: ReturnType<typeof classifyHandOnBoard>;
}): Promise<{ result: EquityResult; villainRangeHash: string }> {
  const { context, handClass } = input;
  const deadCards = new Set([...context.heroHand, ...context.board]);

  const chartAnchoredRange = buildVillainRangeFromCharts(context);
  const baseRange = chartAnchoredRange.size > 0
    ? chartAnchoredRange
    : rangeEstimator.buildPreflopRange(
      context.villainPosition,
      context.preflopAggressor === "villain" ? "raise" : "call",
      context.heroPosition
    );

  const narrowedByHistory = narrowVillainRangeByHistory(baseRange, context);
  const adjustedRange = rangeEstimator.adjustForMultiway(narrowedByHistory, context.numVillains);
  const sampledVillains = rangeEstimator.sampleHandsFromRange(adjustedRange, 16);

  const villainHands = sampledVillains
    .map((combo) => [combo[0] as Card, combo[1] as Card] as [Card, Card])
    .filter(([cardA, cardB]) => {
      if (deadCards.has(cardA) || deadCards.has(cardB) || cardA === cardB) {
        return false;
      }
      deadCards.add(cardA);
      deadCards.add(cardB);
      return true;
    });

  const villainRangeHash = hashRange(villainHands);
  const cacheKey = buildEquityCacheKey(context.heroHand, context.board, villainRangeHash);
  const cached = equityCache.get(cacheKey);
  if (cached) {
    return { result: cached, villainRangeHash };
  }

  if (villainHands.length === 0) {
    const fallback = {
      win: 0,
      tie: 0,
      lose: 0,
      equity: fallbackEquityFromClass(handClass),
      simulations: 0,
    } satisfies EquityResult;
    return { result: fallback, villainRangeHash };
  }

  const result = await getWorkerService().calculateEquity({
    heroHand: context.heroHand,
    villainHands,
    board: context.board,
    simulations: DEFAULT_POSTFLOP_SIMULATIONS,
  });

  equityCache.set(cacheKey, result);
  return { result, villainRangeHash };
}

function blendFrequency(
  baseline: PostflopFrequency,
  solved: PostflopFrequency,
  baselineWeight: number
): PostflopFrequency {
  const baselineShare = clamp01(baselineWeight);
  const solvedShare = 1 - baselineShare;

  return normalizeFrequency({
    check: baseline.check * baselineShare + solved.check * solvedShare,
    betSmall: baseline.betSmall * baselineShare + solved.betSmall * solvedShare,
    betBig: baseline.betBig * baselineShare + solved.betBig * solvedShare,
  });
}

function buildEquityCacheKey(heroHand: [Card, Card], board: Card[], villainRangeHash: string): string {
  const hero = `${heroHand[0]}${heroHand[1]}`;
  const boardKey = [...board].sort().join("");
  return `${hero}-${boardKey}-${villainRangeHash}`;
}

function hashRange(villainHands: Array<[Card, Card]>): string {
  const canonical = villainHands
    .map(([a, b]) => [a, b].sort().join(""))
    .sort()
    .join("|");
  return stableHash(canonical || "empty");
}

function stableHash(seed: string): string {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0).toString(16);
}

function fallbackEquityFromClass(handClass: ReturnType<typeof classifyHandOnBoard>): number {
  if (handClass.type === "made_hand") {
    if (handClass.strength === "strong") return 0.72;
    if (handClass.strength === "medium") return 0.56;
    return 0.4;
  }
  if (handClass.type === "draw") return 0.38;
  return 0.2;
}

function textureToAggressionScore(boardTexture: BoardTextureProfile): number {
  if (boardTexture.wetness === "wet") return 0.72;
  if (boardTexture.wetness === "dry") return 0.38;
  return 0.55;
}

function showdownValueScore(handClass: ReturnType<typeof classifyHandOnBoard>): number {
  if (handClass.type === "made_hand") {
    if (handClass.strength === "strong") return 0.9;
    if (handClass.strength === "medium") return 0.65;
    return 0.35;
  }
  if (handClass.type === "draw") return 0.45;
  return 0.1;
}

function deriveNutAdvantage(
  handClass: ReturnType<typeof classifyHandOnBoard>,
  boardTexture: BoardTextureProfile
): number {
  const classBoost = handClass.type === "made_hand" && handClass.strength === "strong"
    ? 0.85
    : handClass.type === "draw"
      ? 0.55
      : 0.25;

  if (boardTexture.wetness === "wet") return clamp01(classBoost + 0.1);
  return clamp01(classBoost - 0.05);
}

function deriveFoldEquity(context: PostflopContext, boardTexture: BoardTextureProfile): number {
  let score = 0.4;
  if (context.aggressor === "hero") score += 0.2;
  if (context.numVillains > 1) score -= 0.15;
  if (context.toCall > 0) score -= 0.1;
  if (boardTexture.wetness === "dry") score += 0.1;
  return clamp01(score);
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function createTimedLruCache<K, V>(maxEntries: number, ttlMs: number): {
  get: (key: K) => V | undefined;
  set: (key: K, value: V) => void;
} {
  const store = new Map<K, { value: V; expiresAt: number }>();

  return {
    get(key: K): V | undefined {
      const entry = store.get(key);
      if (!entry) return undefined;

      if (entry.expiresAt <= Date.now()) {
        store.delete(key);
        return undefined;
      }

      store.delete(key);
      store.set(key, entry);
      return entry.value;
    },
    set(key: K, value: V): void {
      if (store.has(key)) {
        store.delete(key);
      }

      store.set(key, {
        value,
        expiresAt: Date.now() + ttlMs,
      });

      if (store.size > maxEntries) {
        const oldestKey = store.keys().next().value;
        if (typeof oldestKey !== "undefined") {
          store.delete(oldestKey);
        }
      }
    },
  };
}

export interface PostflopBucketStrategy {
  bucketKey: string;
  preferredAction: PostflopPreferredAction;
  frequency: PostflopFrequency;
  rationaleTemplate: string;
  tags?: string[];
}

export interface PostflopAdvice extends AdvicePayload {
  postflop: NonNullable<AdvicePayload["postflop"]>;
}

export interface StrategyConfig {
  baseRaiseRate: number;
  weights: {
    EquityScore: number;
    TextureScore: number;
    ShowdownValue: number;
  };
  aggressionFactors: {
    nutAdvantage: number;
    foldEquity: number;
  };
}

const DEFAULT_STRATEGY_CONFIG: StrategyConfig = {
  baseRaiseRate: 0.12,
  weights: {
    EquityScore: 0.5,
    TextureScore: 0.15,
    ShowdownValue: 0.25,
  },
  aggressionFactors: {
    nutAdvantage: 0.2,
    foldEquity: 0.3,
  },
};

export class PostflopEngine {
  private readonly bucketIndex = new Map<string, PostflopBucketStrategy>();
  private readonly strategyConfig: StrategyConfig;

  constructor(rows?: PostflopBucketStrategy[], strategyConfig: StrategyConfig = DEFAULT_STRATEGY_CONFIG) {
    this.strategyConfig = strategyConfig;
    const parsedRows = rows ?? loadPostflopRowsFromDisk();
    for (const row of parsedRows) {
      this.bucketIndex.set(row.bucketKey, row);
    }
    if (this.bucketIndex.size > 0) {
      console.log(`[advice-engine] loaded ${this.bucketIndex.size} postflop bucket rows`);
    } else {
      console.log("[advice-engine] no postflop bucket rows found, using heuristic fallback only");
    }
  }

  async getAdvice(context: PostflopContext): Promise<PostflopAdvice> {
    const boardTexture = BoardAnalyzer.analyze(context.board);
    const textureBucket = BoardAnalyzer.toTextureBucket(boardTexture);
    const line = resolveLineToken(context);
    const potType = context.potType ?? inferPotType(context.actionHistory);
    const baseKey = buildBucketKey({
      potType,
      heroPosition: context.heroPosition,
      villainPosition: context.villainPosition,
      street: context.street,
      line,
      textureBucket,
    });
    const bucket = this.resolveBucket({
      baseKey,
      potType,
      heroPosition: context.heroPosition,
      villainPosition: context.villainPosition,
      street: context.street,
      line,
      textureBucket,
    });
    const handClass = classifyHandOnBoard(context.heroHand, context.board);
    const math = MathEngine.buildMathBreakdown({
      potSize: context.potSize,
      toCall: context.toCall,
      effectiveStack: context.effectiveStack,
    });

    const { result: equityResult, villainRangeHash } = await resolvePostflopEquity({
      context,
      handClass,
    });

    const solvedFrequency = buildFrequencyFromScores({
      context,
      boardTexture,
      handClass,
      math,
      equity: equityResult.equity,
      strategyConfig: this.strategyConfig,
    });

    const frequency = normalizeFrequency(
      bucket?.frequency
        ? blendFrequency(bucket.frequency, solvedFrequency, 0.65)
        : solvedFrequency
    );

    const preferredAction = bucket?.preferredAction ?? derivePreferredAction(frequency);
    const mix = normalizeMix(
      toLegacyMix({
        frequency,
        toCall: context.toCall,
      })
    );

    const seed = `${context.tableId}|${context.handId}|${context.seat}|${baseKey}|${context.heroHand[0]}${context.heroHand[1]}`;
    const random = hashToUnitInterval(seed);
    const recommended = enforceLegalRecommendedAction(
      pickByMix(mix, random),
      context.toCall,
      context.effectiveStack
    );
    const frequencyText = formatFrequency(frequency, context.toCall);
    const rationale = buildRationale({
      bucketTemplate: bucket?.rationaleTemplate,
      boardTextureDescription: BoardAnalyzer.describe(boardTexture),
      toCall: context.toCall,
      potSize: context.potSize,
      math,
      handClassDescription: handClass.description,
      frequencyText,
      equity: equityResult.equity,
      simulations: equityResult.simulations,
      villainRangeHash,
    });

    const tags = [...new Set([
      ...(bucket?.tags ?? []),
      `TEXTURE_${textureBucket}`,
      `LINE_${line}`,
      `POT_${potType}`,
      context.numVillains > 1 ? "MULTIWAY" : "HEADS_UP",
      math.isLowSpr ? "LOW_SPR" : "NORMAL_SPR",
      `EQUITY_${Math.round(equityResult.equity * 100)}`,
    ])];

    return {
      tableId: context.tableId,
      handId: context.handId,
      seat: context.seat,
      stage: "postflop",
      spotKey: bucket?.bucketKey ?? baseKey,
      heroHand: `${context.heroHand[0]}${context.heroHand[1]}`,
      mix,
      tags,
      explanation: rationale,
      recommended,
      randomSeed: round2(random),
      math,
      postflop: {
        bucketKey: bucket?.bucketKey ?? baseKey,
        preferredAction,
        frequency,
        frequencyText,
        rationale,
        boardTexture,
      },
    };
  }

  private resolveBucket(input: {
    baseKey: string;
    potType: "SRP" | "3BP" | "4BP";
    heroPosition: string;
    villainPosition: string;
    street: "FLOP" | "TURN" | "RIVER";
    line: "CBET" | "VS_BET" | "BARREL" | "PROBE";
    textureBucket: "DRY_TEXTURE" | "NEUTRAL_TEXTURE" | "WET_TEXTURE";
  }): PostflopBucketStrategy | undefined {
    const candidates = [
      input.baseKey,
      buildBucketKey({ ...input, textureBucket: "NEUTRAL_TEXTURE" }),
      buildBucketKey({ ...input, villainPosition: "ANY" }),
      buildBucketKey({ ...input, villainPosition: "ANY", textureBucket: "NEUTRAL_TEXTURE" }),
    ];

    for (const key of candidates) {
      const row = this.bucketIndex.get(key);
      if (row) return row;
    }
    return undefined;
  }
}

const postflopEngine = new PostflopEngine();

export async function getPostflopAdvice(context: PostflopContext): Promise<PostflopAdvice> {
  return postflopEngine.getAdvice(context);
}

function loadPostflopRowsFromDisk(): PostflopBucketStrategy[] {
  const path = resolvePostflopPath();
  if (!path) return [];

  try {
    const parsed = JSON.parse(readFileSync(path, "utf-8")) as PostflopBucketStrategy[];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((row) =>
      Boolean(row?.bucketKey)
      && Boolean(row?.preferredAction)
      && Boolean(row?.frequency)
      && Boolean(row?.rationaleTemplate)
    );
  } catch (error) {
    console.error(`[advice-engine] failed to load postflop buckets from ${path}:`, error);
    return [];
  }
}

function resolvePostflopPath(): string | null {
  const fromEnv = process.env.CARDPILOT_POSTFLOP_BUCKET_PATH;
  if (fromEnv) return fromEnv;

  const cwdCandidates = [
    join(process.cwd(), "data", "postflop_buckets.json"),
    join(process.cwd(), "data", "postflop_buckets.sample.json"),
  ];

  for (const candidate of cwdCandidates) {
    try {
      readFileSync(candidate, "utf-8");
      return candidate;
    } catch {
      // continue
    }
  }

  const thisDir = fileURLToPath(new URL(".", import.meta.url));
  return join(thisDir, "../../../data/postflop_buckets.sample.json");
}

function inferPotType(actions?: HandAction[]): "SRP" | "3BP" | "4BP" {
  if (!actions || actions.length === 0) return "SRP";
  const preflopRaises = actions.filter(
    (action) => action.street === "PREFLOP" && (action.type === "raise" || action.type === "all_in")
  ).length;

  if (preflopRaises >= 3) return "4BP";
  if (preflopRaises === 2) return "3BP";
  return "SRP";
}

function resolveLineToken(context: PostflopContext): "CBET" | "VS_BET" | "BARREL" | "PROBE" {
  if (context.toCall > 0) {
    return "VS_BET";
  }

  if (context.aggressor === "hero") {
    return context.street === "FLOP" ? "CBET" : "BARREL";
  }

  if (context.street === "FLOP") {
    if (context.preflopAggressor === "hero") {
      return "CBET";
    }
    return context.heroInPosition ? "PROBE" : "VS_BET";
  }

  if (context.preflopAggressor === "hero" && context.heroInPosition) {
    return "BARREL";
  }

  return "PROBE";
}

function buildBucketKey(params: {
  potType: "SRP" | "3BP" | "4BP";
  heroPosition: string;
  villainPosition: string;
  street: "FLOP" | "TURN" | "RIVER";
  line: "CBET" | "VS_BET" | "BARREL" | "PROBE";
  textureBucket: "DRY_TEXTURE" | "NEUTRAL_TEXTURE" | "WET_TEXTURE";
}): string {
  return `${params.potType}_${params.heroPosition}_vs_${params.villainPosition}_${params.street}_${params.line}_${params.textureBucket}`;
}

function buildFrequencyFromScores(input: {
  context: PostflopContext;
  boardTexture: BoardTextureProfile;
  handClass: ReturnType<typeof classifyHandOnBoard>;
  math: MathBreakdown;
  equity: number;
  strategyConfig: StrategyConfig;
}): PostflopFrequency {
  const {
    context,
    boardTexture,
    handClass,
    math,
    equity,
    strategyConfig,
  } = input;

  const textureScore = textureToAggressionScore(boardTexture);
  const showdownValue = showdownValueScore(handClass);
  const nutAdvantage = deriveNutAdvantage(handClass, boardTexture);
  const foldEquity = deriveFoldEquity(context, boardTexture);

  const raiseSignal =
    strategyConfig.baseRaiseRate
    + equity * strategyConfig.weights.EquityScore
    + textureScore * strategyConfig.weights.TextureScore
    + showdownValue * strategyConfig.weights.ShowdownValue
    + nutAdvantage * strategyConfig.aggressionFactors.nutAdvantage
    + foldEquity * strategyConfig.aggressionFactors.foldEquity;

  const raiseFreq = clamp01(raiseSignal);
  const betBigShare = clamp01(
    0.25
    + textureScore * 0.3
    + nutAdvantage * 0.35
    + Math.max(0, equity - 0.5) * 0.2
  );

  if (context.toCall <= 0) {
    const betBig = round4(raiseFreq * betBigShare);
    const betSmall = round4(Math.max(0, raiseFreq - betBig));
    const check = round4(Math.max(0, 1 - raiseFreq));
    return normalizeFrequency({ check, betSmall, betBig });
  }

  const equityRequired = math.equityRequired ?? 0;
  const bluffCatchScore = clamp01(showdownValue * 0.6 + equity * 0.4);
  const foldPressure = clamp01((equityRequired - equity) + (1 - bluffCatchScore) * 0.35);
  const fold = clamp01(foldPressure);
  const call = clamp01(Math.max(0, 1 - raiseFreq - fold));
  const scale = Math.max(EPSILON, raiseFreq + call + fold);

  const normalizedRaise = raiseFreq / scale;
  const normalizedCall = call / scale;
  const betBig = round4(normalizedRaise * betBigShare);
  const betSmall = round4(Math.max(0, normalizedRaise - betBig));

  const equityEdge = equity - equityRequired;
  if (equityEdge < -0.04) {
    const tightenedRaise = clamp01(normalizedRaise * 0.65);
    const tightenedCall = clamp01(normalizedCall * 0.85);
    return normalizeFrequency({
      check: tightenedCall,
      betSmall: tightenedRaise * (1 - betBigShare),
      betBig: tightenedRaise * betBigShare,
    });
  }

  return normalizeFrequency({
    check: normalizedCall,
    betSmall,
    betBig,
  });
}

function normalizeFrequency(frequency: PostflopFrequency): PostflopFrequency {
  const check = Math.max(0, Number.isFinite(frequency.check) ? frequency.check : 0);
  const betSmall = Math.max(0, Number.isFinite(frequency.betSmall) ? frequency.betSmall : 0);
  const betBig = Math.max(0, Number.isFinite(frequency.betBig) ? frequency.betBig : 0);
  const sum = check + betSmall + betBig;

  if (sum <= EPSILON) {
    return { check: 1, betSmall: 0, betBig: 0 };
  }

  if (sum <= 1 + EPSILON) {
    return {
      check: round4(check),
      betSmall: round4(betSmall),
      betBig: round4(betBig),
    };
  }

  return {
    check: round4(check / sum),
    betSmall: round4(betSmall / sum),
    betBig: round4(betBig / sum),
  };
}

function derivePreferredAction(frequency: PostflopFrequency): PostflopPreferredAction {
  if (frequency.betBig >= frequency.betSmall && frequency.betBig >= frequency.check) {
    return "bet_big";
  }
  if (frequency.betSmall >= frequency.check) {
    return "bet_small";
  }
  return "check";
}

function toLegacyMix(input: {
  frequency: PostflopFrequency;
  toCall: number;
}): StrategyMix {
  const raise = input.frequency.betSmall + input.frequency.betBig;
  const call = input.frequency.check;
  const fold = input.toCall > 0 ? Math.max(0, 1 - raise - call) : 0;

  return { raise, call, fold };
}

function normalizeMix(mix: StrategyMix): StrategyMix {
  const raise = Math.max(0, Number.isFinite(mix.raise) ? mix.raise : 0);
  const call = Math.max(0, Number.isFinite(mix.call) ? mix.call : 0);
  const fold = Math.max(0, Number.isFinite(mix.fold) ? mix.fold : 0);
  const sum = raise + call + fold;
  if (sum <= EPSILON) return { raise: 0, call: 0, fold: 1 };
  return {
    raise: round4(raise / sum),
    call: round4(call / sum),
    fold: round4(fold / sum),
  };
}

function pickByMix(mix: StrategyMix, random: number): "raise" | "call" | "fold" {
  if (random < mix.raise) return "raise";
  if (random < mix.raise + mix.call) return "call";
  return "fold";
}

function enforceLegalRecommendedAction(
  action: "raise" | "call" | "fold",
  toCall: number,
  effectiveStack: number
): "raise" | "call" | "fold" {
  if (effectiveStack <= 0) {
    return toCall > 0 ? "fold" : "call";
  }

  if (toCall <= 0 && action === "fold") {
    return "call";
  }

  if (toCall > effectiveStack && action === "call") {
    return "raise";
  }

  return action;
}

function formatFrequency(frequency: PostflopFrequency, toCall: number): string {
  const passive = toCall > 0 ? "Call" : "Check";
  return `Mix: ${pct(frequency.check)} ${passive}, ${pct(frequency.betSmall)} Bet Small, ${pct(frequency.betBig)} Bet Big.`;
}

function buildRationale(input: {
  bucketTemplate?: string;
  boardTextureDescription: string;
  toCall: number;
  potSize: number;
  math: MathBreakdown;
  handClassDescription: string;
  frequencyText: string;
  equity: number;
  simulations: number;
  villainRangeHash: string;
}): string {
  const parts: string[] = [];
  if (input.bucketTemplate) parts.push(input.bucketTemplate);
  parts.push(`Board: ${input.boardTextureDescription}.`);
  parts.push(`Hand class: ${input.handClassDescription}.`);
  parts.push(`Equity model: ${pct(input.equity)} over ${input.simulations} sims.`);
  parts.push(`Range hash: ${input.villainRangeHash.slice(0, 10)}.`);

  if (input.toCall > 0) {
    const callAmount = round2(input.math.callAmount ?? 0);
    const winAmount = round2((input.potSize ?? 0) + (input.math.callAmount ?? 0));
    const equityNeeded = pct(input.math.equityRequired ?? 0);
    parts.push(`Call ${callAmount} to win ${winAmount}; need ${equityNeeded} equity.`);
    if (typeof input.math.mdf === "number") {
      parts.push(`MDF vs this sizing: ${pct(input.math.mdf)}.`);
    }
  }

  if (typeof input.math.spr === "number") {
    const sprText = `SPR ${round2(input.math.spr)}`;
    if (input.math.isLowSpr) {
      parts.push(`${sprText} (< ${input.math.commitmentThreshold ?? 3}), so one-pair hands can become commitment candidates.`);
    } else {
      parts.push(`${sprText}, so keep a balanced check/bet range.`);
    }
  }

  parts.push(input.frequencyText);
  return parts.join(" ");
}

function hashToUnitInterval(seed: string): number {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) / 0x100000000;
}

function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

function round4(value: number): number {
  return Math.round(value * 10_000) / 10_000;
}

function buildVillainRangeFromCharts(context: PostflopContext): HandRange {
  const chartRows = loadPreflopChartRows();
  if (chartRows.length === 0) return new Map<string, number>();

  const effectiveBb = context.effectiveStackBb ?? 100;
  const targetDepth = effectiveBb < 40 ? 40 : effectiveBb <= 80 ? 60 : effectiveBb > 150 ? 150 : 100;
  const formatCandidates = [`cash_6max_${targetDepth}bb`, "cash_6max_100bb"];

  const primarySpot = context.preflopAggressor === "villain"
    ? `${context.villainPosition}_unopened_open2.5x`
    : `${context.villainPosition}_vs_${context.heroPosition}_facing_open2.5x`;

  const fallbackSpots = [
    `${context.villainPosition}_unopened_open2.5x`,
    `${context.villainPosition}_vs_${context.heroPosition}_facing_open2.5x`,
  ];

  const spotCandidates = [primarySpot, ...fallbackSpots.filter((spot) => spot !== primarySpot)];

  const range = new Map<string, number>();

  for (const format of formatCandidates) {
    for (const spot of spotCandidates) {
      const rows = chartRows.filter((row) => row.format === format && row.spot === spot);
      if (rows.length === 0) continue;

      for (const row of rows) {
        const actionWeight = context.preflopAggressor === "villain"
          ? row.mix.raise
          : row.mix.call + row.mix.raise * 0.2;
        if (actionWeight <= 0) continue;
        range.set(row.hand, actionWeight);
      }

      if (range.size > 0) {
        return normalizeRangeWeights(range);
      }
    }
  }

  return range;
}

function narrowVillainRangeByHistory(baseRange: HandRange, context: PostflopContext): HandRange {
  let current = new Map(baseRange);
  if (!context.actionHistory || context.actionHistory.length === 0) return current;

  const villainActions = context.actionHistory.filter((action) => action.seat !== context.seat);

  for (const action of villainActions) {
    if (action.street === "PREFLOP" || action.street === "SHOWDOWN" || action.street === "RUN_IT_TWICE_PROMPT") {
      continue;
    }

    if (action.type !== "check" && action.type !== "call" && action.type !== "raise" && action.type !== "all_in") {
      continue;
    }

    const sizingBucket = context.potSize > EPSILON ? action.amount / context.potSize : undefined;
    current = rangeEstimator.narrowRangePostflop(
      current,
      action.type,
      action.street,
      context.board,
      sizingBucket
    );
  }

  return normalizeRangeWeights(current);
}

function loadPreflopChartRows(): PreflopChartRow[] {
  if (preflopChartRowsCache) return preflopChartRowsCache;

  try {
    const path = resolvePreflopChartPath();
    const parsed = JSON.parse(readFileSync(path, "utf-8")) as PreflopChartRow[];
    preflopChartRowsCache = Array.isArray(parsed) ? parsed : [];
  } catch {
    preflopChartRowsCache = [];
  }

  return preflopChartRowsCache;
}

function resolvePreflopChartPath(): string {
  const fromEnv = process.env.CARDPILOT_CHART_PATH;
  if (fromEnv) return fromEnv;

  const candidates = [
    join(process.cwd(), "data", "preflop_charts.json"),
    join(process.cwd(), "data", "preflop_charts.sample.json"),
  ];

  for (const candidate of candidates) {
    try {
      readFileSync(candidate, "utf-8");
      return candidate;
    } catch {
      // continue
    }
  }

  const thisDir = fileURLToPath(new URL(".", import.meta.url));
  return join(thisDir, "../../../data/preflop_charts.json");
}

function normalizeRangeWeights(range: HandRange): HandRange {
  const total = [...range.values()].reduce((sum, value) => sum + Math.max(0, value), 0);
  if (total <= EPSILON) return range;

  const normalized = new Map<string, number>();
  for (const [hand, weight] of range) {
    normalized.set(hand, Math.max(0, weight) / total);
  }
  return normalized;
}

function getWorkerService(): WorkerService {
  if (!workerService) {
    workerService = new WorkerService();
  }
  return workerService;
}

export const __test__ = {
  resolveLineToken,
  buildFrequencyFromScores,
  enforceLegalRecommendedAction,
  toNormalizedMixForTesting: (frequency: PostflopFrequency, toCall: number) =>
    normalizeMix(toLegacyMix({ frequency, toCall })),
};
