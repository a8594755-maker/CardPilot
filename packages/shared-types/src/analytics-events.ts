// ===== Club Analytics Socket Events =====

import type {
  PlayerAnalytics,
  ProfitDataPoint,
  HourlyHeatmapCell,
  ClubOverviewAnalytics,
  ActivePlayersTrendPoint,
  PlayerSessionStat,
  AnalyticsTimeRange,
  ExportDataType,
} from './analytics-types.js';

// ── Client → Server Payloads ──

export interface ClubAnalyticsGetPayload {
  clubId: string;
  userId?: string; // defaults to self
  timeRange?: AnalyticsTimeRange;
}

export interface ClubProfitChartGetPayload {
  clubId: string;
  userId?: string;
  timeRange?: AnalyticsTimeRange;
}

export interface ClubHourlyHeatmapGetPayload {
  clubId: string;
  userId?: string;
}

export interface ClubOverviewAnalyticsGetPayload {
  clubId: string;
  timeRange?: AnalyticsTimeRange;
}

export interface ClubActivePlayersTrendGetPayload {
  clubId: string;
  timeRange?: AnalyticsTimeRange;
}

export interface ClubSessionsListPayload {
  clubId: string;
  userId?: string;
  limit?: number;
  offset?: number;
}

export interface ClubExportDataPayload {
  clubId: string;
  exportType: ExportDataType;
  timeRange?: AnalyticsTimeRange;
}

// ── Server → Client Payloads ──

export interface ClubAnalyticsResponsePayload {
  clubId: string;
  userId: string;
  analytics: PlayerAnalytics;
}

export interface ClubProfitChartResponsePayload {
  clubId: string;
  userId: string;
  data: ProfitDataPoint[];
}

export interface ClubHourlyHeatmapResponsePayload {
  clubId: string;
  userId: string;
  data: HourlyHeatmapCell[];
}

export interface ClubOverviewAnalyticsResponsePayload {
  clubId: string;
  overview: ClubOverviewAnalytics;
}

export interface ClubActivePlayersTrendResponsePayload {
  clubId: string;
  data: ActivePlayersTrendPoint[];
}

export interface ClubSessionsListResponsePayload {
  clubId: string;
  userId: string;
  sessions: PlayerSessionStat[];
  hasMore: boolean;
}

export interface ClubExportDataResponsePayload {
  clubId: string;
  exportType: ExportDataType;
  csvData: string;
  fileName: string;
}

// ── Event Maps ──

export interface AnalyticsClientToServerEvents {
  club_analytics_get: (payload: ClubAnalyticsGetPayload) => void;
  club_profit_chart_get: (payload: ClubProfitChartGetPayload) => void;
  club_hourly_heatmap_get: (payload: ClubHourlyHeatmapGetPayload) => void;
  club_overview_analytics_get: (payload: ClubOverviewAnalyticsGetPayload) => void;
  club_active_players_trend_get: (payload: ClubActivePlayersTrendGetPayload) => void;
  club_sessions_list: (payload: ClubSessionsListPayload) => void;
  club_export_data: (payload: ClubExportDataPayload) => void;
}

export interface AnalyticsServerToClientEvents {
  club_analytics_response: (payload: ClubAnalyticsResponsePayload) => void;
  club_profit_chart_response: (payload: ClubProfitChartResponsePayload) => void;
  club_hourly_heatmap_response: (payload: ClubHourlyHeatmapResponsePayload) => void;
  club_overview_analytics_response: (payload: ClubOverviewAnalyticsResponsePayload) => void;
  club_active_players_trend_response: (payload: ClubActivePlayersTrendResponsePayload) => void;
  club_sessions_list_response: (payload: ClubSessionsListResponsePayload) => void;
  club_export_data_response: (payload: ClubExportDataResponsePayload) => void;
  club_analytics_error: (payload: { code: string; message: string }) => void;
}
