/**
 * FastBattleSetup — Configuration screen before starting a fast battle session.
 * Select hand count target. Fixed stakes 1/3, 100bb buy-in.
 */

import { useState } from 'react';

interface FastBattleSetupProps {
  onStart: (config: { targetHandCount: number; bigBlind: number }) => void;
  onBack?: () => void;
}

const HAND_COUNT_OPTIONS = [12, 100, 500, 1000];

export function FastBattleSetup({ onStart, onBack }: FastBattleSetupProps) {
  const [handCount, setHandCount] = useState<number | null>(null);

  return (
    <main className="flex-1 flex items-center justify-center p-4">
      <div className="w-full max-w-md space-y-6">
        {/* Header */}
        <div className="text-center relative">
          {onBack && (
            <button
              onClick={onBack}
              className="absolute left-0 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white transition-colors px-2 py-1 rounded hover:bg-slate-700 text-sm"
            >
              Back
            </button>
          )}
          <h1 className="text-2xl font-bold text-white">Fast Battle</h1>
          <p className="text-sm text-slate-400 mt-1">
            Zero-wait high-density training. Fold = next hand instantly.
          </p>
        </div>

        {/* Hand Count */}
        <div className="glass-card p-4 space-y-3">
          <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
            Target Hands
          </label>
          <div className="grid grid-cols-4 gap-2">
            {HAND_COUNT_OPTIONS.map((count) => (
              <button
                key={count}
                onClick={() => setHandCount(count)}
                className={`py-2 px-3 rounded-lg text-sm font-medium transition-colors ${
                  handCount === count
                    ? 'bg-amber-500 text-black'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                {count}
              </button>
            ))}
          </div>
        </div>

        {/* Game Info */}
        <div className="glass-card p-4">
          <div className="flex items-center justify-between text-sm">
            <span className="text-slate-400">Stakes</span>
            <span className="text-slate-200">1/3</span>
          </div>
          <div className="flex items-center justify-between text-sm mt-2">
            <span className="text-slate-400">Buy-in</span>
            <span className="text-slate-200">300 chips (100bb)</span>
          </div>
          <div className="flex items-center justify-between text-sm mt-2">
            <span className="text-slate-400">Opponents</span>
            <span className="text-slate-200">5 AI (V4 GTO)</span>
          </div>
          <div className="flex items-center justify-between text-sm mt-2">
            <span className="text-slate-400">Format</span>
            <span className="text-slate-200">6-max NLH</span>
          </div>
          <div className="flex items-center justify-between text-sm mt-2">
            <span className="text-slate-400">Reset</span>
            <span className="text-slate-200">Fresh 100bb each table</span>
          </div>
        </div>

        {/* Start Button */}
        <button
          disabled={handCount === null}
          onClick={() => handCount !== null && onStart({ targetHandCount: handCount, bigBlind: 3 })}
          className="w-full py-3 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 text-black font-bold text-lg hover:from-amber-400 hover:to-orange-400 transition-all active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Start Battle
        </button>
      </div>
    </main>
  );
}
