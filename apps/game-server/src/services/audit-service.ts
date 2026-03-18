/**
 * Audit Service
 *
 * Server-side orchestrator for the GTO audit pipeline.
 * Responsibilities:
 *   1. Accept hand-end data from server.ts
 *   2. Run AuditEngine to produce decision points + audit results
 *   3. Persist to Supabase (decision_points, gto_audits, session_leak_summaries)
 *   4. Emit audit results to connected clients via Socket.IO
 *
 * All audit work runs asynchronously after hand settlement — never blocks gameplay.
 */

import type { SupabaseClient } from '@supabase/supabase-js';
import type { Server as SocketServer } from 'socket.io';
import {
  AuditEngine,
  aggregateSessionLeaks,
  type AuditHandInput,
  type AuditHandResult,
} from '@cardpilot/advice-engine';
import type {
  DecisionPoint,
  GtoAuditResult,
  HandAuditSummary,
  SessionLeakSummary,
} from '@cardpilot/shared-types';

// ── Public API ──

export interface AuditServiceConfig {
  /** Supabase admin (service_role) client. Null = persistence disabled. */
  supabaseAdmin: SupabaseClient | null;
  /** Socket.IO server for emitting results to clients. Null = emit disabled. */
  io: SocketServer | null;
  /** Max concurrent audit jobs to avoid overloading the event loop. */
  maxConcurrentAudits?: number;
  /** Optional callback invoked after each audit completes (e.g. for fast-battle session tracking). */
  onAuditComplete?: (userId: string, summary: HandAuditSummary) => void;
}

export class AuditService {
  private readonly engine = new AuditEngine();
  private readonly supabase: SupabaseClient | null;
  private readonly io: SocketServer | null;
  private readonly maxConcurrent: number;
  private readonly onAuditCompleteCallback?: (userId: string, summary: HandAuditSummary) => void;
  private activeJobs = 0;

  // In-memory session audit cache for aggregation (sessionId → userId → HandAuditSummary[])
  private readonly sessionCache = new Map<string, Map<string, HandAuditSummary[]>>();

  constructor(config: AuditServiceConfig) {
    this.supabase = config.supabaseAdmin;
    this.io = config.io;
    this.maxConcurrent = config.maxConcurrentAudits ?? 4;
    this.onAuditCompleteCallback = config.onAuditComplete;
    console.log(
      `[audit-service] initialized: supabase=${!!this.supabase}, io=${!!this.io}, maxConcurrent=${this.maxConcurrent}`,
    );
  }

  /**
   * Queue a hand audit. Called by server.ts after hand settlement.
   * Runs fully async — never blocks the caller.
   */
  queueHandAudit(input: AuditHandInput, sessionId?: string): void {
    if (this.activeJobs >= this.maxConcurrent) {
      console.warn('[audit-service] audit queue full, dropping hand', input.handId);
      return;
    }

    this.activeJobs++;
    this.runHandAudit(input, sessionId).finally(() => {
      this.activeJobs--;
    });
  }

  /**
   * Get the current session leak summary from cache.
   */
  getSessionLeakSummary(sessionId: string, userId: string): SessionLeakSummary | null {
    const sessionMap = this.sessionCache.get(sessionId);
    if (!sessionMap) return null;

    const summaries = sessionMap.get(userId);
    if (!summaries || summaries.length === 0) return null;

    return aggregateSessionLeaks(sessionId, userId, summaries);
  }

  /**
   * Clear session cache (e.g. when room closes).
   */
  clearSession(sessionId: string): void {
    this.sessionCache.delete(sessionId);
  }

  // ── Internal ──

  private async runHandAudit(input: AuditHandInput, sessionId?: string): Promise<void> {
    try {
      const result = await this.engine.auditHand(input);

      // Cache for session aggregation
      if (sessionId) {
        this.cacheHandSummary(sessionId, input.heroUserId, result.summary);
      }

      // Persist to Supabase
      await this.persist(result, sessionId);

      // Emit to client
      this.emitToClient(input.heroUserId, input.tableId, result.summary, sessionId);

      // Notify external listeners (e.g. fast-battle pool manager)
      if (this.onAuditCompleteCallback) {
        try {
          this.onAuditCompleteCallback(input.heroUserId, result.summary);
        } catch {
          /* don't let callback errors break audit flow */
        }
      }

      console.log(
        `[audit-service] hand=${input.handId} hero=${input.heroUserId} ` +
          `decisions=${result.summary.decisionCount} leaked=${result.summary.totalLeakedBb.toFixed(2)}bb`,
      );
    } catch (err) {
      console.error(`[audit-service] audit failed for hand=${input.handId}:`, err);
    }
  }

  private cacheHandSummary(sessionId: string, userId: string, summary: HandAuditSummary): void {
    if (!this.sessionCache.has(sessionId)) {
      this.sessionCache.set(sessionId, new Map());
    }
    const sessionMap = this.sessionCache.get(sessionId)!;
    if (!sessionMap.has(userId)) {
      sessionMap.set(userId, []);
    }
    sessionMap.get(userId)!.push(summary);
  }

