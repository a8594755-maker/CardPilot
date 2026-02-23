import { memo, useEffect, useMemo, useState, useCallback, useRef } from "react";
import { PokerCard } from "../PokerCard";
import { getHands, type HandRecord } from "../../lib/hand-history";
import type { Socket } from "socket.io-client";
import type { HistoryHandSummary } from "@cardpilot/shared-types";

/* ═══════════════════════════════════════════════════════════════
   InGameHandHistory
   Right-side drawer showing recent hand history during gameplay.
   Fetches from server (all room history) + localStorage (hero detail).
   ═══════════════════════════════════════════════════════════════ */

interface InGameHandHistoryProps {
  open: boolean;
  onClose: () => void;
  currentRoomCode: string | null;
  socket: Socket | null;
  tableId: string | null;
}

/** Merged display item combining server summary + optional local detail */
type MergedHand = {
  id: string;
  handNo: number;
  endedAt: string;
  time: number;
  stakes: string;
  potSize: number;
  players: Array<{ seat: number; name: string }>;
  winners: Array<{ seat: number; amount: number; handName?: string }>;
  flags: { allIn: boolean; showdown: boolean; bombPot?: boolean; doubleBoard?: boolean };
  local?: HandRecord;
};

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
  socket,
  tableId,
}: InGameHandHistoryProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [serverHands, setServerHands] = useState<HistoryHandSummary[]>([]);
  const [loadingServer, setLoadingServer] = useState(false);
  const lastFetchedRoomRef = useRef<string | null>(null);

  // Refresh hands list every time drawer opens
  useEffect(() => {
    if (open) setRefreshKey((k) => k + 1);
  }, [open]);

  // Fetch from server when drawer opens or room changes
  useEffect(() => {
    if (!open || !socket || !tableId) return;
    // Avoid re-fetching for the same room if already loaded
    if (lastFetchedRoomRef.current === tableId && serverHands.length > 0) return;

    setLoadingServer(true);
    socket.emit("request_room_hands", { roomId: tableId, limit: 200 });
    lastFetchedRoomRef.current = tableId;
  }, [open, socket, tableId]);

  // Listen for server response
  useEffect(() => {
    if (!socket) return;
    const handler = (payload: { roomId: string; hands: HistoryHandSummary[] }) => {
      if (payload.roomId === tableId) {
        setServerHands(payload.hands ?? []);
        setLoadingServer(false);
      }
    };
    socket.on("room_hands" as string, handler);
    return () => { socket.off("room_hands" as string, handler); };
  }, [socket, tableId]);

  // Re-fetch when a new hand ends (to pick up newly persisted hands)
  useEffect(() => {
    if (!socket || !tableId) return;
    const handler = () => {
      // Small delay to let the server persist the hand first
      setTimeout(() => {
        socket.emit("request_room_hands", { roomId: tableId, limit: 200 });
      }, 1500);
    };
    socket.on("hand_ended", handler);
    return () => { socket.off("hand_ended", handler); };
  }, [socket, tableId]);

  // ESC to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Get local hands for current room
  const localHands = useMemo(() => {
    void refreshKey;
    const all = getHands();
    if (currentRoomCode) {
      return all.filter((h) => h.roomCode === currentRoomCode);
    }
    return all;
  }, [currentRoomCode, refreshKey]);

  // Merge server + local hands, deduplicate by handId
  const hands = useMemo((): MergedHand[] => {
    // Index local hands by handId for quick lookup
    const localByHandId = new Map<string, HandRecord>();
    for (const h of localHands) {
      if (h.handId) localByHandId.set(h.handId, h);
    }

    const merged = new Map<string, MergedHand>();

    // Add server hands first (authoritative source)
    for (const sh of serverHands) {
      const local = localByHandId.get(sh.handId);
      merged.set(sh.handId, {
        id: sh.id,
        handNo: sh.handNo,
        endedAt: sh.endedAt,
        time: new Date(sh.endedAt).getTime(),
        stakes: `${sh.blinds.sb}/${sh.blinds.bb}`,
        potSize: sh.summary.totalPot,
        players: sh.players.map((p) => ({ seat: p.seat, name: p.name })),
        winners: sh.summary.winners,
        flags: sh.summary.flags,
        local,
      });
    }

    // Add any local-only hands not already from server
    for (const h of localHands) {
      if (h.handId && merged.has(h.handId)) continue;
      const key = h.handId ?? h.id;
      if (merged.has(key)) continue;
      merged.set(key, {
        id: h.id,
        handNo: 0, // will be assigned later
        endedAt: h.endedAt ?? new Date(h.createdAt).toISOString(),
        time: h.createdAt,
        stakes: h.stakes,
        potSize: h.potSize,
        players: h.playerNames
          ? Object.entries(h.playerNames).map(([s, n]) => ({ seat: Number(s), name: n }))
          : [],
        winners: [],
        flags: {
          allIn: h.tags.includes("all_in"),
          showdown: Object.keys(h.showdownHands ?? {}).length > 0,
          bombPot: h.isBombPotHand,
          doubleBoard: h.isDoubleBoardHand,
        },
        local: h,
      });
    }

    // Sort by time descending (newest first for display)
    const result = [...merged.values()].sort((a, b) => b.time - a.time);

    // Assign handNo for items that don't have one (chronological: oldest = 1)
    // First, create a chronological copy to assign numbers
    const chronological = [...result].reverse();
    for (let i = 0; i < chronological.length; i++) {
      if (chronological[i].handNo === 0) {
        chronological[i].handNo = i + 1;
      }
    }

    return result;
  }, [serverHands, localHands]);

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
          {loadingServer && hands.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-slate-500 text-xs">Loading hand history...</p>
            </div>
          ) : hands.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-slate-500 text-xs">No hands recorded yet</p>
              <p className="text-slate-600 text-[10px] mt-1">Hands will appear here after each round</p>
            </div>
          ) : (
            hands.map((hand) => (
              <HandRow
                key={hand.id}
                hand={hand}
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
  hand: MergedHand;
  expanded: boolean;
  onToggle: () => void;
}

const HandRow = memo(function HandRow({ hand, expanded, onToggle }: HandRowProps) {
  const local = hand.local;
  const net = local?.result ?? 0;
  const hasLocalDetail = !!local;
  const netColor = net > 0 ? "text-emerald-400" : net < 0 ? "text-red-400" : "text-slate-400";
  const time = new Date(hand.time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  return (
    <div className="rounded-lg border border-white/5 bg-white/[0.02] hover:bg-white/[0.04] transition-colors">
      {/* Summary row — always visible */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-3 py-2 text-left"
      >
        {/* Hand # (chronological: oldest=1, newest=N) */}
        <span className="text-[9px] text-slate-600 w-6 shrink-0 font-mono">#{hand.handNo}</span>

        {/* Hero cards (if seated) or player count */}
        {hasLocalDetail && local.heroCards.length >= 2 ? (
          <div className="flex gap-0.5 shrink-0">
            {local.heroCards.slice(0, local.heroCards.length > 2 ? 4 : 2).map((c, i) => (
              <PokerCard key={i} card={c} variant="mini" />
            ))}
          </div>
        ) : (
          <span className="text-[9px] text-slate-500 shrink-0">{hand.players.length}P</span>
        )}

        {/* Position badge (if seated) */}
        {hasLocalDetail ? (
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/5 text-slate-400 font-medium shrink-0">
            {local.position}
          </span>
        ) : null}

        {/* Board cards (compact, if available) */}
        {hasLocalDetail && local.board.length > 0 ? (
          <div className="flex gap-0.5 shrink-0">
            {local.board.slice(0, 5).map((c, i) => (
              <PokerCard key={i} card={c} variant="mini" />
            ))}
          </div>
        ) : (
          <span className="text-[9px] text-slate-500 shrink-0">
            Pot {hand.potSize.toLocaleString()}
          </span>
        )}

        {/* Spacer */}
        <div className="flex-1 min-w-0" />

        {/* Result (if seated) or winners summary */}
        {hasLocalDetail ? (
          <span className={`text-xs font-bold font-mono cp-num shrink-0 ${netColor}`}>
            {net > 0 ? "+" : ""}{net.toLocaleString()}
          </span>
        ) : hand.winners.length > 0 ? (
          <span className="text-[9px] text-emerald-400 shrink-0">
            {hand.winners[0]?.handName ?? `+${hand.winners[0]?.amount.toLocaleString()}`}
          </span>
        ) : null}

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
            {hand.flags.bombPot && <span className="text-orange-400 text-[9px]">Bomb Pot</span>}
            {hand.flags.doubleBoard && <span className="text-purple-400 text-[9px]">Double Board</span>}
            {hand.flags.allIn && <span className="text-red-400 text-[9px]">All-in</span>}
          </div>

          {/* Players */}
          <div>
            <span className="text-[9px] text-slate-500 uppercase tracking-wider font-semibold">Players</span>
            <div className="flex flex-wrap gap-1.5 mt-0.5">
              {hand.players.map((p) => (
                <span key={p.seat} className="text-[9px] text-slate-400">{p.name}</span>
              ))}
            </div>
          </div>

          {/* Winners */}
          {hand.winners.length > 0 && (
            <div>
              <span className="text-[9px] text-slate-500 uppercase tracking-wider font-semibold">Winners</span>
              <div className="mt-0.5 space-y-0.5">
                {hand.winners.map((w, i) => {
                  const pName = hand.players.find((p) => p.seat === w.seat)?.name ?? `Seat ${w.seat}`;
                  return (
                    <div key={i} className="flex items-center gap-2 text-[10px]">
                      <span className="text-slate-300">{pName}</span>
                      <span className="text-emerald-400 font-bold">+{w.amount.toLocaleString()}</span>
                      {w.handName && <span className="text-slate-500">({w.handName})</span>}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ── Local detail (only when hero was seated) ── */}
          {hasLocalDetail && (
            <>
              {/* Board — hide when multiple runouts exist */}
              {!(local.runoutBoards && local.runoutBoards.length > 1) && (
                <div>
                  <span className="text-[9px] text-slate-500 uppercase tracking-wider font-semibold">Board</span>
                  <div className="flex gap-1 mt-0.5">
                    {local.board.length === 0 ? (
                      <span className="text-[10px] text-slate-600 italic">No board (folded preflop)</span>
                    ) : (
                      local.board.map((c, i) => <PokerCard key={i} card={c} variant="seat" />)
                    )}
                  </div>
                </div>
              )}

              {/* Runout boards with per-run winners */}
              {local.runoutBoards && local.runoutBoards.length > 1 && (() => {
                const boards = local.runoutBoards!;
                const payouts = local.doubleBoardPayouts;
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
                    {commonCards.length > 0 && (
                      <div className="flex gap-0.5 mt-0.5 mb-1">
                        {commonCards.map((c, i) => <PokerCard key={i} card={c} variant="seat" />)}
                      </div>
                    )}
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
                            {runPayout && runPayout.winners.length > 0 && (
                              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
                                {runPayout.winners.map((w, wi) => {
                                  const pName = local.playerNames?.[w.seat] ?? `Seat ${w.seat}`;
                                  const isHero = w.seat === local.heroSeat;
                                  return (
                                    <span key={wi} className="text-[9px] flex items-center gap-1">
                                      <span className={isHero ? "text-emerald-300 font-semibold" : "text-slate-300"}>
                                        {pName}
                                      </span>
                                      <span className="text-emerald-400 font-bold">+{w.amount.toLocaleString()}</span>
                                      {w.handName && <span className="text-slate-500">({w.handName})</span>}
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
                <ActionTimeline hand={local} />
              </div>

              {/* Showdown hands */}
              {local.showdownHands && Object.keys(local.showdownHands).length > 0 && (
                <div>
                  <span className="text-[9px] text-slate-500 uppercase tracking-wider font-semibold">Showdown</span>
                  <div className="mt-0.5 space-y-0.5">
                    {Object.entries(local.showdownHands).map(([seatStr, cards]) => {
                      const seatNum = Number(seatStr);
                      const pName = local.playerNames?.[seatNum] ?? `Seat ${seatNum}`;
                      const isHero = seatNum === local.heroSeat;
                      const runsWon = local.doubleBoardPayouts
                        ?.filter((p) => p.winners.some((w) => w.seat === seatNum))
                        .map((p) => p.run) ?? [];
                      const hasMultiRun = (local.runoutBoards?.length ?? 0) > 1;
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
              {local.tags.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {local.tags.map((t) => (
                    <span key={t} className="text-[8px] px-1.5 py-0.5 rounded-full bg-white/5 text-slate-400 border border-white/5">
                      {t}
                    </span>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
});

/* ── Action timeline per street ── */

function ActionTimeline({ hand }: { hand: HandRecord }) {
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
