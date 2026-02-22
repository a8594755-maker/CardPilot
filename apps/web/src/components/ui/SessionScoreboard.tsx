import { memo, useEffect, useMemo } from "react";
import { formatChips } from "../../lib/format-chips";

/* ═══════════════════════════════════════════════════════════════
   SessionScoreboard
   Right-side drawer showing per-room session profit/loss rankings.
   Entries are sorted by net (descending) with rank numbers and
   color-coded results (green = profit, red = loss).
   ═══════════════════════════════════════════════════════════════ */

export type SessionStatsEntry = {
  seat: number | null;
  userId: string;
  name: string;
  totalBuyIn: number;
  totalCashOut: number;
  currentStack: number;
  net: number;
  handsPlayed: number;
  status: string;
};

interface SessionScoreboardProps {
  open: boolean;
  onClose: () => void;
  entries: SessionStatsEntry[];
  currentUserId: string | undefined;
  displayBB: boolean;
  bigBlind: number;
  onRefresh: () => void;
}

export const SessionScoreboard = memo(function SessionScoreboard({
  open,
  onClose,
  entries,
  currentUserId,
  displayBB,
  bigBlind,
  onRefresh,
}: SessionScoreboardProps) {
  // ESC to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Sort by net descending — winners at top
  const sorted = useMemo(
    () => [...entries].sort((a, b) => b.net - a.net),
    [entries],
  );

  // Summary stats
  const summary = useMemo(() => {
    if (entries.length <= 1) return null;
    const totalNet = entries.reduce((sum, e) => sum + e.net, 0);
    const totalHands = Math.max(...entries.map((e) => e.handsPlayed), 0);
    return { totalNet, totalHands, playerCount: entries.length };
  }, [entries]);

  if (!open) return null;

  const chipOpts = { mode: displayBB ? ("bb" as const) : ("chips" as const), bbSize: bigBlind };

  return (
    <>
      {/* Backdrop — click to close */}
      <div
        className="fixed inset-0 bg-black/40 animate-[cpFadeIn_0.15s_ease-out]"
        style={{ zIndex: "var(--cp-z-drawer)" }}
        onClick={onClose}
      />

      {/* Drawer panel — slides in from right */}
      <div
        className="fixed top-0 right-0 bottom-0 w-[360px] max-w-[92vw] bg-[var(--cp-bg-surface)] border-l border-[var(--cp-border-default)] shadow-[var(--cp-shadow-xl)] overflow-y-auto"
        style={{
          zIndex: "calc(var(--cp-z-drawer) + 1)",
          animation: "cpSlideInRight var(--cp-duration-sheet) var(--cp-ease-out)",
          willChange: "transform",
          contain: "paint",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Sticky Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between px-4 py-3 bg-[var(--cp-bg-surface)] border-b border-[var(--cp-border-subtle)]">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-white">Session Scoreboard</h3>
            <span className="text-[9px] text-slate-500 bg-white/5 px-1.5 py-0.5 rounded-full">
              {entries.length}
            </span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={onRefresh}
              className="cp-btn cp-btn-ghost !min-h-[28px] !min-w-[28px] !px-0 text-sm"
              aria-label="Refresh stats"
            >
              ↻
            </button>
            <button
              onClick={onClose}
              className="cp-btn cp-btn-ghost !min-h-[28px] !min-w-[28px] !px-0 text-sm"
              aria-label="Close drawer"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-4">
          {sorted.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-slate-500 text-xs">No session data yet</p>
              <p className="text-slate-600 text-[10px] mt-1">Stats appear after the first hand</p>
            </div>
          ) : (
            <>
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-slate-500 border-b border-white/5">
                    <th className="text-left py-1.5 font-medium w-6">#</th>
                    <th className="text-left py-1.5 font-medium">Player</th>
                    <th className="text-right py-1.5 font-medium">Buy-in</th>
                    <th className="text-right py-1.5 font-medium">Stack</th>
                    <th className="text-right py-1.5 font-medium">Net</th>
                    <th className="text-right py-1.5 font-medium">Hands</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((e, idx) => {
                    const isMe = e.userId === currentUserId;
                    return (
                      <tr
                        key={e.userId}
                        className={`border-b border-white/5 last:border-0 ${isMe ? "bg-cyan-500/8" : ""}`}
                      >
                        <td className="py-2 text-slate-500 font-mono">{idx + 1}</td>
                        <td className="py-2">
                          <div className="flex items-center gap-1.5">
                            <span
                              className={`w-1.5 h-1.5 rounded-full shrink-0 ${e.status === "seated" ? "bg-emerald-400" : "bg-slate-600"}`}
                              title={e.status === "seated" ? "Seated" : "Away"}
                            />
                            <span
                              className={`font-medium truncate max-w-[100px] ${isMe ? "text-cyan-300" : "text-slate-200"}`}
                            >
                              {e.name}
                              {isMe ? " (You)" : ""}
                            </span>
                          </div>
                        </td>
                        <td className="py-2 text-right text-slate-400 font-mono">
                          {formatChips(e.totalBuyIn, chipOpts)}
                        </td>
                        <td className="py-2 text-right text-slate-300 font-mono">
                          {formatChips(e.currentStack, chipOpts)}
                        </td>
                        <td
                          className={`py-2 text-right font-mono font-semibold ${e.net > 0 ? "text-emerald-400" : e.net < 0 ? "text-red-400" : "text-slate-400"}`}
                        >
                          {e.net > 0 ? "+" : ""}
                          {formatChips(e.net, chipOpts)}
                        </td>
                        <td className="py-2 text-right text-slate-500">{e.handsPlayed}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {/* Summary footer */}
              {summary && (
                <div className="flex items-center justify-between mt-3 pt-3 border-t border-white/5 text-[10px]">
                  <span className="text-slate-500">
                    {summary.playerCount} players | {summary.totalHands} hands dealt
                  </span>
                  <span
                    className={`font-mono font-semibold ${summary.totalNet > 0 ? "text-emerald-400" : summary.totalNet < 0 ? "text-red-400" : "text-slate-400"}`}
                  >
                    Table net: {summary.totalNet > 0 ? "+" : ""}
                    {formatChips(summary.totalNet, chipOpts)}
                  </span>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
});

export default SessionScoreboard;
