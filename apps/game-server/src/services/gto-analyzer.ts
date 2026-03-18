import {
  getPostflopAdvice,
  type AdvicePrecision,
  type PostflopContext,
} from '@cardpilot/advice-engine';
import type { Card } from '@cardpilot/poker-evaluator';
import type {
  HistoryGTOHandRecord,
  HistoryGTOAnalysis,
  HistoryGTOSpotAnalysis,
  StrategyMix,
} from '@cardpilot/shared-types';

const STREETS_ORDER = ['PREFLOP', 'FLOP', 'TURN', 'RIVER'] as const;
const STREET_SET = new Set(STREETS_ORDER);

type StreetName = (typeof STREETS_ORDER)[number];
type PostflopStreet = 'FLOP' | 'TURN' | 'RIVER';
type AnalyzerActionType = 'fold' | 'check' | 'call' | 'bet' | 'raise' | 'all_in';

interface ReplayAction {
  idx: number;
  seat: number;
  street: StreetName;
  type: string;
  amount: number;
}

interface DecisionPoint {
  street: PostflopStreet;
  board: string[];
  pot: number;
  toCall: number;
  heroAction: string;
  heroAmount: number;
  effectiveStack: number;
  actionTimelineIdx?: number;
  decisionIndex: number;
  aggressor: 'hero' | 'villain' | 'none';
  preflopAggressor: 'hero' | 'villain' | 'none';
  heroInPosition: boolean;
  numVillains: number;
  villainSeat?: number;
  villainPosition: string;
  actionHistory: ReplayAction[];
}

/**
 * Reconstruct hero decision points from a completed hand record,
 * then run the advice engine on each one and score the hero's play.
 */
export async function analyzeHandGTO(
  handRecord: HistoryGTOHandRecord,
  precision: AdvicePrecision = 'deep',
): Promise<HistoryGTOAnalysis> {
  const decisionPoints = extractDecisionPoints(handRecord);
  const spots: HistoryGTOSpotAnalysis[] = [];
  const bb = Math.max(1, handRecord.bigBlind ?? parseBigBlind(handRecord.stakes) ?? 100);

  for (const dp of decisionPoints) {
    try {
      const context: PostflopContext = {
        tableId: 'history-analysis',
        handId: `gto-${Date.now()}`,
        seat: handRecord.heroSeat,
        street: dp.street,
        heroHand: handRecord.heroCards as [Card, Card],
        board: dp.board as Card[],
        heroPosition: handRecord.heroPosition,
        villainPosition: dp.villainPosition,
        potSize: dp.pot,
        toCall: dp.toCall,
        effectiveStack: dp.effectiveStack,
        aggressor: dp.aggressor,
        preflopAggressor: dp.preflopAggressor,
        heroInPosition: dp.heroInPosition,
        numVillains: dp.numVillains,
        actionHistory: dp.actionHistory.map((a) => ({
          seat: a.seat,
          street: a.street as PostflopContext['street'],
          type: toAdviceActionType(a.type),
          amount: a.amount,
          at: 0,
        })),
        potType: inferPotType(dp.actionHistory),
      };

      const advice = await getPostflopAdvice(context, precision);

      const heroActionKey = mapActionToMixKey(dp.heroAction);
      const recommendedAction = advice.recommended ?? 'call';
      const recommendedFreq = advice.mix[heroActionKey] ?? 0;
      const deviationScore = Math.round(Math.max(0, 1 - recommendedFreq) * 100);

      const alpha = advice.postflop?.alpha ?? 0;
      const mdf = advice.postflop?.mdf ?? 1;
      const equity = advice.math?.equityRequired ?? 0;
      const evLossBb = computeEvLossBb(deviationScore, dp.pot, bb);

      const note = buildSpotNote(
        dp.heroAction,
        recommendedAction,
        recommendedFreq,
        advice.mix,
        evLossBb,
      );

      spots.push({
        street: dp.street,
        board: dp.board,
        pot: dp.pot,
        toCall: dp.toCall,
        effectiveStack: dp.effectiveStack,
        heroAction: dp.heroAction,
        heroAmount: dp.heroAmount,
        actionTimelineIdx: dp.actionTimelineIdx,
        decisionIndex: dp.decisionIndex,
        recommended: {
          action: recommendedAction,
          mix: advice.mix,
        },
        deviationScore,
        evLossBb,
        alpha,
        mdf,
        equity,
        note,
      });
    } catch (err) {
      console.warn(
        `[gto-analyzer] Failed to analyze spot on ${dp.street}:`,
        (err as Error).message,
      );
    }
  }

  const streetScores = computeStreetScores(spots);
  const overallScore = computeOverallScore(spots);

  return {
    overallScore,
    streetScores,
    spots,
    computedAt: Date.now(),
    precision,
  };
}

