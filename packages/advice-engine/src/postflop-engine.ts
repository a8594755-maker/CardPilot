import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { classifyHandOnBoard, type Card } from "@cardpilot/poker-evaluator";
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

const EPSILON = 1e-6;

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
  numVillains: number;
  actionHistory?: HandAction[];
  potType?: "SRP" | "3BP" | "4BP";
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

export class PostflopEngine {
  private readonly bucketIndex = new Map<string, PostflopBucketStrategy>();

  constructor(rows?: PostflopBucketStrategy[]) {
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

  getAdvice(context: PostflopContext): PostflopAdvice {
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

    const frequency = normalizeFrequency(
      bucket?.frequency
      ?? fallbackFrequency({
        context,
        boardTexture,
        handClass,
        math,
      })
    );

    const preferredAction = bucket?.preferredAction ?? derivePreferredAction(frequency);
    const mix = normalizeMix(
      toLegacyMix({
        frequency,
        toCall: context.toCall,
        handClassType: handClass.type,
        equityRequired: math.equityRequired ?? 0,
      })
    );

    const seed = `${context.tableId}|${context.handId}|${context.seat}|${baseKey}|${context.heroHand[0]}${context.heroHand[1]}`;
    const random = hashToUnitInterval(seed);
    const recommended = pickByMix(mix, random);
    const frequencyText = formatFrequency(frequency, context.toCall);
    const rationale = buildRationale({
      bucketTemplate: bucket?.rationaleTemplate,
      boardTextureDescription: BoardAnalyzer.describe(boardTexture),
      toCall: context.toCall,
      potSize: context.potSize,
      math,
      handClassDescription: handClass.description,
      frequencyText,
    });

    const tags = [...new Set([
      ...(bucket?.tags ?? []),
      `TEXTURE_${textureBucket}`,
      `LINE_${line}`,
      `POT_${potType}`,
      context.numVillains > 1 ? "MULTIWAY" : "HEADS_UP",
      math.isLowSpr ? "LOW_SPR" : "NORMAL_SPR",
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

export function getPostflopAdvice(context: PostflopContext): PostflopAdvice {
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
  if (context.toCall > 0) return "VS_BET";
  if (context.street === "FLOP" && context.aggressor !== "hero") return "CBET";
  if (context.aggressor === "hero") return "BARREL";
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

function fallbackFrequency(input: {
  context: PostflopContext;
  boardTexture: BoardTextureProfile;
  handClass: ReturnType<typeof classifyHandOnBoard>;
  math: MathBreakdown;
}): PostflopFrequency {
  const { context, boardTexture, handClass, math } = input;

  if (context.toCall > 0) {
    if (math.isLowSpr && handClass.type === "made_hand" && handClass.strength !== "weak") {
      return { check: 0.45, betSmall: 0.15, betBig: 0.3 };
    }

    if (handClass.type === "draw") {
      if ((math.equityRequired ?? 1) <= 0.25) return { check: 0.65, betSmall: 0.1, betBig: 0.1 };
      if ((math.equityRequired ?? 1) <= 0.33) return { check: 0.5, betSmall: 0.1, betBig: 0.05 };
      return { check: 0.3, betSmall: 0.05, betBig: 0.05 };
    }

    if (handClass.type === "made_hand") {
      return handClass.strength === "strong"
        ? { check: 0.55, betSmall: 0.15, betBig: 0.2 }
        : { check: 0.45, betSmall: 0.1, betBig: 0.1 };
    }

    return { check: 0.3, betSmall: 0.05, betBig: 0.05 };
  }

  if (boardTexture.wetness === "wet") return { check: 0.35, betSmall: 0.2, betBig: 0.45 };
  if (boardTexture.wetness === "dry") return { check: 0.3, betSmall: 0.55, betBig: 0.15 };
  return { check: 0.4, betSmall: 0.4, betBig: 0.2 };
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
  handClassType: "made_hand" | "draw" | "air";
  equityRequired: number;
}): StrategyMix {
  const raise = input.frequency.betSmall + input.frequency.betBig;
  let call = input.frequency.check;
  let fold = input.toCall > 0 ? Math.max(0, 1 - raise - call) : 0;

  if (input.toCall > 0 && input.handClassType === "air" && input.equityRequired > 0.33 && fold < 0.2) {
    fold = 0.2;
    call = Math.max(0, call - 0.2);
  }

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
}): string {
  const parts: string[] = [];
  if (input.bucketTemplate) parts.push(input.bucketTemplate);
  parts.push(`Board: ${input.boardTextureDescription}.`);
  parts.push(`Hand class: ${input.handClassDescription}.`);

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
