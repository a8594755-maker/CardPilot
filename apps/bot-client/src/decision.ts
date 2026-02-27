import type {
  BotProfile,
  Mix,
  StrategyMix,
  LegalActions,
  TableState,
  PlayerActionType,
  DecisionResult,
} from './types.js';
import type { AdaptiveAdjustments } from './session-stats.js';
import type { BotPersona } from './persona.js';
import type { MoodState } from './mood.js';
import type { OpponentAdjustment } from './opponent-model.js';
import type { RaiseContext } from './raise-context.js';
import type { BoardTexture } from './board-integration.js';
import { encodeFeatures, encodeFeaturesV2, type MLP } from '@cardpilot/fast-model';
import { applyPersona } from './persona.js';
import { getMoodMultipliers } from './mood.js';
import { analyzeRaiseContext } from './raise-context.js';
import { getBoardTexture, computeBoardTextureAdjustment, detectAggressor } from './board-integration.js';
import { chooseSizing } from './sizing.js';
import { shouldInjectMistake, injectMistake } from './mistake-budget.js';
import { createEmptyTrace, type DecisionTrace } from './trace-logger.js';
import { estimateEquity } from './monte-carlo.js';

// ===== Normalize mix so sum = 1 =====
function normalize(m: Mix): Mix {
  const sum = m.raise + m.call + m.fold;
  if (sum <= 0) return { raise: 0, call: 0, fold: 1 };
  return { raise: m.raise / sum, call: m.call / sum, fold: m.fold / sum };
}

// ===== Apply personality weights to base mix =====
function applyWeights(base: Mix, weights: Mix): Mix {
  return {
    raise: base.raise * weights.raise,
    call: base.call * weights.call,
    fold: base.fold * weights.fold,
  };
}

// ===== Apply multiplier adjustments =====
function applyMultipliers(m: Mix, adj: { raise: number; call: number; fold: number }): Mix {
  return {
    raise: m.raise * adj.raise,
    call: m.call * adj.call,
    fold: m.fold * adj.fold,
  };
}

// ===== Apply preflop limp share =====
function applyLimpShare(m: Mix, limpShare: number): Mix {
  const shift = m.raise * limpShare;
  return {
    raise: m.raise - shift,
    call: m.call + shift,
    fold: m.fold,
  };
}

// ===== Sample action from mix =====
function sampleAction(m: Mix): 'raise' | 'call' | 'fold' {
  const r = Math.random();
  if (r < m.raise) return 'raise';
  if (r < m.raise + m.call) return 'call';
  return 'fold';
}

// ===== Pick highest probability action =====
function pickMaxAction(m: Mix): 'raise' | 'call' | 'fold' {
  if (m.raise >= m.call && m.raise >= m.fold) return 'raise';
  if (m.call >= m.fold) return 'call';
  return 'fold';
}

// ===== Resolve legality =====
function resolveWithLegality(
  action: 'raise' | 'call' | 'fold',
  legal: LegalActions,
): PlayerActionType {
  if (action === 'fold') {
    if (legal.canCheck) return 'check';
    return 'fold';
  }
  if (action === 'call') {
    if (legal.canCall) return 'call';
    if (legal.canCheck) return 'check';
    return 'fold';
  }
  // action === 'raise'
  if (legal.canRaise) return 'raise';
  if (legal.canCall) return 'call';
  if (legal.canCheck) return 'check';
  return 'fold';
}

// ===== Detect if preflop is "unopened" =====
function isUnopened(state: TableState): boolean {
  if (state.street !== 'PREFLOP') return false;
  const la = state.legalActions;
  if (!la) return false;
  return la.callAmount === 0;
}

// ===== Hero position awareness =====
type PositionGroup = 'ip' | 'oop' | 'bb' | 'unknown';

function classifyPosition(pos: string | undefined): PositionGroup {
  if (!pos) return 'unknown';
  if (pos === 'BTN' || pos === 'CO') return 'ip';
  if (pos === 'BB') return 'bb';
  return 'oop'; // UTG, HJ, SB, MP, etc.
}

