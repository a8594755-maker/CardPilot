/**
 * Audit Engine
 *
 * Computes GTO audit results for hero decision points after a hand ends.
 * Orchestrates: line recognition → advice lookup → deviation scoring → EV diff.
 *
 * Usage:
 *   const engine = new AuditEngine();
 *   const summary = await engine.auditHand({ ... });
 */

import type { HandAction, PlayerActionType, StrategyMix, Street } from '@cardpilot/shared-types';
import type {
  DecisionPoint,
  GtoAuditResult,
  HandAuditSummary,
  SessionLeakSummary,
  StreetLeakBucket,
  SpotLeakBucket,
  LineLeakBucket,
  DeviationBucket,
  LeakCategory,
  DrillSuggestion,
  ActionDeviationType,
  SpotType,
  StackDepthCategory,
  LineTag,
} from '@cardpilot/shared-types';
import { v4 as uuidv4 } from 'uuid';
import { getPreflopAdvice, calculateDeviation } from './index.js';
import { getPostflopAdvice, type PostflopContext } from './postflop-engine.js';
import { recognizeLines, classifyActionDeviation, classifySpotType } from './line-recognition.js';
import type { Card } from '@cardpilot/poker-evaluator';

// ── Public API ──

export interface AuditHandInput {
  /** Hand identity */
  handId: string;
  handHistoryId: string;
  /** Table state at hand end */
  tableId: string;
  bigBlind: number;
  smallBlind: number;
  buttonSeat: number;
  playerSeats: number[];
  /** Full action timeline */
  actions: HandAction[];
  /** Per-seat positions */
  positions: Record<number, string>;
  /** Hero info */
  heroUserId: string;
  heroSeat: number;
  heroCards: [string, string];
  /** Board state */
  board: string[];
  /** Pot at end */
  totalPot: number;
}

export interface AuditHandResult {
  summary: HandAuditSummary;
  decisionPoints: DecisionPoint[];
}

export class AuditEngine {
  /**
   * Audit all hero decision points in a completed hand.
   * Returns decision points + audit results.
   */
  async auditHand(input: AuditHandInput): Promise<AuditHandResult> {
    const lineResult = recognizeLines({
      actions: input.actions,
      heroSeat: input.heroSeat,
      buttonSeat: input.buttonSeat,
      playerSeats: input.playerSeats,
      bigBlind: input.bigBlind,
    });

    const spotType = classifySpotType(lineResult);
    const heroPosition = input.positions[input.heroSeat] ?? 'BTN';

    // Extract hero decision points
    const decisionPoints = extractDecisionPoints({
      input,
      spotType,
      lineTags: lineResult.lineTags,
      heroPosition,
    });

    // Compute GTO audit for each decision point
    const audits: GtoAuditResult[] = [];
    for (const dp of decisionPoints) {
      try {
        const audit = await this.auditDecisionPoint(dp, input, lineResult.preflopAggressorSeat);
        audits.push(audit);
      } catch (err) {
        console.error(`[audit-engine] Failed to audit decision point ${dp.id}:`, err);
      }
    }

    const totalLeakedBb = audits.reduce((sum, a) => sum + a.evDiffBb, 0);
    const totalLeakedChips = audits.reduce((sum, a) => sum + a.evDiffChips, 0);
    const worstDeviation = audits.length > 0 ? Math.max(...audits.map((a) => a.deviationScore)) : 0;

    const summary: HandAuditSummary = {
      handId: input.handId,
      handHistoryId: input.handHistoryId,
      heroUserId: input.heroUserId,
      totalLeakedBb: round4(totalLeakedBb),
      totalLeakedChips: round2(totalLeakedChips),
      decisionCount: audits.length,
      worstDeviationScore: round4(worstDeviation),
      audits,
      handLineTags: lineResult.lineTags,
      spotType,
      computedAt: Date.now(),
    };

    return { summary, decisionPoints };
  }

