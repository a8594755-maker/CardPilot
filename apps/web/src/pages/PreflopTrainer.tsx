// Preflop GTO Trainer — main page.
// Combines scenario selector, hand grid, frequency detail, and drill mode.
// Fetches solution data from static JSON files.

import { useState, useEffect, useCallback } from 'react';
import {
  loadIndex,
  loadSpot,
  type SolutionIndex,
  type SpotSolution,
  type Position,
  type ScenarioType,
} from '../data/preflop-loader';
import { HandGrid } from '../components/preflop/HandGrid';
import { ScenarioSelector } from '../components/preflop/ScenarioSelector';
import { FrequencyDetail } from '../components/preflop/FrequencyDetail';
import { ActionLegend } from '../components/preflop/ActionLegend';
import { ConfigSelector } from '../components/preflop/ConfigSelector';
import { DrillMode } from '../components/preflop/DrillMode';

type Tab = 'charts' | 'drill';

export function PreflopTrainer() {
  const [tab, setTab] = useState<Tab>('charts');
  const [config, setConfig] = useState('cash_6max_100bb');
  const [index, setIndex] = useState<SolutionIndex | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Chart mode state
  const [selectedPosition, setSelectedPosition] = useState<Position>('UTG');
  const [selectedScenario, setSelectedScenario] = useState<ScenarioType | null>(null);
  const [selectedSpot, setSelectedSpot] = useState<string | null>(null);
  const [spotData, setSpotData] = useState<SpotSolution | null>(null);
  const [selectedHand, setSelectedHand] = useState<string | null>(null);

  // Load index
  useEffect(() => {
    setLoading(true);
    setError(null);
    loadIndex(config)
      .then((idx) => {
        setIndex(idx);
        setLoading(false);
        // Auto-select first spot for the current position
        const firstSpot = idx.spots.find((s) => s.heroPosition === selectedPosition);
        if (firstSpot) {
          setSelectedScenario(firstSpot.scenario as ScenarioType);
          setSelectedSpot(firstSpot.spot);
        }
      })
      .catch((err) => {
        setError(`Failed to load: ${err.message}`);
        setLoading(false);
      });
  }, [config]);

  // Load spot data when selection changes
  useEffect(() => {
    if (!selectedSpot || !config) return;
    setSelectedHand(null);
    loadSpot(config, selectedSpot)
      .then(setSpotData)
      .catch(() => setSpotData(null));
  }, [selectedSpot, config]);

  // When position changes, auto-select first matching spot
  const handlePositionChange = useCallback(
    (pos: Position) => {
      setSelectedPosition(pos);
      setSelectedHand(null);
      if (!index) return;
      const spots = index.spots.filter((s) => s.heroPosition === pos);
      if (spots.length > 0) {
        setSelectedScenario(spots[0].scenario as ScenarioType);
        setSelectedSpot(spots[0].spot);
      } else {
        setSelectedScenario(null);
        setSelectedSpot(null);
      }
    },
    [index],
  );

  // When scenario changes, auto-select first matching spot
  const handleScenarioChange = useCallback(
    (scenario: ScenarioType) => {
      setSelectedScenario(scenario);
      setSelectedHand(null);
      if (!index) return;
      const spots = index.spots.filter(
        (s) => s.heroPosition === selectedPosition && s.scenario === scenario,
      );
      if (spots.length > 0) {
        setSelectedSpot(spots[0].spot);
      }
    },
    [index, selectedPosition],
  );

  const handleSpotChange = useCallback((spot: string) => {
    setSelectedSpot(spot);
    setSelectedHand(null);
  }, []);

  if (loading) {
    return (
      <main className="flex-1 p-4 overflow-y-auto">
        <div className="max-w-5xl mx-auto">
          <div className="glass-card p-8 text-center">
            <div className="text-slate-400 text-sm">Loading preflop solutions...</div>
          </div>
        </div>
      </main>
    );
  }

  if (error || !index) {
    return (
      <main className="flex-1 p-4 overflow-y-auto">
        <div className="max-w-5xl mx-auto">
          <div className="glass-card p-8 text-center">
            <h2 className="text-xl font-bold text-white mb-2">Preflop Trainer</h2>
            <p className="text-red-400 text-sm">{error || 'No solution data available.'}</p>
            <p className="text-slate-500 text-xs mt-2">
              Run the preflop solver first:{' '}
              <code className="text-slate-400">npm run preflop:solve</code>
            </p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="flex-1 p-2 sm:p-4 overflow-y-auto">
      <div className="max-w-5xl mx-auto space-y-3">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h2 className="text-xl font-bold text-white">Preflop GTO</h2>
            <p className="text-[10px] text-slate-500">
              {index.spots.length} spots solved — {index.solveDate}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <ConfigSelector selectedConfig={config} onSelectConfig={setConfig} />
            {/* Tab toggle */}
            <div className="flex gap-1 bg-slate-800/60 rounded-lg p-0.5">
              <button
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
                  tab === 'charts'
                    ? 'bg-slate-700 text-white'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
                onClick={() => setTab('charts')}
              >
                Charts
              </button>
              <button
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
                  tab === 'drill'
                    ? 'bg-slate-700 text-white'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
                onClick={() => setTab('drill')}
              >
                Drill
              </button>
            </div>
          </div>
        </div>

        {/* Content */}
        {tab === 'charts' ? (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            {/* Left: Scenario selector */}
            <div className="lg:col-span-1 space-y-3">
              <div className="glass-card p-3">
                <ScenarioSelector
                  index={index}
                  selectedPosition={selectedPosition}
                  selectedScenario={selectedScenario}
                  selectedSpot={selectedSpot}
                  onSelectPosition={handlePositionChange}
                  onSelectScenario={handleScenarioChange}
                  onSelectSpot={handleSpotChange}
                />
              </div>

              {/* Frequency detail */}
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
                        Playing {spotData.summary.rangeSize} / {spotData.summary.totalCombos} hands
                        (
                        {(
                          (spotData.summary.rangeSize / spotData.summary.totalCombos) *
                          100
                        ).toFixed(1)}
                        %)
                      </div>
                    </div>
                    <ActionLegend actions={spotData.actions} />
                  </div>
                  <HandGrid
                    solution={spotData}
                    selectedHand={selectedHand}
                    onSelectHand={setSelectedHand}
                  />
                  <div className="flex justify-between text-[10px] text-slate-600">
                    <span>Suited (↗) | Pairs (↘) | Offsuit (↙)</span>
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
      </div>
    </main>
  );
}
