// Main state management hook for the CFR strategy viewer.
// Handles config/board selection, data loading, and navigation state.

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import type { CfrConfig, FlopEntry, BoardMeta, HandMapData } from '../lib/cfr-api';
import { fetchConfigs, fetchFlops, fetchBoardData, fetchHandMap } from '../lib/cfr-api';
import { detectKeyFormat } from '../lib/cfr-computations';
import { setBetSizesConfig, type Street } from '../lib/cfr-labels';

export interface StrategyViewerState {
  // Config & board
  configs: CfrConfig[];
  selectedConfig: string;
  flops: FlopEntry[];
  selectedBoardId: number | null;

  // Loaded board data
  meta: BoardMeta | null;
  indexed: Map<string, number[]>;
  prefixIndex: Map<string, string[]>;
  handMap: HandMapData | null;
  isV2: boolean;
  bucketCount: number;

  // Navigation
  player: number;
  street: Street;
  historyKey: string;

  // UI
  heatmapMode: 'actions' | 'aggression' | 'strength';
  selectedHand: string | null;
  mode: 'viewer' | 'training';

  // Status
  loading: boolean;
  loadingBoard: boolean;
  error: string | null;
}

export interface StrategyViewerActions {
  selectConfig: (name: string) => void;
  selectBoard: (boardId: number) => void;
  setPlayer: (p: number) => void;
  setStreet: (s: Street) => void;
  setHistoryKey: (h: string) => void;
  setHeatmapMode: (m: 'actions' | 'aggression' | 'strength') => void;
  setSelectedHand: (h: string | null) => void;
  setMode: (m: 'viewer' | 'training') => void;
  clearError: () => void;
}

export function useStrategyViewer(): [StrategyViewerState, StrategyViewerActions] {
  const [configs, setConfigs] = useState<CfrConfig[]>([]);
  const [selectedConfig, setSelectedConfig] = useState('');
  const [flops, setFlops] = useState<FlopEntry[]>([]);
  const [selectedBoardId, setSelectedBoardId] = useState<number | null>(null);

  const [meta, setMeta] = useState<BoardMeta | null>(null);
  const [indexed, setIndexed] = useState<Map<string, number[]>>(new Map());
  const [prefixIndex, setPrefixIndex] = useState<Map<string, string[]>>(new Map());
  const [handMap, setHandMap] = useState<HandMapData | null>(null);
  const [isV2, setIsV2] = useState(false);
  const [bucketCount, setBucketCount] = useState(50);

  const [player, setPlayer] = useState(0);
  const [street, setStreet] = useState<Street>('F');
  const [historyKey, setHistoryKey] = useState('');

  const [heatmapMode, setHeatmapMode] = useState<'actions' | 'aggression' | 'strength'>('actions');
  const [selectedHand, setSelectedHand] = useState<string | null>(null);
  const [mode, setMode] = useState<'viewer' | 'training'>('viewer');

  const [loading, setLoading] = useState(false);
  const [loadingBoard, setLoadingBoard] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load configs on mount, auto-select first available
  useEffect(() => {
    fetchConfigs()
      .then(cfgs => {
        setConfigs(cfgs);
        const first = cfgs.find(c => c.available);
        if (first) setSelectedConfig(first.name);
      })
      .catch(e => setError(`Failed to load configs: ${e.message}`));
  }, []);

  // Load flops when config changes, auto-select first board
  useEffect(() => {
    if (!selectedConfig) { setFlops([]); return; }
    setLoading(true);
    fetchFlops(selectedConfig)
      .then(f => {
        setFlops(f);
        setSelectedBoardId(null);
        setMeta(null);
        setIndexed(new Map());
        setHandMap(null);
        // Auto-select first board for immediate content display
        if (f.length > 0) {
          // Use setTimeout to ensure state is settled before selectBoard runs
          setTimeout(() => selectBoardRef.current(f[0].boardId), 0);
        }
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [selectedConfig]);

  // Load board data + hand map when board selected
  const selectBoard = useCallback((boardId: number) => {
    if (!selectedConfig) return;
    setSelectedBoardId(boardId);
    setLoadingBoard(true);
    setPlayer(0);
    setStreet('F');
    setHistoryKey('');
    setSelectedHand(null);

    Promise.all([
      fetchBoardData(selectedConfig, boardId),
      fetchHandMap(selectedConfig, boardId),
    ])
      .then(([boardData, hm]) => {
        const idx = new Map<string, number[]>();
        const pIdx = new Map<string, string[]>();
        for (const e of boardData.entries) {
          idx.set(e.key, e.probs);
          const lastPipe = e.key.lastIndexOf('|');
          if (lastPipe >= 0) {
            const pfx = e.key.substring(0, lastPipe + 1);
            let arr = pIdx.get(pfx);
            if (!arr) { arr = []; pIdx.set(pfx, arr); }
            arr.push(e.key);
          }
        }
        setMeta(boardData.meta);
        setIndexed(idx);
        setPrefixIndex(pIdx);
        setIsV2(detectKeyFormat(idx));
        setBucketCount(boardData.meta.bucketCount || 50);
        setHandMap(hm);

        // Set bet sizes from meta
        if (boardData.meta.betSizes) {
          setBetSizesConfig(boardData.meta.betSizes);
        } else {
          setBetSizesConfig({ flop: [0.33, 0.75], turn: [0.50, 1.00], river: [0.75, 1.50] });
        }
      })
      .catch(e => setError(e.message))
      .finally(() => setLoadingBoard(false));
  }, [selectedConfig]);

  // Ref to allow effect to call latest selectBoard without dependency issues
  const selectBoardRef = useRef(selectBoard);
  selectBoardRef.current = selectBoard;

  const selectConfig = useCallback((name: string) => {
    setSelectedConfig(name);
  }, []);

  const state: StrategyViewerState = useMemo(() => ({
    configs, selectedConfig, flops, selectedBoardId,
    meta, indexed, prefixIndex, handMap, isV2, bucketCount,
    player, street, historyKey,
    heatmapMode, selectedHand, mode,
    loading, loadingBoard, error,
  }), [
    configs, selectedConfig, flops, selectedBoardId,
    meta, indexed, prefixIndex, handMap, isV2, bucketCount,
    player, street, historyKey,
    heatmapMode, selectedHand, mode,
    loading, loadingBoard, error,
  ]);

  const actions: StrategyViewerActions = useMemo(() => ({
    selectConfig,
    selectBoard,
    setPlayer,
    setStreet: (s: Street) => { setStreet(s); setHistoryKey(''); },
    setHistoryKey,
    setHeatmapMode,
    setSelectedHand,
    setMode,
    clearError: () => setError(null),
  }), [selectConfig, selectBoard]);

  return [state, actions];
}
