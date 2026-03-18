/**
 * FastBattleHUD — Minimal overlay during fast battle play.
 * Shows hand count, cumulative result, and End button.
 */

interface FastBattleHUDProps {
  handsPlayed: number;
  cumulativeResult: number;
  onEnd: () => void;
}

export function FastBattleHUD({ handsPlayed, cumulativeResult, onEnd }: FastBattleHUDProps) {
  const resultColor = cumulativeResult >= 0 ? 'text-emerald-400' : 'text-red-400';
  const resultSign = cumulativeResult >= 0 ? '+' : '';

  return (
    <div className="absolute top-0 left-0 right-0 z-50 pointer-events-none">
      <div className="flex items-center justify-between px-3 py-1.5 bg-black/70 backdrop-blur-sm pointer-events-auto">
        {/* End button */}
        <button
          onClick={onEnd}
          className="text-xs text-slate-400 hover:text-white transition-colors px-2 py-1 rounded hover:bg-slate-700"
        >
          End
        </button>

        {/* Stats */}
        <div className="flex items-center gap-3 text-xs">
          <span className="text-slate-300">
            Hand <span className="text-white font-medium">{handsPlayed}</span>
          </span>

          {/* Result */}
          <span className={`font-mono font-medium ${resultColor}`}>
            {resultSign}
            {cumulativeResult}
          </span>
        </div>

        {/* Spacer to balance layout */}
        <div className="w-10" />
      </div>
    </div>
  );
}