function getPositionAdjustment(
  group: PositionGroup,
  street: string,
  unopened: boolean,
): { raise: number; call: number; fold: number } {
  const postflop = street !== 'PREFLOP';

  switch (group) {
    case 'ip':
      return postflop
        ? { raise: 1.20, call: 1.10, fold: 0.80 }
        : { raise: 1.15, call: 1.05, fold: 0.88 };
    case 'oop':
      return postflop
        ? { raise: 0.85, call: 0.90, fold: 1.15 }
        : { raise: 0.90, call: 0.95, fold: 1.10 };
    case 'bb':
      if (!postflop && !unopened) {
        // BB facing a raise: defend wider (pot odds from blind already invested)
        return { raise: 1.0, call: 1.25, fold: 0.80 };
      }
      return postflop
        ? { raise: 0.90, call: 0.95, fold: 1.10 }
        : { raise: 1.0, call: 1.05, fold: 0.95 };
    default:
      return { raise: 1.0, call: 1.0, fold: 1.0 };
  }
}

// ===== Map street string to lowercase =====
function mapStreet(s: string): 'preflop' | 'flop' | 'turn' | 'river' {
  const low = s.toLowerCase();
  if (low === 'preflop') return 'preflop';
  if (low === 'flop') return 'flop';
  if (low === 'turn') return 'turn';
  return 'river';
}

// ===== Copy mix for trace snapshots =====
function copyMix(m: Mix): Mix {
  return { raise: m.raise, call: m.call, fold: m.fold };
}

// ===== Quick hand strength evaluator (self-contained, no external deps) =====

const RANK_VALUES: Record<string, number> = {
  'A': 14, 'K': 13, 'Q': 12, 'J': 11, 'T': 10,
  '9': 9, '8': 8, '7': 7, '6': 6, '5': 5, '4': 4, '3': 3, '2': 2,
};

function rankValue(r: string): number {
  return RANK_VALUES[r] ?? 0;
}

/**
 * Quick hand strength score (0-1) for fallback decisions.
 * Preflop: rank-based heuristic.
 * Postflop: simplified made-hand classification.
 */
export function quickHandStrength(
  holeCards: [string, string],
  board: string[],
  street: string,
): number {
  const r1 = rankValue(holeCards[0][0]);
  const r2 = rankValue(holeCards[1][0]);
  const suited = holeCards[0][1] === holeCards[1][1];
  const paired = holeCards[0][0] === holeCards[1][0];

  if (street === 'PREFLOP' || board.length === 0) {
    let score = 0;
    if (paired) {
      score = 0.5 + (Math.max(r1, r2) / 14) * 0.5;
    } else {
      const high = Math.max(r1, r2);
      const low = Math.min(r1, r2);
      const gap = high - low;
      // Weight high card heavily — prevents medium connectors (T9, 98) from scoring as monsters
      score = (high / 14) * 0.55 + (low / 14) * 0.15;
      if (suited) score += 0.06;
      if (gap <= 2) score += 0.03;
      if (gap >= 5) score -= 0.04;
    }
    return Math.max(0, Math.min(1, score));
  }

  // Postflop: check for made hands
  const boardRanks = board.map(c => c[0]);
  const boardSuits = board.map(c => c[1]);
  const heroR1 = holeCards[0][0];
  const heroR2 = holeCards[1][0];
  const heroS1 = holeCards[0][1];
  const heroS2 = holeCards[1][1];

  const r1Matches = boardRanks.filter(r => r === heroR1).length;
  const r2Matches = boardRanks.filter(r => r === heroR2).length;

  // Set (pocket pair + one on board)
  if (paired && r1Matches >= 1) return 0.95;

  // Quads
  if (r1Matches >= 3 || r2Matches >= 3) return 0.98;

  // Trips
  if (r1Matches >= 2) return 0.88;
  if (r2Matches >= 2) return 0.88;

  // Two pair
  if (r1Matches >= 1 && r2Matches >= 1) return 0.80;

  // Overpair / underpair
  if (paired) {
    const maxBoardRank = Math.max(...boardRanks.map(r => rankValue(r)));
    if (r1 > maxBoardRank) return 0.72;
    return 0.55;
  }

  // One pair with board
  if (r1Matches >= 1 || r2Matches >= 1) {
    const matchRank = r1Matches >= 1 ? heroR1 : heroR2;
    const sortedBoardRanks = [...boardRanks].sort((a, b) => rankValue(b) - rankValue(a));
    if (matchRank === sortedBoardRanks[0]) {
      const kicker = r1Matches >= 1 ? heroR2 : heroR1;
      const kickerVal = rankValue(kicker);
      return 0.55 + (kickerVal / 14) * 0.15;
    }
    if (sortedBoardRanks.length >= 2 && matchRank === sortedBoardRanks[1]) {
      return 0.45;
    }
    return 0.38;
  }

  // Flush draw check
  const s1BoardCount = boardSuits.filter(s => s === heroS1).length;
  const s2BoardCount = boardSuits.filter(s => s === heroS2).length;
  if (s1BoardCount >= 2 || s2BoardCount >= 2) {
    if (suited && s1BoardCount >= 2) return 0.40;
    return 0.35;
  }

  // Straight draw
  const allRankValues = [r1, r2, ...boardRanks.map(r => rankValue(r))];
  const uniqueRanks = [...new Set(allRankValues)].sort((a, b) => a - b);
  let maxConsecutive = 1;
  let consecutive = 1;
  for (let i = 1; i < uniqueRanks.length; i++) {
    if (uniqueRanks[i] - uniqueRanks[i - 1] === 1) {
      consecutive++;
      maxConsecutive = Math.max(maxConsecutive, consecutive);
    } else {
      consecutive = 1;
    }
  }
  if (maxConsecutive >= 4) return 0.32;
  if (maxConsecutive >= 3) return 0.25;

  // High card
  const high = Math.max(r1, r2);
  return 0.08 + (high / 14) * 0.15;
}

