// Scenario selector: position picker + scenario tabs + spot dropdown.
// 6-seat table visual with clickable positions.

import { memo, useMemo } from 'react';
import type { SolutionIndex } from '../../data/preflop-loader';
import {
  POSITIONS,
  SCENARIO_LABELS,
  getAvailableScenarios,
  getSpotsForPosition,
  type Position,
  type ScenarioType,
} from '../../data/preflop-loader';

interface ScenarioSelectorProps {
  index: SolutionIndex;
  selectedPosition: Position;
  selectedScenario: ScenarioType | null;
  selectedSpot: string | null;
  onSelectPosition: (pos: Position) => void;
  onSelectScenario: (scenario: ScenarioType) => void;
  onSelectSpot: (spot: string) => void;
}

// Position layout around a table (approximate oval)
const SEAT_POSITIONS: Record<Position, { x: number; y: number }> = {
  UTG: { x: 15, y: 25 },
  HJ:  { x: 10, y: 60 },
  CO:  { x: 25, y: 85 },
  BTN: { x: 75, y: 85 },
  SB:  { x: 90, y: 60 },
  BB:  { x: 85, y: 25 },
};

export const ScenarioSelector = memo(function ScenarioSelector({
  index,
  selectedPosition,
  selectedScenario,
  selectedSpot,
  onSelectPosition,
  onSelectScenario,
  onSelectSpot,
}: ScenarioSelectorProps) {
  const availableScenarios = useMemo(
    () => getAvailableScenarios(index, selectedPosition),
    [index, selectedPosition],
  );

  const spotsForPosition = useMemo(
    () => getSpotsForPosition(index, selectedPosition),
    [index, selectedPosition],
  );

  const filteredSpots = useMemo(
    () => selectedScenario
      ? spotsForPosition.filter(s => s.scenario === selectedScenario)
      : spotsForPosition,
    [spotsForPosition, selectedScenario],
  );

  return (
    <div className="space-y-3">
      {/* Position selector — table visual */}
      <div className="relative w-full" style={{ paddingTop: '55%' }}>
        {/* Table oval */}
        <div className="absolute inset-4 rounded-[50%] bg-emerald-900/30 border border-emerald-700/40" />
        <div className="absolute inset-0 top-[45%] left-[35%] w-[30%] text-center">
          <span className="text-[10px] text-emerald-600/60 font-medium uppercase tracking-wider">6-Max</span>
        </div>

        {/* Seat buttons */}
        {POSITIONS.map(pos => {
          const { x, y } = SEAT_POSITIONS[pos];
          const isSelected = pos === selectedPosition;
          const hasSpots = index.spots.some(s => s.heroPosition === pos);
          return (
            <button
              key={pos}
              className={`absolute transform -translate-x-1/2 -translate-y-1/2 px-2 py-1 rounded-lg text-xs font-bold transition-all ${
                isSelected
                  ? 'bg-cyan-500 text-white shadow-lg shadow-cyan-500/30 scale-110'
                  : hasSpots
                    ? 'bg-slate-700 text-slate-200 hover:bg-slate-600 hover:scale-105'
                    : 'bg-slate-800/50 text-slate-500 cursor-not-allowed'
              }`}
              style={{ left: `${x}%`, top: `${y}%` }}
              onClick={() => hasSpots && onSelectPosition(pos)}
              disabled={!hasSpots}
            >
              {pos}
            </button>
          );
        })}
      </div>

      {/* Scenario tabs */}
      <div className="flex flex-wrap gap-1">
        {availableScenarios.map(scenario => (
          <button
            key={scenario}
            className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${
              selectedScenario === scenario
                ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40'
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700 border border-transparent'
            }`}
            onClick={() => onSelectScenario(scenario)}
          >
            {SCENARIO_LABELS[scenario]}
          </button>
        ))}
      </div>

      {/* Spot list */}
      {filteredSpots.length > 1 && (
        <div className="flex flex-wrap gap-1">
          {filteredSpots.map(spot => {
            const label = formatSpotLabel(spot.spot, selectedPosition);
            return (
              <button
                key={spot.spot}
                className={`px-2 py-0.5 rounded text-[10px] font-medium transition-all ${
                  selectedSpot === spot.spot
                    ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                    : 'bg-slate-800/60 text-slate-500 hover:bg-slate-700/60 border border-transparent'
                }`}
                onClick={() => onSelectSpot(spot.spot)}
              >
                {label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
});

function formatSpotLabel(spot: string, hero: Position): string {
  // "BB_vs_BTN_open" → "vs BTN"
  // "UTG_RFI" → "RFI"
  if (spot.endsWith('_RFI')) return 'RFI';
  const vsMatch = spot.match(/vs_(\w+)/);
  if (vsMatch) {
    const villain = vsMatch[1];
    const suffix = spot.includes('3bet') ? ' 3bet' : spot.includes('4bet') ? ' 4bet' : spot.includes('open') ? ' open' : '';
    return `vs ${villain}${suffix}`;
  }
  return spot.replace(`${hero}_`, '');
}
