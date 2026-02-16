import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { HandActionRecord, HandRecord, GTOAnalysis, LocalGTOSpot } from "../../lib/hand-history.js";
import { formatHandAsPokerStars } from "../../lib/hand-history.js";
import { PokerCard } from "../../components/PokerCard.js";
import type { Socket } from "socket.io-client";
import type { HistoryGTOAnalysis } from "@cardpilot/shared-types";

const STREETS = ["PREFLOP", "FLOP", "TURN", "RIVER"];
const EDITABLE_TAGS = ["SRP", "3bet_pot", "4bet_pot", "all_in"];

function splitBoard(board: string[]) {
  return {
    flop: board.slice(0, 3),
    turn: board.slice(3, 4),
    river: board.slice(4, 5),
  };
}

function streetGroups(actions: HandActionRecord[]) {
  return STREETS.map((street) => ({
    street,
    actions: actions.filter((a) => a.street.toUpperCase() === street),
  })).filter((g) => g.actions.length > 0);
}

/** Compute running pot total for action display */
function computeRunningPot(actions: HandActionRecord[], upToIndex: number): number {
  let pot = 0;
  for (let i = 0; i <= upToIndex; i++) {
    const a = actions[i];
    if (a.type !== "fold" && a.type !== "check") {
      pot += a.amount;
    }
  }
  return pot;
}

type GtoState = "idle" | "loading" | "success" | "error";

function mapServerToLocal(server: HistoryGTOAnalysis): GTOAnalysis {
  return {
    overallScore: server.overallScore,
    streets: server.spots.map((s) => ({
      street: s.street,
      action: s.heroAction,
      gtoAction: s.recommended.action,
      evDiff: s.deviationScore,
      accuracy: s.deviationScore <= 20 ? "good" : s.deviationScore <= 50 ? "ok" : "bad",
    })),
    analyzedAt: server.computedAt,
    precision: server.precision,
    streetScores: server.streetScores,
    spots: server.spots.map((s): LocalGTOSpot => ({
      street: s.street,
      pot: s.pot,
      toCall: s.toCall,
      effectiveStack: s.effectiveStack,
      heroAction: s.heroAction,
      heroAmount: s.heroAmount,
      recommendedAction: s.recommended.action,
      recommendedMix: s.recommended.mix,
      deviationScore: s.deviationScore,
      evLossBb: s.evLossBb,
      actionTimelineIdx: s.actionTimelineIdx,
      decisionIndex: s.decisionIndex,
      note: s.note,
    })),
  };
}

interface DecisionPointView {
  id: string;
  street: string;
  pot: number;
  toCall?: number;
  effectiveStack?: number;
  heroAction: string;
  heroAmount: number;
  recommendedAction: string;
  deviationScore: number;
  actionTimelineIdx?: number;
  evLossBb?: number;
  note?: string;
}

