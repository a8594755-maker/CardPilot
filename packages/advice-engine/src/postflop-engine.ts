import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { classifyHandOnBoard, type Card, type EquityResult } from '@cardpilot/poker-evaluator';
import type {
  AdvicePayload,
  BoardTextureProfile,
  HandAction,
  MathBreakdown,
  PostflopFrequency,
  PostflopPreferredAction,
  StrategyMix,
} from '@cardpilot/shared-types';
import { BoardAnalyzer } from './board-analyzer.js';
import { MathEngine } from './math-engine.js';
import { RangeEstimator, type HandRange } from './range-estimator.js';
import { WorkerService } from './WorkerService.js';
import { CfrAdvisor } from './cfr-advisor.js';
import { isS3Configured } from './s3-client.js';

const EPSILON = 1e-6;
const ONE_HOUR_MS = 60 * 60 * 1000;
const MAX_EQUITY_CACHE_ENTRIES = 2000;
const DEFAULT_POSTFLOP_SIMULATIONS = 300;

export type AdvicePrecision = 'fast' | 'deep';

const PRECISION_SIMULATIONS: Record<AdvicePrecision, number> = {
  fast: 800,
  deep: 7000,
};

const equityCache = createTimedLruCache<string, EquityResult>(
  MAX_EQUITY_CACHE_ENTRIES,
  ONE_HOUR_MS,
);
const rangeEstimator = new RangeEstimator();
let workerService: WorkerService | null = null;

process.once('beforeExit', () => {
  if (workerService) {
    void workerService.destroy();
  }
});

export interface PostflopContext {
  tableId: string;
  handId: string;
  seat: number;
  street: 'FLOP' | 'TURN' | 'RIVER';
  heroHand: [Card, Card];
  board: Card[];
  heroPosition: string;
  villainPosition: string;
  potSize: number;
  toCall: number;
  effectiveStack: number;
  effectiveStackBb?: number;
  aggressor: 'hero' | 'villain' | 'none';
  preflopAggressor: 'hero' | 'villain' | 'none';
  heroInPosition: boolean;
  numVillains: number;
  actionHistory?: HandAction[];
  potType?: 'SRP' | '3BP' | '4BP';
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
  precision?: AdvicePrecision;
}): Promise<{ result: EquityResult; villainRangeHash: string }> {
  const { context, handClass, precision } = input;
  const simulations = precision ? PRECISION_SIMULATIONS[precision] : DEFAULT_POSTFLOP_SIMULATIONS;
  const deadCards = new Set([...context.heroHand, ...context.board]);

  const chartAnchoredRange = buildVillainRangeFromCharts(context);
  const baseRange =
    chartAnchoredRange.size > 0
      ? chartAnchoredRange
      : rangeEstimator.buildPreflopRange(
          context.villainPosition,
          context.preflopAggressor === 'villain' ? 'raise' : 'call',
          context.heroPosition,
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
  const precisionTag = precision ?? 'default';
  const cacheKey =
    buildEquityCacheKey(context.heroHand, context.board, villainRangeHash) + `|${precisionTag}`;
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
    simulations,
  });

  equityCache.set(cacheKey, result);
  return { result, villainRangeHash };
}

function blendFrequency(
  baseline: PostflopFrequency,
  solved: PostflopFrequency,
  baselineWeight: number,
): PostflopFrequency {
  const baselineShare = clamp01(baselineWeight);
  const solvedShare = 1 - baselineShare;

  return normalizeFrequency({
    check: baseline.check * baselineShare + solved.check * solvedShare,
    betSmall: baseline.betSmall * baselineShare + solved.betSmall * solvedShare,
    betBig: baseline.betBig * baselineShare + solved.betBig * solvedShare,
  });
}

function buildEquityCacheKey(
  heroHand: [Card, Card],
  board: Card[],
  villainRangeHash: string,
): string {
  const hero = `${heroHand[0]}${heroHand[1]}`;
  const boardKey = [...board].sort().join('');
  return `${hero}-${boardKey}-${villainRangeHash}`;
}

function hashRange(villainHands: Array<[Card, Card]>): string {
  const canonical = villainHands
    .map(([a, b]) => [a, b].sort().join(''))
    .sort()
    .join('|');
  return stableHash(canonical || 'empty');
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
  if (handClass.type === 'made_hand') {
    if (handClass.strength === 'strong') return 0.72;
    if (handClass.strength === 'medium') return 0.56;
    return 0.4;
  }
  if (handClass.type === 'draw') return 0.38;
  return 0.2;
}

