import { memo, useEffect } from "react";
import type { SettlementResult } from "@cardpilot/shared-types";
import { PokerCard } from "../PokerCard";

/* ═══════════════════════════════════════════════════════════════
   HandSummaryDrawer
   Non-blocking right-side drawer for hand settlement details.
   Replaces the old blocking SettlementOverlay modal.
   Opens via "Hand Summary" button during linger or from room log.
   ═══════════════════════════════════════════════════════════════ */

interface HandSummaryDrawerProps {
  open: boolean;
  onClose: () => void;
  settlement: SettlementResult | null;
  playerName: (seat: number) => string;
  revealedHoles?: Record<number, [string, string]>;
  winnerHandNames?: Record<number, string>;
}

export const HandSummaryDrawer = memo(function HandSummaryDrawer({
  open,
  onClose,
  settlement,
  playerName,
  revealedHoles,
  winnerHandNames,
}: HandSummaryDrawerProps) {
  // ESC to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open || !settlement) return null;

  const allWinners = settlement.winnersByRun.flatMap((r) => r.winners);

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
        className="fixed top-0 right-0 bottom-0 w-[340px] max-w-[90vw] bg-[var(--cp-bg-surface)] border-l border-[var(--cp-border-default)] shadow-[var(--cp-shadow-xl)] overflow-y-auto"
        style={{
          zIndex: "calc(var(--cp-z-drawer) + 1)",
          animation: "cpSlideInRight var(--cp-duration-sheet) var(--cp-ease-out)",
          willChange: "transform",
          contain: "paint",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between px-4 py-3 bg-[var(--cp-bg-surface)] border-b border-[var(--cp-border-subtle)]">
          <div>
            <h3 className="text-sm font-bold text-white">Hand Summary</h3>
            <span className="text-[9px] text-slate-500 font-mono">{settlement.handId.slice(0, 8)}</span>
          </div>
          <button
            onClick={onClose}
            className="cp-btn cp-btn-ghost !min-h-[36px] !min-w-[36px] !px-0 text-sm"
            aria-label="Close drawer"
          >
            ✕
          </button>
        </div>

        <div className="p-4 space-y-4">
          {/* Pot summary */}
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-slate-400">
              Pot <span className="text-amber-400 font-bold cp-num">{settlement.totalPot.toLocaleString()}</span>
            </span>
            <span className="text-slate-400">
              Paid <span className="text-emerald-400 font-bold cp-num">{settlement.totalPaid.toLocaleString()}</span>
            </span>
          </div>

          {/* Winners */}
          <div className="space-y-1.5">
            <h4 className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">
              {allWinners.length > 1 ? "Winners" : "Winner"}
            </h4>
            {settlement.winnersByRun.map((run) => (
              <div key={run.run}>
                {settlement.runCount > 1 && (
                  <span className={`text-[9px] font-bold uppercase px-2 py-0.5 rounded-full inline-block mb-1 ${
                    run.run === 1
                      ? "bg-cyan-500/20 text-cyan-400"
                      : run.run === 2
                        ? "bg-amber-500/20 text-amber-400"
                        : "bg-emerald-500/20 text-emerald-400"
                  }`}>
                    Run {run.run}
                  </span>
                )}
                {run.winners.map((w) => (
                  <div key={`${run.run}-${w.seat}`} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-500/8 border border-amber-500/15 mb-1">
                    <div className="w-6 h-6 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-[9px] font-extrabold text-slate-900 shrink-0">
                      {playerName(w.seat)[0]?.toUpperCase() ?? "U"}
                    </div>
                    <div className="flex flex-col min-w-0">
                      <span className="text-white font-semibold text-xs truncate">{playerName(w.seat)}</span>
                      {(w.handName || winnerHandNames?.[w.seat]) && (
                        <span className="text-slate-400 text-[9px]">{w.handName || winnerHandNames?.[w.seat]}</span>
                      )}
                    </div>
                    {revealedHoles?.[w.seat] && (
                      <div className="flex gap-0.5 shrink-0">
                        <PokerCard card={revealedHoles[w.seat][0]} variant="mini" />
                        <PokerCard card={revealedHoles[w.seat][1]} variant="mini" />
                      </div>
                    )}
                    <span className="ml-auto text-amber-400 font-extrabold text-sm cp-num shrink-0">
                      +{w.amount.toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </div>

          {/* Revealed non-winner hands */}
          {revealedHoles && (() => {
            const winnerSeats = new Set(allWinners.map((w) => w.seat));
            const nonWinnerReveals = Object.entries(revealedHoles)
              .filter(([s]) => !winnerSeats.has(Number(s)))
              .map(([s, cards]) => ({ seat: Number(s), cards }));
            if (nonWinnerReveals.length === 0) return null;
            return (
              <div className="space-y-1">
                <h4 className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Shown Hands</h4>
                {nonWinnerReveals.map(({ seat: s, cards }) => (
                  <div key={s} className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/[0.02] border border-white/5">
                    <span className="text-[10px] text-slate-400">{playerName(s)}</span>
                    <div className="flex gap-0.5">
                      <PokerCard card={cards[0]} variant="mini" />
                      <PokerCard card={cards[1]} variant="mini" />
                    </div>
                    {winnerHandNames?.[s] && (
                      <span className="text-[9px] text-slate-500 ml-auto">{winnerHandNames[s]}</span>
                    )}
                  </div>
                ))}
              </div>
            );
          })()}

          {/* Boards */}
          <div>
            <h4 className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold mb-1.5">
              Board{settlement.runCount > 1 ? "s" : ""}
            </h4>
            {settlement.runCount > 1 && settlement.boards.length > 1 ? (() => {
              // Compute common prefix
              const boards = settlement.boards;
              let commonLen = 0;
              const minLen = Math.min(...boards.map((b) => b.length));
              for (let i = 0; i < minLen; i++) {
                if (boards.every((b) => b[i] === boards[0][i])) commonLen = i + 1;
                else break;
              }
              const commonCards = boards[0].slice(0, commonLen);
              const RUN_COLORS = ["text-cyan-400", "text-amber-400", "text-emerald-400"];
              const RUN_BG = ["bg-cyan-500/10 border-cyan-500/20", "bg-amber-500/10 border-amber-500/20", "bg-emerald-500/10 border-emerald-500/20"];
              return (
                <div className="space-y-1.5">
                  {/* Common cards */}
                  {commonCards.length > 0 && (
                    <div className="flex gap-0.5">
                      {commonCards.map((c, i) => (
                        <PokerCard key={i} card={c} variant="mini" />
                      ))}
                    </div>
                  )}
                  {/* Per-run boards with winners */}
                  {boards.map((board, idx) => {
                    const unique = board.slice(commonLen);
                    const displayCards = commonLen === 0 ? board : unique;
                    const runWinners = settlement.winnersByRun.find((r) => r.run === idx + 1)?.winners ?? [];
                    return (
                      <div key={idx} className={`rounded-md border px-2 py-1.5 ${RUN_BG[idx] ?? RUN_BG[0]}`}>
                        <div className="flex items-center gap-1.5">
                          <span className={`text-[9px] font-bold uppercase shrink-0 ${RUN_COLORS[idx] ?? RUN_COLORS[0]}`}>
                            R{idx + 1}
                          </span>
                          <div className="flex gap-0.5">
                            {displayCards.map((c, i) => (
                              <PokerCard key={i} card={c} variant="mini" />
                            ))}
                          </div>
                        </div>
                        {runWinners.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
                            {runWinners.map((w, wi) => (
                              <span key={wi} className="text-[9px] flex items-center gap-1">
                                <span className="text-slate-300">{playerName(w.seat)}</span>
                                <span className="text-emerald-400 font-bold">+{w.amount.toLocaleString()}</span>
                                {(w.handName || winnerHandNames?.[w.seat]) && (
                                  <span className="text-slate-500">({w.handName || winnerHandNames?.[w.seat]})</span>
                                )}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              );
            })() : (
              settlement.boards.map((board, idx) => (
                <div key={idx} className="flex items-center gap-1 mb-1">
                  <div className="flex gap-1">
                    {board.map((c, i) => (
                      <PokerCard key={i} card={c} variant="mini" />
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Payout Ledger */}
          <div>
            <h4 className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold mb-1.5">Payout Ledger</h4>
            <div className="overflow-x-auto">
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="text-slate-500 border-b border-white/5">
                    <th className="text-left py-1 font-medium">Player</th>
                    <th className="text-right py-1 font-medium">Invested</th>
                    <th className="text-right py-1 font-medium">Won</th>
                    <th className="text-right py-1 font-medium">Net</th>
                  </tr>
                </thead>
                <tbody>
                  {settlement.ledger.map((entry) => (
                    <tr key={entry.seat} className="border-b border-white/5 last:border-0">
                      <td className="py-1 text-slate-200 font-medium">
                        <span className="text-slate-500 mr-1">#{entry.seat}</span>
                        {entry.playerName}
                      </td>
                      <td className="py-1 text-right text-red-400/70 font-mono cp-num">
                        {entry.invested > 0 ? `-${entry.invested.toLocaleString()}` : "0"}
                      </td>
                      <td className="py-1 text-right text-emerald-400 font-mono cp-num">
                        {entry.won > 0 ? `+${entry.won.toLocaleString()}` : "0"}
                      </td>
                      <td className={`py-1 text-right font-mono font-semibold cp-num ${
                        entry.net > 0 ? "text-emerald-400" : entry.net < 0 ? "text-red-400" : "text-slate-400"
                      }`}>
                        {entry.net > 0 ? "+" : ""}{entry.net.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pot Breakdown */}
          {settlement.potLayers.length > 1 && (
            <div>
              <h4 className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold mb-1.5">Pot Breakdown</h4>
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="text-slate-500 border-b border-white/5">
                    <th className="text-left py-1 font-medium">Pot</th>
                    <th className="text-right py-1 font-medium">Amount</th>
                    <th className="text-left py-1 font-medium pl-2">Eligible</th>
                  </tr>
                </thead>
                <tbody>
                  {settlement.potLayers.map((layer, idx) => (
                    <tr key={idx} className="border-b border-white/5 last:border-0">
                      <td className="py-1 text-slate-300 font-medium">{layer.label}</td>
                      <td className="py-1 text-right text-amber-400 font-mono cp-num">{layer.amount.toLocaleString()}</td>
                      <td className="py-1 text-left pl-2 text-slate-400">
                        {layer.eligibleSeats.map((s) => playerName(s)).join(", ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
});

export default HandSummaryDrawer;
