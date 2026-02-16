/**
 * GTO Audit Pipeline Types
 *
 * Types for the auto-capture → audit → dashboard pipeline.
 * Used by: game-server (producer), advice-engine (compute), web (consumer).
 */

import type { HandAction, Street, StrategyMix, PlayerActionType, Position } from './index.js';

// ── Line & Spot Classification ──

export type LineTag =
  | 'CBET'
  | 'DELAYED_CBET'
  | 'BARREL'
  | 'DOUBLE_BARREL'
  | 'TRIPLE_BARREL'
  | 'PROBE'
  | 'DONK_BET'
  | 'CHECK_RAISE'
  | 'XR_TURN'
  | 'XR_RIVER'
  | 'FLOAT_BET'
  | 'OVERBET'
  | 'LIMP'
  | 'SQUEEZE'
  | 'THREE_BET'
  | 'FOUR_BET_PLUS'
  | 'COLD_4BET'
  | 'CHECK_BACK'
  | 'LEAD_RIVER';

export type SpotType = 'SRP' | '3BP' | '4BP' | 'LIMPED' | 'SQUEEZE_POT';

export type ActionDeviationType =
  | 'OVERFOLD'
  | 'UNDERFOLD'
  | 'OVERBLUFF'
  | 'UNDERBLUFF'
  | 'OVERCALL'
  | 'UNDERCALL'
  | 'CORRECT';

export type StackDepthCategory = 'short' | 'medium' | 'standard' | 'deep';

// ── Decision Point (captured at each hero action) ──

export interface DecisionPoint {
  /** Unique id for this decision point */
  id: string;
  /** Reference to the hand */
  handHistoryId: string;
  handId: string;
  /** Hero info */
  heroUserId: string;
  heroSeat: number;
  heroPosition: string;
  heroCards: [string, string];
  /** Game state at decision */
  street: Street;
  board: string[];
  pot: number;
  toCall: number;
  effectiveStackBb: number;
  stackDepthCategory: StackDepthCategory;
  /** What hero actually did */
  actualAction: PlayerActionType;
  actualAmount: number;
  /** Contextual tags */
  spotType: SpotType;
  lineTags: LineTag[];
  /** Timing */
  actionIndex: number;
  timestamp: number;
}

// ── GTO Audit Result (computed per decision point) ──

export interface GtoAuditResult {
  /** Reference to the decision point */
  decisionPointId: string;
  handId: string;
  heroUserId: string;
  /** GTO recommended strategy */
  gtoMix: StrategyMix;
  recommendedAction: 'raise' | 'call' | 'fold';
  /** What hero actually did (denormalized for query convenience) */
  actualAction: PlayerActionType;
  /** Deviation metrics */
  deviationScore: number;       // 0 = perfect GTO, 1 = worst possible
  evDiffBb: number;             // EV leaked in big blinds (negative = leaked)
  evDiffChips: number;          // EV leaked in chips
  /** Classification */
  deviationType: ActionDeviationType;
  /** Context (denormalized for dashboards) */
  street: Street;
  spotType: SpotType;
  lineTags: LineTag[];
  heroPosition: string;
  stackDepthCategory: StackDepthCategory;
  /** Math context */
  equity?: number;
  mdf?: number;
  alpha?: number;
  /** Timing */
  computedAt: number;
}

// ── Hand Audit Summary (one per hand per hero) ──

export interface HandAuditSummary {
  handId: string;
  handHistoryId: string;
  heroUserId: string;
  /** Aggregate metrics for the hand */
  totalLeakedBb: number;
  totalLeakedChips: number;
  decisionCount: number;
  worstDeviationScore: number;
  /** Per-decision audits */
  audits: GtoAuditResult[];
  /** Line tags for the whole hand */
  handLineTags: LineTag[];
  spotType: SpotType;
  /** Timing */
  computedAt: number;
}

// ── Session Leak Summary (aggregated across hands in a session) ──