function textureToAggressionScore(boardTexture: BoardTextureProfile): number {
  if (boardTexture.wetness === 'wet') return 0.72;
  if (boardTexture.wetness === 'dry') return 0.38;
  return 0.55;
}

function showdownValueScore(handClass: ReturnType<typeof classifyHandOnBoard>): number {
  if (handClass.type === 'made_hand') {
    if (handClass.strength === 'strong') return 0.9;
    if (handClass.strength === 'medium') return 0.65;
    return 0.35;
  }
  if (handClass.type === 'draw') return 0.45;
  return 0.1;
}

function deriveNutAdvantage(
  handClass: ReturnType<typeof classifyHandOnBoard>,
  boardTexture: BoardTextureProfile,
): number {
  const classBoost =
    handClass.type === 'made_hand' && handClass.strength === 'strong'
      ? 0.85
      : handClass.type === 'draw'
        ? 0.55
        : 0.25;

  if (boardTexture.wetness === 'wet') return clamp01(classBoost + 0.1);
  return clamp01(classBoost - 0.05);
}

function deriveFoldEquity(context: PostflopContext, boardTexture: BoardTextureProfile): number {
  let score = 0.4;
  if (context.aggressor === 'hero') score += 0.2;
  if (context.numVillains > 1) score -= 0.15;
  if (context.toCall > 0) score -= 0.1;
  if (boardTexture.wetness === 'dry') score += 0.1;
  return clamp01(score);
}

