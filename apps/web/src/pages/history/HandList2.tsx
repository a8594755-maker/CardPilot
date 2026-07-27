import { useEffect, useMemo, useRef, useState } from 'react';
import type { HandRecord } from '../../lib/hand-history.js';
import { PokerCard } from '../../components/PokerCard.js';

const ROW_HEIGHT = 118;
const OVERSCAN = 6;

function formatShortDate(ts: number) {
  return new Date(ts).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function dayBucket(ts: number): string {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  if (ts >= start) return 'Today';
  if (ts >= start - 86400000) return 'Yesterday';
  if (ts >= start - 6 * 86400000) return 'This Week';
  return new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/** Sort options for the hand list */
export type HandSort = 'newest' | 'oldest' | 'biggest_pot' | 'biggest_win' | 'biggest_loss';

const SORT_OPTIONS: [HandSort, string][] = [
  ['newest', 'New'],
  ['oldest', 'Old'],
  ['biggest_pot', 'Pot'],
  ['biggest_win', 'Win'],
  ['biggest_loss', 'Loss'],
];

/** Result indicator bar on left edge */
function ResultStripe({ result }: { result: number }) {
  const color = result > 0 ? 'bg-emerald-400' : result < 0 ? 'bg-red-400' : 'bg-slate-600';
  return (
    <div
      className={`absolute left-0 top-3 bottom-3 w-[3px] rounded-r-full ${color} transition-all`}
    />
  );
}

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
      case 'oldest':
        return copy.sort((a, b) => a.createdAt - b.createdAt);
      case 'biggest_pot':
        return copy.sort((a, b) => b.potSize - a.potSize);
      case 'biggest_win':
        return copy.sort((a, b) => (b.result ?? 0) - (a.result ?? 0));
      case 'biggest_loss':
        return copy.sort((a, b) => (a.result ?? 0) - (b.result ?? 0));
      default:
        return copy.sort((a, b) => b.createdAt - a.createdAt);
    }
  }, [hands, sort]);

  const visibleRange = useMemo(() => {
    const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
    const end = Math.min(
      sortedHands.length,
      Math.ceil((scrollTop + height) / ROW_HEIGHT) + OVERSCAN,
    );
    return { start, end };
  }, [sortedHands.length, height, scrollTop]);

  const visibleHands = useMemo(
    () => sortedHands.slice(visibleRange.start, visibleRange.end),
    [sortedHands, visibleRange],
  );

  if (loading) {
    return (
      <div className="flex-1 p-2 space-y-1.5">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="cp-history-skeleton h-[110px] rounded-xl" />
        ))}
      </div>
    );
  }

  if (hands.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <div className="w-12 h-12 rounded-2xl bg-white/[0.04] border border-white/[0.08] flex items-center justify-center mb-3">
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-slate-500"
          >
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
          </svg>
        </div>
        <p className="text-slate-400 text-sm font-medium">No hands yet</p>
        <p className="text-slate-600 text-xs mt-1">Select a room or play some hands.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Sort bar */}
      <div className="flex items-center gap-1 px-3 py-1.5 border-b border-white/[0.06]">
        <span className="text-[9px] text-slate-600 uppercase tracking-wider mr-1 font-medium">
          Sort
        </span>
        {SORT_OPTIONS.map(([key, label]) => (
          <button
            key={key}
            onClick={() => onSortChange(key)}
            className={`text-[10px] px-2 py-0.5 rounded-md transition-all font-medium ${
              sort === key
                ? 'bg-sky-500/15 text-sky-300 border border-sky-500/30'
                : 'text-slate-500 hover:text-slate-300 border border-transparent hover:bg-white/[0.03]'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      {/* Virtualized list */}
      <div
        ref={containerRef}
        className="flex-1 overflow-auto min-h-0 cp-history-scroll"
        onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
      >
        <div style={{ height: sortedHands.length * ROW_HEIGHT, position: 'relative' }}>
          {visibleHands.map((hand, idx) => {
            const absoluteIndex = visibleRange.start + idx;
            const top = absoluteIndex * ROW_HEIGHT;
            const result = hand.result ?? 0;
            const group = dayBucket(hand.createdAt);
            const prev =
              absoluteIndex > 0 ? dayBucket(sortedHands[absoluteIndex - 1].createdAt) : '';
            const boardPreview = hand.board.slice(0, 3);
            const isSelected = selectedId === hand.id;
            return (
              <button
                key={hand.id}
                onClick={() => onSelect(hand.id)}
                className={`absolute left-2 right-2 rounded-xl border text-left transition-all overflow-hidden ${
                  isSelected
                    ? 'border-sky-500/40 bg-sky-500/[0.08] shadow-lg shadow-sky-500/10'
                    : 'border-white/[0.05] bg-white/[0.02] hover:bg-white/[0.04] hover:border-white/[0.10]'
                }`}
                style={{ top, height: ROW_HEIGHT - 6 }}
              >
                {/* Left edge result stripe */}
                <ResultStripe result={result} />

                <div className="pl-3.5 pr-3 py-2.5">
                  {/* Day group pill */}
                  {sort === 'newest' && group !== prev && (
                    <span className="inline-flex text-[9px] font-semibold uppercase tracking-wider text-blue-300/80 bg-blue-500/10 border border-blue-400/20 rounded-md px-2 py-0.5 mb-1.5">
                      {group}
                    </span>
                  )}

                  {/* Row 1: time + position + result */}
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <div className="flex items-center gap-1.5 text-[10px] min-w-0">
                      <span className="text-slate-500">{formatShortDate(hand.createdAt)}</span>
                      <span className="text-slate-700">/</span>
                      <span className="text-cyan-400/80 font-semibold">{hand.position}</span>
                      <span className="text-slate-700">/</span>
                      <span className="text-slate-500">{hand.stakes}</span>
                    </div>
                    <span
                      className={`text-[13px] font-bold tabular-nums leading-none ${
                        result > 0
                          ? 'text-emerald-400'
                          : result < 0
                            ? 'text-red-400'
                            : 'text-slate-500'
                      }`}
                    >
                      {result > 0 ? '+' : ''}
                      {result.toLocaleString()}
                    </span>
                  </div>

                  {/* Row 2: hero cards + board preview + pot */}
                  <div className="flex items-center gap-2">
                    {/* Hero cards */}
                    <div className="flex gap-[2px]">
                      {hand.heroCards.map((c) => (
                        <PokerCard key={c} card={c} variant="mini" />
                      ))}
                    </div>
                    {/* Board preview (flop) */}
                    {boardPreview.length > 0 && (
                      <div className="flex gap-[2px] opacity-50">
                        {boardPreview.map((c, i) => (
                          <PokerCard key={`${c}-${i}`} card={c} variant="mini" />
                        ))}
                      </div>
                    )}
                    <span className="text-[10px] text-slate-600 ml-auto shrink-0 tabular-nums">
                      Pot {hand.potSize.toLocaleString()}
                    </span>
                  </div>

                  {/* Row 3: tags */}
                  {hand.tags.length > 0 && (
                    <div className="flex items-center gap-1 mt-1.5 overflow-hidden flex-nowrap">
                      {hand.tags.slice(0, 3).map((t) => (
                        <span
                          key={t}
                          className="text-[9px] px-1.5 py-[2px] rounded-md bg-white/[0.04] text-slate-500 border border-white/[0.06] whitespace-nowrap shrink-0"
                        >
                          {t}
                        </span>
                      ))}
                      {hand.tags.length > 3 && (
                        <span className="text-[9px] text-slate-600 shrink-0">
                          +{hand.tags.length - 3}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
