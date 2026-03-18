// Preflop viewer state management hook.
// Extracted from PreflopTrainer.tsx for integration into the unified CfrPage.

import { useState, useEffect, useCallback } from 'react';
import {
  loadIndex,
  loadSpot,
  type SolutionIndex,
  type SpotSolution,
  type Position,
  type ScenarioType,
} from '../../../data/preflop-loader';

export interface PreflopViewerState {
  config: string;
  index: SolutionIndex | null;
  loading: boolean;
  error: string | null;
  selectedPosition: Position;
  selectedScenario: ScenarioType | null;
  selectedSpot: string | null;
  spotData: SpotSolution | null;
  selectedHand: string | null;
}

export interface PreflopViewerActions {
  setConfig: (config: string) => void;
  setPosition: (pos: Position) => void;
  setScenario: (scenario: ScenarioType) => void;
  setSpot: (spot: string) => void;
  setSelectedHand: (h: string | null) => void;
}

export function usePreflopViewer(): [PreflopViewerState, PreflopViewerActions] {
  const [config, setConfigRaw] = useState('cash_6max_100bb');
  const [index, setIndex] = useState<SolutionIndex | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPosition, setSelectedPosition] = useState<Position>('UTG');
  const [selectedScenario, setSelectedScenario] = useState<ScenarioType | null>(null);
  const [selectedSpot, setSelectedSpot] = useState<string | null>(null);
  const [spotData, setSpotData] = useState<SpotSolution | null>(null);
  const [selectedHand, setSelectedHand] = useState<string | null>(null);

  // Load index when config changes
  useEffect(() => {
    setLoading(true);
    setError(null);
    loadIndex(config)
      .then((idx) => {
        setIndex(idx);
        setLoading(false);
        // Auto-select first spot for current position
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

  const setConfig = useCallback((c: string) => {
    setConfigRaw(c);
    setSelectedSpot(null);
    setSpotData(null);
    setSelectedHand(null);
  }, []);

  const setPosition = useCallback(
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

  const setScenario = useCallback(
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

  const setSpot = useCallback((spot: string) => {
    setSelectedSpot(spot);
    setSelectedHand(null);
  }, []);

  const state: PreflopViewerState = {
    config,
    index,
    loading,
    error,
    selectedPosition,
    selectedScenario,
    selectedSpot,
    spotData,
    selectedHand,
  };

  const actions: PreflopViewerActions = {
    setConfig,
    setPosition,
    setScenario,
    setSpot,
    setSelectedHand,
  };

  return [state, actions];
}
