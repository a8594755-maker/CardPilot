import type { BotProfile, RaiseSizingContext } from './types.js';
import { PERSONA_ANCHORS } from './persona.js';
import { DEFAULT_MISTAKE_CONFIGS } from './mistake-budget.js';

// ===== Helper: clamp value to [min, max] =====
function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v));
}

// ===== (1) GTO Balanced =====
const gtoBalanced: BotProfile = {
  id: 'gto_balanced',
  displayName: 'GTO Balanced',
  actionWeights: { raise: 1.0, call: 1.0, fold: 1.0 },
  unopenedLimpShare: 0,
  stochastic: true,
  personaAnchors: PERSONA_ANCHORS['gto_balanced'],
  mistakeConfig: DEFAULT_MISTAKE_CONFIGS['gto_balanced'],
  chooseRaiseTo(ctx: RaiseSizingContext): number {
    if (ctx.street === 'preflop') {
      const target = Math.round(2.5 * ctx.bigBlind);
      return clamp(target, ctx.minRaiseTo, ctx.maxRaiseTo);
    }
    const betSize = Math.round(ctx.pot * 0.5);
    const raiseTo = ctx.toCall + betSize;
    return clamp(raiseTo, ctx.minRaiseTo, ctx.maxRaiseTo);
  },
};

// ===== (2) Limp-Fish =====
const limpFish: BotProfile = {
  id: 'limp_fish',
  displayName: 'Limp-Fish (more limping/calling)',
  actionWeights: { raise: 0.75, call: 1.6, fold: 1.1 },
  unopenedLimpShare: 0.45,
  stochastic: true,
  personaAnchors: PERSONA_ANCHORS['limp_fish'],
  mistakeConfig: DEFAULT_MISTAKE_CONFIGS['limp_fish'],
  chooseRaiseTo(ctx: RaiseSizingContext): number {
    if (ctx.street === 'preflop') {
      const target = Math.round(2.1 * ctx.bigBlind);
      return clamp(target, ctx.minRaiseTo, ctx.maxRaiseTo);
    }
    const betSize = Math.round(ctx.pot * 0.33);
    const raiseTo = ctx.toCall + betSize;
    return clamp(raiseTo, ctx.minRaiseTo, ctx.maxRaiseTo);
  },
};

// ===== (3) TAG (tight-aggressive) =====
const tag: BotProfile = {
  id: 'tag',
  displayName: 'TAG (tight-aggressive)',
  actionWeights: { raise: 1.35, call: 0.85, fold: 1.15 },
  unopenedLimpShare: 0,
  stochastic: false,
  personaAnchors: PERSONA_ANCHORS['tag'],
  mistakeConfig: DEFAULT_MISTAKE_CONFIGS['tag'],
  chooseRaiseTo(ctx: RaiseSizingContext): number {
    if (ctx.street === 'preflop') {
      const target = Math.round(2.7 * ctx.bigBlind);
      return clamp(target, ctx.minRaiseTo, ctx.maxRaiseTo);
    }
    const betSize = Math.round(ctx.pot * 0.55);
    const raiseTo = ctx.toCall + betSize;
    return clamp(raiseTo, ctx.minRaiseTo, ctx.maxRaiseTo);
  },
};

// ===== (4) LAG (loose-aggressive / pressure) =====
const lag: BotProfile = {
  id: 'lag',
  displayName: 'LAG (loose-aggressive / pressure)',
  actionWeights: { raise: 1.75, call: 1.05, fold: 0.8 },
  unopenedLimpShare: 0.1,
  stochastic: true,
  personaAnchors: PERSONA_ANCHORS['lag'],
  mistakeConfig: DEFAULT_MISTAKE_CONFIGS['lag'],
  chooseRaiseTo(ctx: RaiseSizingContext): number {
    if (ctx.street === 'preflop') {
      const target = Math.round(3.2 * ctx.bigBlind);
      return clamp(target, ctx.minRaiseTo, ctx.maxRaiseTo);
    }
    const betSize = Math.round(ctx.pot * 0.75);
    const raiseTo = ctx.toCall + betSize;
    return clamp(raiseTo, ctx.minRaiseTo, ctx.maxRaiseTo);
  },
};

// ===== (5) Nit (very tight / risk-averse) =====
const nit: BotProfile = {
  id: 'nit',
  displayName: 'Nit (very tight / risk-averse)',
  actionWeights: { raise: 0.9, call: 0.7, fold: 1.6 },
  unopenedLimpShare: 0,
  stochastic: false,
  personaAnchors: PERSONA_ANCHORS['nit'],
  mistakeConfig: DEFAULT_MISTAKE_CONFIGS['nit'],
  chooseRaiseTo(ctx: RaiseSizingContext): number {
    if (ctx.street === 'preflop') {
      const target = Math.round(2.2 * ctx.bigBlind);
      return clamp(target, ctx.minRaiseTo, ctx.maxRaiseTo);
    }
    const betSize = Math.round(ctx.pot * 0.29);
    const raiseTo = ctx.toCall + betSize;
    return clamp(raiseTo, ctx.minRaiseTo, ctx.maxRaiseTo);
  },
};

// ===== (6) Postflop Trainer (very loose preflop — designed to generate postflop data) =====
const postflopTrainer: BotProfile = {
  id: 'postflop_trainer',
  displayName: 'Postflop Trainer (loose caller)',
  actionWeights: { raise: 0.8, call: 1.8, fold: 0.45 },
  unopenedLimpShare: 0.55,
  stochastic: true,
  personaAnchors: PERSONA_ANCHORS['postflop_trainer'],
  mistakeConfig: DEFAULT_MISTAKE_CONFIGS['postflop_trainer'],
  chooseRaiseTo(ctx: RaiseSizingContext): number {
    if (ctx.street === 'preflop') {
      // Smaller raises preflop → more callers → more multiway flops
      const target = Math.round(2.2 * ctx.bigBlind);
      return clamp(target, ctx.minRaiseTo, ctx.maxRaiseTo);
    }
    const betSize = Math.round(ctx.pot * 0.45);
    const raiseTo = ctx.toCall + betSize;
    return clamp(raiseTo, ctx.minRaiseTo, ctx.maxRaiseTo);
  },
};

// ===== Registry =====
export const PROFILES: Record<string, BotProfile> = {
  gto_balanced: gtoBalanced,
  limp_fish: limpFish,
  tag,
  lag,
  nit,
  postflop_trainer: postflopTrainer,
};

export function getProfile(id: string): BotProfile {
  const p = PROFILES[id];
  if (!p) {
    const available = Object.keys(PROFILES).join(', ');
    throw new Error(`Unknown profile "${id}". Available: ${available}`);
  }
  return p;
}