function deriveRangeAdvantage(input: {
  context: PostflopContext;
  boardTexture: BoardTextureProfile;
  nutAdvantage: number;
  handClass: ReturnType<typeof classifyHandOnBoard>;
}): number {
  const { context, boardTexture, nutAdvantage, handClass } = input;
  let score = 0.45;

  if (context.preflopAggressor === 'hero') score += 0.14;
  if (context.aggressor === 'hero') score += 0.08;
  if (context.heroInPosition) score += 0.06;
  if (context.numVillains > 1) score -= 0.12;

  if (boardTexture.wetness === 'dry') score += 0.05;
  if (boardTexture.wetness === 'wet') score -= 0.03;

  if (handClass.type === 'made_hand' && handClass.strength === 'strong') score += 0.08;
  if (handClass.type === 'air') score -= 0.06;

  score += (nutAdvantage - 0.5) * 0.3;
  return clamp01(score);
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function createTimedLruCache<K, V>(
  maxEntries: number,
  ttlMs: number,
): {
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
        if (typeof oldestKey !== 'undefined') {
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
  postflop: NonNullable<AdvicePayload['postflop']>;
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
  readonly cfrAdvisor: CfrAdvisor;

  constructor(
    rows?: PostflopBucketStrategy[],
    strategyConfig: StrategyConfig = DEFAULT_STRATEGY_CONFIG,
  ) {
    this.strategyConfig = strategyConfig;
    const parsedRows = rows ?? loadPostflopRowsFromDisk();
    for (const row of parsedRows) {
      this.bucketIndex.set(row.bucketKey, row);
    }
    if (this.bucketIndex.size > 0) {
      console.log(`[advice-engine] loaded ${this.bucketIndex.size} postflop bucket rows`);
    } else {
      console.log('[advice-engine] no postflop bucket rows found, using heuristic fallback only');
    }

    this.cfrAdvisor = new CfrAdvisor();
  }

  /** Load CFR data from local files (development) or S3 (production). */
  async initCfr(): Promise<void> {
    if (isS3Configured()) {
      console.log('[advice-engine] loading CFR data from S3...');
      await this.cfrAdvisor.loadFromS3(
        'binary/v1_hu_srp_50bb.bin.gz',
        'meta/pipeline_hu_srp_50bb/_index.json',
        'SRP',
      );
      await this.cfrAdvisor.loadFromS3(
        'binary/pipeline_hu_3bet_50bb.bin.gz',
        'meta/pipeline_hu_3bet_50bb/_index.json',
        '3BP',
      );
      console.log('[advice-engine] CFR data loaded from S3');
    } else {
      const cfrEntries = resolveCfrDataPaths();
      for (const entry of cfrEntries) {
        this.cfrAdvisor.load(entry.binary, entry.metaDir, entry.potType);
      }
    }
  }

  async getAdvice(context: PostflopContext, precision?: AdvicePrecision): Promise<PostflopAdvice> {
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
      precision,
    });

    const solvedFrequency = buildFrequencyFromScores({
      context,
      boardTexture,
      handClass,
      math,
      equity: equityResult.equity,
      strategyConfig: this.strategyConfig,
    });

    // Query CFR solved strategy if available
    const cfrResult = this.cfrAdvisor.isLoaded ? this.cfrAdvisor.query(context) : null;

    let frequency: PostflopFrequency;
    if (cfrResult) {
      // CFR available — blend with heuristic (CFR-weighted)
      const cfrWeight = cfrResult.confidence;
      frequency = normalizeFrequency(
        blendFrequency(solvedFrequency, cfrResult.frequency, 1 - cfrWeight),
      );
    } else {
      frequency = normalizeFrequency(
        bucket?.frequency
          ? blendFrequency(bucket.frequency, solvedFrequency, 0.65)
          : solvedFrequency,
      );
    }

    const preferredAction = bucket?.preferredAction ?? derivePreferredAction(frequency);
    const mix = normalizeMix(
      toLegacyMix({
        frequency,
        toCall: context.toCall,
      }),
    );

    const seed = `${context.tableId}|${context.handId}|${context.seat}|${baseKey}|${context.heroHand[0]}${context.heroHand[1]}`;
    const random = hashToUnitInterval(seed);
    const recommended = enforceLegalRecommendedAction(
      pickByMix(mix, random),
      context.toCall,
      context.effectiveStack,
    );
    const frequencyText = formatFrequency(frequency, context.toCall);
    const adviceSource = cfrResult
      ? cfrResult.source === 'cfr_exact'
        ? 'CFR_SOLVED'
        : 'CFR_NEAREST'
      : bucket
        ? bucket.bucketKey === baseKey
          ? 'EXACT_BUCKET'
          : 'FUZZY_BUCKET'
        : 'HEURISTIC_ENGINE';
    const nutAdvantage = deriveNutAdvantage(handClass, boardTexture);
    const rangeAdvantage = deriveRangeAdvantage({
      context,
      boardTexture,
      nutAdvantage,
      handClass,
    });
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
      adviceSource,
      nutAdvantage,
      rangeAdvantage,
      heroInPosition: context.heroInPosition,
      aggressor: context.aggressor,
      street: context.street,
    });

    const tags = [
      ...new Set([
        ...(bucket?.tags ?? []),
        `TEXTURE_${textureBucket}`,
        `LINE_${line}`,
        `POT_${potType}`,
        context.numVillains > 1 ? 'MULTIWAY' : 'HEADS_UP',
        math.isLowSpr ? 'LOW_SPR' : 'NORMAL_SPR',
        `EQUITY_${Math.round(equityResult.equity * 100)}`,
      ]),
    ];

    const alpha =
      context.toCall > 0 && context.potSize > 0
        ? round4(context.toCall / (context.potSize + context.toCall))
        : 0;
    const mdf = round4(1 - alpha);
    const isStandardNode = Boolean(bucket) || Boolean(cfrResult);

    return {
      tableId: context.tableId,
      handId: context.handId,
      seat: context.seat,
      stage: 'postflop',
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
        alpha,
        mdf,
        isStandardNode,
      },
    };
  }

  private resolveBucket(input: {
    baseKey: string;
    potType: 'SRP' | '3BP' | '4BP';
    heroPosition: string;
    villainPosition: string;
    street: 'FLOP' | 'TURN' | 'RIVER';
    line: 'CBET' | 'VS_BET' | 'BARREL' | 'PROBE';
    textureBucket: 'DRY_TEXTURE' | 'NEUTRAL_TEXTURE' | 'WET_TEXTURE';
  }): PostflopBucketStrategy | undefined {
    const exactCandidate = input.baseKey;
    const fuzzyCandidates = [
      // Texture fallback first: preserve all other dimensions and soften texture strictness.
      ...(input.textureBucket !== 'NEUTRAL_TEXTURE'
        ? [buildBucketKey({ ...input, textureBucket: 'NEUTRAL_TEXTURE' })]
        : []),
      buildBucketKey({ ...input, villainPosition: 'ANY' }),
      buildBucketKey({ ...input, villainPosition: 'ANY', textureBucket: 'NEUTRAL_TEXTURE' }),
      // Pot fallback: for sparse 3BP/4BP data, walk down to SRP equivalents.
      ...(input.potType !== 'SRP'
        ? [
            buildBucketKey({ ...input, potType: 'SRP' }),
            buildBucketKey({ ...input, potType: 'SRP', textureBucket: 'NEUTRAL_TEXTURE' }),
            buildBucketKey({ ...input, potType: 'SRP', villainPosition: 'ANY' }),
            buildBucketKey({
              ...input,
              potType: 'SRP',
              villainPosition: 'ANY',
              textureBucket: 'NEUTRAL_TEXTURE',
            }),
          ]
        : []),
    ];

    const exact = this.bucketIndex.get(exactCandidate);
    if (exact) {
      console.log(`[advice-engine] Advice Source: EXACT_BUCKET (${exactCandidate})`);
      return exact;
    }

    for (const key of fuzzyCandidates) {
      const row = this.bucketIndex.get(key);
      if (row) {
        console.log(`[advice-engine] Advice Source: FUZZY_BUCKET ("${input.baseKey}" → "${key}")`);
        return row;
      }
    }

    if (this.bucketIndex.size > 0) {
      console.log(
        `[advice-engine] Advice Source: HEURISTIC_ENGINE (bucket miss "${input.baseKey}", tried ${1 + fuzzyCandidates.length} candidates)`,
      );
    }
    return undefined;
  }
}

