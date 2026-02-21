import { memo, useEffect, useMemo, useState, useCallback } from "react";
import { PokerCard } from "../PokerCard";
import { getHands, type HandRecord } from "../../lib/hand-history";

/* ═══════════════════════════════════════════════════════════════
   InGameHandHistory
   Right-side drawer showing recent hand history during gameplay.
   Fetches from localStorage and shows hands for the current room.
   ═══════════════════════════════════════════════════════════════ */

interface InGameHandHistoryProps {
  open: boolean;
  onClose: () => void;
  currentRoomCode: string | null;
}

/** Street label abbreviation */
const STREET_SHORT: Record<string, string> = {
  PREFLOP: "Pre",
  FLOP: "Flop",
  TURN: "Turn",
  RIVER: "River",
};

/** Action type to display string */
const ACTION_LABEL: Record<string, string> = {
  fold: "Fold",
  check: "Check",
  call: "Call",
  bet: "Bet",
  raise: "Raise",
  all_in: "All-in",
  post_sb: "SB",
  post_bb: "BB",
  ante: "Ante",
};

export const InGameHandHistory = memo(function InGameHandHistory({
  open,
  onClose,
  currentRoomCode,
}: InGameHandHistoryProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // Refresh hands list every time drawer opens
  useEffect(() => {
    if (open) setRefreshKey((k) => k + 1);
  }, [open]);

  // ESC to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Get hands for current room, most recent first
  const hands = useMemo(() => {
    void refreshKey; // dependency
    const all = getHands();
    if (currentRoomCode) {
      return all.filter((h) => h.roomCode === currentRoomCode).slice(0, 50);
    }
    return all.slice(0, 50);
  }, [currentRoomCode, refreshKey]);

  const toggleExpand = useCallback((id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  }, []);

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/40 animate-[cpFadeIn_0.15s_ease-out]"
        style={{ zIndex: "var(--cp-z-drawer)" }}
        onClick={onClose}
      />

      {/* Drawer panel */}
      <div
        className="fixed top-0 right-0 bottom-0 w-[380px] max-w-[92vw] bg-[var(--cp-bg-surface)] border-l border-[var(--cp-border-default)] shadow-[var(--cp-shadow-xl)] overflow-y-auto"
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
          <div className="flex items-center gap-2">
            <span className="text-sm">📜</span>
            <h3 className="text-sm font-bold text-white">Hand History</h3>
            <span className="text-[9px] text-slate-500 bg-white/5 px-1.5 py-0.5 rounded-full">{hands.length}</span>
          </div>
          <button
            onClick={onClose}
            className="cp-btn cp-btn-ghost !min-h-[36px] !min-w-[36px] !px-0 text-sm"
            aria-label="Close drawer"
          >
            ✕
          </button>
        </div>

        {/* Hand list */}
        <div className="p-2 space-y-1">
          {hands.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-slate-500 text-xs">No hands recorded yet</p>
              <p className="text-slate-600 text-[10px] mt-1">Hands will appear here after each round</p>
            </div>
          ) : (
            hands.map((hand, idx) => (
              <HandRow
                key={hand.id}
                hand={hand}
                index={idx}
                expanded={expandedId === hand.id}
                onToggle={() => toggleExpand(hand.id)}
              />
            ))
          )}
        </div>
      </div>
    </>
  );
});

/* ── Individual hand row ── */

interface HandRowProps {
  hand: HandRecord;
  index: number;
  expanded: boolean;
  onToggle: () => void;
}

