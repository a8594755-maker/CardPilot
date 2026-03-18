import { usePlayMode } from '../../stores/play-mode';

const SEVERITY_CONFIG = {
  optimal: {
    label: 'Excellent',
    color: 'text-green-400',
    bg: 'bg-green-600/20',
    border: 'border-green-600/30',
  },
  minor: {
    label: 'Inaccuracy',
    color: 'text-yellow-400',
    bg: 'bg-yellow-600/20',
    border: 'border-yellow-600/30',
  },
  moderate: {
    label: 'Mistake',
    color: 'text-orange-400',
    bg: 'bg-orange-600/20',
    border: 'border-orange-600/30',
  },
  major: {
    label: 'Major Error',
    color: 'text-red-400',
    bg: 'bg-red-600/20',
    border: 'border-red-600/30',
  },
  blunder: {
    label: 'Blunder',
    color: 'text-red-500',
    bg: 'bg-red-700/20',
    border: 'border-red-700/30',
  },
} as const;

const ACTION_COLORS: Record<string, string> = {
  fold: 'bg-red-500',
  check: 'bg-gray-400',
  call: 'bg-green-500',
  bet_25: 'bg-blue-400',
  bet_33: 'bg-blue-500',
  bet_50: 'bg-blue-600',
  bet_75: 'bg-yellow-500',
  bet_100: 'bg-yellow-600',
  bet_150: 'bg-orange-500',
  raise_25: 'bg-blue-400',
  raise_33: 'bg-blue-500',
  raise_50: 'bg-blue-600',
  raise_75: 'bg-yellow-500',
  raise_100: 'bg-yellow-600',
  raise_150: 'bg-orange-500',
  allin: 'bg-purple-500',
};

function formatActionName(name: string): string {
  if (name.startsWith('bet_')) return `Bet ${name.split('_')[1]}%`;
  if (name.startsWith('raise_')) return `Raise ${name.split('_')[1]}%`;
  return name.charAt(0).toUpperCase() + name.slice(1);
}

export function StrategyBar() {
  const { currentFeedback, showFeedback, setShowFeedback, coachingEnabled } = usePlayMode();

  if (!coachingEnabled || !currentFeedback) return null;

  const severity = SEVERITY_CONFIG[currentFeedback.severity];

  // Sort actions by GTO frequency (descending)
  const sortedActions = Object.entries(currentFeedback.gtoPolicy).sort(([, a], [, b]) => b - a);

  const maxFreq = sortedActions.length > 0 ? sortedActions[0][1] : 1;

  return (
    <div className={`border ${severity.border} rounded-lg overflow-hidden`}>
      {/* Header with severity badge */}
      <div className={`${severity.bg} px-3 py-2 flex items-center justify-between`}>
        <div className="flex items-center gap-2">
          <span className={`text-sm font-semibold ${severity.color}`}>{severity.label}</span>
          {currentFeedback.severity !== 'optimal' && (
            <span className="text-xs text-muted-foreground">
              {currentFeedback.deltaEV >= 0 ? '+' : ''}
              {currentFeedback.deltaEV.toFixed(2)} BB
            </span>
          )}
        </div>
        <button
          onClick={() => setShowFeedback(!showFeedback)}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          {showFeedback ? 'Hide' : 'Show'}
        </button>
      </div>

      {showFeedback && (
        <div className="p-3 space-y-2 bg-card">
          {/* GTO frequency bars */}
          {sortedActions.map(([action, freq]) => {
            const isUserAction =
              currentFeedback.action?.toLowerCase().includes(action.replace('_', ' ')) ||
              action === currentFeedback.action;
            const isBest = action === currentFeedback.bestAction;
            const pct = (freq * 100).toFixed(1);
            const barWidth = maxFreq > 0 ? (freq / maxFreq) * 100 : 0;
            const color = ACTION_COLORS[action] || 'bg-gray-500';
            const ev = currentFeedback.qValues[action];

            return (
              <div key={action} className="flex items-center gap-2 text-xs">
                <div className="w-20 text-right text-muted-foreground truncate">
                  {formatActionName(action)}
                </div>
                <div className="flex-1 h-4 bg-secondary rounded-sm overflow-hidden relative">
                  <div
                    className={`h-full ${color} opacity-70 rounded-sm`}
                    style={{ width: `${barWidth}%` }}
                  />
                  <span className="absolute inset-0 flex items-center px-1 text-[10px] font-mono text-white/80">
                    {pct}%
                  </span>
                </div>
                <div className="w-14 text-right font-mono text-muted-foreground">
                  {ev != null ? `${ev >= 0 ? '+' : ''}${ev.toFixed(1)}` : ''}
                </div>
                <div className="w-6 text-center">
                  {isBest && <span className="text-green-400 text-[10px]">GTO</span>}
                  {isUserAction && !isBest && (
                    <span className="text-yellow-400 text-[10px]">YOU</span>
                  )}
                </div>
              </div>
            );
          })}

          {/* Summary line */}
          <div className="pt-1 border-t border-border flex justify-between text-[10px] text-muted-foreground font-mono">
            <span>
              Best: {formatActionName(currentFeedback.bestAction)} (
              {currentFeedback.bestActionEV.toFixed(1)} BB)
            </span>
            <span>Your EV: {currentFeedback.userActionEV.toFixed(1)} BB</span>
          </div>
        </div>
      )}
    </div>
  );
}