let postflopEngine: PostflopEngine | null = null;
let initPromise: Promise<PostflopEngine> | null = null;

async function ensureEngine(): Promise<PostflopEngine> {
  if (postflopEngine) return postflopEngine;
  if (initPromise) return initPromise;
  initPromise = (async () => {
    const engine = new PostflopEngine();
    await engine.initCfr();
    postflopEngine = engine;
    return engine;
  })();
  return initPromise;
}

export async function getPostflopAdvice(
  context: PostflopContext,
  precision?: AdvicePrecision,
): Promise<PostflopAdvice> {
  const engine = await ensureEngine();
  return engine.getAdvice(context, precision);
}

function loadPostflopRowsFromDisk(): PostflopBucketStrategy[] {
  const path = resolvePostflopPath();
  if (!path) {
    console.warn(
      '[advice-engine] no postflop bucket file path resolved; using heuristic-only mode',
    );
    return [];
  }

  try {
    const raw = readFileSync(path, 'utf-8');
    const parsed = JSON.parse(raw) as PostflopBucketStrategy[];
    if (!Array.isArray(parsed)) {
      console.warn(`[advice-engine] postflop bucket file at ${path} is not an array`);
      return [];
    }
    const valid = parsed.filter(
      (row) =>
        Boolean(row?.bucketKey) &&
        Boolean(row?.preferredAction) &&
        Boolean(row?.frequency) &&
        Boolean(row?.rationaleTemplate),
    );
    if (valid.length < parsed.length) {
      console.warn(
        `[advice-engine] filtered ${parsed.length - valid.length} invalid bucket rows from ${path}`,
      );
    }
    console.log(`[advice-engine] loaded ${valid.length} valid postflop bucket rows from ${path}`);
    return valid;
  } catch (error) {
    console.warn(
      `[advice-engine] failed to load postflop buckets from ${path}: ${(error as Error).message}`,
    );
    return [];
  }
}

function resolvePostflopPath(): string | null {
  const fromEnv = process.env.CARDPILOT_POSTFLOP_BUCKET_PATH;
  if (fromEnv) return fromEnv;

  const cwdCandidates = [
    join(process.cwd(), 'data', 'postflop_buckets.json'),
    join(process.cwd(), 'data', 'postflop_buckets.sample.json'),
  ];

  for (const candidate of cwdCandidates) {
    try {
      readFileSync(candidate, 'utf-8');
      return candidate;
    } catch {
      // continue
    }
  }

  const thisDir = fileURLToPath(new URL('.', import.meta.url));
  return join(thisDir, '../../../data/postflop_buckets.sample.json');
}

interface CfrDataEntry {
  binary: string;
  metaDir: string;
  potType: 'SRP' | '3BP';
}