// ===== Hand-strength-aware fallback policy (enhanced with raise context + position) =====
function fallbackMix(
  state: TableState,
  profile: BotProfile,
  holeCards: [string, string] | null,
  mySeat: number,
  raiseContext: RaiseContext,
  mcEquity?: number,
): Mix {
  const la = state.legalActions;
  if (!la) return { raise: 0, call: 0, fold: 1 };

  const toCall = la.callAmount;
  const bb = state.bigBlind || 1;
  const unopened = isUnopened(state);

  // Compute raw mix from hand strength + raise context
  let rawMix = computeRawFallbackMix(la, toCall, bb, holeCards, state, profile, raiseContext, mcEquity);

  // Apply hero position adjustment
  const heroPos = state.positions[mySeat];
  const posGroup = classifyPosition(heroPos);
  const posAdj = getPositionAdjustment(posGroup, state.street, unopened);
  rawMix = applyMultipliers(rawMix, posAdj);

  return rawMix;
}

function computeRawFallbackMix(
  la: LegalActions,
  toCall: number,
  bb: number,
  holeCards: [string, string] | null,
  state: TableState,
  profile: BotProfile,
  raiseContext: RaiseContext,
  mcEquity?: number,
): Mix {
  // If can check → decide between check and bet/raise based on hand strength
  // fold resolves to check via resolveWithLegality when canCheck is true
  if (la.canCheck) {
    if (!la.canRaise) {
      // Can only check
      return { raise: 0, call: 0, fold: 1 };
    }

    const str = mcEquity ?? (holeCards ? quickHandStrength(holeCards, state.board, state.street) : 0.5);
    const aggressive = profile.actionWeights.raise > 1.2;

    let raiseChance: number;
    if (state.street === 'PREFLOP') {
      // Preflop unopened: prefer raising (opening) over limping
      if (str >= 0.65) {
        raiseChance = aggressive ? 0.80 : 0.65;
      } else if (str >= 0.50) {
        raiseChance = aggressive ? 0.55 : 0.40;
      } else if (str >= 0.35) {
        raiseChance = aggressive ? 0.30 : 0.15;
      } else {
        raiseChance = aggressive ? 0.12 : 0.05;
      }
    } else {
      // Postflop: check vs bet based on hand strength
      if (str >= 0.75) {
        raiseChance = aggressive ? 0.75 : 0.60;
      } else if (str >= 0.55) {
        raiseChance = aggressive ? 0.40 : 0.25;
      } else if (str >= 0.35) {
        raiseChance = aggressive ? 0.20 : 0.10;
      } else {
        // Weak: mostly check, small bluff frequency
        raiseChance = aggressive ? 0.10 : 0.05;
      }
    }

    return { raise: raiseChance, call: 0, fold: 1 - raiseChance };
  }

  // If we don't know our cards, use generic heuristic
  if (!holeCards) {
    if (toCall <= 3 * bb) {
      const raiseChance = la.canRaise ? 0.08 : 0;
      return { raise: raiseChance, call: 0.72, fold: 0.20 };
    }
    return { raise: 0.03, call: 0.30, fold: 0.67 };
  }

  // Hand-strength-aware fallback — use MC equity when available (more accurate postflop)
  const strength = mcEquity ?? quickHandStrength(holeCards, state.board, state.street);
  const potOdds = toCall / (state.pot + toCall);

  // === Raise context adjustments ===
  const epRaiser = raiseContext.raiserPosition === 'UTG' || raiseContext.raiserPosition === 'UTG+1' || raiseContext.raiserPosition === 'MP';
  const lpRaiser = raiseContext.raiserPosition === 'BTN' || raiseContext.raiserPosition === 'CO';
  const facing3betPlus = raiseContext.facingType === 'facing_3bet' || raiseContext.facingType === 'facing_4bet_plus';
  const largeBet = raiseContext.raiseSizeCategory === 'large' || raiseContext.raiseSizeCategory === 'overbet' || raiseContext.raiseSizeCategory === 'allin';
  const isMultiway = raiseContext.isMultiway;
  const shortSPR = raiseContext.spr < 3;

  // Monster hands (set+, two pair+): raise-heavy
  if (strength >= 0.75) {
    let raiseChance = la.canRaise ? 0.65 : 0;
    const foldChance = 0;

    if (facing3betPlus) raiseChance *= 0.80;
    if (isMultiway && strength < 0.85) raiseChance *= 0.70;
    if (shortSPR) raiseChance = Math.min(raiseChance * 1.2, 0.85);

    return { raise: raiseChance, call: 1 - raiseChance - foldChance, fold: foldChance };
  }

  // Strong hands (overpair, top pair good kicker)
  if (strength >= 0.60) {
    let raiseChance = la.canRaise ? 0.35 : 0;
    let foldChance = 0.10;

    if (facing3betPlus) { raiseChance *= 0.60; foldChance += 0.10; }
    if (largeBet) foldChance += 0.08;
    if (epRaiser) foldChance += 0.05;
    if (lpRaiser) raiseChance *= 1.10;
    if (isMultiway) { raiseChance *= 0.70; foldChance += 0.05; }
    if (shortSPR) { raiseChance *= 1.15; foldChance *= 0.7; }

    return { raise: raiseChance, call: Math.max(0, 1 - raiseChance - foldChance), fold: foldChance };
  }

  // Decent hands (top pair, second pair)
  if (strength >= 0.45) {
    let raiseChance = la.canRaise ? 0.10 : 0;
    let foldChance = Math.max(0.05, potOdds * 0.8);

    if (facing3betPlus) { raiseChance = 0; foldChance += 0.20; }
    if (largeBet) foldChance *= 1.30;
    if (epRaiser) foldChance *= 1.15;
    if (lpRaiser) foldChance *= 0.90;
    if (isMultiway) { raiseChance = 0; foldChance += 0.10; }
    if (shortSPR) { foldChance += 0.15; raiseChance = 0; }

    foldChance = Math.min(foldChance, 0.80);
    return { raise: raiseChance, call: Math.max(0, 1 - raiseChance - foldChance), fold: foldChance };
  }

  // Drawing hands (flush draw, OESD)
  if (strength >= 0.30) {
    if (potOdds <= 0.35) {
      let raiseChance = 0.08;
      let foldChance = 0.35;
      if (isMultiway) { raiseChance = 0.03; foldChance = 0.30; }
      if (facing3betPlus) { raiseChance = 0; foldChance = 0.55; }
      if (largeBet) foldChance += 0.10;
      return { raise: raiseChance, call: Math.max(0, 1 - raiseChance - foldChance), fold: foldChance };
    }
    return { raise: 0.03, call: 0.27, fold: 0.70 };
  }

  // Weak hands
  if (toCall <= 2 * bb) {
    let foldChance = 0.63;
    if (facing3betPlus) foldChance = 0.85;
    if (largeBet) foldChance = 0.80;
    return { raise: 0.02, call: Math.max(0, 1 - 0.02 - foldChance), fold: foldChance };
  }
  let foldChance = 0.87;
  if (facing3betPlus) foldChance = 0.95;
  return { raise: 0.01, call: Math.max(0, 1 - 0.01 - foldChance), fold: foldChance };
}

