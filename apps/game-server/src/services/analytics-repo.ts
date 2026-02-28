/**
 * Analytics persistence adapter — Supabase-backed queries for club analytics.
 * Uses the service-role client (same pattern as ClubRepo).
 *
 * Every public method is a no-op when Supabase is not configured,
 * allowing the server to run in offline / dev mode.
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import type {
  PlayerAnalytics,
  ProfitDataPoint,
  HourlyHeatmapCell,
  ClubOverviewAnalytics,
  ActivePlayersTrendPoint,
  PlayerSessionStat,
  AnalyticsTimeRange,
} from "@cardpilot/shared-types";
import { logInfo, logWarn } from "../logger";

// ── Helpers ──

function timeRangeToDate(range: AnalyticsTimeRange): string {
  const now = new Date();
  switch (range) {
    case "7d":
      now.setDate(now.getDate() - 7);
      return now.toISOString().slice(0, 10);
    case "30d":
      now.setDate(now.getDate() - 30);
      return now.toISOString().slice(0, 10);
    case "90d":
      now.setDate(now.getDate() - 90);
      return now.toISOString().slice(0, 10);
    case "all":
      return "2000-01-01";
  }
}

function rowToSession(r: Record<string, unknown>): PlayerSessionStat {
  return {
    id: String(r.id),
    clubId: String(r.club_id),
    userId: String(r.user_id),
    tableId: String(r.table_id),
    tableName: String(r.table_name ?? ""),
    startedAt: String(r.started_at),
    endedAt: r.ended_at ? String(r.ended_at) : null,
    hands: Number(r.hands ?? 0),
    buyIn: Number(r.buy_in ?? 0),
    cashOut: Number(r.cash_out ?? 0),
    net: Number(r.net ?? 0),
    peakStack: Number(r.peak_stack ?? 0),
    vpipHands: Number(r.vpip_hands ?? 0),
    pfrHands: Number(r.pfr_hands ?? 0),
  };
}

// ── AnalyticsRepo ──

export class AnalyticsRepo {
  private readonly db: SupabaseClient | null;

  constructor() {
    const disabled = process.env.DISABLE_SUPABASE === "1";
    const url = disabled ? undefined : process.env.SUPABASE_URL;
    const serviceKey = disabled ? undefined : process.env.SUPABASE_SERVICE_ROLE_KEY;
    this.db = url && serviceKey
      ? createClient(url, serviceKey, { auth: { persistSession: false } })
      : null;

    logInfo({
      event: "analytics_repo.init",
      message: this.db ? "AnalyticsRepo connected to Supabase" : `AnalyticsRepo running in offline mode${disabled ? " (DISABLED via env)" : " (no Supabase)"}`,
    });
  }

  enabled(): boolean {
    return this.db !== null;
  }

  // ═══════════════ PLAYER ANALYTICS ═══════════════

  async getPlayerAnalytics(
    clubId: string,
    userId: string,
    timeRange: AnalyticsTimeRange = "30d",
  ): Promise<PlayerAnalytics> {
    const empty: PlayerAnalytics = {
      totalHands: 0, totalSessions: 0, totalBuyIn: 0, totalCashOut: 0,
      totalNet: 0, totalRake: 0, vpipHands: 0, pfrHands: 0,
      winningDays: 0, losingDays: 0, breakEvenDays: 0,
      vpipPercent: 0, pfrPercent: 0, winRateBbPer100: 0, avgProfitPerSession: 0,
    };
    if (!this.db) return empty;

    const dayFrom = timeRangeToDate(timeRange);
    const { data, error } = await this.db.rpc("club_get_player_analytics", {
      _club_id: clubId,
      _user_id: userId,
      _day_from: dayFrom,
    });

    if (error) {
      logWarn({ event: "analytics_repo.getPlayerAnalytics.failed", message: error.message });
      throw new Error(`Failed to get player analytics: ${error.message}`);
    }

    const row = Array.isArray(data) ? data[0] : data;
    if (!row) return empty;

    const totalHands = Number(row.total_hands ?? 0);
    const totalSessions = Number(row.total_sessions ?? 0);
    const vpipHands = Number(row.vpip_hands ?? 0);
    const pfrHands = Number(row.pfr_hands ?? 0);
    const totalNet = Number(row.total_net ?? 0);

    return {
      totalHands,
      totalSessions,
      totalBuyIn: Number(row.total_buy_in ?? 0),
      totalCashOut: Number(row.total_cash_out ?? 0),
      totalNet,
      totalRake: Number(row.total_rake ?? 0),
      vpipHands,
      pfrHands,
      winningDays: Number(row.winning_days ?? 0),
      losingDays: Number(row.losing_days ?? 0),
      breakEvenDays: Number(row.break_even_days ?? 0),
      vpipPercent: totalHands > 0 ? Math.round((vpipHands / totalHands) * 100) : 0,
      pfrPercent: totalHands > 0 ? Math.round((pfrHands / totalHands) * 100) : 0,
      winRateBbPer100: 0, // requires bigBlind context — computed on client
      avgProfitPerSession: totalSessions > 0 ? Math.round(totalNet / totalSessions) : 0,
    };
  }

  // ═══════════════ PROFIT CHART ═══════════════

  async getProfitOverTime(
    clubId: string,
    userId: string,
    timeRange: AnalyticsTimeRange = "30d",
  ): Promise<ProfitDataPoint[]> {
    if (!this.db) return [];

    const dayFrom = timeRangeToDate(timeRange);
    const { data, error } = await this.db.rpc("club_get_profit_over_time", {
      _club_id: clubId,
      _user_id: userId,
      _day_from: dayFrom,
    });

    if (error) {
      logWarn({ event: "analytics_repo.getProfitOverTime.failed", message: error.message });
      throw new Error(`Failed to get profit data: ${error.message}`);
    }

    return (data ?? []).map((row: Record<string, unknown>) => ({
      day: String(row.day),
      dailyNet: Number(row.daily_net ?? 0),
      cumulativeNet: Number(row.cumulative_net ?? 0),
      hands: Number(row.hands ?? 0),
    }));
  }

  // ═══════════════ HOURLY HEATMAP ═══════════════

  async getHourlyHeatmap(
    clubId: string,
    userId: string,
  ): Promise<HourlyHeatmapCell[]> {
    if (!this.db) return [];

    const { data, error } = await this.db.rpc("club_get_hourly_heatmap", {
      _club_id: clubId,
      _user_id: userId,
    });

    if (error) {
      logWarn({ event: "analytics_repo.getHourlyHeatmap.failed", message: error.message });
      throw new Error(`Failed to get heatmap data: ${error.message}`);
    }

    return (data ?? []).map((row: Record<string, unknown>) => ({
      dayOfWeek: Number(row.day_of_week),
      hourOfDay: Number(row.hour_of_day),
      hands: Number(row.hands ?? 0),
      net: Number(row.net ?? 0),
    }));
  }

  // ═══════════════ CLUB OVERVIEW ═══════════════

  async getOverviewAnalytics(
    clubId: string,
    timeRange: AnalyticsTimeRange = "30d",
  ): Promise<ClubOverviewAnalytics> {
    const empty: ClubOverviewAnalytics = {
      totalHands: 0, uniquePlayers: 0, totalBuyIn: 0,
      totalCashOut: 0, totalRake: 0, totalSessions: 0, avgHandsPerPlayer: 0,
    };
    if (!this.db) return empty;

    const dayFrom = timeRangeToDate(timeRange);
    const { data, error } = await this.db.rpc("club_get_overview_analytics", {
      _club_id: clubId,
      _day_from: dayFrom,
    });

    if (error) {
      logWarn({ event: "analytics_repo.getOverviewAnalytics.failed", message: error.message });
      throw new Error(`Failed to get overview analytics: ${error.message}`);
    }

    const row = Array.isArray(data) ? data[0] : data;
    if (!row) return empty;

    return {
      totalHands: Number(row.total_hands ?? 0),
      uniquePlayers: Number(row.unique_players ?? 0),
      totalBuyIn: Number(row.total_buy_in ?? 0),
      totalCashOut: Number(row.total_cash_out ?? 0),
      totalRake: Number(row.total_rake ?? 0),
      totalSessions: Number(row.total_sessions ?? 0),
      avgHandsPerPlayer: Number(row.avg_hands_per_player ?? 0),
    };
  }

  // ═══════════════ ACTIVE PLAYERS TREND ═══════════════

  async getActivePlayersTrend(
    clubId: string,
    timeRange: AnalyticsTimeRange = "30d",
  ): Promise<ActivePlayersTrendPoint[]> {
    if (!this.db) return [];

    const dayFrom = timeRangeToDate(timeRange);
    const { data, error } = await this.db.rpc("club_get_active_players_trend", {
      _club_id: clubId,
      _day_from: dayFrom,
    });

    if (error) {
      logWarn({ event: "analytics_repo.getActivePlayersTrend.failed", message: error.message });
      throw new Error(`Failed to get active players trend: ${error.message}`);
    }

    return (data ?? []).map((row: Record<string, unknown>) => ({
      day: String(row.day),
      activePlayers: Number(row.active_players ?? 0),
      totalHands: Number(row.total_hands ?? 0),
      totalNet: Number(row.total_net ?? 0),
    }));
  }

  // ═══════════════ SESSIONS ═══════════════

  async listSessions(
    clubId: string,
    userId: string,
    limit = 50,
    offset = 0,
  ): Promise<{ sessions: PlayerSessionStat[]; hasMore: boolean }> {
    if (!this.db) return { sessions: [], hasMore: false };

    const safeLimit = Math.max(1, Math.min(limit, 200));
    const { data, error } = await this.db
      .from("club_player_session_stats")
      .select("*")
      .eq("club_id", clubId)
      .eq("user_id", userId)
      .order("started_at", { ascending: false })
      .range(offset, offset + safeLimit);

    if (error) {
      logWarn({ event: "analytics_repo.listSessions.failed", message: error.message });
      throw new Error(`Failed to list sessions: ${error.message}`);
    }

    const rows = data ?? [];
    const hasMore = rows.length > safeLimit;
    const slice = hasMore ? rows.slice(0, safeLimit) : rows;

    return {
      sessions: slice.map((row: unknown) => rowToSession(row as Record<string, unknown>)),
      hasMore,
    };
  }

  // ═══════════════ CSV EXPORT ═══════════════

  async exportPlayerStats(
    clubId: string,
    timeRange: AnalyticsTimeRange = "30d",
  ): Promise<string> {
    if (!this.db) return "";

    const dayFrom = timeRangeToDate(timeRange);
    const { data, error } = await this.db
      .from("club_player_daily_stats")
      .select("*")
      .eq("club_id", clubId)
      .gte("day", dayFrom)
      .order("day", { ascending: false });

    if (error) {
      logWarn({ event: "analytics_repo.exportPlayerStats.failed", message: error.message });
      return "";
    }

    const rows = data ?? [];
    if (rows.length === 0) return "";

    const headers = "day,user_id,hands,buy_in,cash_out,net,rake,vpip_hands,pfr_hands";
    const csvRows = rows.map((r: Record<string, unknown>) =>
      `${r.day},${r.user_id},${r.hands},${r.buy_in},${r.cash_out},${r.net},${r.rake},${r.vpip_hands ?? 0},${r.pfr_hands ?? 0}`
    );
    return [headers, ...csvRows].join("\n");
  }

  async exportSessions(
    clubId: string,
    userId: string,
    timeRange: AnalyticsTimeRange = "30d",
  ): Promise<string> {
    if (!this.db) return "";

    const dayFrom = timeRangeToDate(timeRange);
    const { data, error } = await this.db
      .from("club_player_session_stats")
      .select("*")
      .eq("club_id", clubId)
      .eq("user_id", userId)
      .gte("started_at", dayFrom)
      .order("started_at", { ascending: false });

    if (error) {
      logWarn({ event: "analytics_repo.exportSessions.failed", message: error.message });
      return "";
    }

    const rows = data ?? [];
    if (rows.length === 0) return "";

    const headers = "started_at,ended_at,table_name,hands,buy_in,cash_out,net,peak_stack,vpip_hands,pfr_hands";
    const csvRows = rows.map((r: Record<string, unknown>) =>
      `${r.started_at},${r.ended_at ?? ""},${r.table_name},${r.hands},${r.buy_in},${r.cash_out},${r.net},${r.peak_stack},${r.vpip_hands ?? 0},${r.pfr_hands ?? 0}`
    );
    return [headers, ...csvRows].join("\n");
  }
}