  /**
   * Audit a single decision point against GTO.
   */
  private async auditDecisionPoint(
    dp: DecisionPoint,
    input: AuditHandInput,
    pfaSeat: number | null,
  ): Promise<GtoAuditResult> {
    const now = Date.now();
    let gtoMix: StrategyMix;
    let recommendedAction: 'raise' | 'call' | 'fold';
    let equity: number | undefined;
    let mdf: number | undefined;
    let alpha: number | undefined;

    if (dp.street === 'PREFLOP') {
      // Use preflop advice engine
      const heroPos = dp.heroPosition;
      const villainPos = findVillainPosition(input, dp);
      const isUnopened = !input.actions.some(
        (a) =>
          a.street === 'PREFLOP' &&
          a.at < actionTimestamp(input.actions, dp) &&
          (a.type === 'raise' || a.type === 'all_in') &&
          a.seat !== dp.heroSeat,
      );

      const advice = getPreflopAdvice({
        tableId: input.tableId,
        handId: input.handId,
        seat: dp.heroSeat,
        heroPos,
        villainPos,
        line: isUnopened ? 'unopened' : 'facing_open',
        heroHand: `${dp.heroCards[0][0]}${dp.heroCards[1][0]}${suitedness(dp.heroCards)}`,
        effectiveStackBb: dp.effectiveStackBb,
        bigBlind: input.bigBlind,
        potSize: dp.pot,
        raiseAmount: dp.toCall > 0 ? dp.toCall : undefined,
      });

      gtoMix = advice.mix;
      recommendedAction = advice.recommended ?? 'fold';
    } else {
      // Use postflop advice engine
      const heroIsPfa = pfaSeat === dp.heroSeat;
      const villainPos = findVillainPosition(input, dp);

      const context: PostflopContext = {
        tableId: input.tableId,
        handId: input.handId,
        seat: dp.heroSeat,
        street: dp.street as 'FLOP' | 'TURN' | 'RIVER',
        heroHand: dp.heroCards as [Card, Card],
        board: dp.board as Card[],
        heroPosition: dp.heroPosition,
        villainPosition: villainPos,
        potSize: dp.pot,
        toCall: dp.toCall,
        effectiveStack: dp.effectiveStackBb * input.bigBlind,
        effectiveStackBb: dp.effectiveStackBb,
        aggressor: heroIsPfa ? 'hero' : 'villain',
        preflopAggressor: heroIsPfa ? 'hero' : pfaSeat !== null ? 'villain' : 'none',
        heroInPosition: isInPosition(dp.heroPosition, villainPos),
        numVillains: input.playerSeats.length - 1,
        actionHistory: input.actions,
        potType: dp.spotType === '3BP' ? '3BP' : dp.spotType === '4BP' ? '4BP' : 'SRP',
      };

      const advice = await getPostflopAdvice(context, 'fast');
      gtoMix = advice.mix;
      recommendedAction = advice.recommended ?? 'fold';
      equity = advice.postflop?.alpha !== undefined ? 1 - (advice.postflop.alpha ?? 0) : undefined;
      mdf = advice.postflop?.mdf;
      alpha = advice.postflop?.alpha;
    }

    // Compute deviation
    const deviationScore = calculateDeviation(gtoMix, dp.actualAction);
    const deviationType = classifyActionDeviation({
      gtoMix,
      actualAction: mapActionToTriple(dp.actualAction),
    });

    // Compute EV difference (simplified: deviation * pot * direction)
    const evDiffChips = computeEvDiff(gtoMix, dp.actualAction, dp.pot, deviationScore);
    const evDiffBb = input.bigBlind > 0 ? evDiffChips / input.bigBlind : 0;

    return {
      decisionPointId: dp.id,
      handId: input.handId,
      heroUserId: input.heroUserId,
      gtoMix,
      recommendedAction,
      actualAction: dp.actualAction,
      deviationScore: round4(deviationScore),
      evDiffBb: round4(evDiffBb),
      evDiffChips: round2(evDiffChips),
      deviationType,
      street: dp.street,
      spotType: dp.spotType,
      lineTags: dp.lineTags,
      heroPosition: dp.heroPosition,
      stackDepthCategory: dp.stackDepthCategory,
      equity,
      mdf,
      alpha,
      computedAt: now,
    };
  }
}

// ── Decision Point Extraction ──