// ===== Fast model prediction (imitation-learned middle layer) =====
function fastModelMix(
  model: MLP,
  state: TableState,
  holeCards: [string, string],
): Mix {
  const me = state.players.find(p => p.seat === state.actorSeat);
  const heroPosition = state.positions?.[state.actorSeat ?? 0] ?? 'BTN';
  const villains = state.players.filter(p => p.inHand && !p.folded && p.seat !== state.actorSeat);
  const numVillains = villains.length || 1;
  const heroInPosition = heroPosition === 'BTN' || heroPosition === 'CO';
  const heroRaisedPreflop = state.actions.some(
    a => a.seat === state.actorSeat && a.street === 'PREFLOP' && a.type === 'raise',
  );
  const effectiveStack = me
    ? Math.min(me.stack, ...villains.map(v => v.stack))
    : 100;

  const bb = state.bigBlind || 1;
  const callAmount = state.legalActions?.callAmount ?? 0;

  const features = model.isMultiHead
    ? encodeFeaturesV2(
        holeCards, state.board, state.street, state.pot, bb, callAmount,
        effectiveStack, heroPosition, heroInPosition, numVillains, heroRaisedPreflop,
        state.actions, state.players, state.actorSeat ?? 0,
      )
    : encodeFeatures(
        holeCards, state.board, state.street, state.pot, bb, callAmount,
        effectiveStack, heroPosition, heroInPosition, numVillains, heroRaisedPreflop,
      );

  return model.predict(features);
}

