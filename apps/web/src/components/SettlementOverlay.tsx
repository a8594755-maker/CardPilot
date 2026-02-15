import { useState, useEffect, useCallback, memo } from "react";
import type { SettlementResult, TablePlayer } from "@cardpilot/shared-types";

interface SettlementOverlayProps {
  settlement: SettlementResult;
  players: TablePlayer[];
  autoStartScheduled: boolean;
  autoStartBlockReason: string | null;
  countdownSeconds: number;
  onDismiss: () => void;
  onDealNow?: () => void;
  isHost: boolean;
  getCardImagePath: (card: string) => string;
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
  getCardImagePath,
}: SettlementOverlayProps) {
  const [showDrawer, setShowDrawer] = useState(false);

  const playerName = useCallback(
    (seat: number) => {
      const p = players.find((pl) => pl.seat === seat);
      return p?.name ?? `Seat ${seat}`;
    },
    [players]
  );

  // Combine all winners across runs for overlay header
  const allWinners = settlement.winnersByRun.flatMap((r) => r.winners);
  const uniqueWinnerSeats = [...new Set(allWinners.map((w) => w.seat))];

  return (
    <div className="w-full max-w-2xl mt-2 shrink-0 animate-[fadeSlideUp_0.5s_ease-out]">
      <div className="relative rounded-2xl border border-amber-500/30 bg-gradient-to-b from-amber-500/10 via-black/60 to-black/80 backdrop-blur-md px-6 py-4 shadow-[0_0_30px_rgba(245,158,11,0.15)]">
        {/* Close button */}
        <button
          onClick={onDismiss}
          className="absolute top-2 right-3 text-slate-500 hover:text-white text-sm transition-colors"
          title="Dismiss"
        >
          ✕
        </button>

        {/* Header */}
        <div className="flex items-center justify-center gap-2 mb-1">
          <span className="text-2xl">🏆</span>
          <span className="text-amber-400 text-lg font-extrabold tracking-wide uppercase">
            Hand Result
          </span>
          <span className="text-2xl">🏆</span>
        </div>
        <div className="text-center text-[10px] text-slate-500 font-mono mb-3">
          {settlement.handId.slice(0, 8)}
        </div>

        {/* Pot summary */}
        <div className="flex items-center justify-center gap-4 mb-3 text-[11px]">
          <span className="text-slate-400">
            Total Pot:{" "}
            <span className="text-amber-400 font-bold">
              {settlement.totalPot.toLocaleString()}
            </span>
          </span>
          <span className="text-slate-500">Rake: 0</span>
          <span className="text-slate-400">
            Paid:{" "}
            <span className="text-emerald-400 font-bold">
              {settlement.totalPaid.toLocaleString()}
            </span>
          </span>
        </div>

        {/* Run-it-twice: show per-run results */}
        {settlement.runCount === 2 ? (
          <div className="space-y-2 mb-3">
            {settlement.winnersByRun.map((run) => (
              <div
                key={run.run}
                className="rounded-xl border border-white/10 bg-white/[0.03] p-3"
              >
                <div className="flex items-center gap-2 mb-2">
                  <span
                    className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${
                      run.run === 1
                        ? "bg-cyan-500/20 text-cyan-400"
                        : "bg-amber-500/20 text-amber-400"
                    }`}
                  >
                    Run {run.run}
                  </span>
                  <div className="flex gap-0.5">
                    {run.board.map((c, i) => (
                      <img
                        key={i}
                        src={getCardImagePath(c)}
                        alt={c}
                        className="w-7 h-auto rounded"
                      />
                    ))}
                  </div>
                </div>
                <div className="flex flex-col gap-1">
                  {run.winners.map((w) => (
                    <WinnerRow
                      key={`${run.run}-${w.seat}`}
                      seat={w.seat}
                      name={playerName(w.seat)}
                      amount={w.amount}
                      handName={w.handName}
                      invested={settlement.contributions[w.seat] ?? 0}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          /* Standard single-run winners */
          <div className="flex flex-col items-center gap-2 mb-3">
            {allWinners.map((w) => (
              <WinnerRow
                key={w.seat}
                seat={w.seat}
                name={playerName(w.seat)}
                amount={w.amount}
                handName={w.handName}
                invested={settlement.contributions[w.seat] ?? 0}
              />
            ))}
          </div>
        )}

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

        {/* Host deal button when auto-start is off */}
        {isHost && !autoStartScheduled && onDealNow && (
          <div className="text-center mb-2">
            <button
              onClick={onDealNow}
              className="px-4 py-1.5 rounded-lg text-xs font-semibold bg-gradient-to-r from-blue-500 to-blue-600 text-white shadow-lg hover:from-blue-400 hover:to-blue-500 transition-all"
            >
              Deal Now
            </button>
          </div>
        )}

        {/* Hand Summary button */}
        <div className="text-center">
          <button
            onClick={() => setShowDrawer(!showDrawer)}
            className="text-[11px] px-3 py-1.5 rounded-lg bg-white/5 text-slate-300 border border-white/10 hover:bg-white/10 transition-all"
          >
            {showDrawer ? "Hide Details" : "Hand Summary"}
          </button>
        </div>

        {/* Hand Summary Drawer */}
        {showDrawer && (
          <HandSummaryDrawer
            settlement={settlement}
            playerName={playerName}
            getCardImagePath={getCardImagePath}
          />
        )}
      </div>
    </div>
  );
});

/* ── Winner Row ── */
function WinnerRow({
  seat,
  name,
  amount,
  handName,
  invested,
}: {
  seat: number;
  name: string;
  amount: number;
  handName?: string;
  invested: number;
}) {
  const net = amount - invested;
  return (
    <div className="flex items-center gap-3 px-4 py-2 rounded-xl bg-amber-500/10 border border-amber-500/20 animate-[fadeSlideUp_0.6s_ease-out]">
      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-xs font-extrabold text-slate-900 shadow-lg shrink-0">
        {name[0]?.toUpperCase() ?? "?"}
      </div>
      <div className="flex flex-col min-w-0">
        <span className="text-white font-bold text-sm truncate">{name}</span>
        {handName && (
          <span className="text-slate-400 text-[10px]">{handName}</span>
        )}
      </div>
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
  getCardImagePath,
}: {
  settlement: SettlementResult;
  playerName: (seat: number) => string;
  getCardImagePath: (card: string) => string;
}) {
  return (
    <div className="mt-4 space-y-3 border-t border-white/10 pt-3 max-h-[50vh] overflow-y-auto">
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
            <div className="flex gap-0.5">
              {board.map((c, i) => (
                <img
                  key={i}
                  src={getCardImagePath(c)}
                  alt={c}
                  className="w-8 h-auto rounded"
                />
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