function resolveCfrDataPaths(): CfrDataEntry[] {
  const thisDir = fileURLToPath(new URL('.', import.meta.url));
  const results: CfrDataEntry[] = [];

  const configs: { name: string; potType: 'SRP' | '3BP' }[] = [
    { name: 'v1_hu_srp_50bb', potType: 'SRP' },
    { name: 'pipeline_hu_3bet_50bb', potType: '3BP' },
  ];

  for (const cfg of configs) {
    const binCandidates = [
      join(process.cwd(), 'data', 'cfr', `${cfg.name}.bin.gz`),
      join(thisDir, `../../../data/cfr/${cfg.name}.bin.gz`),
    ];

    let binary: string | null = null;
    for (const candidate of binCandidates) {
      if (existsSync(candidate)) {
        binary = candidate;
        break;
      }
    }
    if (!binary) continue;

    const metaDir = binary.replace(/\.bin(\.gz)?$/, '');
    results.push({ binary, metaDir, potType: cfg.potType });
    console.log(`[advice-engine] CFR data (${cfg.potType}): binary=${binary}`);
  }

  return results;
}

function inferPotType(actions?: HandAction[]): 'SRP' | '3BP' | '4BP' {
  if (!actions || actions.length === 0) return 'SRP';
  const preflopRaises = actions.filter(
    (action) =>
      action.street === 'PREFLOP' && (action.type === 'raise' || action.type === 'all_in'),
  ).length;

  if (preflopRaises >= 3) return '4BP';
  if (preflopRaises === 2) return '3BP';
  return 'SRP';
}

function resolveLineToken(context: PostflopContext): 'CBET' | 'VS_BET' | 'BARREL' | 'PROBE' {
  if (context.toCall > 0) {
    return 'VS_BET';
  }

  if (context.aggressor === 'hero') {
    return context.street === 'FLOP' ? 'CBET' : 'BARREL';
  }

  if (context.street === 'FLOP') {
    if (context.preflopAggressor === 'hero') {
      return 'CBET';
    }
    return context.heroInPosition ? 'PROBE' : 'VS_BET';
  }

  if (context.preflopAggressor === 'hero' && context.heroInPosition) {
    return 'BARREL';
  }

  return 'PROBE';
}

