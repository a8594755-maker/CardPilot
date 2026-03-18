// Preflop welcome screen — shown when no spot is selected yet.

import { memo } from 'react';

export const PreflopWelcome = memo(function PreflopWelcome() {
  return (
    <div className="flex items-center justify-center py-20">
      <div className="text-center max-w-md space-y-4">
        <div className="text-4xl">♠♥♦♣</div>
        <h2 className="text-xl font-bold text-white">Preflop GTO Strategy</h2>
        <p className="text-sm text-slate-400">
          Select a position and scenario from the sidebar to view GTO preflop ranges.
        </p>
        <div className="bg-[var(--cp-bg-surface)] border border-white/10 rounded-xl p-4 text-left space-y-2">
          <div className="text-xs font-semibold text-slate-300">Quick Guide</div>
          <ul className="text-[11px] text-slate-500 space-y-1.5">
            <li>
              <span className="text-cyan-400 font-medium">1.</span> Choose a config (100bb / 50bb /
              Ante)
            </li>
            <li>
              <span className="text-cyan-400 font-medium">2.</span> Click a position on the table
              (UTG → BB)
            </li>
            <li>
              <span className="text-cyan-400 font-medium">3.</span> Select a scenario (RFI, Facing
              Open, etc.)
            </li>
            <li>
              <span className="text-cyan-400 font-medium">4.</span> The hand matrix shows GTO
              frequencies
            </li>
            <li>
              <span className="text-cyan-400 font-medium">5.</span> Click any hand for detailed
              action breakdown
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
});
