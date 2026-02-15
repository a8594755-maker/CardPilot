import { useMemo, useState } from "react";
import type { HandActionRecord, HandRecord } from "../../lib/hand-history.js";
import { formatHandAsPokerStars } from "../../lib/hand-history.js";
import { PokerCard } from "../../components/PokerCard.js";

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

export function HandDetail2({
  hand,
  onCopy,
  onDownload,
  onToggleTag,
}: {
  hand: HandRecord | null;
  onCopy: (text: string) => Promise<void>;
  onDownload: (hand: HandRecord) => void;
  onToggleTag: (tag: string) => void;
}) {
  const [customTag, setCustomTag] = useState("");
  const [copied, setCopied] = useState<"hh" | "json" | null>(null);

  const groupedActions = useMemo(() => (hand ? streetGroups(hand.actions) : []), [hand]);

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

      {/* Hero Cards */}
      <div>
        <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Hero Cards</div>
        <div className="flex gap-1.5">
          {hand.heroCards.map((c) => (
            <PokerCard key={c} card={c} variant="table" />
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
                        <PokerCard key={`f${i}`} card={c} variant="seat" />
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
                        <PokerCard key={`t${i}`} card={c} variant="seat" />
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
                        <PokerCard key={`r${i}`} card={c} variant="seat" />
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
                        <PokerCard key={c} card={c} variant="mini" />
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
          {groupedActions.map((group) => {
            // Find global offset for running pot computation
            let globalIdx = 0;
            for (const g of groupedActions) {
              if (g.street === group.street) break;
              globalIdx += g.actions.length;
            }
            return (
              <div key={group.street} className="rounded-lg border border-white/[0.06] overflow-hidden">
                <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-cyan-400 bg-slate-800/60 border-b border-white/[0.06]">
                  {group.street}
                </div>
                {group.actions.map((a, idx) => {
                  const isHeroAction = heroSeat != null && a.seat === heroSeat;
                  const runningPot = computeRunningPot(hand.actions, globalIdx + idx);
                  const playerName = hand.playerNames?.[a.seat] || `Seat ${a.seat}`;
                  return (
                    <div
                      key={`${group.street}_${idx}`}
                      className={`flex items-center gap-2 px-3 py-1.5 text-[11px] border-b border-white/[0.04] last:border-b-0 ${
                        isHeroAction ? "bg-sky-500/[0.04]" : ""
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
