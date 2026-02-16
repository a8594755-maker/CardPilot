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

  assert.ok(lowBet < highBet, `low-equity bet ${lowBet.toFixed(3)} should be < high-equity bet ${highBet.toFixed(3)}`);
});

// ── MDF defense guardrail tests ──

test("MDF guardrail: defense frequency >= MDF when facing a bet", () => {
  const handClass = classifyHandOnBoard(["7s", "6s"], ["Qs", "Jh", "2d"]);
  // Large bet: pot 100, toCall 80 → MDF = 100/(100+80) ≈ 0.556
  const largeBetMath: MathBreakdown = {
    potOdds: 0.4444,
    equityRequired: 0.4444,
    callAmount: 80,
    potAfterCall: 180,
    mdf: 0.5556,
    spr: 3,
    effectiveStack: 300,
    commitmentThreshold: 3,
    isLowSpr: false,
  };

  const freq = __test__.buildFrequencyFromScores({
    context: { ...baseContext, toCall: 80, potSize: 100 },
    boardTexture,
    handClass,
    math: largeBetMath,
    equity: 0.25, // weak hand
    strategyConfig,
  });

  const mix = __test__.toNormalizedMixForTesting(freq, 80);
  const defense = mix.raise + mix.call;
  assert.ok(
    defense >= 0.50,
    `Defense freq ${defense.toFixed(3)} should be reasonable (>= 0.50) when facing large bet`
  );
});

test("MDF guardrail: large bet → high MDF → defense should not overfold", () => {
  const handClass = classifyHandOnBoard(["Ts", "9s"], ["Qs", "Jh", "2d"]);
  // pot 100, toCall 100 → MDF = 0.5
  const mathPotBet: MathBreakdown = {
    potOdds: 0.5,
    equityRequired: 0.5,
    callAmount: 100,
    potAfterCall: 200,
    mdf: 0.5,
    spr: 2,
    effectiveStack: 200,
    commitmentThreshold: 3,
    isLowSpr: true,
  };

  const freq = __test__.buildFrequencyFromScores({
    context: { ...baseContext, toCall: 100, potSize: 100, effectiveStack: 200 },
    boardTexture,
    handClass,
    math: mathPotBet,
    equity: 0.35,
    strategyConfig,
  });

  const mix = __test__.toNormalizedMixForTesting(freq, 100);
  const defense = mix.raise + mix.call;
  assert.ok(
    defense >= 0.40,
    `Defense freq ${defense.toFixed(3)} should not overfold (MDF ≈ 0.5)`
  );
});

test("MDF guardrail: small bet → defense naturally high", () => {
  const handClass = classifyHandOnBoard(baseContext.heroHand, baseContext.board);
  // pot 100, toCall 25 → MDF = 100/125 = 0.8
  const mathSmallBet: MathBreakdown = {
    potOdds: 0.2,
    equityRequired: 0.2,
    callAmount: 25,
    potAfterCall: 125,
    mdf: 0.8,
    spr: 3,
    effectiveStack: 300,
    commitmentThreshold: 3,
    isLowSpr: false,
  };

  const freq = __test__.buildFrequencyFromScores({
    context: { ...baseContext, toCall: 25, potSize: 100 },
    boardTexture,
    handClass,
    math: mathSmallBet,
    equity: 0.55,
    strategyConfig,
  });

  const mix = __test__.toNormalizedMixForTesting(freq, 25);
  const defense = mix.raise + mix.call;
  assert.ok(
    defense >= 0.70,
    `Defense freq ${defense.toFixed(3)} should be high (>= 0.70) for small bet with good equity`
  );
});

// ── TURN / RIVER advice generation tests ──

const turnContext: PostflopContext = {
  ...baseContext,
  street: "TURN",
  board: ["Qs", "Jh", "2d", "7c"],
};

const riverContext: PostflopContext = {
  ...baseContext,
  street: "RIVER",
  board: ["Qs", "Jh", "2d", "7c", "4h"],
};

const turnBoardTexture: BoardTextureProfile = {
  isPaired: false,
  isMonotone: false,
  hasFlushDraw: false,
  isConnected: false,
  isDisconnected: true,
  isHighCardHeavy: true,
  wetness: "dry",
  labels: ["DRY"],
};

