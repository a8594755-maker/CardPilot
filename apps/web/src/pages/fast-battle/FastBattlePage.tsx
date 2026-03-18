/**
 * FastBattlePage — Main page for the "Infinite Fast Battle" training mode.
 *
 * Three phases:
 * 1. Landing — Start button to begin
 * 2. Playing — handled by table view (App.tsx), this page not visible
 * 3. Review — session summary with all hands and cards on End
 */

import { useEffect } from 'react';
import type { FastBattleState } from '../../hooks/useFastBattle';
import { FastBattleReview } from './FastBattleReview';

interface FastBattlePageProps {
  fastBattle: FastBattleState;
  onExit: () => void;
}

const INFINITE_HANDS = 999_999;

export function FastBattlePage({ fastBattle, onExit }: FastBattlePageProps) {
  // Pre-warm pool when user navigates to this page
  useEffect(() => {
    // Reset stale playing/switching state (e.g. after server restart or page refresh)
    if (fastBattle.phase === 'playing' || fastBattle.phase === 'switching') {
      fastBattle.resetToSetup();
    }
    fastBattle.warmup();
  }, []);

  // ── Review Phase (after End button) ──
  if (fastBattle.phase === 'report' && fastBattle.report) {
    return (
      <FastBattleReview
        report={fastBattle.report}
        onPlayAgain={() =>
          fastBattle.startSession({ targetHandCount: INFINITE_HANDS, bigBlind: 3 })
        }
        onExit={onExit}
      />
    );
  }

  // ── Landing Phase ──
  return (
    <main className="flex-1 flex items-center justify-center p-4">
      <div className="w-full max-w-md space-y-6">
        {/* Header */}
        <div className="text-center">
          <h1 className="text-2xl font-bold text-white">Fast Battle</h1>
          <p className="text-sm text-slate-400 mt-1">
            Infinite rapid-fire training. Fold = next hand instantly.
          </p>
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
        </div>

        {/* Start Button */}
        <button
          onClick={() => fastBattle.startSession({ targetHandCount: INFINITE_HANDS, bigBlind: 3 })}
          className="w-full py-3 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 text-black font-bold text-lg hover:from-amber-400 hover:to-orange-400 transition-all active:scale-[0.98]"
        >
          Start Battle
        </button>

        {/* Back */}
        <button
          onClick={onExit}
          className="w-full py-2 text-sm text-slate-400 hover:text-white transition-colors"
        >
          Back to Lobby
        </button>
      </div>
    </main>
  );
}
