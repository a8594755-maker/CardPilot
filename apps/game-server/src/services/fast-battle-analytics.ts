/**
 * Fast Battle Analytics — Report Generation
 *
 * Computes behavior stats (VPIP, PFR, 3Bet, etc.) from raw hand records
 * and assembles the full FastBattleReport using the existing audit pipeline.
 */

import type {
  FastBattleHandRecord,
  FastBattleBehaviorStats,
  FastBattleProblemHand,
  FastBattleReport,
} from '@cardpilot/shared-types';
import type { HandAuditSummary } from '@cardpilot/shared-types';
import { aggregateSessionLeaks } from '@cardpilot/advice-engine';

// ── Main Entry Point ──

export function generateFastBattleReport(
  handRecords: FastBattleHandRecord[],
  handAuditSummaries: HandAuditSummary[],
  session: {
    sessionId: string;
    userId: string;
    startedAt: number;
    endedAt: number | null;
    bigBlind: number;
  },
): FastBattleReport {
  const stats = computeBehaviorStats(handRecords, session);
  const sessionLeak =
    handAuditSummaries.length > 0
      ? aggregateSessionLeaks(session.sessionId, session.userId, handAuditSummaries)
      : null;
  const problemHands = rankProblemHands(handAuditSummaries);

  // Enrich problem hands with actual hole cards, position, board from hand records
  for (const ph of problemHands) {
    const rec = handRecords.find((r) => r.handId === ph.handId);
    if (rec) {
      ph.holeCards = rec.holeCards;
      ph.heroPosition = rec.heroPosition;
      ph.board = rec.board;
    }
  }

  const recommendations = sessionLeak?.suggestedDrills ?? [];

  return {
    sessionId: session.sessionId,
    stats,
    sessionLeak,
    problemHands,
    recommendations,
    handRecords,
    handCount: handRecords.length,
    durationMs: (session.endedAt ?? Date.now()) - session.startedAt,
  };
}

// ── Behavior Stats ──

