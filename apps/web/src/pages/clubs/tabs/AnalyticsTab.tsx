import React, { memo, useCallback, useMemo } from 'react';
import type {
  PlayerAnalytics,
  ProfitDataPoint,
  HourlyHeatmapCell,
  ClubOverviewAnalytics,
  ActivePlayersTrendPoint,
  PlayerSessionStat,
  AnalyticsTimeRange,
  ExportDataType,
} from '@cardpilot/shared-types';
import { EmptyState } from '../shared';

// ── Types ──

interface AnalyticsActions {
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

interface AnalyticsState {
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

interface AnalyticsTabProps {
  analyticsActions: AnalyticsActions;
  analyticsState: AnalyticsState;
  isAdmin: boolean;
}

// ── Constants ──

const TIME_RANGES: { label: string; value: AnalyticsTimeRange }[] = [
  { label: '7d', value: '7d' },
  { label: '30d', value: '30d' },
  { label: '90d', value: '90d' },
  { label: 'All', value: 'all' },
];

const DAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

// ── Helpers ──

function formatNumber(n: number): string {
  return n.toLocaleString();
}

function formatNet(n: number): string {
  const prefix = n > 0 ? '+' : '';
  return `${prefix}${n.toLocaleString()}`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function netColorClass(n: number): string {
  if (n > 0) return 'text-emerald-400';
  if (n < 0) return 'text-red-400';
  return 'text-slate-400';
}

/** Map a value 0..max to a heatmap color class */
function heatmapColor(hands: number, maxHands: number): string {
  if (hands === 0 || maxHands === 0) return 'bg-slate-800';
  const ratio = hands / maxHands;
  if (ratio < 0.25) return 'bg-emerald-900/50';
  if (ratio < 0.6) return 'bg-emerald-600';
  return 'bg-emerald-400';
}

// ── Skeleton Shimmer ──

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-slate-700/50 ${className}`} />;
}

// ── Sub-components ──

/** Time Range Selector */
function TimeRangeSelector({
  current,
  onChange,
}: {
  current: AnalyticsTimeRange;
  onChange: (range: AnalyticsTimeRange) => void;
}) {
  return (
    <div className="flex rounded-lg overflow-hidden border border-slate-700">
      {TIME_RANGES.map((r) => (
        <button
          key={r.value}
          onClick={() => onChange(r.value)}
          className={`px-3 py-1.5 text-xs font-medium transition-colors ${
            current === r.value
              ? 'bg-amber-600 text-white'
              : 'bg-slate-800 text-slate-400 hover:text-slate-200'
          }`}
        >
          {r.label}
        </button>
      ))}
    </div>
  );
}

/** Single stat card */
function StatCard({
  label,
  value,
  colorClass = 'text-white',
}: {
  label: string;
  value: string;
  colorClass?: string;
}) {
  return (
    <div className="bg-white/5 rounded-xl p-4 border border-white/5">
      <p className="text-xs text-slate-400 mb-1">{label}</p>
      <p className={`text-lg font-semibold ${colorClass}`}>{value}</p>
    </div>
  );
}

/** Stats cards grid (loading skeleton variant) */
function StatsCardsSkeleton() {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="bg-white/5 rounded-xl p-4 border border-white/5 space-y-2">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-6 w-24" />
        </div>
      ))}
    </div>
  );
}

/** Stats cards grid */
function StatsCards({ analytics }: { analytics: PlayerAnalytics }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
      <StatCard label="Total Hands" value={formatNumber(analytics.totalHands)} />
      <StatCard label="Total Sessions" value={formatNumber(analytics.totalSessions)} />
      <StatCard
        label="Net Profit"
        value={formatNet(analytics.totalNet)}
        colorClass={netColorClass(analytics.totalNet)}
      />
      <StatCard label="VPIP%" value={`${analytics.vpipPercent.toFixed(1)}%`} />
      <StatCard label="PFR%" value={`${analytics.pfrPercent.toFixed(1)}%`} />
      <StatCard
        label="Win Rate"
        value={`${formatNet(analytics.avgProfitPerSession)} avg/session`}
        colorClass={netColorClass(analytics.avgProfitPerSession)}
      />
    </div>
  );
}

/** SVG profit chart with gradient fill */
function ProfitChart({ data }: { data: ProfitDataPoint[] }) {
  if (data.length === 0) {
    return (
      <EmptyState
        icon="📈"
        title="No data yet"
        description="Play some hands to see your profit chart."
      />
    );
  }

  const width = 600;
  const height = 200;
  const padX = 0;
  const padY = 10;

  const values = data.map((d) => d.cumulativeNet);
  const minVal = Math.min(0, ...values);
  const maxVal = Math.max(0, ...values);
  const range = maxVal - minVal || 1;

  const scaleX = (i: number) => padX + (i / Math.max(data.length - 1, 1)) * (width - 2 * padX);
  const scaleY = (v: number) => padY + (1 - (v - minVal) / range) * (height - 2 * padY);

  const points = data.map((d, i) => `${scaleX(i)},${scaleY(d.cumulativeNet)}`);
  const polyline = points.join(' ');

  // Area fill path: line + close along the bottom
  const lastVal = values[values.length - 1];
  const isPositive = lastVal >= 0;
  const strokeColor = isPositive ? '#34d399' : '#f87171'; // emerald-400 / red-400
  const gradientId = isPositive ? 'profitGradPos' : 'profitGradNeg';
  const gradStart = isPositive ? '#34d399' : '#f87171';

  // Build SVG path for area
  const areaPath = [
    `M ${scaleX(0)},${scaleY(0)}`,
    ...data.map((d, i) => `L ${scaleX(i)},${scaleY(d.cumulativeNet)}`),
    `L ${scaleX(data.length - 1)},${scaleY(0)}`,
    'Z',
  ].join(' ');

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto" preserveAspectRatio="none">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={gradStart} stopOpacity="0.3" />
          <stop offset="100%" stopColor={gradStart} stopOpacity="0.02" />
        </linearGradient>
      </defs>

      {/* Zero line */}
      <line
        x1={padX}
        y1={scaleY(0)}
        x2={width - padX}
        y2={scaleY(0)}
        stroke="#475569"
        strokeWidth="0.5"
        strokeDasharray="4 2"
      />

      {/* Gradient area */}
      <path d={areaPath} fill={`url(#${gradientId})`} />

      {/* Line */}
      <polyline
        points={polyline}
        fill="none"
        stroke={strokeColor}
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Hourly heatmap grid */
function HourlyHeatmap({ data }: { data: HourlyHeatmapCell[] }) {
  // Build lookup map
  const cellMap = useMemo(() => {
    const map = new Map<string, HourlyHeatmapCell>();
    for (const cell of data) {
      map.set(`${cell.dayOfWeek}-${cell.hourOfDay}`, cell);
    }
    return map;
  }, [data]);

  const maxHands = useMemo(() => {
    if (data.length === 0) return 0;
    return Math.max(...data.map((c) => c.hands));
  }, [data]);

  if (data.length === 0) {
    return (
      <EmptyState
        icon="🗓️"
        title="No heatmap data"
        description="Play some hands to see your activity heatmap."
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[520px]">
        {/* Hour labels */}
        <div className="flex ml-10 mb-1 gap-px">
          {Array.from({ length: 24 }).map((_, h) => (
            <div key={h} className="flex-1 text-center text-[10px] text-slate-500">
              {h % 4 === 0 ? h : ''}
            </div>
          ))}
        </div>

        {/* Rows */}
        {Array.from({ length: 7 }).map((_, dow) => (
          <div key={dow} className="flex items-center gap-px mb-px">
            <span className="w-10 text-[10px] text-slate-500 text-right pr-2 shrink-0">
              {DAY_LABELS[dow]}
            </span>
            {Array.from({ length: 24 }).map((_, h) => {
              const cell = cellMap.get(`${dow}-${h}`);
              const hands = cell?.hands ?? 0;
              return (
                <div
                  key={h}
                  className={`flex-1 aspect-square rounded-sm ${heatmapColor(hands, maxHands)}`}
                  title={`${DAY_LABELS[dow]} ${h}:00 — ${hands} hands`}
                />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Session history table */
function SessionHistory({
  sessions,
  hasMore,
  onLoadMore,
}: {
  sessions: PlayerSessionStat[];
  hasMore: boolean;
  onLoadMore: () => void;
}) {
  if (sessions.length === 0) {
    return (
      <EmptyState
        icon="🃏"
        title="No sessions yet"
        description="Your session history will appear here after you play."
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-lg border border-slate-700">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-700 bg-slate-800/60 text-left text-slate-500">
              <th className="px-3 py-2 font-medium">Table</th>
              <th className="px-3 py-2 font-medium">Started</th>
              <th className="px-3 py-2 font-medium">Hands</th>
              <th className="px-3 py-2 font-medium">Net</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {sessions.map((s) => (
              <tr key={s.id} className="hover:bg-slate-800/40 transition-colors">
                <td className="px-3 py-2 text-slate-300">{s.tableName}</td>
                <td className="px-3 py-2 text-slate-400">{formatDate(s.startedAt)}</td>
                <td className="px-3 py-2 text-slate-400">{formatNumber(s.hands)}</td>
                <td className={`px-3 py-2 font-medium ${netColorClass(s.net)}`}>
                  {formatNet(s.net)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {hasMore && (
        <div className="flex justify-center">
          <button
            onClick={onLoadMore}
            className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
          >
            Load More
          </button>
        </div>
      )}
    </div>
  );
}

/** Admin overview cards */
function AdminOverview({ overview }: { overview: ClubOverviewAnalytics }) {
  const cards = [
    { label: 'Total Hands', value: formatNumber(overview.totalHands) },
    { label: 'Unique Players', value: formatNumber(overview.uniquePlayers) },
    { label: 'Total Buy-In', value: formatNumber(overview.totalBuyIn) },
    { label: 'Total Cash-Out', value: formatNumber(overview.totalCashOut) },
    { label: 'Total Rake', value: formatNumber(overview.totalRake) },
    {
      label: 'Avg Hands/Player',
      value: formatNumber(Math.round(overview.avgHandsPerPlayer)),
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
      {cards.map((c) => (
        <StatCard key={c.label} label={c.label} value={c.value} />
      ))}
    </div>
  );
}

// ── Section Header ──

function SectionHeader({ title }: { title: string }) {
  return <h3 className="text-sm font-semibold text-slate-300">{title}</h3>;
}

// ── Main Component ──

export const AnalyticsTab = memo(function AnalyticsTab({
  analyticsActions,
  analyticsState: state,
  isAdmin,
}: AnalyticsTabProps) {
  const handleTimeRangeChange = useCallback(
    (range: AnalyticsTimeRange) => {
      analyticsActions.setTimeRange(range);
      analyticsActions.loadAll(range);
    },
    [analyticsActions],
  );

  const handleLoadMoreSessions = useCallback(() => {
    analyticsActions.loadSessions(undefined, state.sessions.length);
  }, [analyticsActions, state.sessions.length]);

  const handleExportStats = useCallback(() => {
    analyticsActions.exportData('stats', state.timeRange);
  }, [analyticsActions, state.timeRange]);

  const handleExportSessions = useCallback(() => {
    analyticsActions.exportData('sessions', state.timeRange);
  }, [analyticsActions, state.timeRange]);

  return (
    <div className="space-y-6">
      {/* ── Time Range Selector ── */}
      <section>
        <TimeRangeSelector current={state.timeRange} onChange={handleTimeRangeChange} />
      </section>

      {/* ── Stats Cards ── */}
      <section className="space-y-2">
        <SectionHeader title="Player Stats" />
        {state.loading && !state.analytics ? (
          <StatsCardsSkeleton />
        ) : state.analytics ? (
          <StatsCards analytics={state.analytics} />
        ) : (
          <EmptyState
            icon="📊"
            title="No analytics yet"
            description="Play some hands to see your stats."
          />
        )}
      </section>

      {/* ── Profit Chart ── */}
      <section className="space-y-2">
        <SectionHeader title="Cumulative P&L" />
        {state.loading && state.profitData.length === 0 ? (
          <Skeleton className="h-[200px] w-full" />
        ) : (
          <div className="rounded-xl border border-white/5 bg-white/5 p-4">
            <ProfitChart data={state.profitData} />
          </div>
        )}
      </section>

      {/* ── Hourly Heatmap ── */}
      <section className="space-y-2">
        <SectionHeader title="Activity Heatmap" />
        {state.loading && state.heatmapData.length === 0 ? (
          <Skeleton className="h-[180px] w-full" />
        ) : (
          <div className="rounded-xl border border-white/5 bg-white/5 p-4">
            <HourlyHeatmap data={state.heatmapData} />
          </div>
        )}
      </section>

      {/* ── Session History ── */}
      <section className="space-y-2">
        <SectionHeader title="Session History" />
        {state.loading && state.sessions.length === 0 ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : (
          <SessionHistory
            sessions={state.sessions}
            hasMore={state.sessionsHasMore}
            onLoadMore={handleLoadMoreSessions}
          />
        )}
      </section>

      {/* ── Admin Overview ── */}
      {isAdmin && (
        <section className="space-y-2">
          <SectionHeader title="Club Overview (Admin)" />
          {state.loading && !state.overviewAnalytics ? (
            <StatsCardsSkeleton />
          ) : state.overviewAnalytics ? (
            <AdminOverview overview={state.overviewAnalytics} />
          ) : (
            <EmptyState
              icon="🏢"
              title="No club overview data"
              description="Overview analytics will appear once there is activity."
            />
          )}
        </section>
      )}

      {/* ── Export Buttons ── */}
      <section className="flex flex-wrap gap-2 pt-2">
        <button
          onClick={handleExportStats}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
        >
          Export Stats CSV
        </button>
        <button
          onClick={handleExportSessions}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
        >
          Export Sessions CSV
        </button>
      </section>
    </div>
  );
});

export default AnalyticsTab;