function extractDecisionPoints(params: {
  input: AuditHandInput;
  spotType: SpotType;
  lineTags: LineTag[];
  heroPosition: string;
}): DecisionPoint[] {
  const { input, spotType, lineTags, heroPosition } = params;
  const points: DecisionPoint[] = [];

  const heroActions = input.actions.filter(
    (a) =>
      a.seat === input.heroSeat &&
      isPlayerAction(a.type) &&
      (a.street === 'PREFLOP' ||
        a.street === 'FLOP' ||
        a.street === 'TURN' ||
        a.street === 'RIVER'),
  );

  for (let i = 0; i < heroActions.length; i++) {
    const action = heroActions[i];
    const board = boardAtStreet(input.board, action.street);
    const pot = estimatePotAtAction(input.actions, action);
    const toCall = estimateToCallAtAction(input.actions, action);
    const effectiveStackBb =
      input.bigBlind > 0 ? estimateEffectiveStack(input, action) / input.bigBlind : 100;

    points.push({
      id: uuidv4(),
      handHistoryId: input.handHistoryId,
      handId: input.handId,
      heroUserId: input.heroUserId,
      heroSeat: input.heroSeat,
      heroPosition,
      heroCards: input.heroCards,
      street: action.street,
      board,
      pot,
      toCall,
      effectiveStackBb: round2(effectiveStackBb),
      stackDepthCategory: classifyStack(effectiveStackBb),
      actualAction: action.type as PlayerActionType,
      actualAmount: action.amount,
      spotType,
      lineTags,
      actionIndex: i,
      timestamp: action.at,
    });
  }

  return points;
}

// ── Session Leak Aggregation ──

export function aggregateSessionLeaks(
  sessionId: string,
  heroUserId: string,
  handSummaries: HandAuditSummary[],
): SessionLeakSummary {
  const byStreet: Record<string, StreetLeakBucket> = {};
  const bySpotType: Record<SpotType, SpotLeakBucket> = {} as Record<SpotType, SpotLeakBucket>;
  const byLineTag: Record<string, LineLeakBucket> = {};
  const byDeviation: Record<ActionDeviationType, DeviationBucket> = {} as Record<
    ActionDeviationType,
    DeviationBucket
  >;

  let totalLeakedBb = 0;
  let totalLeakedChips = 0;
  let totalDecisions = 0;

  for (const hand of handSummaries) {
    totalLeakedBb += hand.totalLeakedBb;
    totalLeakedChips += hand.totalLeakedChips;

    for (const audit of hand.audits) {
      totalDecisions++;

      // By street
      const streetKey = audit.street;
      if (!byStreet[streetKey]) {
        byStreet[streetKey] = {
          street: streetKey,
          leakedBb: 0,
          decisionCount: 0,
          avgDeviationScore: 0,
        };
      }
      byStreet[streetKey].leakedBb += audit.evDiffBb;
      byStreet[streetKey].decisionCount++;

      // By spot type
      const spot = audit.spotType;
      if (!bySpotType[spot]) {
        bySpotType[spot] = { spotType: spot, leakedBb: 0, decisionCount: 0, avgDeviationScore: 0 };
      }
      bySpotType[spot].leakedBb += audit.evDiffBb;
      bySpotType[spot].decisionCount++;

      // By line tags
      for (const tag of audit.lineTags) {
        if (!byLineTag[tag]) {
          byLineTag[tag] = { lineTag: tag, leakedBb: 0, decisionCount: 0, avgDeviationScore: 0 };
        }
        byLineTag[tag].leakedBb += audit.evDiffBb;
        byLineTag[tag].decisionCount++;
      }

      // By deviation type
      const devType = audit.deviationType;
      if (!byDeviation[devType]) {
        byDeviation[devType] = { deviationType: devType, count: 0, leakedBb: 0 };
      }
      byDeviation[devType].count++;
      byDeviation[devType].leakedBb += audit.evDiffBb;
    }
  }

  // Compute averages
  for (const bucket of Object.values(byStreet)) {
    if (bucket.decisionCount > 0) {
      bucket.avgDeviationScore = round4(bucket.leakedBb / bucket.decisionCount);
      bucket.leakedBb = round4(bucket.leakedBb);
    }
  }
  for (const bucket of Object.values(bySpotType)) {
    if (bucket.decisionCount > 0) {
      bucket.avgDeviationScore = round4(bucket.leakedBb / bucket.decisionCount);
      bucket.leakedBb = round4(bucket.leakedBb);
    }
  }
  for (const bucket of Object.values(byLineTag)) {
    if (bucket.decisionCount > 0) {
      bucket.avgDeviationScore = round4(bucket.leakedBb / bucket.decisionCount);
      bucket.leakedBb = round4(bucket.leakedBb);
    }
  }

  // Top leaks: rank all buckets by absolute leaked bb
  const topLeaks = buildTopLeaks(byStreet, bySpotType, byLineTag, byDeviation, totalDecisions);
  const suggestedDrills = buildDrillSuggestions(topLeaks);

  const handsPlayed = handSummaries.length;
  const leakedBbPer100 = handsPlayed > 0 ? round4((totalLeakedBb / handsPlayed) * 100) : 0;

  return {
    sessionId,
    heroUserId,
    totalLeakedBb: round4(totalLeakedBb),
    totalLeakedChips: round2(totalLeakedChips),
    handsPlayed,
    handsAudited: handSummaries.filter((h) => h.audits.length > 0).length,
    leakedBbPer100,
    byStreet,
    bySpotType,
    byLineTag,
    byDeviation,
    topLeaks,
    suggestedDrills,
    computedAt: Date.now(),
  };
}