function computeBehaviorStats(
  records: FastBattleHandRecord[],
  session: { startedAt: number; endedAt: number | null; bigBlind: number },
): FastBattleBehaviorStats {
  if (records.length === 0) {
    return emptyStats();
  }

  let vpipCount = 0;
  let pfrCount = 0;
  let threeBetCount = 0;
  let threeBetOpportunity = 0;
  let foldTo3BetCount = 0;
  let foldTo3BetOpportunity = 0;
  let cbetFlopCount = 0;
  let cbetFlopOpportunity = 0;
  let cbetTurnCount = 0;
  let cbetTurnOpportunity = 0;
  let betsAndRaises = 0;
  let calls = 0;
  let showdownCount = 0;
  let wonAtShowdown = 0;
  let handsWon = 0;
  let totalNetChips = 0;

  for (const hand of records) {
    const preflopActions = hand.heroActions.filter((a) => a.street === 'PREFLOP');
    const flopActions = hand.heroActions.filter((a) => a.street === 'FLOP');
    const turnActions = hand.heroActions.filter((a) => a.street === 'TURN');

    // VPIP: voluntarily put money in preflop (excludes posting blinds)
    const voluntaryPreflop = preflopActions.some(
      (a) => a.action === 'call' || a.action === 'raise' || a.action === 'all_in',
    );
    if (voluntaryPreflop) vpipCount++;

    // PFR: preflop raise
    const raisedPreflop = preflopActions.some((a) => a.action === 'raise' || a.action === 'all_in');
    if (raisedPreflop) pfrCount++;

    // 3-Bet: hero raised after there was already a raise preflop
    // Simplified: if hero raised and it wasn't the first raise (toCall > 1bb)
    const heroRaisePreflop = preflopActions.find(
      (a) => a.action === 'raise' || a.action === 'all_in',
    );
    if (heroRaisePreflop && heroRaisePreflop.toCall > 0) {
      // This was a re-raise (3-bet or more)
      threeBetOpportunity++;
      threeBetCount++;
    } else if (
      preflopActions.some((a) => a.action === 'call' || a.action === 'fold') &&
      preflopActions.some((a) => a.toCall > session.bigBlind)
    ) {
      // Had opportunity to 3-bet but didn't
      threeBetOpportunity++;
    }

    // Fold to 3-bet: hero raised, got re-raised, then folded
    if (raisedPreflop) {
      const foldAfterRaise = preflopActions.find((a) => a.action === 'fold' && a.toCall > 0);
      if (foldAfterRaise) {
        foldTo3BetOpportunity++;
        foldTo3BetCount++;
      }
    }

    // C-bet flop: hero was preflop raiser and bet on flop
    if (raisedPreflop && flopActions.length > 0) {
      cbetFlopOpportunity++;
      if (flopActions.some((a) => a.action === 'raise' || a.action === 'all_in')) {
        cbetFlopCount++;
      }
    }

    // C-bet turn: hero c-bet flop and bet turn
    if (
      raisedPreflop &&
      flopActions.some((a) => a.action === 'raise' || a.action === 'all_in') &&
      turnActions.length > 0
    ) {
      cbetTurnOpportunity++;
      if (turnActions.some((a) => a.action === 'raise' || a.action === 'all_in')) {
        cbetTurnCount++;
      }
    }

    // Aggression: count bets+raises vs calls across all streets
    for (const a of hand.heroActions) {
      if (a.action === 'raise' || a.action === 'all_in') betsAndRaises++;
      if (a.action === 'call') calls++;
    }

    // Showdown stats
    if (hand.wentToShowdown) {
      showdownCount++;
      if (hand.result > 0) wonAtShowdown++;
    }

    // Win tracking
    if (hand.result > 0) handsWon++;
    totalNetChips += hand.result;
  }

  const total = records.length;
  const elapsed = (session.endedAt ?? Date.now()) - session.startedAt;
  const decisionsPerHour = elapsed > 0 ? Math.round((total / elapsed) * 3_600_000) : 0;

  return {
    handsPlayed: total,
    handsWon,
    vpip: total > 0 ? round2(vpipCount / total) : 0,
    pfr: total > 0 ? round2(pfrCount / total) : 0,
    threeBet: threeBetOpportunity > 0 ? round2(threeBetCount / threeBetOpportunity) : 0,
    foldTo3Bet: foldTo3BetOpportunity > 0 ? round2(foldTo3BetCount / foldTo3BetOpportunity) : 0,
    cbetFlop: cbetFlopOpportunity > 0 ? round2(cbetFlopCount / cbetFlopOpportunity) : 0,
    cbetTurn: cbetTurnOpportunity > 0 ? round2(cbetTurnCount / cbetTurnOpportunity) : 0,
    aggressionFactor: calls > 0 ? round2(betsAndRaises / calls) : betsAndRaises > 0 ? 999 : 0,
    wtsd: total > 0 ? round2(showdownCount / total) : 0,
    wsd: showdownCount > 0 ? round2(wonAtShowdown / showdownCount) : 0,
    netChips: totalNetChips,
    netBb: session.bigBlind > 0 ? round2(totalNetChips / session.bigBlind) : 0,
    decisionsPerHour,
  };
}

// ── Problem Hands ──

function rankProblemHands(audits: HandAuditSummary[]): FastBattleProblemHand[] {
  // Sort by total leaked BB descending, take top 10
  const sorted = [...audits]
    .filter((a) => a.totalLeakedBb > 0)
    .sort((a, b) => b.totalLeakedBb - a.totalLeakedBb)
    .slice(0, 10);

  return sorted.map((audit, i) => ({
    rank: i + 1,
    handId: audit.handId,
    heroPosition: '', // Will be enriched from hand records if available
    holeCards: ['??', '??'] as [string, string],
    board: [],
    audits: audit.audits,
    totalLeakedBb: audit.totalLeakedBb,
  }));
}

// ── Helpers ──

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

function emptyStats(): FastBattleBehaviorStats {
  return {
    handsPlayed: 0,
    handsWon: 0,
    vpip: 0,
    pfr: 0,
    threeBet: 0,
    foldTo3Bet: 0,
    cbetFlop: 0,
    cbetTurn: 0,
    aggressionFactor: 0,
    wtsd: 0,
    wsd: 0,
    netChips: 0,
    netBb: 0,
    decisionsPerHour: 0,
  };
}