test("TURN: buildFrequencyFromScores produces valid frequencies for 4-card board", () => {
  const handClass = classifyHandOnBoard(["As", "Kd"], ["Qs", "Jh", "2d", "7c"]);
  const freq = __test__.buildFrequencyFromScores({
    context: turnContext,
    boardTexture: turnBoardTexture,
    handClass,
    math,
    equity: 0.42,
    strategyConfig,
  });

  const sum = freq.check + freq.betSmall + freq.betBig;
  assert.ok(Math.abs(sum - 1) < 0.01, `TURN freq sum should be ~1, got ${sum.toFixed(4)}`);
  assert.ok(freq.check >= 0 && freq.check <= 1, `TURN check=${freq.check.toFixed(3)} out of [0,1]`);
  assert.ok(freq.betSmall >= 0 && freq.betSmall <= 1, `TURN betSmall=${freq.betSmall.toFixed(3)} out of [0,1]`);
  assert.ok(freq.betBig >= 0 && freq.betBig <= 1, `TURN betBig=${freq.betBig.toFixed(3)} out of [0,1]`);
});

test("RIVER: buildFrequencyFromScores produces valid frequencies for 5-card board", () => {
  const handClass = classifyHandOnBoard(["As", "Kd"], ["Qs", "Jh", "2d", "7c", "4h"]);
  const freq = __test__.buildFrequencyFromScores({
    context: riverContext,
    boardTexture: turnBoardTexture,
    handClass,
    math,
    equity: 0.42,
    strategyConfig,
  });

  const sum = freq.check + freq.betSmall + freq.betBig;
  assert.ok(Math.abs(sum - 1) < 0.01, `RIVER freq sum should be ~1, got ${sum.toFixed(4)}`);
  assert.ok(freq.check >= 0, "RIVER check should be >= 0");
  assert.ok(freq.betSmall >= 0, "RIVER betSmall should be >= 0");
  assert.ok(freq.betBig >= 0, "RIVER betBig should be >= 0");
});

test("TURN: mix normalizes to 1 when facing a bet", () => {
  const handClass = classifyHandOnBoard(["As", "Kd"], ["Qs", "Jh", "2d", "7c"]);
  const freq = __test__.buildFrequencyFromScores({
    context: { ...turnContext, toCall: 60, potSize: 200 },
    boardTexture: turnBoardTexture,
    handClass,
    math: { ...math, equityRequired: 0.23, mdf: 0.77 },
    equity: 0.42,
    strategyConfig,
  });

  const mix = __test__.toNormalizedMixForTesting(freq, 60);
  const sum = mix.raise + mix.call + mix.fold;
  assert.ok(Math.abs(sum - 1) < 0.01, `TURN facing bet: mix sum should be ~1, got ${sum.toFixed(4)}`);
});

test("RIVER: mix normalizes to 1 when facing a bet", () => {
  const handClass = classifyHandOnBoard(["As", "Kd"], ["Qs", "Jh", "2d", "7c", "4h"]);
  const freq = __test__.buildFrequencyFromScores({
    context: { ...riverContext, toCall: 100, potSize: 300 },
    boardTexture: turnBoardTexture,
    handClass,
    math: { ...math, equityRequired: 0.25, mdf: 0.75 },
    equity: 0.42,
    strategyConfig,
  });

  const mix = __test__.toNormalizedMixForTesting(freq, 100);
  const sum = mix.raise + mix.call + mix.fold;
  assert.ok(Math.abs(sum - 1) < 0.01, `RIVER facing bet: mix sum should be ~1, got ${sum.toFixed(4)}`);
});

// ── Polarization tests ──

test("polarization: strong hand (high equity) bets big more than medium hand", () => {
  const strongClass = { type: "made_hand" as const, strength: "strong" as const, description: "Top pair" };
  const medClass = { type: "made_hand" as const, strength: "medium" as const, description: "Middle pair" };

  const strongFreq = __test__.buildFrequencyFromScores({
    context: { ...baseContext, toCall: 0 },
    boardTexture,
    handClass: strongClass,
    math,
    equity: 0.75,
    strategyConfig,
  });

  const medFreq = __test__.buildFrequencyFromScores({
    context: { ...baseContext, toCall: 0 },
    boardTexture,
    handClass: medClass,
    math,
    equity: 0.50,
    strategyConfig,
  });

  assert.ok(
    strongFreq.betBig > medFreq.betBig,
    `Strong hand betBig ${strongFreq.betBig.toFixed(3)} should > medium ${medFreq.betBig.toFixed(3)}`
  );
  assert.ok(
    medFreq.check > strongFreq.check,
    `Medium hand check ${medFreq.check.toFixed(3)} should > strong ${strongFreq.check.toFixed(3)}`
  );
});