export function extractDecisionPoints(hand: HistoryGTOHandRecord): DecisionPoint[] {
  if (Array.isArray(hand.actionTimeline) && hand.actionTimeline.length > 0) {
    return extractDecisionPointsFromTimeline(hand);
  }
  return extractDecisionPointsFromActions(hand);
}

function extractDecisionPointsFromTimeline(hand: HistoryGTOHandRecord): DecisionPoint[] {
  const heroSeat = hand.heroSeat;
  const timeline = hand.actionTimeline ?? [];
  const replayActions = normalizeActions(hand.actions);
  const positionsBySeat = mergePositionsBySeat(hand, replayActions);
  const villainSeats = uniqueVillainSeats(replayActions, heroSeat);
  const preflopAggressor = computePreflopAggressor(replayActions, heroSeat);
  const heroInPosition = isInPosition(positionsBySeat[heroSeat] ?? hand.heroPosition);

  const points: DecisionPoint[] = [];
  let decisionIndex = 0;
  let lastStreet: StreetName | null = null;
  let streetAggressorSeat: number | null = null;

  for (const entry of timeline) {
    const street = entry.street;
    if (!isPostflopStreet(street)) continue;
    if (lastStreet !== street) {
      streetAggressorSeat = null;
      lastStreet = street;
    }

    if (entry.seat === heroSeat) {
      const villainSeat = pickVillainSeat({
        heroSeat,
        villainSeats,
        aggressorSeat: streetAggressorSeat,
        history: replayActions.filter((action) => action.idx < entry.idx),
      });

      points.push({
        street,
        board: boardForStreet(hand.board, street),
        pot: Math.max(0, entry.potBefore),
        toCall: Math.max(0, entry.toCallBefore),
        heroAction: entry.type,
        heroAmount: Math.max(0, entry.amount),
        effectiveStack: Math.max(0, entry.effectiveStackBefore),
        actionTimelineIdx: entry.idx,
        decisionIndex,
        aggressor: aggressorRole(streetAggressorSeat, heroSeat),
        preflopAggressor,
        heroInPosition,
        numVillains: Math.max(1, villainSeats.length),
        villainSeat,
        villainPosition: resolveVillainPosition(villainSeat, positionsBySeat),
        actionHistory: replayActions.filter((action) => action.idx < entry.idx),
      });
      decisionIndex += 1;
    }

    if (isAggressiveAction(entry.type, entry.toCallBefore, entry.amount)) {
      streetAggressorSeat = entry.seat;
    }
  }

  return points;
}