const HandRow = memo(function HandRow({ hand, index, expanded, onToggle }: HandRowProps) {
  const net = hand.result ?? 0;
  const netColor = net > 0 ? "text-emerald-400" : net < 0 ? "text-red-400" : "text-slate-400";
  const time = new Date(hand.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  return (
    <div className="rounded-lg border border-white/5 bg-white/[0.02] hover:bg-white/[0.04] transition-colors">
      {/* Summary row — always visible */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-3 py-2 text-left"
      >
        {/* Hand # */}
        <span className="text-[9px] text-slate-600 w-5 shrink-0 font-mono">#{index + 1}</span>

        {/* Hero cards */}
        <div className="flex gap-0.5 shrink-0">
          {hand.heroCards.slice(0, hand.heroCards.length > 2 ? 4 : 2).map((c, i) => (
            <PokerCard key={i} card={c} variant="mini" />
          ))}
        </div>

        {/* Position badge */}
        <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/5 text-slate-400 font-medium shrink-0">
          {hand.position}
        </span>

        {/* Board cards (compact) */}
        <div className="flex gap-0.5 shrink-0">
          {hand.board.slice(0, 5).map((c, i) => (
            <PokerCard key={i} card={c} variant="mini" />
          ))}
        </div>

        {/* Spacer */}
        <div className="flex-1 min-w-0" />

        {/* Result */}
        <span className={`text-xs font-bold font-mono cp-num shrink-0 ${netColor}`}>
          {net > 0 ? "+" : ""}{net.toLocaleString()}
        </span>

        {/* Time */}
        <span className="text-[9px] text-slate-600 shrink-0">{time}</span>

        {/* Expand indicator */}
        <span className="text-[10px] text-slate-500 shrink-0">{expanded ? "▾" : "▸"}</span>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="px-3 pb-3 pt-1 border-t border-white/5 space-y-2 animate-[cpFadeIn_0.15s_ease-out]">
          {/* Stakes & pot info */}
          <div className="flex items-center gap-3 text-[10px]">
            <span className="text-slate-500">Stakes: <span className="text-slate-300">{hand.stakes}</span></span>
            <span className="text-slate-500">Pot: <span className="text-amber-400 font-bold cp-num">{hand.potSize.toLocaleString()}</span></span>
            {hand.isBombPotHand && <span className="text-orange-400 text-[9px]">Bomb Pot</span>}
            {hand.isDoubleBoardHand && <span className="text-purple-400 text-[9px]">Double Board</span>}
          </div>

          {/* Board — hide when multiple runouts exist (shown inline below) */}
          {!(hand.runoutBoards && hand.runoutBoards.length > 1) && (
            <div>
              <span className="text-[9px] text-slate-500 uppercase tracking-wider font-semibold">Board</span>
              <div className="flex gap-1 mt-0.5">
                {hand.board.length === 0 ? (
                  <span className="text-[10px] text-slate-600 italic">No board (folded preflop)</span>
                ) : (
                  hand.board.map((c, i) => <PokerCard key={i} card={c} variant="seat" />)
                )}
              </div>
            </div>
          )}

          {/* Runout boards with per-run winners */}
          {hand.runoutBoards && hand.runoutBoards.length > 1 && (() => {
            const boards = hand.runoutBoards;
            const payouts = hand.doubleBoardPayouts;
            // Find common prefix cards
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
              <div>
                <span className="text-[9px] text-slate-500 uppercase tracking-wider font-semibold">Board</span>
                {/* Common cards (shared across runs) */}
                {commonCards.length > 0 && (
                  <div className="flex gap-0.5 mt-0.5 mb-1">
                    {commonCards.map((c, i) => <PokerCard key={i} card={c} variant="seat" />)}
                  </div>
                )}
                {/* Per-run boards */}
                <div className="space-y-1.5 mt-1">
                  {boards.map((b, bIdx) => {
                    const unique = b.slice(commonLen);
                    const displayCards = commonLen === 0 ? b : unique;
                    const runPayout = payouts?.find((p) => p.run === bIdx + 1);
                    return (
                      <div key={bIdx} className={`rounded-md border px-2 py-1.5 ${RUN_BG[bIdx] ?? RUN_BG[0]}`}>
                        <div className="flex items-center gap-1.5">
                          <span className={`text-[9px] font-bold shrink-0 ${RUN_COLORS[bIdx] ?? RUN_COLORS[0]}`}>
                            R{bIdx + 1}
                          </span>
                          <div className="flex gap-0.5">
                            {displayCards.map((c, i) => <PokerCard key={i} card={c} variant="mini" />)}
                          </div>
                        </div>
                        {/* Per-run winner */}
                        {runPayout && runPayout.winners.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
                            {runPayout.winners.map((w, wi) => {
                              const pName = hand.playerNames?.[w.seat] ?? `Seat ${w.seat}`;
                              const isHero = w.seat === hand.heroSeat;
                              return (
                                <span key={wi} className="text-[9px] flex items-center gap-1">
                                  <span className={isHero ? "text-emerald-300 font-semibold" : "text-slate-300"}>
                                    {pName}
                                  </span>
                                  <span className="text-emerald-400 font-bold">+{w.amount.toLocaleString()}</span>
                                  {w.handName && (
                                    <span className="text-slate-500">({w.handName})</span>
                                  )}
                                </span>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })()}

          {/* Action timeline */}
          <div>
            <span className="text-[9px] text-slate-500 uppercase tracking-wider font-semibold">Actions</span>
            <ActionTimeline hand={hand} />
          </div>

          {/* Showdown hands */}
          {hand.showdownHands && Object.keys(hand.showdownHands).length > 0 && (
            <div>
              <span className="text-[9px] text-slate-500 uppercase tracking-wider font-semibold">Showdown</span>
              <div className="mt-0.5 space-y-0.5">
                {Object.entries(hand.showdownHands).map(([seatStr, cards]) => {
                  const seatNum = Number(seatStr);
                  const pName = hand.playerNames?.[seatNum] ?? `Seat ${seatNum}`;
                  const isHero = seatNum === hand.heroSeat;
                  // Determine which runs this player won
                  const runsWon = hand.doubleBoardPayouts
                    ?.filter((p) => p.winners.some((w) => w.seat === seatNum))
                    .map((p) => p.run) ?? [];
                  const hasMultiRun = (hand.runoutBoards?.length ?? 0) > 1;
                  const RUN_BADGE = ["bg-cyan-500/20 text-cyan-400", "bg-amber-500/20 text-amber-400", "bg-emerald-500/20 text-emerald-400"];
                  return (
                    <div key={seatStr} className="flex items-center gap-2 text-[10px]">
                      <span className={`${isHero ? "text-cyan-300 font-semibold" : "text-slate-400"} shrink-0`}>{pName}</span>
                      {cards === "mucked" ? (
                        <span className="text-slate-600 italic text-[9px]">mucked</span>
                      ) : (
                        <div className="flex gap-0.5 shrink-0">
                          {cards.map((c, i) => <PokerCard key={i} card={c} variant="mini" />)}
                        </div>
                      )}
                      {/* Per-run win badges */}
                      {hasMultiRun && runsWon.length > 0 && (
                        <div className="flex gap-0.5 ml-auto shrink-0">
                          {runsWon.map((r) => (
                            <span key={r} className={`text-[8px] px-1.5 py-0.5 rounded-full font-bold ${RUN_BADGE[(r - 1)] ?? RUN_BADGE[0]}`}>
                              R{r}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Tags */}
          {hand.tags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {hand.tags.map((t) => (
                <span key={t} className="text-[8px] px-1.5 py-0.5 rounded-full bg-white/5 text-slate-400 border border-white/5">
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
});

/* ── Action timeline per street ── */

function ActionTimeline({ hand }: { hand: HandRecord }) {
  // Group actions by street
  const streets = useMemo(() => {
    const actions = hand.actionTimeline ?? hand.actions;
    if (!actions || actions.length === 0) return [];

    const grouped: Record<string, typeof actions> = {};
    for (const a of actions) {
      const street = a.street ?? "PREFLOP";
      if (!grouped[street]) grouped[street] = [];
      grouped[street].push(a);
    }

    const order = ["PREFLOP", "FLOP", "TURN", "RIVER"];
    return order
      .filter((s) => grouped[s] && grouped[s].length > 0)
      .map((s) => ({ street: s, actions: grouped[s] }));
  }, [hand.actionTimeline, hand.actions]);

  if (streets.length === 0) {
    return <p className="text-[10px] text-slate-600 italic mt-0.5">No actions recorded</p>;
  }

  return (
    <div className="mt-0.5 space-y-1">
      {streets.map(({ street, actions }) => (
        <div key={street}>
          <span className="text-[9px] font-semibold text-slate-400">{STREET_SHORT[street] ?? street}</span>
          <div className="flex flex-wrap gap-x-1.5 gap-y-0.5 mt-0.5">
            {actions.map((a, i) => {
              const pName = hand.playerNames?.[a.seat] ?? `S${a.seat}`;
              const isHero = a.seat === hand.heroSeat;
              const label = ACTION_LABEL[a.type] ?? a.type;
              const showAmount = a.amount > 0 && !["fold", "check"].includes(a.type);
              return (
                <span
                  key={i}
                  className={`text-[9px] ${isHero ? "text-cyan-300" : "text-slate-400"}`}
                >
                  {pName} {label}{showAmount ? ` ${a.amount.toLocaleString()}` : ""}
                  {i < actions.length - 1 && <span className="text-slate-600 ml-0.5">·</span>}
                </span>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

export default InGameHandHistory;