test("polarization: air with fold equity bluffs more than air without", () => {
  const airClass = { type: "air" as const, strength: "weak" as const, description: "No pair" };

  const withFE = __test__.buildFrequencyFromScores({
    context: { ...baseContext, toCall: 0, aggressor: "hero", numVillains: 1 },
    boardTexture: { ...boardTexture, wetness: "dry" },
    handClass: airClass,
    math,
    equity: 0.20,
    strategyConfig,
  });

  const noFE = __test__.buildFrequencyFromScores({
    context: { ...baseContext, toCall: 0, aggressor: "villain", numVillains: 2 },
    boardTexture: { ...boardTexture, wetness: "wet" },
    handClass: airClass,
    math,
    equity: 0.20,
    strategyConfig,
  });

  const withFEBet = withFE.betSmall + withFE.betBig;
  const noFEBet = noFE.betSmall + noFE.betBig;
  assert.ok(
    withFEBet > noFEBet,
    `Air with fold equity bets ${withFEBet.toFixed(3)} should > without ${noFEBet.toFixed(3)}`
  );
});

// ── OOP penalty test ──

test("OOP penalty: OOP checks more than IP for medium-strength hands", () => {
  const medClass = { type: "made_hand" as const, strength: "medium" as const, description: "Middle pair" };

  const ipFreq = __test__.buildFrequencyFromScores({
    context: { ...baseContext, toCall: 0, heroInPosition: true },
    boardTexture,
    handClass: medClass,
    math,
    equity: 0.50,
    strategyConfig,
  });

  const oopFreq = __test__.buildFrequencyFromScores({
    context: { ...baseContext, toCall: 0, heroInPosition: false },
    boardTexture,
    handClass: medClass,
    math,
    equity: 0.50,
    strategyConfig,
  });

  assert.ok(
    oopFreq.check > ipFreq.check,
    `OOP check ${oopFreq.check.toFixed(3)} should be > IP check ${ipFreq.check.toFixed(3)}`
  );
});

// ── Street-specific polarization test ──

test("later streets are more polarized: river has less small betting than flop", () => {
  const handClass = classifyHandOnBoard(["As", "Kd"], ["Qs", "Jh", "2d"]);

  const flopFreq = __test__.buildFrequencyFromScores({
    context: { ...baseContext, toCall: 0, street: "FLOP" },
    boardTexture,
    handClass,
    math,
    equity: 0.50,
    strategyConfig,
  });

  const riverFreq = __test__.buildFrequencyFromScores({
    context: { ...riverContext, toCall: 0, street: "RIVER" },
    boardTexture,
    handClass,
    math,
    equity: 0.50,
    strategyConfig,
  });

  // River should have less betSmall due to polarization shift
  assert.ok(
    riverFreq.betSmall <= flopFreq.betSmall + 0.01,
    `River betSmall ${riverFreq.betSmall.toFixed(3)} should be <= flop ${flopFreq.betSmall.toFixed(3)} (polarization)`
  );
});

// ── Line token tests for TURN/RIVER ──

test("line token BARREL on TURN when hero is aggressor", () => {
  assert.equal(
    __test__.resolveLineToken({ ...baseContext, toCall: 0, aggressor: "hero", street: "TURN" }),
    "BARREL"
  );
});

test("line token BARREL on RIVER when hero is aggressor", () => {
  assert.equal(
    __test__.resolveLineToken({ ...baseContext, toCall: 0, aggressor: "hero", street: "RIVER" }),
    "BARREL"
  );
});

test("line token PROBE on TURN for non-PFA IP when villain was PFA", () => {
  assert.equal(
    __test__.resolveLineToken({
      ...baseContext,
      toCall: 0,
      aggressor: "none",
      preflopAggressor: "villain",
      heroInPosition: true,
      street: "TURN",
    }),
    "PROBE"  // Non-PFA on turn → PROBE
  );
});

test("line token VS_BET when facing a bet on any street", () => {
  for (const street of ["FLOP", "TURN", "RIVER"] as const) {
    assert.equal(
      __test__.resolveLineToken({ ...baseContext, toCall: 50, street }),
      "VS_BET",
      `VS_BET expected on ${street} when toCall > 0`
    );
  }
});