function extractDecisionPointsFromActions(hand: HistoryGTOHandRecord): DecisionPoint[] {
  const replayActions = normalizeActions(hand.actions);
  const heroSeat = hand.heroSeat;
  const positionsBySeat = mergePositionsBySeat(hand, replayActions);
  const villainSeats = uniqueVillainSeats(replayActions, heroSeat);
  const preflopAggressor = computePreflopAggressor(replayActions, heroSeat);
  const heroInPosition = isInPosition(positionsBySeat[heroSeat] ?? hand.heroPosition);

  const seatSet = new Set(replayActions.map((a) => a.seat));
  const seatList = [...seatSet];
  const stacks = initStacksBySeat(hand, seatList);
  const folded = new Set<number>();
  const streetCommitted: Record<number, number> = {};
  for (const seat of seatList) streetCommitted[seat] = 0;

  const points: DecisionPoint[] = [];
  let currentStreet: StreetName = 'PREFLOP';
  let currentBetTo = 0;
  let pot = 0;
  let streetAggressorSeat: number | null = null;
  let decisionIndex = 0;

  for (const action of replayActions) {
    if (action.street !== currentStreet) {
      currentStreet = action.street;
      currentBetTo = 0;
      streetAggressorSeat = null;
      for (const key of Object.keys(streetCommitted)) {
        streetCommitted[Number(key)] = 0;
      }
    }

    const seat = action.seat;
    if (typeof stacks[seat] !== 'number') stacks[seat] = hand.stackSize;
    if (typeof streetCommitted[seat] !== 'number') streetCommitted[seat] = 0;

    const committedBefore = streetCommitted[seat];
    const toCallBefore = Math.max(0, currentBetTo - committedBefore);
    const actorStackBefore = Math.max(0, stacks[seat]);
    const opponentStacks = Object.entries(stacks)
      .filter(([otherSeat]) => Number(otherSeat) !== seat && !folded.has(Number(otherSeat)))
      .map(([, stack]) => Math.max(0, stack));
    const maxOppStack = opponentStacks.length > 0 ? Math.max(...opponentStacks) : actorStackBefore;
    const effectiveStackBefore = Math.max(0, Math.min(actorStackBefore, maxOppStack));

    if (
      seat === heroSeat &&
      isPostflopStreet(action.street) &&
      isPlayerDecisionAction(action.type)
    ) {
      const villainSeat = pickVillainSeat({
        heroSeat,
        villainSeats,
        aggressorSeat: streetAggressorSeat,
        history: replayActions.filter((a) => a.idx < action.idx),
      });

      points.push({
        street: action.street,
        board: boardForStreet(hand.board, action.street),
        pot,
        toCall: toCallBefore,
        heroAction: action.type,
        heroAmount: Math.max(0, action.amount),
        effectiveStack: effectiveStackBefore,
        actionTimelineIdx: action.idx,
        decisionIndex,
        aggressor: aggressorRole(streetAggressorSeat, heroSeat),
        preflopAggressor,
        heroInPosition,
        numVillains: Math.max(1, villainSeats.length),
        villainSeat,
        villainPosition: resolveVillainPosition(villainSeat, positionsBySeat),
        actionHistory: replayActions.filter((a) => a.idx < action.idx),
      });
      decisionIndex += 1;
    }

    if (action.type === 'fold') {
      folded.add(seat);
    }

    const amount = Math.max(0, action.amount);
    if (amount > 0) {
      streetCommitted[seat] = committedBefore + amount;
      stacks[seat] = Math.max(0, actorStackBefore - amount);
      pot += amount;
    }

    if (isAggressiveAction(action.type, toCallBefore, amount)) {
      currentBetTo = Math.max(currentBetTo, streetCommitted[seat]);
      streetAggressorSeat = seat;
    } else if (
      action.type === 'post_sb' ||
      action.type === 'post_bb' ||
      action.type === 'post_dead_blind'
    ) {
      currentBetTo = Math.max(currentBetTo, streetCommitted[seat]);
    }
  }

  return points;
}

function normalizeActions(actions: HistoryGTOHandRecord['actions']): ReplayAction[] {
  const normalized: ReplayAction[] = [];
  for (let idx = 0; idx < actions.length; idx++) {
    const action = actions[idx];
    const streetRaw = String(action.street ?? '').toUpperCase() as StreetName;
    if (!STREET_SET.has(streetRaw)) continue;
    normalized.push({
      idx,
      seat: Number(action.seat ?? 0),
      street: streetRaw,
      type: String(action.type ?? 'check'),
      amount: Math.max(0, Number(action.amount ?? 0)),
    });
  }
  return normalized;
}

function computePreflopAggressor(
  actions: ReplayAction[],
  heroSeat: number,
): 'hero' | 'villain' | 'none' {
  const preflopRaises = actions.filter(
    (a) =>
      a.street === 'PREFLOP' && (a.type === 'raise' || a.type === 'bet' || a.type === 'all_in'),
  );
  if (preflopRaises.length === 0) return 'none';
  return preflopRaises[preflopRaises.length - 1].seat === heroSeat ? 'hero' : 'villain';
}

function mergePositionsBySeat(
  hand: HistoryGTOHandRecord,
  actions: ReplayAction[],
): Record<number, string> {
  const fromPayload = hand.positionsBySeat ? normalizeSeatMap(hand.positionsBySeat) : {};
  if (Object.keys(fromPayload).length > 0) return fromPayload;
  if (typeof hand.buttonSeat !== 'number') return {};

  const seats = [...new Set(actions.map((a) => a.seat))].sort((a, b) => a - b);
  if (seats.length === 0) return {};
  return inferPositionsByButton(hand.buttonSeat, seats);
}

