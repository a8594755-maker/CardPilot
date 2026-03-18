// Preflop content — full-width grid layout matching original PreflopTrainer.
// Left column: scenario selector + frequency detail.
// Right column: hand grid + action legend.

import { memo, useState } from 'react';
import type { PreflopViewerState, PreflopViewerActions } from '../../hooks/usePreflopViewer';
import { ConfigSelector } from '../../../../components/preflop/ConfigSelector';
import { ScenarioSelector } from '../../../../components/preflop/ScenarioSelector';
import { FrequencyDetail } from '../../../../components/preflop/FrequencyDetail';
import { HandGrid } from '../../../../components/preflop/HandGrid';
import { ActionLegend } from '../../../../components/preflop/ActionLegend';
import { DrillMode } from '../../../../components/preflop/DrillMode';

type Tab = 'charts' | 'drill';

interface PreflopContentProps {
  state: PreflopViewerState;
  actions: PreflopViewerActions;
}

export const PreflopContent = memo(function PreflopContent({
  state,
  actions,
}: PreflopContentProps) {
  const [tab, setTab] = useState<Tab>('charts');
  const { config, index, spotData, selectedHand } = state;

  if (!index) return null;

  return (
    <>
      {/* Config + tab controls */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <ConfigSelector selectedConfig={config} onSelectConfig={actions.setConfig} />
        <div className="flex gap-1 bg-slate-800/60 rounded-lg p-0.5">
          <button
            className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
              tab === 'charts' ? 'bg-slate-700 text-white' : 'text-slate-500 hover:text-slate-300'
            }`}
            onClick={() => setTab('charts')}
          >
            Charts
          </button>
          <button
            className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
              tab === 'drill' ? 'bg-slate-700 text-white' : 'text-slate-500 hover:text-slate-300'
            }`}
            onClick={() => setTab('drill')}
          >
            Drill
          </button>
        </div>
      </div>

      {/* Content */}
      {tab === 'charts' ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          {/* Left: Scenario selector + Frequency detail */}
          <div className="lg:col-span-1 space-y-3">
            <div className="glass-card p-3">
              <ScenarioSelector
                index={index}
                selectedPosition={state.selectedPosition}
                selectedScenario={state.selectedScenario}
                selectedSpot={state.selectedSpot}
                onSelectPosition={actions.setPosition}
                onSelectScenario={actions.setScenario}
                onSelectSpot={actions.setSpot}
              />
            </div>

            {spotData && (
              <div className="glass-card p-3">
                <FrequencyDetail solution={spotData} selectedHand={selectedHand} />
              </div>
            )}
          </div>

          {/* Right: Hand grid */}
          <div className="lg:col-span-2">
            {spotData ? (
              <div className="glass-card p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-semibold text-white">
                      {spotData.heroPosition} — {spotData.spot.replace(/_/g, ' ')}
                    </div>
                    <div className="text-[10px] text-slate-500">
                      Playing {spotData.summary.rangeSize} / {spotData.summary.totalCombos} hands (
                      {((spotData.summary.rangeSize / spotData.summary.totalCombos) * 100).toFixed(
                        1,
                      )}
                      %)
                    </div>
                  </div>
                  <ActionLegend actions={spotData.actions} />
                </div>
                <HandGrid
                  solution={spotData}
                  selectedHand={selectedHand}
                  onSelectHand={actions.setSelectedHand}
                />
                <div className="flex justify-between text-[10px] text-slate-600">
                  <span>Suited (\u2197) | Pairs (\u2198) | Offsuit (\u2199)</span>
                  <span>{spotData.metadata.solver}</span>
                </div>
              </div>
            ) : (
              <div className="glass-card p-8 text-center">
                <div className="text-slate-500 text-sm">Select a spot to view the chart</div>
              </div>
            )}
          </div>
        </div>
      ) : (
        /* Drill mode */
        <div className="max-w-lg mx-auto">
          <div className="glass-card p-4">
            <DrillMode index={index} config={config} />
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="text-center text-[10px] text-slate-700 pb-4">
        CardPilot Preflop CFR Solver — {index.spots.length} scenarios, 169 hand classes each
      </div>
    </>
  );
});
