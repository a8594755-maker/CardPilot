import { useEffect, useMemo, useState } from 'react';
import type { HandActionRecord, HandRecord } from '../../lib/hand-history.js';

const STREETS = ['PREFLOP', 'FLOP', 'TURN', 'RIVER'];

function buildTimeline(actions: HandActionRecord[]) {
  return actions.map((a, idx) => ({ ...a, idx }));
}

export function HandReplay({ hand }: { hand: HandRecord | null }) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);

  const timeline = useMemo(() => buildTimeline(hand?.actions ?? []), [hand]);

  useEffect(() => {
    setIndex(0);
    setPlaying(false);
  }, [hand?.id]);

  useEffect(() => {
    if (!playing || timeline.length <= 1) return;
    const t = setInterval(() => {
      setIndex((v) => {
        if (v >= timeline.length - 1) {
          setPlaying(false);
          return v;
        }
        return v + 1;
      });
    }, 900);
    return () => clearInterval(t);
  }, [playing, timeline.length]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (!hand) return;
      if (e.key === 'ArrowRight' || e.key.toLowerCase() === 'k') {
        setIndex((v) => Math.min(timeline.length - 1, v + 1));
      }
      if (e.key === 'ArrowLeft' || e.key.toLowerCase() === 'j') {
        setIndex((v) => Math.max(0, v - 1));
      }
      if (e.key === ' ') {
        e.preventDefault();
        setPlaying((v) => !v);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [hand, timeline.length]);

  if (!hand) return <div className="history-empty">Select a hand to replay.</div>;
  if (timeline.length === 0)
    return <div className="history-empty">No action log found for this hand.</div>;

  const current = timeline[index];
  const shown = timeline.slice(0, index + 1);

  return (
    <div className="history-replay history-sheet-in">
      <div className="history-replay-controls">
        <button
          className="btn-ghost text-xs !py-1.5 !px-2"
          onClick={() => setIndex((v) => Math.max(0, v - 1))}
        >
          Prev
        </button>
        <button className="btn-ghost text-xs !py-1.5 !px-2" onClick={() => setPlaying((v) => !v)}>
          {playing ? 'Pause' : 'Play'}
        </button>
        <button
          className="btn-ghost text-xs !py-1.5 !px-2"
          onClick={() => setIndex((v) => Math.min(timeline.length - 1, v + 1))}
        >
          Next
        </button>
        <span className="text-xs text-slate-500 ml-2">
          {index + 1}/{timeline.length}
        </span>
      </div>
      <input
        type="range"
        min={0}
        max={timeline.length - 1}
        value={index}
        onChange={(e) => setIndex(Number(e.target.value))}
      />
      <div className="text-xs text-slate-400 mt-2">
        Current: {current.street} · Seat {current.seat} · {current.type.toUpperCase()}{' '}
        {current.amount > 0 ? current.amount : ''}
      </div>
      <div className="history-actions-wrap mt-3">
        {STREETS.map((street) => {
          const items = shown.filter((a) => a.street.toUpperCase() === street);
          if (!items.length) return null;
          return (
            <div key={street} className="history-street-group">
              <div className="history-street-title">{street}</div>
              {items.map((a) => (
                <div key={a.idx} className="history-action-row">
                  <span className="text-slate-400">Seat {a.seat}</span>
                  <span className="text-white">{a.type.toUpperCase()}</span>
                  <span className="ml-auto text-slate-300">{a.amount || '-'}</span>
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
