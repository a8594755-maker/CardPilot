import { useEffect, useMemo, useState } from 'react';
import type { HandActionRecord, HandRecord } from '../../lib/hand-history.js';
import { PokerCard } from '../../components/PokerCard.js';

const STREETS = ['PREFLOP', 'FLOP', 'TURN', 'RIVER'];
const STREET_CARD_COUNTS: Record<string, number> = { PREFLOP: 0, FLOP: 3, TURN: 4, RIVER: 5 };

function buildTimeline(actions: HandActionRecord[]) {
  return actions.map((a, idx) => ({ ...a, idx }));
}

/** Action type color helper */
function actionColor(type: string): string {
  if (type === 'fold') return 'text-slate-500';
  if (type === 'raise' || type === 'all_in' || type === 'bet') return 'text-amber-400';
  if (type === 'call') return 'text-emerald-400';
  return 'text-slate-300'; // check
}

const SPEEDS: [number, string][] = [
  [1200, '0.5x'],
  [900, '1x'],
  [500, '2x'],
];

export function HandReplay2({ hand }: { hand: HandRecord | null }) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(900);

  const timeline = useMemo(() => buildTimeline(hand?.actions ?? []), [hand]);

  useEffect(() => {
    setIndex(0);
    setPlaying(false);
  }, [hand?.id]);

  // Auto-play timer
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
    }, speed);
    return () => clearInterval(t);
  }, [playing, timeline.length, speed]);

  // Keyboard controls
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

  if (!hand) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <div className="w-14 h-14 rounded-2xl bg-white/[0.03] border border-white/[0.08] flex items-center justify-center mb-4">
          <svg
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-slate-600"
          >
            <polygon points="5 3 19 12 5 21 5 3" />
          </svg>
        </div>
        <p className="text-slate-400 text-sm font-medium">Select a hand to replay</p>
        <p className="text-slate-600 text-xs mt-1">Step through the action street by street</p>
      </div>
    );
  }
  if (timeline.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <p className="text-slate-500 text-sm">No action log for this hand.</p>
      </div>
    );
  }

  const current = timeline[index];
  const shown = timeline.slice(0, index + 1);

  // Board visibility
  const currentStreet = current.street.toUpperCase();
  const boardCardsToShow = STREET_CARD_COUNTS[currentStreet] ?? 0;

  // Running pot
  let runningPot = 0;
  for (let i = 0; i <= index; i++) {
    const a = timeline[i];
    if (a.type !== 'fold' && a.type !== 'check') {
      runningPot += a.amount;
    }
  }

  const heroSeat = hand.heroSeat;
  const progress = timeline.length > 1 ? (index / (timeline.length - 1)) * 100 : 0;

  return (
    <div className="flex-1 overflow-auto p-3 space-y-3 cp-history-scroll">
      {/* ── Board Stage ── */}
      <div className="rounded-xl bg-gradient-to-b from-emerald-950/20 to-slate-900/40 border border-white/[0.06] p-4">
        {/* Hero cards + Pot + Street */}
        <div className="flex items-center gap-4 mb-4">
          <div>
            <div className="text-[9px] text-slate-500 uppercase mb-1 font-medium">Hero</div>
            <div className="flex gap-1">
              {hand.heroCards.map((c) => (
                <PokerCard key={c} card={c} variant="seat" />
              ))}
            </div>
          </div>
          <div className="flex-1 text-center">
            <div className="text-[9px] text-slate-500 uppercase mb-1 font-medium">Pot</div>
            <div className="text-xl font-extrabold text-white tabular-nums">
              {runningPot.toLocaleString()}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[9px] text-slate-500 uppercase mb-1 font-medium">Street</div>
            <div className="text-sm font-bold text-cyan-400">{currentStreet}</div>
          </div>
        </div>

        {/* Board cards */}
        <div className="flex items-center justify-center gap-1.5 min-h-[72px]">
          {hand.board.length > 0 ? (
            hand.board.map((c, i) => (
              <div
                key={`${c}-${i}`}
                className={`transition-all duration-300 ease-out ${
                  i >= boardCardsToShow
                    ? 'opacity-[0.15] scale-[0.88] blur-[1px]'
                    : 'opacity-100 scale-100'
                }`}
              >
                <PokerCard card={c} variant="seat" />
              </div>
            ))
          ) : (
            <span className="text-[11px] text-slate-600 italic">Preflop</span>
          )}
        </div>
      </div>

      {/* ── Controls ── */}
      <div className="rounded-xl bg-white/[0.02] border border-white/[0.06] p-3">
        {/* Transport buttons */}
        <div className="flex items-center gap-2 mb-2.5">
          <button
            className="cp-replay-btn text-[11px] px-3 py-1.5 rounded-lg bg-white/[0.04] text-slate-300 border border-white/[0.07] hover:bg-white/[0.08] transition-all disabled:opacity-30 font-medium"
            disabled={index === 0}
            onClick={() => setIndex((v) => Math.max(0, v - 1))}
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M15 18l-6-6 6-6" />
            </svg>
          </button>
          <button
            className={`cp-replay-btn text-[11px] px-4 py-1.5 rounded-lg border transition-all font-semibold flex items-center gap-1.5 ${
              playing
                ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
            }`}
            onClick={() => setPlaying((v) => !v)}
          >
            {playing ? (
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="4" width="4" height="16" rx="1" />
                <rect x="14" y="4" width="4" height="16" rx="1" />
              </svg>
            ) : (
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
            )}
            {playing ? 'Pause' : 'Play'}
          </button>
          <button
            className="cp-replay-btn text-[11px] px-3 py-1.5 rounded-lg bg-white/[0.04] text-slate-300 border border-white/[0.07] hover:bg-white/[0.08] transition-all disabled:opacity-30 font-medium"
            disabled={index >= timeline.length - 1}
            onClick={() => setIndex((v) => Math.min(timeline.length - 1, v + 1))}
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M9 18l6-6-6-6" />
            </svg>
          </button>

          {/* Counter */}
          <span className="text-[10px] text-slate-500 ml-1 tabular-nums font-medium">
            {index + 1}/{timeline.length}
          </span>

          {/* Speed */}
          <div className="ml-auto flex items-center gap-1 bg-white/[0.03] rounded-lg border border-white/[0.06] px-1 py-0.5">
            {SPEEDS.map(([ms, label]) => (
              <button
                key={String(ms)}
                onClick={() => setSpeed(Number(ms))}
                className={`text-[9px] px-1.5 py-0.5 rounded-md transition-all font-medium ${
                  speed === Number(ms)
                    ? 'bg-sky-500/20 text-sky-300'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Progress bar */}
        <div
          className="relative h-1.5 rounded-full bg-slate-700/50 overflow-hidden cursor-pointer"
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
            setIndex(Math.round(pct * (timeline.length - 1)));
          }}
        >
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-sky-500 to-cyan-400 transition-all duration-150"
            style={{ width: `${progress}%` }}
          />
        </div>

        {/* Hint */}
        <div className="text-[9px] text-slate-600 mt-1.5 text-center">
          ← → or J/K to step / Space to play
        </div>
      </div>

      {/* ── Current Action ── */}
      <div
        className={`rounded-xl p-3 border transition-all ${
          heroSeat != null && current.seat === heroSeat
            ? 'border-sky-500/25 bg-sky-500/[0.05]'
            : 'border-white/[0.06] bg-white/[0.02]'
        }`}
      >
        <div className="flex items-center gap-2.5">
          <span
            className={`text-[12px] font-medium ${heroSeat != null && current.seat === heroSeat ? 'text-sky-300' : 'text-slate-400'}`}
          >
            {hand.playerNames?.[current.seat] || `Seat ${current.seat}`}
          </span>
          <span className={`text-[14px] font-bold uppercase ${actionColor(current.type)}`}>
            {current.type}
          </span>
          {current.amount > 0 && (
            <span className="text-[14px] text-slate-200 tabular-nums font-semibold">
              {current.amount.toLocaleString()}
            </span>
          )}
        </div>
      </div>

      {/* ── Action Log ── */}
      <div>
        <div className="text-[10px] uppercase tracking-[0.1em] text-slate-500 font-semibold mb-2">
          Action Log
        </div>
        <div className="space-y-1.5">
          {STREETS.map((street) => {
            const items = shown.filter((a) => a.street.toUpperCase() === street);
            if (!items.length) return null;
            return (
              <div key={street} className="rounded-xl border border-white/[0.06] overflow-hidden">
                <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.1em] text-cyan-400/80 bg-white/[0.03] border-b border-white/[0.06]">
                  {street}
                </div>
                {items.map((a) => {
                  const isHero = heroSeat != null && a.seat === heroSeat;
                  const isCurrent = a.idx === index;
                  return (
                    <div
                      key={a.idx}
                      className={`flex items-center gap-2 px-3 py-1.5 text-[11px] border-b border-white/[0.04] last:border-b-0 transition-all ${
                        isCurrent ? 'bg-sky-500/[0.08]' : isHero ? 'bg-sky-500/[0.03]' : ''
                      }`}
                    >
                      <span
                        className={`min-w-[70px] truncate ${isHero ? 'text-sky-300 font-medium' : 'text-slate-500'}`}
                      >
                        {hand.playerNames?.[a.seat] || `Seat ${a.seat}`}
                      </span>
                      <span className={`font-semibold uppercase ${actionColor(a.type)}`}>
                        {a.type}
                      </span>
                      {a.amount > 0 && (
                        <span className="text-slate-300 tabular-nums">
                          {a.amount.toLocaleString()}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