function normalizeSeatMap(input: Record<number, string>): Record<number, string> {
  const out: Record<number, string> = {};
  for (const [key, value] of Object.entries(input)) {
    const seat = Number(key);
    if (!Number.isFinite(seat) || typeof value !== 'string' || value.length === 0) continue;
    out[seat] = value;
  }
  return out;
}

function inferPositionsByButton(buttonSeat: number, seats: number[]): Record<number, string> {
  const sorted = [...new Set(seats)].sort((a, b) => a - b);
  const clockwise = [
    ...sorted.filter((s) => s > buttonSeat),
    ...sorted.filter((s) => s <= buttonSeat),
  ];
  if (clockwise.length < 2) return {};

  const order = [buttonSeat, ...clockwise];
  const labelsByCount: Record<number, string[]> = {
    2: ['BTN', 'BB'],
    3: ['BTN', 'SB', 'BB'],
    4: ['BTN', 'SB', 'BB', 'UTG'],
    5: ['BTN', 'SB', 'BB', 'UTG', 'CO'],
    6: ['BTN', 'SB', 'BB', 'UTG', 'HJ', 'CO'],
    7: ['BTN', 'SB', 'BB', 'UTG', 'MP', 'HJ', 'CO'],
    8: ['BTN', 'SB', 'BB', 'UTG', 'UTG+1', 'MP', 'HJ', 'CO'],
    9: ['BTN', 'SB', 'BB', 'UTG', 'UTG+1', 'MP', 'MP+1', 'HJ', 'CO'],
  };
  const labels = labelsByCount[order.length];
  if (!labels) return {};

  const map: Record<number, string> = {};
  for (let i = 0; i < order.length; i++) {
    map[order[i]] = labels[i] ?? 'UNKNOWN';
  }
  return map;
}

function uniqueVillainSeats(actions: ReplayAction[], heroSeat: number): number[] {
  return [...new Set(actions.map((a) => a.seat).filter((seat) => seat !== heroSeat))];
}

function initStacksBySeat(hand: HistoryGTOHandRecord, seats: number[]): Record<number, number> {
  const stacksFromPayload = hand.stacksBySeatAtStart
    ? normalizeSeatNumberMap(hand.stacksBySeatAtStart)
    : {};
  const stacks: Record<number, number> = {};
  for (const seat of seats) {
    stacks[seat] = Math.max(0, stacksFromPayload[seat] ?? hand.stackSize);
  }
  return stacks;
}

function normalizeSeatNumberMap(input: Record<number, number>): Record<number, number> {
  const out: Record<number, number> = {};
  for (const [key, value] of Object.entries(input)) {
    const seat = Number(key);
    const stack = Number(value);
    if (!Number.isFinite(seat) || !Number.isFinite(stack)) continue;
    out[seat] = stack;
  }
  return out;
}

function pickVillainSeat(args: {
  heroSeat: number;
  villainSeats: number[];
  aggressorSeat: number | null;
  history: ReplayAction[];
}): number | undefined {
  if (args.aggressorSeat != null && args.aggressorSeat !== args.heroSeat) {
    return args.aggressorSeat;
  }

  for (let i = args.history.length - 1; i >= 0; i--) {
    const action = args.history[i];
    if (action.seat === args.heroSeat) continue;
    if (isPlayerDecisionAction(action.type)) return action.seat;
  }

  return args.villainSeats[0];
}

function resolveVillainPosition(
  villainSeat: number | undefined,
  positionsBySeat: Record<number, string>,
): string {
  if (villainSeat == null) return 'UNKNOWN';
  return positionsBySeat[villainSeat] ?? 'UNKNOWN';
}

function aggressorRole(
  aggressorSeat: number | null,
  heroSeat: number,
): 'hero' | 'villain' | 'none' {
  if (aggressorSeat == null) return 'none';
  return aggressorSeat === heroSeat ? 'hero' : 'villain';
}

function boardForStreet(board: string[], street: PostflopStreet): string[] {
  if (street === 'FLOP') return board.slice(0, 3);
  if (street === 'TURN') return board.slice(0, 4);
  return board.slice(0, 5);
}

