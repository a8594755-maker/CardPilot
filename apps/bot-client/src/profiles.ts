import type { BotProfile, RaiseSizingContext } from './types.js';

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
  chooseRaiseTo(ctx: RaiseSizingContext): number {
    if (ctx.street === 'preflop') {
      // Standard open ~2.5bb
      const target = Math.round(2.5 * ctx.bigBlind);
      return clamp(target, ctx.minRaiseTo, ctx.maxRaiseTo);
    }
    // Postflop: ~50% pot sizing
    const betSize = Math.round(ctx.pot * 0.50);
    const raiseTo = ctx.toCall + betSize;
    return clamp(raiseTo, ctx.minRaiseTo, ctx.maxRaiseTo);
  },
};

// ===== (2) Limp-Fish =====
const limpFish: BotProfile = {
  id: 'limp_fish',
  displayName: 'Limp-Fish (more limping/calling)',
  actionWeights: { raise: 0.75, call: 1.60, fold: 1.10 },
  unopenedLimpShare: 0.45,
  stochastic: true,
  chooseRaiseTo(ctx: RaiseSizingContext): number {
    if (ctx.street === 'preflop') {
      // Small raises near minRaiseTo (~2.1bb)
      const target = Math.round(2.1 * ctx.bigBlind);
      return clamp(target, ctx.minRaiseTo, ctx.maxRaiseTo);
    }
    // Postflop: smaller sizing ~33% pot
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
  chooseRaiseTo(ctx: RaiseSizingContext): number {
    if (ctx.street === 'preflop') {
      // ~2.7bb
      const target = Math.round(2.7 * ctx.bigBlind);
      return clamp(target, ctx.minRaiseTo, ctx.maxRaiseTo);
    }
    // Postflop: ~55% pot
    const betSize = Math.round(ctx.pot * 0.55);
    const raiseTo = ctx.toCall + betSize;
    return clamp(raiseTo, ctx.minRaiseTo, ctx.maxRaiseTo);
  },
};

// ===== (4) LAG (loose-aggressive / pressure) =====
const lag: BotProfile = {
  id: 'lag',
  displayName: 'LAG (loose-aggressive / pressure)',
  actionWeights: { raise: 1.75, call: 1.05, fold: 0.80 },
  unopenedLimpShare: 0.10,
  stochastic: true,
  chooseRaiseTo(ctx: RaiseSizingContext): number {
    if (ctx.street === 'preflop') {
      // Larger opens ~3.2bb
      const target = Math.round(3.2 * ctx.bigBlind);
      return clamp(target, ctx.minRaiseTo, ctx.maxRaiseTo);
    }
    // Postflop: ~75% pot (more pressure)
    const betSize = Math.round(ctx.pot * 0.75);
    const raiseTo = ctx.toCall + betSize;
    return clamp(raiseTo, ctx.minRaiseTo, ctx.maxRaiseTo);
  },
};

// ===== (5) Nit (very tight / risk-averse) =====
const nit: BotProfile = {
  id: 'nit',
  displayName: 'Nit (very tight / risk-averse)',
  actionWeights: { raise: 0.90, call: 0.70, fold: 1.60 },
  unopenedLimpShare: 0,
  stochastic: false,
  chooseRaiseTo(ctx: RaiseSizingContext): number {
    if (ctx.street === 'preflop') {
      // Smaller ~2.2bb
      const target = Math.round(2.2 * ctx.bigBlind);
      return clamp(target, ctx.minRaiseTo, ctx.maxRaiseTo);
    }
    // Postflop: ~25-33% pot (use 29% as midpoint)
    const betSize = Math.round(ctx.pot * 0.29);
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
};

export function getProfile(id: string): BotProfile {
  const p = PROFILES[id];
  if (!p) {
    const available = Object.keys(PROFILES).join(', ');
    throw new Error(`Unknown profile "${id}". Available: ${available}`);
  }
  return p;
}
