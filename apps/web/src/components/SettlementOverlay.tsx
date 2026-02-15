import { useState, useEffect, useCallback, memo } from "react";
import { createPortal } from "react-dom";
import type { SettlementResult, TablePlayer } from "@cardpilot/shared-types";
import { PokerCard } from "./PokerCard";
import { CardZoomModal } from "./CardZoomModal";

interface SettlementOverlayProps {
  settlement: SettlementResult;
  players: TablePlayer[];
  autoStartScheduled: boolean;
  autoStartBlockReason: string | null;
  countdownSeconds: number;
  onDismiss: () => void;
  onDealNow?: () => void;
  isHost: boolean;
  /** Revealed hole cards from the final table state, keyed by seat */
  revealedHoles?: Record<number, [string, string]>;
  /** Winner hand names from the final table state, keyed by seat */
  winnerHandNames?: Record<number, string>;
}

export const SettlementOverlay = memo(function SettlementOverlay({
  settlement,
  players,
  autoStartScheduled,
  autoStartBlockReason,
  countdownSeconds,
  onDismiss,
  onDealNow,
  isHost,
  revealedHoles,
  winnerHandNames,
}: SettlementOverlayProps) {
  const [showDrawer, setShowDrawer] = useState(false);
  const [zoomCards, setZoomCards] = useState<{ cards: string[]; label: string; sublabel?: string } | null>(null);
  const [run2Expanded, setRun2Expanded] = useState(false);

  // ESC to close overlay
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (zoomCards) { setZoomCards(null); return; }
        onDismiss();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onDismiss, zoomCards]);

  const playerName = useCallback(
    (seat: number) => {
      const p = players.find((pl) => pl.seat === seat);
      return p?.name ?? `Seat ${seat}`;
    },
    [players]
  );

  // Combine all winners across runs for overlay header
  const allWinners = settlement.winnersByRun.flatMap((r) => r.winners);

  // Countdown expired + no new hand yet = "waiting for server" state
  const countdownExpired = countdownSeconds <= 0;
  const showWaitingFallback = autoStartScheduled && countdownExpired;

  const overlay = (
    <div
      className="fixed inset-0 z-[90] flex items-end sm:items-center justify-center"
      style={{ paddingBottom: "calc(env(safe-area-inset-bottom, 0px) + var(--app-footer-h, 0px) + 12px)", paddingTop: "calc(var(--topbar-h, 0px) + 12px)" }}
      onClick={onDismiss}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-[2px]" />

      {/* Modal */}
      <div
        className="relative w-full max-w-2xl mx-3 rounded-2xl border border-amber-500/25 bg-gradient-to-b from-amber-500/8 via-black/70 to-black/85 backdrop-blur-sm shadow-lg shadow-black/30 animate-[fadeSlideUp_0.35s_ease-out] flex flex-col"
        style={{ maxHeight: "calc(100vh - var(--topbar-h, 0px) - var(--app-footer-h, 0px) - 24px - env(safe-area-inset-bottom, 0px))" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Sticky header */}
        <div className="sticky top-0 z-10 px-5 pb-2 pt-4 bg-gradient-to-b from-black/90 to-transparent rounded-t-2xl shrink-0">
          {/* Close button */}
          <button
            onClick={onDismiss}
            className="absolute top-1 right-3 text-slate-500 hover:text-white text-sm transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center"
            title="Dismiss (Esc)"
          >
            ✕
          </button>

          {/* Header */}
          <div className="flex items-center justify-center gap-2 mb-1 pt-1">
            <span className="text-amber-400 text-base font-extrabold tracking-wide uppercase">
              Hand Result
            </span>
          </div>
          <div className="text-center text-[10px] text-slate-500 font-mono mb-2">
            {settlement.handId.slice(0, 8)}
          </div>

          {/* Pot summary */}
          <div className="flex items-center justify-center gap-4 text-[11px]">
            <span className="text-slate-400">
              Pot{" "}
              <span className="text-amber-400 font-bold">
                {settlement.totalPot.toLocaleString()}
              </span>
            </span>
            <span className="text-slate-600">·</span>
            <span className="text-slate-500">Rake 0</span>
            <span className="text-slate-600">·</span>
            <span className="text-slate-400">
              Paid{" "}
              <span className="text-emerald-400 font-bold">
                {settlement.totalPaid.toLocaleString()}
              </span>
            </span>
          </div>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto overflow-x-hidden px-5 min-h-0">
        {/* Run-it-twice: show per-run results */}
        {settlement.runCount === 2 ? (
          <div className="space-y-2 mb-3 mt-2">
            {settlement.winnersByRun.map((run) => {
              const isRun2 = run.run === 2;
              const collapsed = isRun2 && !run2Expanded;
              return (
                <div
                  key={run.run}
                  className="rounded-xl border border-white/8 bg-white/[0.02] p-3"
                >
                  <div
                    className={`flex items-center gap-2 ${collapsed ? "" : "mb-2"} ${isRun2 ? "cursor-pointer" : ""}`}
                    onClick={isRun2 ? () => setRun2Expanded(!run2Expanded) : undefined}
                  >
                    <span
                      className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${
                        run.run === 1
                          ? "bg-cyan-500/20 text-cyan-400"
                          : "bg-amber-500/20 text-amber-400"
                      }`}
                    >
                      Run {run.run}
                    </span>
                    <div className="flex gap-1">
                      {run.board.map((c, i) => (
                        <PokerCard
                          key={i}
                          card={c}
                          variant="mini"
                          onClick={() =>
                            setZoomCards({
                              cards: run.board,
                              label: `Run ${run.run} Board`,
                            })
                          }
                        />
                      ))}
                    </div>
                    {isRun2 && (
                      <span className="ml-auto text-[10px] text-slate-500">
                        {collapsed ? "▸ expand" : "▾ collapse"}
                      </span>
                    )}
                  </div>
                  {!collapsed && (
                    <div className="flex flex-col gap-1">
                      {run.winners.map((w) => (
                        <WinnerRow
                          key={`${run.run}-${w.seat}`}
                          seat={w.seat}
                          name={playerName(w.seat)}
                          amount={w.amount}
                          handName={w.handName}
                          invested={settlement.contributions[w.seat] ?? 0}
                          revealedCards={revealedHoles?.[w.seat]}
                          onClickCards={
                            revealedHoles?.[w.seat]
                              ? () =>
                                  setZoomCards({
                                    cards: revealedHoles[w.seat],
                                    label: playerName(w.seat),
                                    sublabel: w.handName ?? winnerHandNames?.[w.seat],
                                  })
                              : undefined
                          }
                        />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          /* Standard single-run winners */
          <div className="flex flex-col items-center gap-2 mb-3 mt-2">
            {allWinners.map((w) => (
              <WinnerRow
                key={w.seat}
                seat={w.seat}
                name={playerName(w.seat)}
                amount={w.amount}
                handName={w.handName}
                invested={settlement.contributions[w.seat] ?? 0}
                revealedCards={revealedHoles?.[w.seat]}
                onClickCards={
                  revealedHoles?.[w.seat]
                    ? () =>
                        setZoomCards({
                          cards: revealedHoles![w.seat],
                          label: playerName(w.seat),
                          sublabel: w.handName ?? winnerHandNames?.[w.seat],
                        })
                    : undefined
                }
              />
            ))}
          </div>
        )}

        {/* Revealed hole cards for non-winners (if any) */}
        {revealedHoles && (() => {
          const winnerSeats = new Set(allWinners.map((w) => w.seat));
          const nonWinnerReveals = Object.entries(revealedHoles)
            .filter(([s]) => !winnerSeats.has(Number(s)))
            .map(([s, cards]) => ({ seat: Number(s), cards }));
          if (nonWinnerReveals.length === 0) return null;
          return (
            <div className="mb-3 space-y-1">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider text-center">Shown Hands</div>
              {nonWinnerReveals.map(({ seat: s, cards }) => (
                <div
                  key={s}
                  className="flex items-center justify-center gap-2 cursor-pointer hover:opacity-80 transition-opacity min-h-[44px]"
                  onClick={() =>
                    setZoomCards({
                      cards,
                      label: playerName(s),
                      sublabel: winnerHandNames?.[s] ?? "Revealed hand",
                    })
                  }
                >
                  <span className="text-[10px] text-slate-400">{playerName(s)}</span>
                  <div className="flex gap-0.5">
                    <PokerCard card={cards[0]} variant="seat" />
                    <PokerCard card={cards[1]} variant="seat" />
                  </div>
                </div>
              ))}
            </div>
          );
        })()}

        {/* Countdown / Status */}
        <div className="text-center mb-2">
          {autoStartScheduled && countdownSeconds > 0 ? (
            <span className="text-[11px] text-slate-400">
              Next hand in{" "}
              <span className="text-amber-400 font-bold text-sm">
                {countdownSeconds}
              </span>
              …
            </span>
          ) : showWaitingFallback ? (
            <span className="text-[11px] text-amber-300 animate-pulse">
              Waiting for server…
            </span>
          ) : autoStartBlockReason ? (
            <span className="text-[11px] text-amber-300">
              {autoStartBlockReason}
            </span>
          ) : (
            <span className="text-[10px] text-slate-500">
              Next hand starting soon…
            </span>
          )}
        </div>

        {/* Host deal button: show when auto-start is off OR when countdown expired as a fallback */}
        {isHost && onDealNow && (!autoStartScheduled || showWaitingFallback) && (
          <div className="text-center mb-2">
            <button
              onClick={onDealNow}
              className="px-4 py-1.5 rounded-lg text-xs font-semibold bg-gradient-to-r from-blue-500 to-blue-600 text-white shadow-lg hover:from-blue-400 hover:to-blue-500 transition-all min-h-[44px]"
            >
              Deal Now
            </button>
          </div>
        )}

        {/* Action buttons row */}
        <div className="flex items-center justify-center gap-2 pb-1">
          <button
            onClick={() => setShowDrawer(!showDrawer)}
            className="text-[11px] px-3 py-1.5 rounded-lg bg-white/5 text-slate-300 border border-white/10 hover:bg-white/10 transition-all min-h-[44px]"
          >
            {showDrawer ? "Hide Details" : "Hand Summary"}
          </button>
          <button
            onClick={onDismiss}
            className="text-[11px] px-3 py-1.5 rounded-lg bg-white/10 text-white border border-white/15 hover:bg-white/20 transition-all font-semibold min-h-[44px]"
          >
            Continue
          </button>
        </div>

        {/* Hand Summary Drawer */}
        {showDrawer && (
          <HandSummaryDrawer
            settlement={settlement}
            playerName={playerName}
          />
        )}
        </div>{/* end scrollable body */}
      </div>{/* end modal */}

      {/* Card zoom modal */}
      {zoomCards && (
        <CardZoomModal
          cards={zoomCards.cards}
          label={zoomCards.label}
          sublabel={zoomCards.sublabel}
          onClose={() => setZoomCards(null)}
        />
      )}
    </div>
  );

  return createPortal(overlay, document.body);
});

/* ── Winner Row ── */
function WinnerRow({
  seat,
  name,
  amount,
  handName,
  invested,
  revealedCards,
  onClickCards,
}: {
  seat: number;
  name: string;
  amount: number;
  handName?: string;
  invested: number;
  revealedCards?: [string, string];
  onClickCards?: () => void;
}) {
  const net = amount - invested;
  return (
    <div className="flex items-center gap-3 px-3 py-2 rounded-xl bg-amber-500/8 border border-amber-500/15 animate-[fadeSlideUp_0.35s_ease-out]">
      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-xs font-extrabold text-slate-900 shrink-0">
        {name[0]?.toUpperCase() ?? "?"}
      </div>
      <div className="flex flex-col min-w-0">
        <span className="text-white font-bold text-sm truncate">{name}</span>
        {handName && (
          <span className="text-slate-400 text-[10px]">{handName}</span>
        )}
      </div>
      {revealedCards && (
        <div
          className={`flex gap-0.5 shrink-0 ${onClickCards ? "cursor-pointer hover:opacity-80 transition-opacity" : ""}`}
          onClick={onClickCards}
          title={onClickCards ? "Tap to zoom" : undefined}
        >
          <PokerCard card={revealedCards[0]} variant="seat" />
          <PokerCard card={revealedCards[1]} variant="seat" />
        </div>
      )}
      <div className="ml-auto text-right shrink-0">
        <div className="text-amber-400 font-extrabold text-base">
          +{amount.toLocaleString()}
        </div>
        <div
          className={`text-[10px] font-mono ${
            net > 0
              ? "text-emerald-400"
              : net < 0
              ? "text-red-400"
              : "text-slate-400"
          }`}
        >
          net {net > 0 ? "+" : ""}
          {net.toLocaleString()}
        </div>
      </div>
    </div>
  );
}

/* ── Hand Summary Drawer ── */
function HandSummaryDrawer({
  settlement,
  playerName,
}: {
  settlement: SettlementResult;
  playerName: (seat: number) => string;
}) {
  return (
    <div className="mt-4 space-y-3 border-t border-white/10 pt-3">
      {/* Boards */}
      <div>
        <h4 className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">
          Board{settlement.runCount === 2 ? "s" : ""}
        </h4>
        {settlement.boards.map((board, idx) => (
          <div key={idx} className="flex items-center gap-1 mb-1">
            {settlement.runCount === 2 && (
              <span
                className={`text-[9px] font-bold uppercase w-10 shrink-0 ${
                  idx === 0 ? "text-cyan-400" : "text-amber-400"
                }`}
              >
                Run {idx + 1}
              </span>
            )}
            <div className="flex gap-1">
              {board.map((c, i) => (
                <PokerCard key={i} card={c} variant="mini" />
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Pot Breakdown */}
      <div>
        <h4 className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">
          Pot Breakdown
        </h4>
        <table className="w-full text-[10px]">
          <thead>
            <tr className="text-slate-500 border-b border-white/5">
              <th className="text-left py-1 font-medium">Pot</th>
              <th className="text-right py-1 font-medium">Amount</th>
              <th className="text-left py-1 font-medium pl-2">
                Eligible Seats
              </th>
              {settlement.runCount === 2 && (
                <>
                  <th className="text-right py-1 font-medium">Run 1</th>
                  <th className="text-right py-1 font-medium">Run 2</th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {settlement.potLayers.map((layer, idx) => (
              <tr
                key={idx}
                className="border-b border-white/5 last:border-0"
              >
                <td className="py-1 text-slate-300 font-medium">
                  {layer.label}
                </td>
                <td className="py-1 text-right text-amber-400 font-mono">
                  {layer.amount.toLocaleString()}
                </td>
                <td className="py-1 text-left pl-2 text-slate-400">
                  {layer.eligibleSeats
                    .map((s) => playerName(s))
                    .join(", ")}
                </td>
                {settlement.runCount === 2 && (
                  <>
                    <td className="py-1 text-right text-cyan-400 font-mono">
                      {Math.ceil(layer.amount / 2).toLocaleString()}
                    </td>
                    <td className="py-1 text-right text-amber-400 font-mono">
                      {Math.floor(layer.amount / 2).toLocaleString()}
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Payout Ledger */}
      <div>
        <h4 className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">
          Payout Ledger
        </h4>
        <div className="overflow-x-auto">
          <table className="w-full text-[10px] min-w-[400px]">
            <thead>
              <tr className="text-slate-500 border-b border-white/5">
                <th className="text-left py-1 font-medium">Player</th>
                <th className="text-right py-1 font-medium">Start</th>
                <th className="text-right py-1 font-medium">Invested</th>
                <th className="text-right py-1 font-medium">Won</th>
                <th className="text-right py-1 font-medium">End</th>
                <th className="text-right py-1 font-medium">Net</th>
              </tr>
            </thead>
            <tbody>
              {settlement.ledger.map((entry) => (
                <tr
                  key={entry.seat}
                  className="border-b border-white/5 last:border-0"
                >
                  <td className="py-1 text-slate-200 font-medium">
                    <span className="text-slate-500 mr-1">#{entry.seat}</span>
                    {entry.playerName}
                  </td>
                  <td className="py-1 text-right text-slate-400 font-mono">
                    {entry.startStack.toLocaleString()}
                  </td>
                  <td className="py-1 text-right text-red-400/70 font-mono">
                    {entry.invested > 0
                      ? `-${entry.invested.toLocaleString()}`
                      : "0"}
                  </td>
                  <td className="py-1 text-right text-emerald-400 font-mono">
                    {entry.won > 0
                      ? `+${entry.won.toLocaleString()}`
                      : "0"}
                  </td>
                  <td className="py-1 text-right text-slate-300 font-mono">
                    {entry.endStack.toLocaleString()}
                  </td>
                  <td
                    className={`py-1 text-right font-mono font-semibold ${
                      entry.net > 0
                        ? "text-emerald-400"
                        : entry.net < 0
                        ? "text-red-400"
                        : "text-slate-400"
                    }`}
                  >
                    {entry.net > 0 ? "+" : ""}
                    {entry.net.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Conservation check */}
      <div className="text-center text-[9px] text-slate-600 font-mono">
        totalPot={settlement.totalPot} · totalPaid={settlement.totalPaid} ·
        rake={settlement.rake} · Δ=
        {settlement.totalPot - settlement.totalPaid - settlement.rake}
      </div>
    </div>
  );
}
