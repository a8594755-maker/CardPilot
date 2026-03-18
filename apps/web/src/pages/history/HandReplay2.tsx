import { useEffect, useMemo, useState } from 'react';
import type { HandActionRecord, HandRecord } from '../../lib/hand-history.js';
import { PokerCard } from '../../components/PokerCard.js';

const STREETS = ['PREFLOP', 'FLOP', 'TURN', 'RIVER'];
const STREET_CARD_COUNTS: Record<string, number> = { PREFLOP: 0, FLOP: 3, TURN: 4, RIVER: 5 };

function buildTimeline(actions: HandActionRecord[]) {
  return actions.map((a, idx) => ({ ...a, idx }));
}

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
        <div className="text-4xl mb-3 opacity-30">▶</div>
        <p className="text-slate-400 text-sm">Select a hand to replay</p>
      </div>
    );
  }
  if (timeline.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <p className="text-slate-400 text-sm">No action log for this hand.</p>
      </div>
    );
  }

  const current = timeline[index];
  const shown = timeline.slice(0, index + 1);

  // Determine how many board cards to show based on current street
  const currentStreet = current.street.toUpperCase();
  const boardCardsToShow = STREET_CARD_COUNTS[currentStreet] ?? 0;

  // Compute running pot
  let runningPot = 0;
  for (let i = 0; i <= index; i++) {
    const a = timeline[i];
    if (a.type !== 'fold' && a.type !== 'check') {
      runningPot += a.amount;
    }
  }

  const heroSeat = hand.heroSeat;

  return (
    <div className="flex-1 overflow-auto p-3 space-y-4">
      {/* Controls */}
      <div className="rounded-xl bg-slate-800/40 border border-white/[0.06] p-3">
        <div className="flex items-center gap-2 mb-3">
          <button
            className="text-[11px] px-2.5 py-1 rounded-md bg-slate-700/50 text-slate-300 border border-white/[0.08] hover:bg-slate-700/70 transition-all disabled:opacity-30"
            disabled={index === 0}
            onClick={() => setIndex((v) => Math.max(0, v - 1))}
          >
            ◀ Prev
          </button>
          <button
            className={`text-[11px] px-3 py-1 rounded-md border transition-all font-semibold ${
              playing
                ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
            }`}
            onClick={() => setPlaying((v) => !v)}
          >
            {playing ? '⏸ Pause' : '▶ Play'}
          </button>
          <button
            className="text-[11px] px-2.5 py-1 rounded-md bg-slate-700/50 text-slate-300 border border-white/[0.08] hover:bg-slate-700/70 transition-all disabled:opacity-30"
            disabled={index >= timeline.length - 1}
            onClick={() => setIndex((v) => Math.min(timeline.length - 1, v + 1))}
          >
            Next ▶
          </button>
          <span className="text-[10px] text-slate-500 ml-2 tabular-nums">
            {index + 1} / {timeline.length}
          </span>
          {/* Speed toggle */}
          <div className="ml-auto flex items-center gap-1">
            <span className="text-[9px] text-slate-500 uppercase">Speed:</span>
            {[
              [1200, '0.5x'],
              [900, '1x'],
              [500, '2x'],
            ].map(([ms, label]) => (
              <button
                key={String(ms)}
                onClick={() => setSpeed(Number(ms))}
                className={`text-[8px] px-1 py-0.5 rounded-sm transition-all ${
                  speed === Number(ms)
                    ? 'bg-sky-500/20 text-sky-300'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {String(label)}
              </button>
            ))}
          </div>
        </div>
        {/* Scrubber */}
        <input
          type="range"
          min={0}
          max={timeline.length - 1}
          value={index}
          onChange={(e) => setIndex(Number(e.target.value))}
          className="w-full h-1.5 rounded-full appearance-none bg-slate-700 cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-sky-400 [&::-webkit-slider-thumb]:shadow-lg"
        />
        <div className="text-[10px] text-slate-500 mt-1">
          ← → or J/K to step · Space to play/pause
        </div>
      </div>

      {/* Current state display */}
      <div className="rounded-xl bg-slate-800/30 border border-white/[0.06] p-3">
        {/* Hero cards */}
        <div className="flex items-center gap-3 mb-3">
          <div>
            <div className="text-[9px] text-slate-500 uppercase mb-1">Hero</div>
            <div className="flex gap-0.5">
              {hand.heroCards.map((c) => (
                <PokerCard key={c} card={c} variant="seat" />
              ))}
            </div>
          </div>
          <div className="ml-4">
            <div className="text-[9px] text-slate-500 uppercase mb-1">Pot</div>
            <div className="text-lg font-bold text-white tabular-nums">
              {runningPot.toLocaleString()}
            </div>
          </div>
          <div className="ml-auto text-right">
            <div className="text-[9px] text-slate-500 uppercase mb-1">Street</div>
            <div className="text-sm font-semibold text-cyan-400">{currentStreet}</div>
          </div>
        </div>

        {/* Board cards with animation */}
        <div className="flex items-center gap-1 min-h-[44px]">
          {hand.board.length > 0 ? (
            hand.board.map((c, i) => (
              <PokerCard
                key={`${c}-${i}`}
                card={c}
                variant="seat"
                className={`transition-all duration-300 ${i >= boardCardsToShow ? 'opacity-30 scale-90' : 'opacity-100 scale-100'}`}
              />
            ))
          ) : (
            <span className="text-[11px] text-slate-500 italic">No board yet</span>
          )}
        </div>
      </div>

      {/* Current action highlight */}
      <div
        className={`rounded-lg p-3 border ${
          heroSeat != null && current.seat === heroSeat
            ? 'border-sky-500/30 bg-sky-500/[0.06]'
            : 'border-white/[0.06] bg-white/[0.02]'
        }`}
      >
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">
            {hand.playerNames?.[current.seat] || `Seat ${current.seat}`}
          </span>
          <span
            className={`text-sm font-bold uppercase ${
              current.type === 'fold'
                ? 'text-slate-500'
                : current.type === 'raise' || current.type === 'all_in'
                  ? 'text-amber-400'
                  : current.type === 'call'
                    ? 'text-emerald-400'
                    : current.type === 'check'
                      ? 'text-slate-300'
                      : 'text-white'
            }`}
          >
            {current.type}
          </span>
          {current.amount > 0 && (
            <span className="text-sm text-slate-200 tabular-nums">
              {current.amount.toLocaleString()}
            </span>
          )}
        </div>
      </div>

      {/* Action log so far */}
      <div>
        <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Action Log</div>
        <div className="space-y-1.5">
          {STREETS.map((street) => {
            const items = shown.filter((a) => a.street.toUpperCase() === street);
            if (!items.length) return null;
            return (
              <div key={street} className="rounded-lg border border-white/[0.06] overflow-hidden">
                <div className="px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-cyan-400 bg-slate-800/60 border-b border-white/[0.06]">
                  {street}
                </div>
                {items.map((a) => {
                  const isHero = heroSeat != null && a.seat === heroSeat;
                  const isCurrent = a.idx === index;
                  return (
                    <div
                      key={a.idx}
                      className={`flex items-center gap-2 px-3 py-1 text-[11px] border-b border-white/[0.04] last:border-b-0 ${
                        isCurrent ? 'bg-sky-500/10' : isHero ? 'bg-sky-500/[0.03]' : ''
                      }`}
                    >
                      <span
                        className={`min-w-[70px] truncate ${isHero ? 'text-sky-300' : 'text-slate-400'}`}
                      >
                        {hand.playerNames?.[a.seat] || `Seat ${a.seat}`}
                      </span>
                      <span
                        className={`font-semibold uppercase ${
                          a.type === 'fold'
                            ? 'text-slate-500'
                            : a.type === 'raise' || a.type === 'all_in'
                              ? 'text-amber-400'
                              : a.type === 'call'
                                ? 'text-emerald-400'
                                : 'text-slate-300'
                        }`}
                      >
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