export function HandDetail2({
  hand,
  onCopy,
  onDownload,
  onToggleTag,
  socket,
  onSaveAnalysis,
}: {
  hand: HandRecord | null;
  onCopy: (text: string) => Promise<void>;
  onDownload: (hand: HandRecord) => void;
  onToggleTag: (tag: string) => void;
  socket?: Socket | null;
  onSaveAnalysis?: (handId: string, analysis: GTOAnalysis) => void;
}) {
  const [customTag, setCustomTag] = useState("");
  const [copied, setCopied] = useState<"hh" | "json" | null>(null);
  const [gtoState, setGtoState] = useState<GtoState>("idle");
  const [gtoResult, setGtoResult] = useState<HistoryGTOAnalysis | null>(null);
  const [gtoError, setGtoError] = useState<string | null>(null);
  const [selectedActionIdx, setSelectedActionIdx] = useState<number | null>(null);
  const actionRefs = useRef<Record<number, HTMLDivElement | null>>({});

  // Reset GTO state when hand changes; restore from local cache if available
  useEffect(() => {
    setGtoState(hand?.gtoAnalysis ? "success" : "idle");
    setGtoResult(null);
    setGtoError(null);
    setSelectedActionIdx(null);
  }, [hand?.id]);

  // Listen for GTO result from server
  useEffect(() => {
    if (!socket || !hand) return;
    const handler = (payload: { handId: string; gtoAnalysis: HistoryGTOAnalysis | null; error?: string }) => {
      if (payload.handId !== hand.id) return;
      if (payload.error || !payload.gtoAnalysis) {
        setGtoState("error");
        setGtoError(payload.error ?? "Analysis failed");
        return;
      }
      setGtoResult(payload.gtoAnalysis);
      setGtoState("success");
      // Persist to localStorage
      const localAnalysis = mapServerToLocal(payload.gtoAnalysis);
      onSaveAnalysis?.(hand.id, localAnalysis);
    };
    socket.on("history_gto_result" as string, handler);
    return () => { socket.off("history_gto_result" as string, handler); };
  }, [socket, hand?.id, onSaveAnalysis]);

  const requestAnalysis = useCallback((precision: "fast" | "deep") => {
    if (!socket || !hand) return;
    setGtoState("loading");
    setGtoError(null);
    setGtoResult(null);
    socket.emit("history_gto_analyze" as string, {
      handId: hand.id,
      handRecord: {
        heroCards: hand.heroCards,
        board: hand.board,
        heroSeat: hand.heroSeat ?? 0,
        heroPosition: hand.position,
        stakes: hand.stakes,
        tableSize: hand.tableSize,
        potSize: hand.potSize,
        stackSize: hand.stackSize,
        actions: hand.actions,
        actionTimeline: hand.actionTimeline,
        buttonSeat: hand.buttonSeat,
        positionsBySeat: hand.positionsBySeat,
        stacksBySeatAtStart: hand.stacksBySeatAtStart,
        potLayers: hand.potLayers,
        payoutLedger: hand.payoutLedger,
        smallBlind: hand.smallBlind,
        bigBlind: hand.bigBlind,
        playerNames: hand.playerNames,
      },
      precision,
    });
  }, [socket, hand]);

  const groupedActions = useMemo(() => (hand ? streetGroups(hand.actions) : []), [hand]);
  const groupedActionsWithIndex = useMemo(() => {
    let cursor = 0;
    return groupedActions.map((group) => ({
      ...group,
      actions: group.actions.map((action) => {
        const globalIdx = cursor;
        cursor += 1;
        return { action, globalIdx };
      }),
    }));
  }, [groupedActions]);

  const decisionPoints = useMemo<DecisionPointView[]>(() => {
    if (gtoResult?.spots?.length) {
      return gtoResult.spots.map((spot, idx) => ({
        id: `server-${idx}`,
        street: spot.street,
        pot: spot.pot,
        toCall: spot.toCall,
        effectiveStack: spot.effectiveStack,
        heroAction: spot.heroAction,
        heroAmount: spot.heroAmount,
        recommendedAction: spot.recommended.action,
        deviationScore: spot.deviationScore,
        actionTimelineIdx: spot.actionTimelineIdx,
        evLossBb: spot.evLossBb,
        note: spot.note,
      }));
    }

    if (hand?.gtoAnalysis?.spots?.length) {
      return hand.gtoAnalysis.spots.map((spot, idx) => ({
        id: `local-${idx}`,
        street: spot.street,
        pot: spot.pot,
        toCall: spot.toCall,
        effectiveStack: spot.effectiveStack,
        heroAction: spot.heroAction,
        heroAmount: spot.heroAmount,
        recommendedAction: spot.recommendedAction,
        deviationScore: spot.deviationScore,
        actionTimelineIdx: spot.actionTimelineIdx,
        evLossBb: spot.evLossBb,
        note: spot.note,
      }));
    }

    return [];
  }, [gtoResult, hand?.gtoAnalysis]);

  const onSelectDecisionPoint = useCallback((point: DecisionPointView) => {
    if (typeof point.actionTimelineIdx !== "number") return;
    setSelectedActionIdx(point.actionTimelineIdx);
    const node = actionRefs.current[point.actionTimelineIdx];
    if (node) {
      node.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, []);

  if (!hand) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <div className="text-4xl mb-3 opacity-30">🔍</div>
        <p className="text-slate-400 text-sm">Select a hand to view details</p>
      </div>
    );
  }

  const runouts = hand.runoutBoards && hand.runoutBoards.length > 0 ? hand.runoutBoards : [hand.board];
  const result = hand.result ?? 0;
  const heroSeat = hand.heroSeat;

  const handleCopyHH = async () => {
    const text = formatHandAsPokerStars(hand);
    await onCopy(text);
    setCopied("hh");
    setTimeout(() => setCopied(null), 2000);
  };

  const handleCopyJSON = async () => {
    await onCopy(JSON.stringify(hand, null, 2));
    setCopied("json");
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div className="flex-1 overflow-auto p-3 space-y-4">
      {/* Header */}
      <div className="rounded-xl bg-slate-800/40 border border-white/[0.06] p-4">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <div className="flex items-center gap-2 mb-2">
              {hand.roomName || hand.roomCode ? (
                <span className="text-xs text-slate-400 font-medium">
                  {hand.roomName || hand.roomCode}
                </span>
              ) : null}
              {hand.handId && (
                <span className="text-[10px] font-mono text-slate-500">#{hand.handId.slice(0, 12)}</span>
              )}
            </div>
            <div className="flex items-center gap-2 text-[11px] text-slate-400">
              <span className="font-medium text-white">{hand.gameType} {hand.stakes}</span>
              <span className="text-slate-600">·</span>
              <span>{hand.tableSize}-max</span>
              <span className="text-slate-600">·</span>
              <span className="text-cyan-400/80">{hand.position}</span>
              {hand.heroName && (
                <>
                  <span className="text-slate-600">·</span>
                  <span>{hand.heroName}</span>
                </>
              )}
            </div>
            <div className="text-[10px] text-slate-500 mt-1">
              {hand.endedAt
                ? new Date(hand.endedAt).toLocaleString()
                : new Date(hand.createdAt).toLocaleString()}
            </div>
          </div>
          <div className="flex flex-col items-end gap-1">
            <div className={`text-xl font-bold tabular-nums ${
              result > 0 ? "text-emerald-400" : result < 0 ? "text-red-400" : "text-slate-300"
            }`}>
              {result > 0 ? "+" : ""}{result.toLocaleString()}
            </div>
            <div className="flex items-center gap-2 text-[11px] text-slate-400">
              <span>Pot {hand.potSize.toLocaleString()}</span>
              <span className="text-slate-600">·</span>
              <span>Stack {hand.stackSize.toLocaleString()}</span>
            </div>
          </div>
        </div>
      </div>

      {/* GTO Analysis */}
      <div className="rounded-xl bg-slate-800/40 border border-white/[0.06] p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">GTO Analysis</div>
          <div className="flex items-center gap-2">
            {gtoState !== "loading" && (
              <>
                <button
                  onClick={() => requestAnalysis("deep")}
                  disabled={!socket}
                  title={!socket ? "Connect to the live game server to enable GTO analysis." : "Run deep server-side GTO analysis"}
                  className="text-[10px] px-3 py-1.5 rounded-lg bg-gradient-to-r from-purple-600/80 to-indigo-600/80 text-white font-semibold border border-purple-500/30 hover:from-purple-500/90 hover:to-indigo-500/90 transition-all disabled:opacity-45 disabled:cursor-not-allowed"
                >
                  Analyze (Deep)
                </button>
                <button
                  onClick={() => requestAnalysis("fast")}
                  disabled={!socket}
                  title={!socket ? "Connect to the live game server to enable GTO analysis." : "Run fast server-side GTO analysis"}
                  className="text-[10px] px-3 py-1.5 rounded-lg bg-slate-700/50 text-slate-300 border border-white/[0.08] hover:bg-slate-700/70 transition-all disabled:opacity-45 disabled:cursor-not-allowed"
                >
                  Fast
                </button>
              </>
            )}
          </div>
        </div>

        {gtoState === "loading" && (
          <div className="flex items-center gap-2 py-4">
            <div className="w-4 h-4 border-2 border-purple-400 border-t-transparent rounded-full animate-spin" />
            <span className="text-xs text-slate-400">Running deep analysis...</span>
          </div>
        )}

        {gtoState === "error" && (
          <div className="text-xs text-red-400 py-2">{gtoError ?? "Analysis failed"}</div>
        )}

        {gtoState === "success" && (gtoResult || hand.gtoAnalysis) && (
          <GtoResultView result={gtoResult} localAnalysis={hand.gtoAnalysis} />
        )}

        {gtoState === "idle" && !hand.gtoAnalysis && !socket && (
          <div className="text-xs text-slate-500 py-2">Connect to server to run GTO analysis.</div>
        )}
        {gtoState === "idle" && !hand.gtoAnalysis && socket && (
          <div className="text-xs text-slate-500 py-2">Press Analyze to evaluate this hand against GTO strategy.</div>
        )}
      </div>

      {/* Decision Points */}
      {decisionPoints.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Decision Points</div>
          <div className="space-y-1.5">
            {decisionPoints.map((point, idx) => {
              const badge = deviationBadge(point.deviationScore);
              const isLinked = typeof point.actionTimelineIdx === "number";
              return (
                <button
                  key={point.id}
                  onClick={() => onSelectDecisionPoint(point)}
                  disabled={!isLinked}
                  className={`w-full text-left rounded-lg border p-2.5 transition-all ${
                    isLinked
                      ? "border-white/[0.08] bg-slate-800/30 hover:border-sky-500/40"
                      : "border-white/[0.04] bg-slate-800/20 opacity-80"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[10px] font-bold text-cyan-400 uppercase">{point.street}</span>
                    <span className={`text-[9px] px-1.5 py-0.5 rounded-full border ${badge.cls}`}>{badge.label}</span>
                    <span className="text-[10px] text-slate-600">#{idx + 1}</span>
                    <span className="ml-auto text-[10px] text-slate-500 tabular-nums">
                      pot {point.pot.toLocaleString()}
                      {typeof point.toCall === "number" ? ` · toCall ${point.toCall.toLocaleString()}` : ""}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-300">
                    <span className="text-slate-500">You: </span>
                    <span className="font-semibold uppercase">{point.heroAction}</span>
                    {point.heroAmount > 0 && <span className="ml-1 tabular-nums">{point.heroAmount.toLocaleString()}</span>}
                    <span className="mx-2 text-slate-600">→</span>
                    <span className="text-slate-500">GTO: </span>
                    <span className="font-semibold uppercase text-purple-300">{point.recommendedAction}</span>
                    {typeof point.evLossBb === "number" && (
                      <span className="ml-2 text-[10px] text-amber-300">~{point.evLossBb.toFixed(2)} bb loss</span>
                    )}
                  </div>
                  {point.note && <div className="text-[10px] text-slate-500 mt-1 truncate">{point.note}</div>}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Hero Cards */}
      <div>
        <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Hero Cards</div>
        <div className="flex gap-1.5">
          {hand.heroCards.map((c) => (
            <PokerCard key={c} card={c} variant="seat" />
          ))}
        </div>
      </div>

      {/* Board / Runouts */}
      <div>
        <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Board</div>
        {runouts.map((board, idx) => {
          const split = splitBoard(board);
          return (
            <div
              key={idx}
              className="rounded-lg bg-slate-800/30 border border-white/[0.06] p-3 mb-2"
            >
              {runouts.length > 1 && (
                <div className="text-[10px] font-semibold text-amber-400 uppercase mb-2">
                  Run {idx + 1}
                </div>
              )}
              <div className="flex items-center gap-4 flex-wrap">
                {/* Flop */}
                {split.flop.length > 0 && (
                  <div>
                    <div className="text-[9px] text-slate-500 uppercase mb-1">Flop</div>
                    <div className="flex gap-0.5">
                      {split.flop.map((c, i) => (
                        <PokerCard key={`f${i}`} card={c} variant="mini" />
                      ))}
                    </div>
                  </div>
                )}
                {/* Turn */}
                {split.turn.length > 0 && (
                  <div>
                    <div className="text-[9px] text-slate-500 uppercase mb-1">Turn</div>
                    <div className="flex gap-0.5">
                      {split.turn.map((c, i) => (
                        <PokerCard key={`t${i}`} card={c} variant="mini" />
                      ))}
                    </div>
                  </div>
                )}
                {/* River */}
                {split.river.length > 0 && (
                  <div>
                    <div className="text-[9px] text-slate-500 uppercase mb-1">River</div>
                    <div className="flex gap-0.5">
                      {split.river.map((c, i) => (
                        <PokerCard key={`r${i}`} card={c} variant="mini" />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Showdown Hands */}
      {hand.showdownHands && Object.keys(hand.showdownHands).length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Showdown</div>
          <div className="space-y-1.5">
            {Object.entries(hand.showdownHands).map(([seatStr, cards]) => {
              const seatNum = Number(seatStr);
              const playerName = hand.playerNames?.[seatNum] || `Seat ${seatNum}`;
              const isHero = seatNum === heroSeat;
              return (
                <div
                  key={seatStr}
                  className={`flex items-center gap-3 rounded-lg px-3 py-2 border ${
                    isHero
                      ? "border-sky-500/30 bg-sky-500/5"
                      : "border-white/[0.06] bg-white/[0.02]"
                  }`}
                >
                  <span className={`text-xs font-medium min-w-[80px] ${isHero ? "text-sky-300" : "text-slate-300"}`}>
                    {playerName}
                    {isHero && <span className="text-[9px] text-sky-500 ml-1">(Hero)</span>}
                  </span>
                  {cards === "mucked" ? (
                    <span className="text-[11px] text-slate-500 italic">Mucked</span>
                  ) : (
                    <div className="flex gap-0.5">
                      {cards.map((c) => (
                        <PokerCard key={c} card={c} variant="seat" />
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
      <div>
        <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Tags</div>
        <div className="flex items-center flex-wrap gap-1.5">
          {EDITABLE_TAGS.map((tag) => (
            <button
              key={tag}
              onClick={() => onToggleTag(tag)}
              className={`text-[10px] px-2.5 py-1 rounded-full border transition-all ${
                hand.tags.includes(tag)
                  ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                  : "bg-slate-800/40 text-slate-400 border-white/[0.08] hover:border-white/[0.15]"
              }`}
            >
              {tag}
            </button>
          ))}
          <input
            className="text-[10px] bg-slate-800/40 border border-white/[0.08] rounded-full px-2.5 py-1 text-slate-300 w-[90px] outline-none focus:border-sky-500/40"
            value={customTag}
            placeholder="+ tag"
            onChange={(e) => setCustomTag(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                const tag = customTag.trim();
                if (tag && !hand.tags.includes(tag)) onToggleTag(tag);
                setCustomTag("");
              }
            }}
          />
        </div>
      </div>

      {/* Action Timeline */}
      <div>
        <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Actions</div>
        <div className="space-y-2">
          {groupedActionsWithIndex.map((group) => {
            return (
              <div key={group.street} className="rounded-lg border border-white/[0.06] overflow-hidden">
                <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-cyan-400 bg-slate-800/60 border-b border-white/[0.06]">
                  {group.street}
                </div>
                {group.actions.map(({ action: a, globalIdx }, idx) => {
                  const isHeroAction = heroSeat != null && a.seat === heroSeat;
                  const runningPot = computeRunningPot(hand.actions, globalIdx);
                  const isSelected = selectedActionIdx === globalIdx;
                  const playerName = hand.playerNames?.[a.seat] || `Seat ${a.seat}`;
                  return (
                    <div
                      key={`${group.street}_${idx}`}
                      ref={(el) => {
                        actionRefs.current[globalIdx] = el;
                      }}
                      className={`flex items-center gap-2 px-3 py-1.5 text-[11px] border-b border-white/[0.04] last:border-b-0 ${
                        isSelected
                          ? "bg-amber-500/10 ring-1 ring-amber-500/40"
                          : isHeroAction
                            ? "bg-sky-500/[0.04]"
                            : ""
                      }`}
                    >
                      <span className={`min-w-[80px] truncate ${isHeroAction ? "text-sky-300 font-medium" : "text-slate-400"}`}>
                        {playerName}
                      </span>
                      <span className={`font-semibold uppercase ${
                        a.type === "fold" ? "text-slate-500" :
                        a.type === "raise" || a.type === "all_in" ? "text-amber-400" :
                        a.type === "call" ? "text-emerald-400" :
                        "text-slate-300"
                      }`}>
                        {a.type}
                      </span>
                      {a.amount > 0 && (
                        <span className="text-slate-300 tabular-nums">{a.amount.toLocaleString()}</span>
                      )}
                      <span className="ml-auto text-[10px] text-slate-600 tabular-nums">
                        pot {runningPot.toLocaleString()}
                      </span>
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>

      {/* Export buttons */}
      <div className="flex items-center gap-2 pt-2 border-t border-white/[0.06]">
        <button
          onClick={handleCopyHH}
          className="text-[11px] px-3 py-2 rounded-lg bg-slate-700/50 text-slate-300 border border-white/[0.08] hover:bg-slate-700/70 transition-all"
        >
          {copied === "hh" ? "✓ Copied!" : "📋 Copy HH"}
        </button>
        <button
          onClick={handleCopyJSON}
          className="text-[11px] px-3 py-2 rounded-lg bg-slate-700/50 text-slate-300 border border-white/[0.08] hover:bg-slate-700/70 transition-all"
        >
          {copied === "json" ? "✓ Copied!" : "📋 Copy JSON"}
        </button>
        <button
          onClick={() => onDownload(hand)}
          className="text-[11px] px-3 py-2 rounded-lg bg-slate-700/50 text-slate-300 border border-white/[0.08] hover:bg-slate-700/70 transition-all"
        >
          ⬇ Export JSON
        </button>
      </div>
    </div>
  );
}

// ── GTO Result View ──

function scoreColor(score: number): string {
  if (score >= 80) return "text-emerald-400";
  if (score >= 50) return "text-amber-400";
  return "text-red-400";
}

function scoreBg(score: number): string {
  if (score >= 80) return "bg-emerald-500";
  if (score >= 50) return "bg-amber-500";
  return "bg-red-500";
}

function deviationBadge(score: number): { label: string; cls: string } {
  if (score <= 20) return { label: "Good", cls: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30" };
  if (score <= 50) return { label: "OK", cls: "bg-amber-500/20 text-amber-300 border-amber-500/30" };
  return { label: "Miss", cls: "bg-red-500/20 text-red-300 border-red-500/30" };
}

function GtoResultView({
  result,
  localAnalysis,
}: {
  result: HistoryGTOAnalysis | null;
  localAnalysis?: GTOAnalysis | null;
}) {
  // Prefer server result, fall back to persisted local analysis
  const overallScore = result?.overallScore ?? localAnalysis?.overallScore ?? 0;
  const streetScores = result?.streetScores ?? null;
  const spots = result?.spots ?? [];
  const precision = result?.precision ?? "cached";
  const computedAt = result?.computedAt ?? localAnalysis?.analyzedAt ?? 0;

  return (
    <div className="space-y-3">
      {/* Overall score */}
      <div className="flex items-center gap-4">
        <div className={`text-3xl font-extrabold tabular-nums ${scoreColor(overallScore)}`}>
          {Math.round(overallScore)}
        </div>
        <div className="flex-1">
          <div className="text-[10px] text-slate-500 mb-1">Overall GTO Score</div>
          <div className="h-2 rounded-full bg-slate-700/60 overflow-hidden">
            <div className={`h-full rounded-full ${scoreBg(overallScore)} transition-all`} style={{ width: `${overallScore}%` }} />
          </div>
        </div>
        <div className="text-[9px] text-slate-600 text-right shrink-0">
          {precision !== "cached" && <div>{precision} mode</div>}
          {computedAt > 0 && <div>{new Date(computedAt).toLocaleTimeString()}</div>}
        </div>
      </div>

      {/* Street breakdown */}
      {streetScores && (
        <div className="flex items-center gap-3">
          {(["flop", "turn", "river"] as const).map((s) => {
            const val = streetScores[s];
            if (val === null) return null;
            return (
              <div key={s} className="flex-1 min-w-0">
                <div className="text-[9px] text-slate-500 uppercase mb-1">{s}</div>
                <div className="h-1.5 rounded-full bg-slate-700/60 overflow-hidden">
                  <div className={`h-full rounded-full ${scoreBg(val)} transition-all`} style={{ width: `${val}%` }} />
                </div>
                <div className={`text-[10px] font-bold tabular-nums mt-0.5 ${scoreColor(val)}`}>{Math.round(val)}</div>
              </div>
            );
          })}
        </div>
      )}

      {/* Spots list */}
      {spots.length > 0 && (
        <div className="space-y-1.5 max-h-[280px] overflow-auto">
          {spots.map((spot, idx) => {
            const badge = deviationBadge(spot.deviationScore);
            return (
              <div key={idx} className="rounded-lg border border-white/[0.06] bg-slate-800/30 p-2.5">
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-[10px] font-bold text-cyan-400 uppercase">{spot.street}</span>
                  <span className={`text-[9px] px-1.5 py-0.5 rounded-full border ${badge.cls}`}>{badge.label}</span>
                  <span className="ml-auto text-[10px] text-slate-500 tabular-nums">pot {spot.pot.toLocaleString()}</span>
                </div>
                <div className="flex items-center gap-3 text-[11px]">
                  <div>
                    <span className="text-slate-500">You: </span>
                    <span className="text-white font-semibold uppercase">{spot.heroAction}</span>
                    {spot.heroAmount > 0 && <span className="text-slate-400 ml-1">{spot.heroAmount.toLocaleString()}</span>}
                  </div>
                  <div>
                    <span className="text-slate-500">GTO: </span>
                    <span className="text-purple-300 font-semibold uppercase">{spot.recommended.action}</span>
                    <span className="text-slate-500 ml-1 text-[10px]">
                      (R{Math.round(spot.recommended.mix.raise * 100)}
                      /C{Math.round(spot.recommended.mix.call * 100)}
                      /F{Math.round(spot.recommended.mix.fold * 100)})
                    </span>
                  </div>
                </div>
                {spot.alpha > 0 && (
                  <div className="flex items-center gap-3 mt-1 text-[10px] text-slate-500">
                    <span>Alpha: {Math.round(spot.alpha * 100)}%</span>
                    <span>MDF: {Math.round(spot.mdf * 100)}%</span>
                    <span>Eq: {Math.round(spot.equity * 100)}%</span>
                  </div>
                )}
                <div className="text-[10px] text-slate-400 mt-1">{spot.note}</div>
              </div>
            );
          })}
        </div>
      )}

      {/* Local-only fallback (when server result is not available but local analysis exists) */}
      {spots.length === 0 && localAnalysis && localAnalysis.streets.length > 0 && (
        <div className="space-y-1.5">
          {localAnalysis.streets.map((s, idx) => {
            const badge = deviationBadge(s.evDiff);
            return (
              <div key={idx} className="rounded-lg border border-white/[0.06] bg-slate-800/30 p-2.5">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold text-cyan-400 uppercase">{s.street}</span>
                  <span className={`text-[9px] px-1.5 py-0.5 rounded-full border ${badge.cls}`}>{badge.label}</span>
                </div>
                <div className="text-[11px] mt-1">
                  <span className="text-slate-500">You: </span>
                  <span className="text-white font-semibold uppercase">{s.action}</span>
                  <span className="text-slate-500 mx-1">vs GTO:</span>
                  <span className="text-purple-300 font-semibold uppercase">{s.gtoAction}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
