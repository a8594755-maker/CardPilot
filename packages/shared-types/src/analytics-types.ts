// ===== Club Analytics Domain Types =====

export type AnalyticsTimeRange = '7d' | '30d' | '90d' | 'all';

export interface PlayerAnalytics {
  totalHands: number;
  totalSessions: number;
  totalBuyIn: number;
  totalCashOut: number;
  totalNet: number;
  totalRake: number;
  vpipHands: number;
  pfrHands: number;
  winningDays: number;
  losingDays: number;
  breakEvenDays: number;
  // Computed on client
  vpipPercent: number;
  pfrPercent: number;
  winRateBbPer100: number;
  avgProfitPerSession: number;
}

export interface ProfitDataPoint {
  day: string;
  dailyNet: number;
  cumulativeNet: number;
  hands: number;
}

export interface HourlyHeatmapCell {
  dayOfWeek: number; // 0=Sunday
  hourOfDay: number; // 0-23
  hands: number;
  net: number;
}

export interface ClubOverviewAnalytics {
  totalHands: number;
  uniquePlayers: number;
  totalBuyIn: number;
  totalCashOut: number;
  totalRake: number;
  totalSessions: number;
  avgHandsPerPlayer: number;
}

export interface ActivePlayersTrendPoint {
  day: string;
  activePlayers: number;
  totalHands: number;
  totalNet: number;
}

export interface PlayerSessionStat {
  id: string;
  clubId: string;
  userId: string;
  tableId: string;
  tableName: string;
  startedAt: string;
  endedAt: string | null;
  hands: number;
  buyIn: number;
  cashOut: number;
  net: number;
  peakStack: number;
  vpipHands: number;
  pfrHands: number;
}

export type ExportDataType = 'transactions' | 'stats' | 'sessions' | 'leaderboard';
