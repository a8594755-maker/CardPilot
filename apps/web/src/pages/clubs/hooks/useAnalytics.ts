import { useState, useEffect, useCallback, useRef } from 'react';
import type { Socket } from 'socket.io-client';
import type {
  PlayerAnalytics,
  ProfitDataPoint,
  HourlyHeatmapCell,
  ClubOverviewAnalytics,
  ActivePlayersTrendPoint,
  PlayerSessionStat,
  AnalyticsTimeRange,
  ExportDataType,
  ClubAnalyticsResponsePayload,
  ClubProfitChartResponsePayload,
  ClubHourlyHeatmapResponsePayload,
  ClubOverviewAnalyticsResponsePayload,
  ClubActivePlayersTrendResponsePayload,
  ClubSessionsListResponsePayload,
  ClubExportDataResponsePayload,
} from '@cardpilot/shared-types';

export interface AnalyticsActions {
  loadAnalytics: (timeRange?: AnalyticsTimeRange) => void;
  loadProfitChart: (timeRange?: AnalyticsTimeRange) => void;
  loadHeatmap: () => void;
  loadOverview: (timeRange?: AnalyticsTimeRange) => void;
  loadActivePlayersTrend: (timeRange?: AnalyticsTimeRange) => void;
  loadSessions: (limit?: number, offset?: number) => void;
  exportData: (exportType: ExportDataType, timeRange?: AnalyticsTimeRange) => void;
  setTimeRange: (range: AnalyticsTimeRange) => void;
  loadAll: (range?: AnalyticsTimeRange) => void;
}

export interface AnalyticsState {
  analytics: PlayerAnalytics | null;
  profitData: ProfitDataPoint[];
  heatmapData: HourlyHeatmapCell[];
  overviewAnalytics: ClubOverviewAnalytics | null;
  activePlayersTrend: ActivePlayersTrendPoint[];
  sessions: PlayerSessionStat[];
  sessionsHasMore: boolean;
  timeRange: AnalyticsTimeRange;
  loading: boolean;
}

