import { useEffect, useMemo, useRef, useState } from "react";
import type { HandRecord } from "../../lib/hand-history.js";
import { getCardImagePath } from "../../lib/card-images.js";

const ROW_HEIGHT = 108;
const OVERSCAN = 6;

function formatShortDate(ts: number) {
  return new Date(ts).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function dayBucket(ts: number): string {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  if (ts >= start) return "Today";
  if (ts >= start - 86400000) return "Yesterday";
  if (ts >= start - 6 * 86400000) return "This Week";
  return new Date(ts).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Mini card image component */
function MiniCard({ card, size = 28 }: { card: string; size?: number }) {
  return (
    <img
      src={getCardImagePath(card)}
      alt={card}
      className="rounded-sm shadow-sm"
      style={{ height: size, width: "auto" }}
      loading="lazy"
    />
  );
}

/** Sort options for the hand list */
export type HandSort = "newest" | "oldest" | "biggest_pot" | "biggest_win" | "biggest_loss";

export function HandList2({
  hands,
  selectedId,
  loading,
  onSelect,
  sort,
  onSortChange,
}: {
  hands: HandRecord[];
  selectedId: string | null;
  loading: boolean;
  onSelect: (id: string) => void;
  sort: HandSort;
  onSortChange: (s: HandSort) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [height, setHeight] = useState(480);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setHeight(el.clientHeight));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Apply sort
  const sortedHands = useMemo(() => {
    const copy = [...hands];
    switch (sort) {
      case "oldest": return copy.sort((a, b) => a.createdAt - b.createdAt);
      case "biggest_pot": return copy.sort((a, b) => b.potSize - a.potSize);
      case "biggest_win": return copy.sort((a, b) => (b.result ?? 0) - (a.result ?? 0));
      case "biggest_loss": return copy.sort((a, b) => (a.result ?? 0) - (b.result ?? 0));
      default: return copy.sort((a, b) => b.createdAt - a.createdAt);
    }
  }, [hands, sort]);

  const visibleRange = useMemo(() => {
    const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
    const end = Math.min(sortedHands.length, Math.ceil((scrollTop + height) / ROW_HEIGHT) + OVERSCAN);
    return { start, end };
  }, [sortedHands.length, height, scrollTop]);

  const visibleHands = useMemo(() => sortedHands.slice(visibleRange.start, visibleRange.end), [sortedHands, visibleRange]);

  if (loading) {
    return (
      <div className="flex-1 p-2 space-y-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="history-row-skeleton h-[100px]" />
        ))}
      </div>
    );
  }

  if (hands.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
        <div className="text-3xl mb-3 opacity-40">📋</div>
        <p className="text-slate-400 text-sm font-medium">No hands in this room</p>
        <p className="text-slate-500 text-xs mt-1">Select a different room or play some hands.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Sort bar */}
      <div className="flex items-center gap-1.5 px-3 py-2 border-b border-white/[0.06]">
        <span className="text-[10px] text-slate-500 uppercase tracking-wider mr-1">Sort:</span>
        {([
          ["newest", "Newest"],
          ["oldest", "Oldest"],
          ["biggest_pot", "Pot ↓"],
          ["biggest_win", "Win ↓"],
          ["biggest_loss", "Loss ↓"],
        ] as [HandSort, string][]).map(([key, label]) => (
          <button
            key={key}
            onClick={() => onSortChange(key)}
            className={`text-[10px] px-2 py-1 rounded-md transition-all ${
              sort === key
                ? "bg-sky-500/20 text-sky-300 border border-sky-500/40"
                : "text-slate-500 hover:text-slate-300 border border-transparent"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      {/* Virtualized list */}
      <div
        ref={containerRef}
        className="flex-1 overflow-auto min-h-0"
        onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
      >
        <div style={{ height: sortedHands.length * ROW_HEIGHT, position: "relative" }}>
          {visibleHands.map((hand, idx) => {
            const absoluteIndex = visibleRange.start + idx;
            const top = absoluteIndex * ROW_HEIGHT;
            const result = hand.result ?? 0;
            const group = dayBucket(hand.createdAt);
            const prev = absoluteIndex > 0 ? dayBucket(sortedHands[absoluteIndex - 1].createdAt) : "";
            const boardPreview = hand.board.slice(0, 3);
            return (
              <button
                key={hand.id}
                onClick={() => onSelect(hand.id)}
                className={`absolute left-2 right-2 rounded-xl border p-2.5 text-left transition-all ${
                  selectedId === hand.id
                    ? "border-sky-500/60 bg-sky-500/10 shadow-lg shadow-sky-900/20"
                    : "border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.05] hover:border-white/[0.12]"
                }`}
                style={{ top, height: ROW_HEIGHT - 8 }}
              >
                {/* Day group pill */}
                {sort === "newest" && group !== prev && (
                  <span className="history-group-pill mb-1">{group}</span>
                )}
                {/* Row 1: time + position + result */}
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-[11px]">
                    <span className="text-slate-500">{formatShortDate(hand.createdAt)}</span>
                    <span className="text-slate-600">·</span>
                    <span className="text-cyan-400/80 font-medium">{hand.position}</span>
                    <span className="text-slate-600">·</span>
                    <span className="text-slate-500">{hand.stakes}</span>
                  </div>
                  <span className={`text-sm font-bold tabular-nums ${
                    result > 0 ? "text-emerald-400" : result < 0 ? "text-red-400" : "text-slate-400"
                  }`}>
                    {result > 0 ? "+" : ""}{result.toLocaleString()}
                  </span>
                </div>
                {/* Row 2: hero cards + board preview + pot */}
                <div className="flex items-center gap-2 mt-1.5">
                  {/* Hero cards */}
                  <div className="flex gap-0.5 shrink-0">
                    {hand.heroCards.map((c) => (
                      <MiniCard key={c} card={c} size={30} />
                    ))}
                  </div>
                  {/* Board preview (first 3 cards) */}
                  {boardPreview.length > 0 && (
                    <div className="flex gap-0.5 shrink-0 ml-1 opacity-60">
                      {boardPreview.map((c, i) => (
                        <MiniCard key={`${c}-${i}`} card={c} size={22} />
                      ))}
                    </div>
                  )}
                  <span className="text-[10px] text-slate-500 ml-auto shrink-0">Pot {hand.potSize.toLocaleString()}</span>
                </div>
                {/* Row 3: tags */}
                {hand.tags.length > 0 && (
                  <div className="flex items-center gap-1 mt-1.5">
                    {hand.tags.slice(0, 4).map((t) => (
                      <span key={t} className="text-[9px] px-1.5 py-0.5 rounded-full bg-slate-700/40 text-slate-400 border border-white/[0.06]">
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