  private async persist(result: AuditHandResult, sessionId?: string): Promise<void> {
    if (!this.supabase) return;

    try {
      // 1. Persist decision points
      if (result.decisionPoints.length > 0) {
        await this.persistDecisionPoints(result.decisionPoints);
      }

      // 2. Persist GTO audits
      if (result.summary.audits.length > 0) {
        await this.persistGtoAudits(result.summary.audits);
      }

      // 3. Update session leak summary
      if (sessionId) {
        await this.updateSessionLeakSummary(sessionId, result.summary.heroUserId);
      }
    } catch (err) {
      console.error('[audit-service] persistence failed:', err);
    }
  }

  private async persistDecisionPoints(points: DecisionPoint[]): Promise<void> {
    if (!this.supabase || points.length === 0) return;

    const rows = points.map((dp) => ({
      id: dp.id,
      hand_history_id: dp.handHistoryId,
      hand_id: dp.handId,
      hero_user_id: dp.heroUserId,
      hero_seat: dp.heroSeat,
      hero_position: dp.heroPosition,
      hero_cards: JSON.stringify(dp.heroCards),
      street: dp.street,
      board: JSON.stringify(dp.board),
      pot: dp.pot,
      to_call: dp.toCall,
      effective_stack_bb: dp.effectiveStackBb,
      stack_depth_category: dp.stackDepthCategory,
      actual_action: dp.actualAction,
      actual_amount: dp.actualAmount,
      spot_type: dp.spotType,
      line_tags: JSON.stringify(dp.lineTags),
      action_index: dp.actionIndex,
    }));

    const { error } = await this.supabase
      .from('decision_points')
      .upsert(rows, { onConflict: 'id' });

    if (error) {
      console.warn('[audit-service] decision_points upsert failed:', error.message);
    }
  }

  private async persistGtoAudits(audits: GtoAuditResult[]): Promise<void> {
    if (!this.supabase || audits.length === 0) return;

    const rows = audits.map((a) => ({
      decision_point_id: a.decisionPointId,
      hand_id: a.handId,
      hero_user_id: a.heroUserId,
      gto_mix_raise: a.gtoMix.raise,
      gto_mix_call: a.gtoMix.call,
      gto_mix_fold: a.gtoMix.fold,
      recommended_action: a.recommendedAction,
      actual_action: a.actualAction,
      deviation_score: a.deviationScore,
      ev_diff_bb: a.evDiffBb,
      ev_diff_chips: a.evDiffChips,
      deviation_type: a.deviationType,
      street: a.street,
      spot_type: a.spotType,
      line_tags: JSON.stringify(a.lineTags),
      hero_position: a.heroPosition,
      stack_depth_category: a.stackDepthCategory,
      equity: a.equity ?? null,
      mdf: a.mdf ?? null,
      alpha: a.alpha ?? null,
    }));

    const { error } = await this.supabase
      .from('gto_audits')
      .upsert(rows, { onConflict: 'decision_point_id' });

    if (error) {
      console.warn('[audit-service] gto_audits upsert failed:', error.message);
    }
  }

  private async updateSessionLeakSummary(sessionId: string, userId: string): Promise<void> {
    if (!this.supabase) return;

    const summary = this.getSessionLeakSummary(sessionId, userId);
    if (!summary) return;

    const row = {
      room_session_id: sessionId,
      hero_user_id: userId,
      total_leaked_bb: summary.totalLeakedBb,
      total_leaked_chips: summary.totalLeakedChips,
      hands_played: summary.handsPlayed,
      hands_audited: summary.handsAudited,
      leaked_bb_per_100: summary.leakedBbPer100,
      by_street: JSON.stringify(summary.byStreet),
      by_spot_type: JSON.stringify(summary.bySpotType),
      by_line_tag: JSON.stringify(summary.byLineTag),
      by_deviation: JSON.stringify(summary.byDeviation),
      top_leaks: JSON.stringify(summary.topLeaks),
      suggested_drills: JSON.stringify(summary.suggestedDrills),
      updated_at: new Date().toISOString(),
    };

    const { error } = await this.supabase
      .from('session_leak_summaries')
      .upsert(row, { onConflict: 'room_session_id,hero_user_id' });

    if (error) {
      console.warn('[audit-service] session_leak_summaries upsert failed:', error.message);
    }
  }

  private emitToClient(
    userId: string,
    tableId: string,
    summary: HandAuditSummary,
    sessionId?: string,
  ): void {
    if (!this.io) return;

    // Emit hand audit to the hero's room
    this.io.to(tableId).emit('hand_audit_complete', {
      userId,
      summary,
    });

    // Emit session leak update if available
    if (sessionId) {
      const sessionSummary = this.getSessionLeakSummary(sessionId, userId);
      if (sessionSummary) {
        this.io.to(tableId).emit('session_leak_update', {
          userId,
          summary: sessionSummary,
        });
      }
    }
  }
}