function inferPotType(actions: ReplayAction[]): 'SRP' | '3BP' | '4BP' {
  const preflopRaises = actions.filter(
    (a) =>
      a.street === 'PREFLOP' && (a.type === 'raise' || a.type === 'bet' || a.type === 'all_in'),
  ).length;
  if (preflopRaises >= 3) return '4BP';
  if (preflopRaises === 2) return '3BP';
  return 'SRP';
}

function mapActionToMixKey(action: string): keyof StrategyMix {
  if (action === 'fold') return 'fold';
  if (action === 'call' || action === 'check') return 'call';
  return 'raise';
}

function toAdviceActionType(action: string): 'fold' | 'check' | 'call' | 'raise' | 'all_in' {
  if (
    action === 'fold' ||
    action === 'check' ||
    action === 'call' ||
    action === 'raise' ||
    action === 'all_in'
  ) {
    return action;
  }
  if (action === 'bet') return 'raise';
  return 'call';
}

function isPostflopStreet(street: string): street is PostflopStreet {
  return street === 'FLOP' || street === 'TURN' || street === 'RIVER';
}

function isPlayerDecisionAction(actionType: string): actionType is AnalyzerActionType {
  return (
    actionType === 'fold' ||
    actionType === 'check' ||
    actionType === 'call' ||
    actionType === 'bet' ||
    actionType === 'raise' ||
    actionType === 'all_in'
  );
}

function isAggressiveAction(actionType: string, toCallBefore: number, amount: number): boolean {
  if (actionType === 'bet' || actionType === 'raise') return true;
  if (actionType !== 'all_in') return false;
  return toCallBefore === 0 || amount > toCallBefore;
}

function parseBigBlind(stakes: string): number | null {
  const parts = stakes.split('/');
  if (parts.length < 2) return null;
  const bb = Number(parts[1]);
  return Number.isFinite(bb) && bb > 0 ? bb : null;
}

function computeEvLossBb(deviationScore: number, pot: number, bb: number): number {
  const potBb = Math.max(0, pot) / Math.max(1, bb);
  const proxy = (deviationScore / 100) * Math.max(0.1, potBb) * 0.35;
  return Math.round(proxy * 100) / 100;
}

function isInPosition(position: string): boolean {
  return ['BTN', 'CO', 'HJ'].includes(position);
}

function buildSpotNote(
  heroAction: string,
  recommended: string,
  heroFreq: number,
  mix: StrategyMix,
  evLossBb: number,
): string {
  const evNote = ` Approx EV proxy loss: ${evLossBb.toFixed(2)}bb (derived from deviation score × pot size).`;
  if (heroFreq >= 0.5) {
    return `Good: ${heroAction} is within the recommended range (${Math.round(heroFreq * 100)}% frequency).${evNote}`;
  }
  if (heroFreq >= 0.2) {
    return `Acceptable: ${heroAction} is a minor deviation. GTO prefers ${recommended} (${Math.round(mix[mapActionToMixKey(recommended)] * 100)}%).${evNote}`;
  }
  return `Deviation: ${heroAction} is rarely recommended here (${Math.round(heroFreq * 100)}%). GTO strongly prefers ${recommended}.${evNote}`;
}

function computeStreetScores(spots: HistoryGTOSpotAnalysis[]): {
  flop: number | null;
  turn: number | null;
  river: number | null;
} {
  const byStreet: Record<string, number[]> = { FLOP: [], TURN: [], RIVER: [] };
  for (const s of spots) {
    const key = s.street.toUpperCase();
    if (byStreet[key]) {
      byStreet[key].push(100 - s.deviationScore);
    }
  }
  return {
    flop: byStreet.FLOP.length > 0 ? avg(byStreet.FLOP) : null,
    turn: byStreet.TURN.length > 0 ? avg(byStreet.TURN) : null,
    river: byStreet.RIVER.length > 0 ? avg(byStreet.RIVER) : null,
  };
}

function computeOverallScore(spots: HistoryGTOSpotAnalysis[]): number {
  if (spots.length === 0) return 100;
  const scores = spots.map((s) => 100 - s.deviationScore);
  return Math.round(avg(scores));
}

function avg(arr: number[]): number {
  if (arr.length === 0) return 0;
  return arr.reduce((s, v) => s + v, 0) / arr.length;
}