// ── Helpers ──

function isPlayerAction(type: string): boolean {
  return ['fold', 'check', 'call', 'raise', 'all_in'].includes(type);
}

function boardAtStreet(fullBoard: string[], street: Street): string[] {
  if (street === 'PREFLOP') return [];
  if (street === 'FLOP') return fullBoard.slice(0, 3);
  if (street === 'TURN') return fullBoard.slice(0, 4);
  return fullBoard.slice(0, 5);
}

function estimatePotAtAction(actions: HandAction[], target: HandAction): number {
  let pot = 0;
  for (const a of actions) {
    if (a.at >= target.at) break;
    if (a.amount > 0) pot += a.amount;
  }
  return pot;
}

function estimateToCallAtAction(actions: HandAction[], target: HandAction): number {
  // Find the current bet level on this street before hero's action
  let currentBet = 0;
  let heroCommitted = 0;

  for (const a of actions) {
    if (a.at >= target.at) break;
    if (a.street !== target.street) continue;

    if (a.type === 'raise' || a.type === 'all_in') {
      currentBet = Math.max(currentBet, a.amount);
    }
    if (a.seat === target.seat) {
      heroCommitted += a.amount;
    }
  }

  return Math.max(0, currentBet - heroCommitted);
}

function estimateEffectiveStack(input: AuditHandInput, _action: HandAction): number {
  // Rough estimate: assume starting stack = totalPot / playerCount * 2
  // In practice this should come from hand start stacks
  return input.totalPot * 3;
}

function classifyStack(bbStack: number): StackDepthCategory {
  if (bbStack < 40) return 'short';
  if (bbStack <= 80) return 'medium';
  if (bbStack > 150) return 'deep';
  return 'standard';
}

function findVillainPosition(input: AuditHandInput, dp: DecisionPoint): string {
  // Find the main villain (last aggressor or first non-hero seat)
  const otherSeats = input.playerSeats.filter((s) => s !== dp.heroSeat);
  if (otherSeats.length === 0) return 'BB';

  // Try to find the last aggressor before hero's action
  const priorActions = input.actions.filter(
    (a) =>
      a.at < dp.timestamp && a.seat !== dp.heroSeat && (a.type === 'raise' || a.type === 'all_in'),
  );

  if (priorActions.length > 0) {
    const lastAggressor = priorActions[priorActions.length - 1];
    return input.positions[lastAggressor.seat] ?? 'BB';
  }

  return input.positions[otherSeats[0]] ?? 'BB';
}

function actionTimestamp(actions: HandAction[], dp: DecisionPoint): number {
  return dp.timestamp;
}

function suitedness(cards: [string, string]): string {
  if (cards[0].length < 2 || cards[1].length < 2) return 'o';
  return cards[0][1] === cards[1][1] ? 's' : 'o';
}

const POSITION_ORDER = ['SB', 'BB', 'UTG', 'MP', 'HJ', 'CO', 'BTN'];

function isInPosition(heroPos: string, villainPos: string): boolean {
  const heroIdx = POSITION_ORDER.indexOf(heroPos);
  const villainIdx = POSITION_ORDER.indexOf(villainPos);
  if (heroIdx < 0 || villainIdx < 0) return false;
  return heroIdx > villainIdx;
}

function mapActionToTriple(action: PlayerActionType): 'raise' | 'call' | 'fold' {
  if (action === 'raise' || action === 'all_in') return 'raise';
  if (action === 'call' || action === 'check') return 'call';
  return 'fold';
}

