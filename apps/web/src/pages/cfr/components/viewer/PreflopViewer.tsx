// Preflop viewer — main content area for preflop mode.
// Shows spot info, hand grid, action legend, and selected-hand detail.

import { memo } from 'react';
import type { PreflopViewerState, PreflopViewerActions } from '../../hooks/usePreflopViewer';
import { HandGrid } from '../../../../components/preflop/HandGrid';
import { ActionLegend } from '../../../../components/preflop/ActionLegend';
import { getActionColor, getActionLabel } from '../../../../data/preflop-loader';

interface PreflopViewerProps {
  state: PreflopViewerState;
  actions: PreflopViewerActions;
}

export const PreflopViewer = memo(function PreflopViewer({ state, actions }: PreflopViewerProps) {
  const { spotData, selectedHand } = state;
  if (!spotData) return null;

  const { summary, metadata } = spotData;
  const rangePct = ((summary.rangeSize / summary.totalCombos) * 100).toFixed(1);

  return (
    <div className="space-y-4">
      {/* Spot info panel */}
      <div className="bg-[var(--cp-bg-surface)] border border-white/10 rounded-xl p-5">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <div className="text-base font-bold text-white">
              {spotData.heroPosition} — {formatSpotTitle(spotData)}
            </div>
            <div className="text-xs text-slate-400 mt-1">
              Playing {summary.rangeSize} / {summary.totalCombos} hands ({rangePct}%)
              {spotData.villainPosition && ` · vs ${spotData.villainPosition}`}
              {' · '}{spotData.potSize} bb pot
            </div>
          </div>
          <div className="flex items-center gap-4 text-[10px] text-slate-500">
            <span>{(metadata.iterations / 1e6).toFixed(0)}M iterations</span>
            <span>Exploitability: {metadata.exploitability}</span>
          </div>
        </div>

        {/* Aggregate frequency bar */}
        <div className="mt-4">
          <div className="flex h-6 rounded-lg overflow-hidden">
            {spotData.actions.map(action => {
              const freq = summary.actionFrequencies[action] ?? 0;
              if (freq < 0.005) return null;
              return (
                <div
                  key={action}
                  className="flex items-center justify-center text-[10px] font-semibold text-white/90 transition-all"
                  style={{
                    width: `${Math.max(freq * 100, 1)}%`,
                    backgroundColor: getActionColor(action),
                  }}
                  title={`${getActionLabel(action)}: ${(freq * 100).toFixed(1)}%`}
                >
                  {freq > 0.08 && `${(freq * 100).toFixed(0)}%`}
                </div>
              );
            })}
          </div>
        </div>

        {/* Action legend */}
        <div className="mt-3">
          <ActionLegend actions={spotData.actions} />
        </div>
      </div>

      {/* Hand grid */}
      <div className="bg-[var(--cp-bg-surface)] border border-white/10 rounded-xl p-5">
        <HandGrid
          solution={spotData}
          selectedHand={selectedHand}
          onSelectHand={actions.setSelectedHand}
        />
        <div className="flex justify-between text-[10px] text-slate-600 mt-2">
          <span>Suited (upper-right) · Pairs (diagonal) · Offsuit (lower-left)</span>
          <span>{metadata.solver}</span>
        </div>
      </div>

      {/* Selected hand detail (inline below grid) */}
      {selectedHand && spotData.grid[selectedHand] && (
        <div className="bg-[var(--cp-bg-surface)] border border-white/10 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h3 className="text-sm font-bold text-white">{selectedHand}</h3>
              <p className="text-[10px] text-slate-500">{handDescription(selectedHand)}</p>
            </div>
            <button
              onClick={() => actions.setSelectedHand(null)}
              className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              Clear
            </button>
          </div>

          {/* Per-action breakdown */}
          <div className="space-y-1.5">
            {spotData.actions.map(action => {
              const freq = spotData.grid[selectedHand][action] ?? 0;
              if (freq < 0.001) return null;
              const pct = (freq * 100).toFixed(1);
              return (
                <div key={action} className="flex items-center gap-2">
                  <span className="w-14 text-[11px] font-medium text-slate-400 text-right truncate">
                    {getActionLabel(action)}
                  </span>
                  <div className="flex-1 h-5 rounded-full bg-white/5 overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-300"
                      style={{
                        width: `${Math.max(freq * 100, 0.5)}%`,
                        backgroundColor: getActionColor(action),
                      }}
                    />
                  </div>
                  <span className="w-12 text-right text-xs font-semibold text-slate-300 tabular-nums">
                    {pct}%
                  </span>
                </div>
              );
            })}
          </div>

          <div className="mt-2 text-[10px] text-slate-600">
            {isPureSpot(spotData.grid[selectedHand]) ? 'Pure spot' : 'Mixed spot'}
          </div>
        </div>
      )}
    </div>
  );
});

function formatSpotTitle(solution: { scenario: string; villainPosition?: string; spot: string }): string {
  if (solution.scenario === 'RFI') return 'Raise First In';
  if (solution.scenario === 'facing_open') return `Facing ${solution.villainPosition} Open`;
  if (solution.scenario === 'facing_3bet') return `Facing ${solution.villainPosition} 3-Bet`;
  if (solution.scenario === 'facing_4bet') return `Facing ${solution.villainPosition} 4-Bet`;
  if (solution.scenario === 'squeeze') return `Squeeze vs ${solution.villainPosition}`;
  return solution.spot.replace(/_/g, ' ');
}

function handDescription(hc: string): string {
  if (hc.length === 2) return `Pocket ${hc[0]}s`;
  const suffix = hc[2] === 's' ? 'suited' : 'offsuit';
  return `${hc[0]}${hc[1]} ${suffix}`;
}

function isPureSpot(freqs: Record<string, number>): boolean {
  return Object.values(freqs).some(f => f >= 0.9);
}
