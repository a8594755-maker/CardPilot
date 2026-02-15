import type { MathBreakdown } from "@cardpilot/shared-types";

const EPSILON = 1e-9;

export interface PotOddsResult {
  callAmount: number;
  potSize: number;
  potAfterCall: number;
  potOdds: number;
  equityRequired: number;
}

export interface MdfResult {
  potBeforeBet: number;
  betSize: number;
  mdf: number;
}

export interface SprResult {
  effectiveStack: number;
  potSize: number;
  spr: number;
  commitmentThreshold: number;
  isLowSpr: boolean;
}

export class MathEngine {
  static calculatePotOdds(potSize: number, toCall: number): PotOddsResult {
    const safePot = Math.max(0, potSize);
    const safeCall = Math.max(0, toCall);
    const potAfterCall = safePot + safeCall;
    const potOdds = potAfterCall > EPSILON ? safeCall / potAfterCall : 0;

    return {
      callAmount: round4(safeCall),
      potSize: round4(safePot),
      potAfterCall: round4(potAfterCall),
      potOdds: round4(potOdds),
      equityRequired: round4(potOdds)
    };
  }

  static calculateMDF(potBeforeBet: number, betSize: number): MdfResult {
    const safePot = Math.max(0, potBeforeBet);
    const safeBet = Math.max(0, betSize);
    const denominator = safePot + safeBet;
    const mdf = denominator > EPSILON ? safePot / denominator : 1;

    return {
      potBeforeBet: round4(safePot),
      betSize: round4(safeBet),
      mdf: round4(clamp01(mdf))
    };
  }

  static calculateSPR(
    effectiveStack: number,
    potSize: number,
    commitmentThreshold = 3
  ): SprResult {
    const safeStack = Math.max(0, effectiveStack);
    const safePot = Math.max(EPSILON, potSize);
    const spr = safeStack / safePot;

    return {
      effectiveStack: round4(safeStack),
      potSize: round4(Math.max(0, potSize)),
      spr: round4(spr),
      commitmentThreshold,
      isLowSpr: spr < commitmentThreshold
    };
  }

  static buildMathBreakdown(params: {
    potSize: number;
    toCall: number;
    effectiveStack: number;
    commitmentThreshold?: number;
  }): MathBreakdown {
    const potOdds = this.calculatePotOdds(params.potSize, params.toCall);
    const potBeforeBet = Math.max(0, params.potSize - params.toCall);
    const mdfResult = params.toCall > 0
      ? this.calculateMDF(potBeforeBet, params.toCall)
      : undefined;
    const spr = this.calculateSPR(
      params.effectiveStack,
      params.potSize,
      params.commitmentThreshold ?? 3
    );

    return {
      potOdds: potOdds.potOdds,
      equityRequired: potOdds.equityRequired,
      callAmount: potOdds.callAmount,
      potAfterCall: potOdds.potAfterCall,
      mdf: mdfResult?.mdf,
      spr: spr.spr,
      effectiveStack: spr.effectiveStack,
      commitmentThreshold: spr.commitmentThreshold,
      isLowSpr: spr.isLowSpr
    };
  }
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function round4(value: number): number {
  return Math.round(value * 10_000) / 10_000;
}
