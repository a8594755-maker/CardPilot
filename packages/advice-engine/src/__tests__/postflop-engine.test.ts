import test from "node:test";
import assert from "node:assert/strict";
import { classifyHandOnBoard } from "@cardpilot/poker-evaluator";
import type { BoardTextureProfile, MathBreakdown } from "@cardpilot/shared-types";
import { __test__, type PostflopContext, type StrategyConfig } from "../postflop-engine.js";

const strategyConfig: StrategyConfig = {
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

const boardTexture: BoardTextureProfile = {
  isPaired: false,
  isMonotone: false,
  hasFlushDraw: true,
  isConnected: true,
  isDisconnected: false,
  isHighCardHeavy: false,
  wetness: "wet",
  labels: ["WET"],
};

const baseContext: PostflopContext = {
  tableId: "t1",
  handId: "h1",
  seat: 1,
  street: "FLOP",
  heroHand: ["As", "Kd"],
  board: ["Qs", "Jh", "2d"],
  heroPosition: "BTN",
  villainPosition: "BB",
  potSize: 100,
  toCall: 40,
  effectiveStack: 300,
  effectiveStackBb: 100,
  aggressor: "villain",
  preflopAggressor: "hero",
  heroInPosition: true,
  numVillains: 1,
  actionHistory: [],
  potType: "SRP",
};

const math: MathBreakdown = {
  potOdds: 0.2857,
  equityRequired: 0.2857,
  callAmount: 40,
  potAfterCall: 140,
  spr: 3,
  effectiveStack: 300,
  commitmentThreshold: 3,
  isLowSpr: false,
};

test("line classification uses preflop aggressor + IP/OOP context", () => {
  assert.equal(__test__.resolveLineToken({ ...baseContext, toCall: 10 }), "VS_BET");
  assert.equal(__test__.resolveLineToken({ ...baseContext, toCall: 0, aggressor: "hero", street: "FLOP" }), "CBET");
  assert.equal(__test__.resolveLineToken({ ...baseContext, toCall: 0, aggressor: "hero", street: "TURN" }), "BARREL");
  assert.equal(
    __test__.resolveLineToken({
      ...baseContext,
      toCall: 0,
      aggressor: "none",
      preflopAggressor: "villain",
      heroInPosition: true,
      street: "FLOP",
    }),
    "PROBE"
  );
  assert.equal(
    __test__.resolveLineToken({
      ...baseContext,
      toCall: 0,
      aggressor: "none",
      preflopAggressor: "hero",
      heroInPosition: false,
      street: "FLOP",
    }),
    "CBET"
  );
});

test("mix sums to 1 after normalization", () => {
  const handClass = classifyHandOnBoard(baseContext.heroHand, baseContext.board);
  const freq = __test__.buildFrequencyFromScores({
    context: baseContext,
    boardTexture,
    handClass,
    math,
    equity: 0.42,
    strategyConfig,
  });

  const mix = __test__.toNormalizedMixForTesting(freq, baseContext.toCall);
  const sum = mix.raise + mix.call + mix.fold;
  assert.ok(Math.abs(sum - 1) < 0.0002, `expected normalized mix sum ~= 1, got ${sum}`);
});

test("recommended action legality guard handles no-check fold and all-in calls", () => {
  assert.equal(__test__.enforceLegalRecommendedAction("fold", 0, 120), "call");
  assert.equal(__test__.enforceLegalRecommendedAction("call", 150, 100), "raise");
  assert.equal(__test__.enforceLegalRecommendedAction("raise", 0, 0), "call");
});

test("equity-based adjustment tightens betting when equity is below required", () => {
  const handClass = classifyHandOnBoard(baseContext.heroHand, baseContext.board);

  const highEq = __test__.buildFrequencyFromScores({
    context: baseContext,
    boardTexture,
    handClass,
    math: { ...math, equityRequired: 0.3 },
    equity: 0.45,
    strategyConfig,
  });

  const lowEq = __test__.buildFrequencyFromScores({
    context: baseContext,
    boardTexture,
    handClass,
    math: { ...math, equityRequired: 0.35 },
    equity: 0.2,
    strategyConfig,
  });

  const highBet = highEq.betSmall + highEq.betBig;
  const lowBet = lowEq.betSmall + lowEq.betBig;

  assert.ok(lowBet < highBet, "low-equity node should reduce betting frequencies");
  assert.ok(lowEq.check + lowBet <= highEq.check + highBet, "low-equity path should not increase total active frequency");
});
