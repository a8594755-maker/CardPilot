// Preflop sidebar — config selector, position/scenario picker, frequency detail.
// Mirrors FlopSidebar layout (380px, sticky, dark surface).

import { memo } from 'react';
import type { PreflopViewerState, PreflopViewerActions } from '../../hooks/usePreflopViewer';
import { ConfigSelector } from '../../../../components/preflop/ConfigSelector';
import { ScenarioSelector } from '../../../../components/preflop/ScenarioSelector';
import { FrequencyDetail } from '../../../../components/preflop/FrequencyDetail';

interface PreflopSidebarProps {
  state: PreflopViewerState;
  actions: PreflopViewerActions;
}

export const PreflopSidebar = memo(function PreflopSidebar({ state, actions }: PreflopSidebarProps) {
  const { config, index, loading, error, selectedPosition, selectedScenario, selectedSpot, spotData, selectedHand } = state;

  return (
    <aside className="w-[380px] min-w-[380px] bg-[var(--cp-bg-surface)] border-r border-white/10 flex flex-col h-screen sticky top-0 max-lg:w-full max-lg:min-w-0 max-lg:h-auto max-lg:max-h-[50vh] max-lg:relative">
      {/* Header */}
      <div className="px-5 py-4 border-b border-white/10">
        <h1 className="text-lg font-bold text-white mb-2">GTO Strategy</h1>
        <ConfigSelector selectedConfig={config} onSelectConfig={actions.setConfig} />
      </div>

      {/* Loading / Error */}
      {loading && (
        <div className="px-5 py-8 text-center text-slate-400 text-sm">Loading solutions...</div>
      )}
      {error && (
        <div className="px-5 py-4 text-center text-red-400 text-sm">{error}</div>
      )}

      {/* Position + Scenario selector */}
      {index && !loading && (
        <div className="px-5 py-3 border-b border-white/10">
          <ScenarioSelector
            index={index}
            selectedPosition={selectedPosition}
            selectedScenario={selectedScenario}
            selectedSpot={selectedSpot}
            onSelectPosition={actions.setPosition}
            onSelectScenario={actions.setScenario}
            onSelectSpot={actions.setSpot}
          />
        </div>
      )}

      {/* Frequency detail */}
      {spotData && (
        <div className="flex-1 overflow-y-auto px-5 py-3">
          <FrequencyDetail solution={spotData} selectedHand={selectedHand} />
        </div>
      )}

      {/* Footer info */}
      {index && !loading && (
        <div className="px-5 py-2 border-t border-white/10 text-[10px] text-slate-600">
          {index.spots.length} spots — {index.solveDate}
        </div>
      )}
    </aside>
  );
});
