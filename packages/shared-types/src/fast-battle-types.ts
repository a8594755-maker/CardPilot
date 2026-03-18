/**
 * Fast Battle Types
 *
 * Types for the "Infinite Fast Battle" training mode.
 * Used by: game-server (pool manager), web (UI + hook).
 */

import type { GtoAuditResult, SessionLeakSummary, DrillSuggestion } from './audit-types.js';
import type { Street, PlayerActionType } from './index.js';

// ── Session Configuration ──

export interface FastBattleConfig {
  targetHandCount: number; // 12 | 100 | 500 | 1000
  bigBlind?: number; // default 100
  botModelVersion?: string; // default 'v4'
}

// ── Socket Event Payloads: Client → Server ──

export interface FastBattleStartPayload {
  targetHandCount: number;
  bigBlind?: number;
  botModelVersion?: string;
}

// ── Socket Event Payloads: Server → Client ──

export interface FastBattleSessionStartedPayload {
  sessionId: string;
  targetHandCount: number;
  bigBlind: number;
}

export interface FastBattleTableAssignedPayload {
  tableId: string;
  roomCode: string;
  seat: number; // always 1
  buyIn: number;
  handNumber: number; // 1-indexed in session
  totalHands: number;
}

export interface FastBattleHandResultPayload {
  handId: string;
  handNumber: number;
  result: number; // net chips won/lost
  heroPosition: string;
  holeCards: [string, string];
  board: string[];
  wentToShowdown: boolean;
  cumulativeResult: number; // running total
}

export interface FastBattleProgressPayload {
  handsPlayed: number;
  targetHandCount: number;
  cumulativeResult: number;
  decisionsPerHour: number;
}

export interface FastBattleSessionEndedPayload {
  sessionId: string;
  report: FastBattleReport;
}

export interface FastBattleErrorPayload {
  message: string;
  code: 'NO_ROOM_AVAILABLE' | 'SESSION_NOT_FOUND' | 'ALREADY_IN_SESSION';
}

// ── Analytics Report ──

export interface FastBattleReport {
  sessionId: string;
  // A. Behavior stats
  stats: FastBattleBehaviorStats;
  // B. Leak summary (from existing audit pipeline)
  sessionLeak: SessionLeakSummary | null;
  // C. Problem hands (top 10)
  problemHands: FastBattleProblemHand[];
  // D. Training recommendations
  recommendations: DrillSuggestion[];
  // E. Full hand records (for session review)
  handRecords: FastBattleHandRecord[];
  // Summary
  handCount: number;
  durationMs: number;
}

export interface FastBattleBehaviorStats {
  handsPlayed: number;
  handsWon: number;
  vpip: number; // voluntarily put $ in pot %
  pfr: number; // preflop raise %
  threeBet: number; // 3-bet %
  foldTo3Bet: number; // fold to 3-bet %
  cbetFlop: number; // c-bet frequency (flop)
  cbetTurn: number; // c-bet frequency (turn)
  aggressionFactor: number; // (bets + raises) / calls
  wtsd: number; // went to showdown %
  wsd: number; // won at showdown %
  netChips: number;
  netBb: number;
  decisionsPerHour: number;
}

export interface FastBattleProblemHand {
  rank: number;
  handId: string;
  heroPosition: string;
  holeCards: [string, string];
  board: string[];
  audits: GtoAuditResult[];
  totalLeakedBb: number;
}

// ── Internal Session Data (server-side, but shared for type safety) ──

export interface FastBattleHandRecord {
  handId: string;
  tableId: string;
  heroSeat: number;
  heroPosition: string;
  holeCards: [string, string];
  /** All players' hole cards: seat → [card1, card2] */
  allHoleCards: Record<number, [string, string]>;
  board: string[];
  heroActions: FastBattleHeroAction[];
  result: number; // net chips won/lost
  totalPot: number;
  wentToShowdown: boolean;
  startedAt: number;
  endedAt: number;
}

export interface FastBattleHeroAction {
  street: Street;
  action: PlayerActionType;
  amount: number;
  pot: number;
  toCall: number;
}
