import React, { memo, useCallback, useEffect, useRef, useState } from "react";
import type {
  ClubLeaderboardEntry,
  ClubLeaderboardMetric,
  ClubLeaderboardRange,
} from "@cardpilot/shared-types";
import { EmptyState } from "../shared";
import type { ClubSocketActions } from "../hooks/useClubSocket";

// ── Props ──

interface LeaderboardTabProps {
  clubId: string;
  leaderboardRows: ClubLeaderboardEntry[];
  myRank: number | null;
  actions: ClubSocketActions;
}

// ── Constants ──

const RANGES: { label: string; value: ClubLeaderboardRange }[] = [
  { label: "Day", value: "day" },
  { label: "Week", value: "week" },
  { label: "All", value: "all" },
];

const METRICS: { label: string; value: ClubLeaderboardMetric }[] = [
  { label: "Net", value: "net" },
  { label: "Hands", value: "hands" },
  { label: "Buy-in", value: "buyin" },
  { label: "Deposits", value: "deposits" },
];

// ── Component ──

export const LeaderboardTab = memo(function LeaderboardTab({
  clubId,
  leaderboardRows,
  myRank,
  actions,
}: LeaderboardTabProps) {
  const [leaderboardRange, setLeaderboardRange] = useState<ClubLeaderboardRange>("week");
  const [leaderboardMetric, setLeaderboardMetric] = useState<ClubLeaderboardMetric>("net");

  // Debounced fetch to avoid rapid-fire requests when switching filters quickly
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const debouncedFetch = useCallback(
    (range: ClubLeaderboardRange, metric: ClubLeaderboardMetric) => {
      clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        actions.fetchLeaderboard(range, metric);
      }, 300);
    },
    [actions],
  );

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => clearTimeout(debounceRef.current);
  }, []);

  // Fetch leaderboard data whenever range or metric changes (debounced)
  useEffect(() => {
    debouncedFetch(leaderboardRange, leaderboardMetric);
  }, [leaderboardRange, leaderboardMetric, debouncedFetch, clubId]);

  return (
    <div className="space-y-4">
      {/* ── Controls ── */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Time range buttons */}
        <div className="flex rounded-lg overflow-hidden border border-slate-700">
          {RANGES.map((r) => (
            <button
              key={r.value}
              onClick={() => setLeaderboardRange(r.value)}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                leaderboardRange === r.value
                  ? "bg-amber-600 text-white"
                  : "bg-slate-800 text-slate-400 hover:text-slate-200"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>

        {/* Metric dropdown */}
        <select
          value={leaderboardMetric}
          onChange={(e) => setLeaderboardMetric(e.target.value as ClubLeaderboardMetric)}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 outline-none focus:border-cyan-500"
        >
          {METRICS.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>

        {/* Refresh button */}
        <button
          onClick={() => actions.fetchLeaderboard(leaderboardRange, leaderboardMetric)}
          className="ml-auto rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
        >
          Refresh
        </button>
      </div>

      {/* ── My Rank ── */}
      {myRank !== null && (
        <div className="rounded-lg border border-amber-800/40 bg-amber-900/20 px-4 py-2 text-sm">
          <span className="text-slate-400">Your rank:</span>{" "}
          <span className="font-bold text-amber-400">#{myRank}</span>
        </div>
      )}

      {/* ── Leaderboard Table ── */}
      {leaderboardRows.length === 0 ? (
        <EmptyState
          icon="🏆"
          title="No leaderboard data yet."
          description="Play some hands to appear on the leaderboard."
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-700">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-700 bg-slate-800/60 text-left text-slate-500">
                <th className="px-3 py-2 font-medium">Rank</th>
                <th className="px-3 py-2 font-medium">Player</th>
                <th className="px-3 py-2 font-medium">Metric</th>
                <th className="px-3 py-2 font-medium">Balance</th>
                <th className="px-3 py-2 font-medium">Hands</th>
                <th className="px-3 py-2 font-medium">Net</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {leaderboardRows.map((row) => (
                <tr key={row.userId} className="hover:bg-slate-800/40 transition-colors">
                  <td className="px-3 py-2 font-bold text-amber-400">#{row.rank}</td>
                  <td className="px-3 py-2 text-slate-300">
                    {row.displayName || row.userId.slice(0, 8)}
                  </td>
                  <td className="px-3 py-2 font-mono text-cyan-400">
                    {row.metricValue.toLocaleString()}
                  </td>
                  <td className="px-3 py-2 text-slate-400">
                    {row.balance.toLocaleString()}
                  </td>
                  <td className="px-3 py-2 text-slate-400">{row.hands.toLocaleString()}</td>
                  <td
                    className={`px-3 py-2 font-medium ${
                      row.net > 0
                        ? "text-emerald-400"
                        : row.net < 0
                        ? "text-red-400"
                        : "text-slate-400"
                    }`}
                  >
                    {row.net > 0 ? "+" : ""}
                    {row.net.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
});

export default LeaderboardTab;