// ===== Decision context passed to decide() =====
export interface DecisionContext {
  state: TableState;
  profile: BotProfile;
  advice: StrategyMix | null;
  holeCards: [string, string] | null;
  mySeat: number;
  adaptiveAdj?: AdaptiveAdjustments;
  persona?: BotPersona;
  moodState?: MoodState;
  opponentAdj?: OpponentAdjustment;
  handNumber?: number;
  fastModel?: MLP | null;
}

// ===== Main decision function (enhanced pipeline) =====
export function decide(ctx: DecisionContext): DecisionResult {
  const {
    state, profile, advice, holeCards, mySeat,
    adaptiveAdj, persona, moodState, opponentAdj, handNumber,
    fastModel,
  } = ctx;

  const la = state.legalActions;
  if (!la) {
    return { action: 'fold', reasoning: 'no legalActions available' };
  }

  // Initialize trace
  const trace = createEmptyTrace();
  trace.handId = state.handId ?? '';
  trace.street = state.street;
  trace.holeCards = holeCards;
  trace.board = state.board;
  trace.pot = state.pot;
  trace.toCall = la.callAmount;
  trace.potOdds = la.callAmount / (state.pot + la.callAmount || 1);
  trace.position = state.positions[mySeat] ?? '';

  // Step 0: Compute context
  const raiseContext = analyzeRaiseContext(state, mySeat);
  trace.raiseContext = {
    facingType: raiseContext.facingType,
    raiserPosition: raiseContext.raiserPosition,
    raiseSizeBB: raiseContext.raiseSize,
    raiseSizeCategory: raiseContext.raiseSizeCategory,
    numCallers: raiseContext.numCallers,
    isMultiway: raiseContext.isMultiway,
    spr: raiseContext.spr,
  };

  const boardTexture = getBoardTexture(state.board);
  if (boardTexture) {
    trace.boardTexture = {
      category: boardTexture.category,
      wetness: boardTexture.wetness,
      isPaired: boardTexture.isPaired,
      hasFlushDraw: boardTexture.hasFlushDraw,
      highCard: boardTexture.highCard,
    };
  }

  const strength = holeCards ? quickHandStrength(holeCards, state.board, state.street) : null;
  trace.handStrength = strength;

  // Step 1: base mix — three-tier fallback
  //   1. Monte Carlo advice (strongest, slow)
  //   2. Learned fast model (fast, close to teacher)
  //   3. quickHandStrength heuristic (instant, basic) — now context-aware
  let baseMix: Mix;
  let source: string;
  if (advice) {
    baseMix = { raise: advice.raise, call: advice.call, fold: advice.fold };
    source = 'advice';
  } else if (fastModel && holeCards) {
    baseMix = fastModelMix(fastModel, state, holeCards);
    source = 'fast-model';
  } else {
    // Compute Monte Carlo equity for postflop fallback (guarded by env flag)
    let mcEquity: number | undefined;
    if (holeCards && state.board.length >= 3 && process.env['BOT_USE_MC'] === '1') {
      const numOpponents = state.players.filter(
        p => p.inHand && !p.folded && p.seat !== mySeat,
      ).length;
      if (numOpponents >= 1) {
        const mcResult = estimateEquity(holeCards, state.board, numOpponents, 500, 80);
        mcEquity = mcResult.equity;
      }
    }

    baseMix = fallbackMix(state, profile, holeCards, mySeat, raiseContext, mcEquity);
    source = mcEquity != null
      ? `fallback+MC(eq=${mcEquity.toFixed(2)})`
      : holeCards ? 'fallback+hand' : 'fallback';
  }
  trace.source = source;
  trace.baseMix = copyMix(baseMix);

  // Step 2a: apply personality weights
  let m = applyWeights(baseMix, profile.actionWeights);
  m = normalize(m);
  trace.afterWeights = copyMix(m);

  // Step 2b: apply persona
  if (persona) {
    const facingLargeBet = la.callAmount > state.pot * 0.5;
    m = applyPersona(m, persona, state.street, strength ?? undefined, facingLargeBet);
    trace.personaSeed = persona.seed;
    trace.personaMultipliers = {
      raise: persona.raiseMultiplier,
      call: persona.callMultiplier,
      fold: persona.foldMultiplier,
    };
  }
  trace.afterPersona = copyMix(m);

  // Step 2c: apply board texture adjustment (postflop only)
  if (boardTexture && state.street !== 'PREFLOP') {
    const isAggressor = detectAggressor(state.actions, mySeat, state.street);
    const btAdj = computeBoardTextureAdjustment(
      boardTexture, isAggressor, strength ?? 0.5, state.street,
    );
    m = applyMultipliers(m, { raise: btAdj.raiseAdj, call: btAdj.callAdj, fold: btAdj.foldAdj });
    m = normalize(m);
  }
  trace.afterBoardTexture = copyMix(m);

  // Step 2d: apply adaptive session adjustments
  if (adaptiveAdj) {
    m = applyMultipliers(m, { raise: adaptiveAdj.raiseAdj, call: adaptiveAdj.callAdj, fold: adaptiveAdj.foldAdj });
    m = normalize(m);
    trace.adaptiveAdj = { raise: adaptiveAdj.raiseAdj, call: adaptiveAdj.callAdj, fold: adaptiveAdj.foldAdj };
  }
  trace.afterAdaptive = copyMix(m);

  // Step 2e: apply opponent adjustment
  if (opponentAdj) {
    m = applyMultipliers(m, { raise: opponentAdj.raiseAdj, call: opponentAdj.callAdj, fold: opponentAdj.foldAdj });
    m = normalize(m);
    trace.opponentAdj = { raise: opponentAdj.raiseAdj, call: opponentAdj.callAdj, fold: opponentAdj.foldAdj };
  }
  trace.afterOpponent = copyMix(m);

  // Step 2f: apply mood multipliers
  if (moodState) {
    const mm = getMoodMultipliers(moodState);
    m = applyMultipliers(m, mm);
    m = normalize(m);
    trace.moodValue = moodState.value;
  }
  trace.afterMood = copyMix(m);

  // Step 3: preflop unopened limp share
  const limpShare = profile.unopenedLimpShare ?? 0;
  if (limpShare > 0 && isUnopened(state)) {
    m = applyLimpShare(m, limpShare);
    m = normalize(m);
  }
  trace.afterLimp = copyMix(m);

  // Step 3.5: mistake injection
  const bb = state.bigBlind || 1;
  const potBB = state.pot / bb;
  const myPlayer = state.players.find(p => p.seat === mySeat);
  const isAllIn = la.callAmount >= (myPlayer?.stack ?? 0) * 0.9;
  let sizingLeak = false;

  if (
    profile.mistakeConfig &&
    handNumber != null &&
    strength != null &&
    shouldInjectMistake(profile.mistakeConfig, handNumber, strength, potBB, isAllIn)
  ) {
    const { mix: adjustedMix, result } = injectMistake(m, profile.mistakeConfig, strength, potBB);
    m = adjustedMix;
    trace.mistakeApplied = true;
    trace.mistakeDescription = result.description;
    sizingLeak = result.sizingLeak;
  }
  trace.afterMistake = copyMix(m);

  // Step 4: choose action
  const rawAction = profile.stochastic ? sampleAction(m) : pickMaxAction(m);
  trace.sampledAction = rawAction;

  // Step 5: resolve legality
  const action = resolveWithLegality(rawAction, la);
  trace.resolvedAction = action;

  // Step 6: if raise, compute sizing (enhanced with discrete candidates)
  let amount: number | undefined;
  if (action === 'raise' && la.canRaise) {
    const sizingResult = chooseSizing({
      street: mapStreet(state.street),
      pot: state.pot,
      toCall: la.callAmount,
      bigBlind: state.bigBlind,
      minRaiseTo: la.minRaise,
      maxRaiseTo: la.maxRaise,
      handStrength: strength ?? 0.5,
      boardTexture,
      raiseContext,
      persona: persona ?? null,
    });
    amount = sizingResult.amount;
    trace.raiseAmount = amount;
    trace.raiseSizeCategory = sizingResult.category;

    // Sizing leak: intentionally pick suboptimal size
    if (sizingLeak) {
      const offsets = [0.8, 1.25];
      const factor = offsets[Math.floor(Math.random() * offsets.length)];
      amount = Math.max(la.minRaise, Math.min(la.maxRaise, Math.round(amount * factor)));
      trace.raiseAmount = amount;
    }
  }

  // Build human-readable reasoning from trace
  const reasoning = formatReasoning(trace, m);

  return { action, amount, reasoning, trace };
}