function buildBucketKey(params: {
  potType: 'SRP' | '3BP' | '4BP';
  heroPosition: string;
  villainPosition: string;
  street: 'FLOP' | 'TURN' | 'RIVER';
  line: 'CBET' | 'VS_BET' | 'BARREL' | 'PROBE';
  textureBucket: 'DRY_TEXTURE' | 'NEUTRAL_TEXTURE' | 'WET_TEXTURE';
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
  const { context, boardTexture, handClass, math, equity, strategyConfig } = input;

  const textureScore = textureToAggressionScore(boardTexture);
  const nutAdvantage = deriveNutAdvantage(handClass, boardTexture);
  const rangeAdvantage = deriveRangeAdvantage({
    context,
    boardTexture,
    nutAdvantage,
    handClass,
  });
  const foldEquity = deriveFoldEquity(context, boardTexture);
  const showdownValue = showdownValueScore(handClass);
  const spr = math.spr ?? 10;
  const isLowSpr = spr < (math.commitmentThreshold ?? 3);
  const isDraw = handClass.type === 'draw';
  const isStrong = handClass.type === 'made_hand' && handClass.strength === 'strong';
  const isMedium = handClass.type === 'made_hand' && handClass.strength === 'medium';
  const isAir = handClass.type === 'air';
  const isTopValueSlice = isStrong && equity >= 0.68;
  const canRangeBet = context.aggressor === 'hero' && nutAdvantage > 0.6 && rangeAdvantage > 0.58;

  let checkSignal = 0.34;
  let betSmallSignal = 0.33;
  let betBigSignal = 0.33;

  // Polarized engine: top value + draws (bluffs) bet, medium showdown checks to protect range.
  if (canRangeBet) {
    // Nut/range advantage unlocks high-frequency small betting independent of precise hand equity.
    checkSignal = 0.15;
    betSmallSignal = 0.65 + (rangeAdvantage - 0.58) * 0.25;
    betBigSignal = 0.2 + Math.max(0, equity - 0.55) * 0.2;
  } else if (
    context.aggressor === 'hero' &&
    (isTopValueSlice || (equity >= 0.85 && handClass.type === 'made_hand'))
  ) {
    checkSignal = 0.18;
    betSmallSignal = 0.14;
    betBigSignal = 0.68 + (nutAdvantage - 0.5) * 0.2;
  } else if (context.aggressor === 'hero' && (isDraw || (isAir && foldEquity >= 0.45))) {
    checkSignal = 0.34 + (1 - foldEquity) * 0.15;
    betSmallSignal = 0.17;
    betBigSignal = 0.49 + foldEquity * 0.22 + (nutAdvantage - 0.5) * 0.08;
  } else if (isMedium || (showdownValue >= 0.55 && equity >= 0.4 && equity <= 0.72)) {
    // Showdown-heavy region: increase checking to keep protected check/call/check-back nodes.
    checkSignal = 0.72 + (1 - textureScore) * 0.12;
    betSmallSignal = 0.22 + textureScore * 0.05;
    betBigSignal = 0.06;
  } else if (equity >= 0.62) {
    checkSignal = 0.3;
    betSmallSignal = 0.28;
    betBigSignal = 0.42;
  } else if (isAir && foldEquity < 0.35) {
    checkSignal = 0.82;
    betSmallSignal = 0.14;
    betBigSignal = 0.04;
  } else {
    checkSignal = 0.62;
    betSmallSignal = 0.26;
    betBigSignal = 0.12;
  }

  // OOP adjustment: globally reduce betting frequency and shift EV into checking lines.
  if (!context.heroInPosition) {
    const oopReduction = isStrong ? 0.08 : 0.18;
    const shiftedFromSmall = betSmallSignal * oopReduction;
    const shiftedFromBig = betBigSignal * (oopReduction * 0.85);
    betSmallSignal = Math.max(0, betSmallSignal - shiftedFromSmall);
    betBigSignal = Math.max(0, betBigSignal - shiftedFromBig);
    checkSignal += shiftedFromSmall + shiftedFromBig;
  }

  // SPR adjustment: low SPR allows wider stack-off/value-jam behavior.
  if (isLowSpr && (isStrong || isMedium)) {
    betBigSignal += 0.15;
    checkSignal -= 0.15;
  }

  // Nut-advantage pressure: in non-range-bet nodes, still increase aggression when we own top-end combos.
  if (!canRangeBet && nutAdvantage > 0.7) {
    betBigSignal += 0.1;
    betSmallSignal += 0.04;
    checkSignal -= 0.14;
  }

  // Later streets are naturally more polarized (less medium-size betting).
  if (context.street === 'TURN' || context.street === 'RIVER') {
    const polarizationShift = context.street === 'RIVER' ? 0.22 : 0.14;
    betBigSignal += betSmallSignal * polarizationShift;
    betSmallSignal -= betSmallSignal * polarizationShift;
  }

  // Continuation pressure when hero has initiative.
  if (context.aggressor === 'hero') {
    betBigSignal += 0.05;
    betSmallSignal += 0.04;
    checkSignal -= 0.09;
  }

  // Config baseline tuning.
  const configBoost = strategyConfig.baseRaiseRate;
  betBigSignal = clamp01(
    betBigSignal +
      configBoost * 0.24 +
      strategyConfig.aggressionFactors.nutAdvantage * nutAdvantage * 0.15,
  );
  betSmallSignal = clamp01(
    betSmallSignal +
      configBoost * 0.18 +
      strategyConfig.aggressionFactors.foldEquity * foldEquity * 0.08,
  );
  checkSignal = clamp01(checkSignal);

  if (context.toCall <= 0) {
    return normalizeFrequency({
      check: clamp01(checkSignal),
      betSmall: clamp01(betSmallSignal),
      betBig: clamp01(betBigSignal),
    });
  }

  // Facing a bet: reinterpret outputs as call/raise/fold weights.
  const equityRequired = math.equityRequired ?? 0;

  // MDF floor: defense (call + raise) must not drop below MDF
  const mdf =
    math.mdf ??
    (context.potSize > EPSILON ? context.potSize / (context.potSize + context.toCall) : 1);

  const equityEdge = equity - equityRequired;
  let foldSignal: number;
  if (equityEdge >= 0) {
    foldSignal = clamp01(0.05 - equityEdge * 0.3);
  } else {
    foldSignal = clamp01(Math.abs(equityEdge) * 1.5 + (isAir ? 0.2 : 0));
  }

  let raiseSignal = clamp01(betBigSignal + betSmallSignal * 0.3);

  // Dampen aggression when equity is insufficient to call
  if (equityEdge < 0) {
    // Reduce raise frequency proportional to how far behind we are.
    // e.g. edge -0.1 reduces raises by 20%
    raiseSignal = clamp01(raiseSignal * (1 + Math.max(-0.8, equityEdge * 2.0)));
  }

  if (!context.heroInPosition) {
    // OOP favors check-call/check-raise mixes over pure aggression.
    raiseSignal = clamp01(raiseSignal * 0.82);
  }

  let callSignal = clamp01(1 - raiseSignal - foldSignal);

  // Enforce MDF floor
  const defenseFreq = raiseSignal + callSignal;
  if (defenseFreq < mdf && mdf > EPSILON && mdf < 1) {
    if (defenseFreq > EPSILON) {
      // Prioritize calling to close the MDF gap.
      // Linearly scaling both raise and call (old behavior) artificially inflated aggression
      // for low-equity hands that were folding too much.
      const gap = mdf - defenseFreq;
      callSignal = clamp01(callSignal + gap);
    } else {
      callSignal = mdf;
    }
    foldSignal = clamp01(1 - raiseSignal - callSignal);
  }

  // Determine big vs small raise split
  const betBigShare = clamp01(
    0.35 + nutAdvantage * 0.3 + textureScore * 0.15 + Math.max(0, equity - 0.5) * 0.2,
  );

  const betBig = round4(raiseSignal * betBigShare);
  const betSmall = round4(Math.max(0, raiseSignal - betBig));

  return normalizeFrequency({
    check: callSignal,
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
    return 'bet_big';
  }
  if (frequency.betSmall >= frequency.check) {
    return 'bet_small';
  }
  return 'check';
}

function toLegacyMix(input: { frequency: PostflopFrequency; toCall: number }): StrategyMix {
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

function pickByMix(mix: StrategyMix, random: number): 'raise' | 'call' | 'fold' {
  if (random < mix.raise) return 'raise';
  if (random < mix.raise + mix.call) return 'call';
  return 'fold';
}

function enforceLegalRecommendedAction(
  action: 'raise' | 'call' | 'fold',
  toCall: number,
  effectiveStack: number,
): 'raise' | 'call' | 'fold' {
  if (effectiveStack <= 0) {
    return toCall > 0 ? 'fold' : 'call';
  }

  if (toCall <= 0 && action === 'fold') {
    return 'call';
  }

  if (toCall > effectiveStack && action === 'call') {
    return 'raise';
  }

  return action;
}

function formatFrequency(frequency: PostflopFrequency, toCall: number): string {
  const passive = toCall > 0 ? 'Call' : 'Check';
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
  adviceSource?: string;
  nutAdvantage: number;
  rangeAdvantage: number;
  heroInPosition: boolean;
  aggressor: 'hero' | 'villain' | 'none';
  street: 'FLOP' | 'TURN' | 'RIVER';
}): string {
  const parts: string[] = [];
  if (input.adviceSource) {
    const sourceText =
      input.adviceSource === 'HEURISTIC_ENGINE' ? 'Live Calculation' : 'Solved Strategy';
    parts.push(`[${sourceText}: ${input.adviceSource}]`);
  }
  if (input.bucketTemplate) parts.push(input.bucketTemplate);
  parts.push(`Board: ${input.boardTextureDescription}.`);
  parts.push(`Hand class: ${input.handClassDescription}.`);

  if (input.rangeAdvantage >= 0.6 && input.nutAdvantage >= 0.6) {
    parts.push(
      'Strategic read: you hold both range and nut advantage on this texture, so a high-frequency small-bet strategy is justified even with medium equity segments.',
    );
  } else if (input.nutAdvantage >= 0.6) {
    parts.push(
      "Strategic read: your top-end density is stronger than villain's, so pressure with value-heavy betting and selective bluffs is preferred.",
    );
  } else if (input.rangeAdvantage <= 0.42) {
    parts.push(
      'Strategic read: your range is structurally capped here, so protect EV via a tighter check/call-first strategy.',
    );
  } else {
    parts.push(
      'Strategic read: range equities are close, so keep a protected checking range while mixing pressure at controlled frequencies.',
    );
  }

  if (input.aggressor === 'hero') {
    parts.push(
      'As the initiative player, the model polarizes into value bets and bluff candidates while preserving medium-strength checks.',
    );
  }
  if (!input.heroInPosition) {
    parts.push(
      `Being out of position on the ${input.street} reduces pure betting frequency and shifts weight into check/call and check/raise lines.`,
    );
  }

  parts.push(`Equity model: ${pct(input.equity)} over ${input.simulations} sims.`);
  parts.push(`Range hash: ${input.villainRangeHash.slice(0, 10)}.`);

  if (input.toCall > 0) {
    const callAmount = round2(input.math.callAmount ?? 0);
    const winAmount = round2((input.potSize ?? 0) + (input.math.callAmount ?? 0));
    const equityNeeded = pct(input.math.equityRequired ?? 0);
    parts.push(`Call ${callAmount} to win ${winAmount}; need ${equityNeeded} equity.`);
    if (typeof input.math.mdf === 'number') {
      parts.push(`MDF vs this sizing: ${pct(input.math.mdf)}.`);
    }
  }

  if (typeof input.math.spr === 'number') {
    const sprText = `SPR ${round2(input.math.spr)}`;
    if (input.math.isLowSpr) {
      parts.push(
        `${sprText} (< ${input.math.commitmentThreshold ?? 3}), so one-pair hands can become commitment candidates.`,
      );
    } else {
      parts.push(`${sprText}, so keep a balanced check/bet range.`);
    }
  }

  parts.push(input.frequencyText);
  return parts.join(' ');
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
  const targetDepth =
    effectiveBb < 40 ? 40 : effectiveBb <= 80 ? 60 : effectiveBb > 150 ? 150 : 100;
  const formatCandidates = [`cash_6max_${targetDepth}bb`, 'cash_6max_100bb'];

  const primarySpot =
    context.preflopAggressor === 'villain'
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
        const actionWeight =
          context.preflopAggressor === 'villain'
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

  // Track villain aggression count for range tightening
  let villainPostflopAggCount = 0;

  for (const action of villainActions) {
    if (
      action.street === 'PREFLOP' ||
      action.street === 'SHOWDOWN' ||
      action.street === 'RUN_IT_TWICE_PROMPT'
    ) {
      continue;
    }

    if (
      action.type !== 'check' &&
      action.type !== 'call' &&
      action.type !== 'raise' &&
      action.type !== 'all_in'
    ) {
      continue;
    }

    if (action.type === 'raise' || action.type === 'all_in') {
      villainPostflopAggCount++;
    }

    const sizingBucket = context.potSize > EPSILON ? action.amount / context.potSize : undefined;
    current = rangeEstimator.narrowRangePostflop(
      current,
      action.type,
      action.street,
      context.board,
      sizingBucket,
    );
  }

  // If villain has shown postflop aggression, remove bottom portion of range
  // to simulate a stronger perceived range (GTO assumption)
  if (villainPostflopAggCount > 0 && current.size > 2) {
    const sorted = [...current.entries()].sort((a, b) => b[1] - a[1]);
    // Keep top 50% on single aggression, top 35% on double+ aggression
    const keepRatio = villainPostflopAggCount >= 2 ? 0.35 : 0.5;
    const keepCount = Math.max(2, Math.ceil(sorted.length * keepRatio));
    current = new Map(sorted.slice(0, keepCount));
  }

  return normalizeRangeWeights(current);
}

function loadPreflopChartRows(): PreflopChartRow[] {
  if (preflopChartRowsCache) return preflopChartRowsCache;

  try {
    const path = resolvePreflopChartPath();
    const parsed = JSON.parse(readFileSync(path, 'utf-8')) as PreflopChartRow[];
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
    join(process.cwd(), 'data', 'preflop_charts.json'),
    join(process.cwd(), 'data', 'preflop_charts.sample.json'),
  ];

  for (const candidate of candidates) {
    try {
      readFileSync(candidate, 'utf-8');
      return candidate;
    } catch {
      // continue
    }
  }

  const thisDir = fileURLToPath(new URL('.', import.meta.url));
  return join(thisDir, '../../../data/preflop_charts.json');
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