export interface SessionLeakSummary {
  sessionId: string;
  heroUserId: string;
  /** Headline numbers */
  totalLeakedBb: number;
  totalLeakedChips: number;
  handsPlayed: number;
  handsAudited: number;
  leakedBbPer100: number;
  /** Breakdown by street */
  byStreet: Record<string, StreetLeakBucket>;
  /** Breakdown by spot type */
  bySpotType: Record<SpotType, SpotLeakBucket>;
  /** Breakdown by line tag */
  byLineTag: Record<string, LineLeakBucket>;
  /** Breakdown by action deviation */
  byDeviation: Record<ActionDeviationType, DeviationBucket>;
  /** Top recurring leaks (ranked by total leaked bb) */
  topLeaks: LeakCategory[];
  /** Suggested drills */
  suggestedDrills: DrillSuggestion[];
  computedAt: number;
}

export interface StreetLeakBucket {
  street: string;
  leakedBb: number;
  decisionCount: number;
  avgDeviationScore: number;
}

export interface SpotLeakBucket {
  spotType: SpotType;
  leakedBb: number;
  decisionCount: number;
  avgDeviationScore: number;
}

export interface LineLeakBucket {
  lineTag: string;
  leakedBb: number;
  decisionCount: number;
  avgDeviationScore: number;
}

export interface DeviationBucket {
  deviationType: ActionDeviationType;
  count: number;
  leakedBb: number;
}

export interface LeakCategory {
  rank: number;
  label: string;
  description: string;
  leakedBb: number;
  frequency: number;      // how often this leak occurs as fraction of total decisions
  spotType?: SpotType;
  street?: string;
  lineTag?: string;
  deviationType?: ActionDeviationType;
}

export interface DrillSuggestion {
  leakCategory: string;
  drillType: 'replay' | 'scenario' | 'quiz';
  title: string;
  description: string;
  /** Deep link params for navigation */
  linkParams?: {
    handHistoryId?: string;
    decisionPointId?: string;
    spotType?: SpotType;
    lineTag?: string;
  };
}

// ── Exploit / Node Lock Types (Phase 2 placeholder) ──

export interface VillainModelParams {
  foldToCbet: number;         // 0-1
  bluffFreqFlop: number;      // 0-1
  bluffFreqTurn: number;      // 0-1
  bluffFreqRiver: number;     // 0-1
  aggressionFactor: number;   // 0-5+
  riverUnderbluff: boolean;
  riverOverbluff: boolean;
}

export const DEFAULT_VILLAIN_MODEL: VillainModelParams = {
  foldToCbet: 0.5,
  bluffFreqFlop: 0.4,
  bluffFreqTurn: 0.3,
  bluffFreqRiver: 0.2,
  aggressionFactor: 1.0,
  riverUnderbluff: false,
  riverOverbluff: false,
};

export interface ExploitResult {
  gtoMix: StrategyMix;
  exploitMix: StrategyMix;
  evShiftBb: number;
  villainModel: VillainModelParams;
  label: string;   // e.g. "Exploit (vs underbluff): check 85%"
}

// ── Club Training Metrics (Phase 3 placeholder) ──

export interface ClubMemberTrainingMetrics {
  clubId: string;
  userId: string;
  userName: string;
  /** GTO adherence score: 0-100 */
  gtoAdherenceScore: number;
  /** Leaked bb per 100 hands */
  leakedBbPer100: number;
  /** Total hands analyzed */
  handsAnalyzed: number;
  /** Top 3 leak categories */
  topLeaks: LeakCategory[];
  /** Improvement trend: positive = improving */
  improvementTrendPct: number;
  updatedAt: number;
}

export interface ClubTrainingLeaderboard {
  clubId: string;
  /** Ranked by GTO adherence score (desc) */
  mostAligned: ClubMemberTrainingMetrics[];
  /** Ranked by improvement trend (desc) */
  mostImproved: ClubMemberTrainingMetrics[];
  computedAt: number;
}

// ── Socket Events for Audit Pipeline ──

export interface AuditEvents {
  /** Server → Client: hand audit completed */
  hand_audit_complete: HandAuditSummary;
  /** Server → Client: session leak summary updated */
  session_leak_update: SessionLeakSummary;
}