// ===== Legacy-compatible wrapper (preserves old call signature) =====
export function decideLegacy(
  state: TableState,
  profile: BotProfile,
  advice: StrategyMix | null,
  holeCards: [string, string] | null = null,
  adaptiveAdj?: AdaptiveAdjustments,
  fastModel?: MLP | null,
): DecisionResult {
  const mySeat = state.actorSeat ?? 0;
  return decide({
    state, profile, advice, holeCards, mySeat, adaptiveAdj, fastModel,
  });
}

function formatReasoning(trace: DecisionTrace, finalMix: Mix): string {
  const pos = trace.position ? ` pos=${trace.position}` : '';
  const str = trace.handStrength != null ? ` str=${trace.handStrength.toFixed(2)}` : '';
  const bt = trace.boardTexture ? ` board=${trace.boardTexture.category}(w=${trace.boardTexture.wetness})` : '';
  const rc = trace.raiseContext ? ` facing=${trace.raiseContext.facingType}` : '';
  const mood = trace.moodValue !== 0 ? ` mood=${trace.moodValue.toFixed(2)}` : '';
  const mistake = trace.mistakeApplied ? ` MISTAKE:${trace.mistakeDescription}` : '';

  const fmtMix = (m: Mix) => `R:${m.raise.toFixed(2)} C:${m.call.toFixed(2)} F:${m.fold.toFixed(2)}`;

  return (
    `src=${trace.source}${pos}${str}${bt}${rc}${mood}${mistake} ` +
    `base=(${fmtMix(trace.baseMix)}) final=(${fmtMix(finalMix)}) ` +
    `raw=${trace.sampledAction} → ${trace.resolvedAction}` +
    `${trace.raiseAmount != null ? ` amt=${trace.raiseAmount}` : ''}` +
    `${trace.raiseSizeCategory ? ` size=${trace.raiseSizeCategory}` : ''}`
  );
}