export function useAnalytics(
  socket: Socket | null,
  clubId: string,
  userId: string,
): { actions: AnalyticsActions; state: AnalyticsState } {
  const [analytics, setAnalytics] = useState<PlayerAnalytics | null>(null);
  const [profitData, setProfitData] = useState<ProfitDataPoint[]>([]);
  const [heatmapData, setHeatmapData] = useState<HourlyHeatmapCell[]>([]);
  const [overviewAnalytics, setOverviewAnalytics] = useState<ClubOverviewAnalytics | null>(null);
  const [activePlayersTrend, setActivePlayersTrend] = useState<ActivePlayersTrendPoint[]>([]);
  const [sessions, setSessions] = useState<PlayerSessionStat[]>([]);
  const [sessionsHasMore, setSessionsHasMore] = useState(false);
  const [timeRange, setTimeRangeState] = useState<AnalyticsTimeRange>('30d');
  const [loading, setLoading] = useState(false);

  // Track current clubId to reset on change
  const clubIdRef = useRef(clubId);
  useEffect(() => {
    if (clubIdRef.current !== clubId) {
      clubIdRef.current = clubId;
      setAnalytics(null);
      setProfitData([]);
      setHeatmapData([]);
      setOverviewAnalytics(null);
      setActivePlayersTrend([]);
      setSessions([]);
      setSessionsHasMore(false);
      setTimeRangeState('30d');
      setLoading(false);
    }
  }, [clubId]);

  // Actions
  const loadAnalytics = useCallback(
    (range?: AnalyticsTimeRange) => {
      setLoading(true);
      socket?.emit('club_analytics_get', { clubId, userId, timeRange: range ?? timeRange });
    },
    [socket, clubId, userId, timeRange],
  );

  const loadProfitChart = useCallback(
    (range?: AnalyticsTimeRange) => {
      setLoading(true);
      socket?.emit('club_profit_chart_get', { clubId, userId, timeRange: range ?? timeRange });
    },
    [socket, clubId, userId, timeRange],
  );

  const loadHeatmap = useCallback(() => {
    setLoading(true);
    socket?.emit('club_hourly_heatmap_get', { clubId, userId });
  }, [socket, clubId, userId]);

  const loadOverview = useCallback(
    (range?: AnalyticsTimeRange) => {
      setLoading(true);
      socket?.emit('club_overview_analytics_get', { clubId, timeRange: range ?? timeRange });
    },
    [socket, clubId, timeRange],
  );

  const loadActivePlayersTrend = useCallback(
    (range?: AnalyticsTimeRange) => {
      setLoading(true);
      socket?.emit('club_active_players_trend_get', { clubId, timeRange: range ?? timeRange });
    },
    [socket, clubId, timeRange],
  );

  const loadSessions = useCallback(
    (limit?: number, offset?: number) => {
      setLoading(true);
      socket?.emit('club_sessions_list', { clubId, userId, limit, offset });
    },
    [socket, clubId, userId],
  );

  const exportData = useCallback(
    (exportType: ExportDataType, range?: AnalyticsTimeRange) => {
      socket?.emit('club_export_data', { clubId, exportType, timeRange: range ?? timeRange });
    },
    [socket, clubId, timeRange],
  );

  const loadAll = useCallback(
    (range?: AnalyticsTimeRange) => {
      const r = range ?? timeRange;
      loadAnalytics(r);
      loadProfitChart(r);
      loadHeatmap();
      loadOverview(r);
    },
    [loadAnalytics, loadProfitChart, loadHeatmap, loadOverview, timeRange],
  );

  const setTimeRange = useCallback(
    (range: AnalyticsTimeRange) => {
      setTimeRangeState(range);
      loadAll(range);
    },
    [loadAll],
  );

  // Socket listeners
  useEffect(() => {
    if (!socket) return;

    const onAnalyticsResponse = (payload: ClubAnalyticsResponsePayload) => {
      if (payload.clubId !== clubId) return;
      setLoading(false);
      setAnalytics(payload.analytics);
    };

    const onProfitChartResponse = (payload: ClubProfitChartResponsePayload) => {
      if (payload.clubId !== clubId) return;
      setLoading(false);
      setProfitData(payload.data);
    };

    const onHeatmapResponse = (payload: ClubHourlyHeatmapResponsePayload) => {
      if (payload.clubId !== clubId) return;
      setLoading(false);
      setHeatmapData(payload.data);
    };

    const onOverviewResponse = (payload: ClubOverviewAnalyticsResponsePayload) => {
      if (payload.clubId !== clubId) return;
      setLoading(false);
      setOverviewAnalytics(payload.overview);
    };

    const onActivePlayersTrendResponse = (payload: ClubActivePlayersTrendResponsePayload) => {
      if (payload.clubId !== clubId) return;
      setLoading(false);
      setActivePlayersTrend(payload.data);
    };

    const onSessionsListResponse = (payload: ClubSessionsListResponsePayload) => {
      if (payload.clubId !== clubId) return;
      setLoading(false);
      setSessions(payload.sessions);
      setSessionsHasMore(payload.hasMore);
    };

    const onExportDataResponse = (payload: ClubExportDataResponsePayload) => {
      if (payload.clubId !== clubId) return;
      const blob = new Blob([payload.csvData], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = payload.fileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    };

    const onError = (payload: { code: string; message: string }) => {
      setLoading(false);
      console.warn('[analytics] error:', payload.code, payload.message);
    };

    socket.on('club_analytics_response', onAnalyticsResponse);
    socket.on('club_profit_chart_response', onProfitChartResponse);
    socket.on('club_hourly_heatmap_response', onHeatmapResponse);
    socket.on('club_overview_analytics_response', onOverviewResponse);
    socket.on('club_active_players_trend_response', onActivePlayersTrendResponse);
    socket.on('club_sessions_list_response', onSessionsListResponse);
    socket.on('club_export_data_response', onExportDataResponse);
    socket.on('club_analytics_error', onError);

    return () => {
      socket.off('club_analytics_response', onAnalyticsResponse);
      socket.off('club_profit_chart_response', onProfitChartResponse);
      socket.off('club_hourly_heatmap_response', onHeatmapResponse);
      socket.off('club_overview_analytics_response', onOverviewResponse);
      socket.off('club_active_players_trend_response', onActivePlayersTrendResponse);
      socket.off('club_sessions_list_response', onSessionsListResponse);
      socket.off('club_export_data_response', onExportDataResponse);
      socket.off('club_analytics_error', onError);
    };
  }, [socket, clubId]);

  // On mount: load all initial data when socket and clubId are ready
  useEffect(() => {
    if (!socket || !clubId) return;
    loadAll();
  }, [socket, clubId]);

  return {
    actions: {
      loadAnalytics,
      loadProfitChart,
      loadHeatmap,
      loadOverview,
      loadActivePlayersTrend,
      loadSessions,
      exportData,
      setTimeRange,
      loadAll,
    },
    state: {
      analytics,
      profitData,
      heatmapData,
      overviewAnalytics,
      activePlayersTrend,
      sessions,
      sessionsHasMore,
      timeRange,
      loading,
    },
  };
}
