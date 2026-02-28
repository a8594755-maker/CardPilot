// Frequency detail panel — shows action breakdown for a spot or selected hand.
// Horizontal bar chart per action, range size, summary stats.

import { memo, useMemo } from 'react';
import {
  getActionColor,
  getActionLabel,
  type SpotSolution,
} from '../../data/preflop-loader';

interface FrequencyDetailProps {
  solution: SpotSolution;
  selectedHand: string | null;
}

export const FrequencyDetail = memo(function FrequencyDetail({ solution, selectedHand }: FrequencyDetailProps) {
  const { actions, grid, summary } = solution;

  // If a hand is selected, show its specific frequencies; otherwise show aggregate
  const freqs = useMemo(() => {
    if (selectedHand && grid[selectedHand]) {
      return grid[selectedHand];
    }
    return summary.actionFrequencies;
  }, [selectedHand, grid, summary.actionFrequencies]);

  const title = selectedHand || `${solution.heroPosition} — ${formatScenario(solution)}`;

  return (
    <div className="space-y-3">
      {/* Title */}
      <div>
        <h3 className="text-sm font-bold text-white">{title}</h3>
        {selectedHand && (
          <p className="text-[10px] text-slate-500 mt-0.5">
            {handClassDescription(selectedHand)}
          </p>
        )}
        {!selectedHand && (
          <p className="text-[10px] text-slate-500 mt-0.5">
            Aggregate across all {summary.totalCombos} hand classes
          </p>
        )}
      </div>

      {/* Action frequency bars */}
      <div className="space-y-1.5">
        {actions.map(action => {
          const freq = freqs[action] ?? 0;
          const pct = Math.round(freq * 1000) / 10;
          const color = getActionColor(action);
          const label = getActionLabel(action);
          return (
            <div key={action} className="flex items-center gap-2">
              <span className="w-14 text-[11px] font-medium text-slate-400 text-right truncate">{label}</span>
              <div className="flex-1 h-5 rounded-full bg-white/5 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${Math.max(pct, 0.5)}%`,
                    backgroundColor: color,
                    opacity: freq > 0.01 ? 1 : 0.3,
                  }}
                />
              </div>
              <span className="w-12 text-right text-xs font-semibold text-slate-300 tabular-nums">
                {pct.toFixed(1)}%
              </span>
            </div>
          );
        })}
      </div>

      {/* Summary stats */}
      {!selectedHand && (
        <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-700/50">
          <StatBox label="Range Size" value={`${summary.rangeSize} / ${summary.totalCombos}`} />
          <StatBox label="Pot Size" value={`${solution.potSize} bb`} />
          {solution.villainPosition && (
            <StatBox label="Villain" value={solution.villainPosition} />
          )}
          <StatBox label="Scenario" value={formatScenario(solution)} />
        </div>
      )}

      {/* Per-hand detail */}
      {selectedHand && grid[selectedHand] && (
        <div className="pt-2 border-t border-slate-700/50">
          <div className="text-[10px] text-slate-500 mb-1.5">Strategy Detail</div>
          <div className="space-y-0.5">
            {actions.map(action => {
              const freq = grid[selectedHand][action] ?? 0;
              if (freq < 0.001) return null;
              return (
                <div key={action} className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">{getActionLabel(action)}</span>
                  <span className="font-semibold tabular-nums" style={{ color: getActionColor(action) }}>
                    {(freq * 100).toFixed(1)}%
                  </span>
                </div>
              );
            })}
          </div>
          <div className="mt-2 text-[10px] text-slate-600">
            {isPureSpot(grid[selectedHand]) ? 'Pure spot' : 'Mixed spot'}
          </div>
        </div>
      )}
    </div>
  );
});

function StatBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-slate-800/40 rounded-md px-2 py-1.5">
      <div className="text-[9px] text-slate-500 uppercase tracking-wider">{label}</div>
      <div className="text-xs font-semibold text-white">{value}</div>
    </div>
  );
}

function formatScenario(solution: SpotSolution): string {
  if (solution.scenario === 'RFI') return 'Raise First In';
  if (solution.scenario === 'facing_open') return `vs ${solution.villainPosition} Open`;
  if (solution.scenario === 'facing_3bet') return `vs ${solution.villainPosition} 3-Bet`;
  if (solution.scenario === 'facing_4bet') return `vs ${solution.villainPosition} 4-Bet`;
  return solution.scenario;
}

function handClassDescription(hc: string): string {
  if (hc.length === 2) return `Pocket ${hc[0]}s`;
  const suffix = hc[2] === 's' ? 'suited' : 'offsuit';
  return `${hc[0]}${hc[1]} ${suffix}`;
}

function isPureSpot(freqs: Record<string, number>): boolean {
  return Object.values(freqs).some(f => f >= 0.9);
}
