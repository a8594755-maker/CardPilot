import { useEffect, useMemo, useRef, useState } from 'react';
import type { HandRecord } from '../../lib/hand-history.js';

const ROW_HEIGHT = 96;
const OVERSCAN = 8;

function formatShortDate(ts: number) {
  return new Date(ts).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function dayBucket(ts: number): string {
  const d = new Date(ts);
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterdayStart = start - 24 * 60 * 60 * 1000;
  const weekStart = start - 6 * 24 * 60 * 60 * 1000;
  if (ts >= start) return 'Today';
  if (ts >= yesterdayStart) return 'Yesterday';
  if (ts >= weekStart) return 'This Week';
  return d.toLocaleDateString();
}

export function HandList({
  hands,
  selectedId,
  loading,
  onSelect,
}: {
  hands: HandRecord[];
  selectedId: string | null;
  loading: boolean;
  onSelect: (id: string) => void;
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

  const visibleRange = useMemo(() => {
    const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
    const end = Math.min(hands.length, Math.ceil((scrollTop + height) / ROW_HEIGHT) + OVERSCAN);
    return { start, end };
  }, [hands.length, height, scrollTop]);

  const visibleHands = useMemo(
    () => hands.slice(visibleRange.start, visibleRange.end),
    [hands, visibleRange],
  );

  if (loading) {
    return (
      <div className="history-list p-3">
        {Array.from({ length: 9 }).map((_, idx) => (
          <div key={idx} className="history-row-skeleton" />
        ))}
      </div>
    );
  }

  if (hands.length === 0) {
    return <div className="history-empty">No hands matched the filters.</div>;
  }

  return (
    <div
      ref={containerRef}
      className="history-list"
      onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
    >
      <div style={{ height: hands.length * ROW_HEIGHT, position: 'relative' }}>
        {visibleHands.map((hand, idx) => {
          const absoluteIndex = visibleRange.start + idx;
          const top = absoluteIndex * ROW_HEIGHT;
          const result = hand.result ?? 0;
          const group = dayBucket(hand.createdAt);
          const prev = absoluteIndex > 0 ? dayBucket(hands[absoluteIndex - 1].createdAt) : '';
          return (
            <button
              key={hand.id}
              onClick={() => onSelect(hand.id)}
              className={`history-list-row ${selectedId === hand.id ? 'history-list-row-active' : ''}`}
              style={{ top, height: ROW_HEIGHT - 8 }}
            >
              {group !== prev ? <span className="history-group-pill">{group}</span> : null}
              <div className="history-list-head">
                <span className="text-[11px] text-slate-500">
                  {formatShortDate(hand.createdAt)}
                </span>
                <span className="text-[11px] text-slate-500">
                  {hand.stakes} · {hand.tableSize} max · {hand.position}
                </span>
              </div>
              <div className="history-list-main">
                <span className="font-mono text-sm text-white">{hand.heroCards.join(' ')}</span>
                <span className="text-[11px] text-slate-500">Pot {hand.potSize}</span>
                <span
                  className={`text-sm font-semibold ml-auto ${result > 0 ? 'text-emerald-400' : result < 0 ? 'text-red-400' : 'text-slate-400'}`}
                >
                  {result > 0 ? '+' : ''}
                  {result}
                </span>
              </div>
              <div className="history-tags-inline">
                {hand.tags.slice(0, 3).map((t) => (
                  <span key={t} className="history-tag-small">
                    {t}
                  </span>
                ))}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