/**
 * Compute simplified EV difference.
 *
 * For a properly calibrated EV diff you'd need full game tree traversal.
 * This approximation uses: deviation * pot * sign.
 *
 * Negative = leaked value (hero chose worse than GTO).
 * Positive = hero found an exploit (or lucky deviation).
 */
function computeEvDiff(
  gtoMix: StrategyMix,
  actualAction: PlayerActionType,
  pot: number,
  deviationScore: number,
): number {
  if (deviationScore < 0.01) return 0;

  const mapped = mapActionToTriple(actualAction);
  const gtoFreq = gtoMix[mapped];
  const bestFreq = Math.max(gtoMix.raise, gtoMix.call, gtoMix.fold);

  // If hero chose the best action, no leak
  if (gtoFreq >= bestFreq - 0.01) return 0;

  // Leak magnitude: proportion of pot scaled by deviation severity
  // Negative means hero leaked value
  return -round2(deviationScore * pot * 0.15);
}

function buildTopLeaks(
  byStreet: Record<string, StreetLeakBucket>,
  bySpotType: Record<SpotType, SpotLeakBucket>,
  byLineTag: Record<string, LineLeakBucket>,
  byDeviation: Record<ActionDeviationType, DeviationBucket>,
  totalDecisions: number,
): LeakCategory[] {
  const candidates: LeakCategory[] = [];

  // Add street leaks
  for (const bucket of Object.values(byStreet)) {
    if (bucket.leakedBb < -0.01) {
      candidates.push({
        rank: 0,
        label: `${bucket.street} leaks`,
        description: `Leaked ${Math.abs(bucket.leakedBb).toFixed(1)} bb on ${bucket.street} across ${bucket.decisionCount} decisions`,
        leakedBb: bucket.leakedBb,
        frequency: totalDecisions > 0 ? bucket.decisionCount / totalDecisions : 0,
        street: bucket.street,
      });
    }
  }

  // Add deviation type leaks
  for (const bucket of Object.values(byDeviation)) {
    if (bucket.leakedBb < -0.01 && bucket.deviationType !== 'CORRECT') {
      candidates.push({
        rank: 0,
        label: formatDeviationType(bucket.deviationType),
        description: `${bucket.count} instances of ${formatDeviationType(bucket.deviationType).toLowerCase()}, leaked ${Math.abs(bucket.leakedBb).toFixed(1)} bb`,
        leakedBb: bucket.leakedBb,
        frequency: totalDecisions > 0 ? bucket.count / totalDecisions : 0,
        deviationType: bucket.deviationType,
      });
    }
  }

  // Add line tag leaks
  for (const bucket of Object.values(byLineTag)) {
    if (bucket.leakedBb < -0.01) {
      candidates.push({
        rank: 0,
        label: `${formatLineTag(bucket.lineTag)} leaks`,
        description: `Leaked ${Math.abs(bucket.leakedBb).toFixed(1)} bb in ${formatLineTag(bucket.lineTag)} spots`,
        leakedBb: bucket.leakedBb,
        frequency: totalDecisions > 0 ? bucket.decisionCount / totalDecisions : 0,
        lineTag: bucket.lineTag,
      });
    }
  }

  // Sort by absolute leaked bb (worst first) and take top 5
  candidates.sort((a, b) => a.leakedBb - b.leakedBb);
  return candidates.slice(0, 5).map((c, i) => ({ ...c, rank: i + 1 }));
}

function buildDrillSuggestions(topLeaks: LeakCategory[]): DrillSuggestion[] {
  return topLeaks.slice(0, 3).map((leak) => ({
    leakCategory: leak.label,
    drillType: 'replay' as const,
    title: `Fix: ${leak.label}`,
    description: leak.description,
    linkParams: {
      spotType: leak.spotType,
      lineTag: leak.lineTag,
    },
  }));
}

function formatDeviationType(type: ActionDeviationType): string {
  const labels: Record<ActionDeviationType, string> = {
    OVERFOLD: 'Over-folding',
    UNDERFOLD: 'Under-folding',
    OVERBLUFF: 'Over-bluffing',
    UNDERBLUFF: 'Under-bluffing',
    OVERCALL: 'Over-calling',
    UNDERCALL: 'Under-calling',
    CORRECT: 'Correct',
  };
  return labels[type] ?? type;
}

function formatLineTag(tag: string): string {
  return tag.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function round2(v: number): number {
  return Math.round(v * 100) / 100;
}

function round4(v: number): number {
  return Math.round(v * 10000) / 10000;
}
