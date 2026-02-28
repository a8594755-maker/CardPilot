// Action tree navigation hook — find child actions, navigate, undo.
// Ported from packages/cfr-solver/viewer/index.html lines 1074-1145.

import { useMemo, useCallback } from 'react';
import type { Street } from '../lib/cfr-labels';
import { getActionLabels, getActionChars } from '../lib/cfr-labels';
import { findSampleEntry, hasEntryWithPrefix } from '../lib/cfr-computations';

export interface ChildAction {
  label: string;
  historyKey: string;
  street: Street;
  player: number;
}

interface ActionTreeInput {
  indexed: Map<string, number[]>;
  prefixIndex: Map<string, string[]>;
  meta: { boardId: number } | null;
  player: number;
  street: Street;
  historyKey: string;
  bucketCount: number;
  isV2: boolean;
}

interface ActionTreeActions {
  setHistoryKey: (h: string) => void;
  setStreet: (s: Street) => void;
  setPlayer: (p: number) => void;
}

export function useActionTree(input: ActionTreeInput, treeActions: ActionTreeActions) {
  const { indexed, prefixIndex, meta, player, street, historyKey, bucketCount, isV2 } = input;

  const prefix = useMemo(() => {
    const boardId = meta?.boardId ?? 0;
    return `${street}|${boardId}|${player}|${historyKey}|`;
  }, [meta, player, street, historyKey]);

  const sampleEntry = useMemo(() => {
    return findSampleEntry(indexed, prefix, bucketCount, isV2, prefixIndex);
  }, [indexed, prefix, bucketCount, isV2, prefixIndex]);

  const numActions = sampleEntry?.probs.length ?? 0;

  const actionLabels = useMemo(() => {
    if (numActions === 0) return [];
    return getActionLabels(historyKey, numActions, street);
  }, [historyKey, numActions, street]);

  const childActions = useMemo((): ChildAction[] => {
    if (!meta || numActions === 0) return [];
    const boardId = meta.boardId;
    const labels = getActionLabels(historyKey, numActions, street);
    const chars = getActionChars(historyKey, numActions);
    const children: ChildAction[] = [];

    for (let i = 0; i < numActions; i++) {
      const ch = chars[i];
      if (ch === 'f') continue; // skip fold

      let nextHistory: string, nextStreet: Street, nextPlayer: number;
      const curStreetHist = (historyKey || '').split('/').pop() || '';

      if (ch === 'x' && curStreetHist.length === 0) {
        // First check → stays on same street, opponent acts
        nextHistory = historyKey + ch;
        nextStreet = street;
        nextPlayer = 1 - player;
      } else if (ch === 'x') {
        // Second check → street transition
        nextHistory = historyKey + ch + '/';
        nextStreet = street === 'F' ? 'T' : street === 'T' ? 'R' : street;
        nextPlayer = 0;
      } else if (ch === 'c') {
        // Call → street transition
        nextHistory = historyKey + ch + '/';
        nextStreet = street === 'F' ? 'T' : street === 'T' ? 'R' : street;
        nextPlayer = 0;
      } else {
        // Bet/Raise/Allin → opponent acts
        nextHistory = historyKey + ch;
        nextStreet = street;
        nextPlayer = 1 - player;
      }

      const nextPrefix = `${nextStreet}|${boardId}|${nextPlayer}|${nextHistory}|`;
      if (hasEntryWithPrefix(indexed, nextPrefix, bucketCount, isV2, prefixIndex)) {
        children.push({ label: labels[i], historyKey: nextHistory, street: nextStreet, player: nextPlayer });
      }
    }
    return children;
  }, [meta, historyKey, numActions, street, player, indexed, prefixIndex, bucketCount, isV2]);

  const navigateTo = useCallback((action: ChildAction) => {
    treeActions.setHistoryKey(action.historyKey);
    // Only set street/player if they changed (avoid unnecessary re-renders from setStreet clearing history)
    if (action.street !== street) {
      // Direct state updates without going through setStreet (which clears historyKey)
      // We handle this by setting historyKey FIRST, then calling raw setters
    }
    // Use the raw setters from useStrategyViewer
    (treeActions as any).setPlayer?.(action.player);
  }, [treeActions, street]);

  const goBack = useCallback(() => {
    if (!historyKey || !meta) return;
    let h = historyKey;
    if (h.endsWith('/')) h = h.slice(0, -1);
    h = h.slice(0, -1);

    const boardId = meta.boardId;
    for (const s of ['F', 'T', 'R'] as Street[]) {
      for (const p of [0, 1]) {
        const px = `${s}|${boardId}|${p}|${h}|`;
        if (hasEntryWithPrefix(indexed, px, bucketCount, isV2, prefixIndex)) {
          treeActions.setHistoryKey(h);
          if (s !== street) treeActions.setStreet(s);
          treeActions.setPlayer(p);
          return;
        }
      }
    }
    goRoot();
  }, [historyKey, meta, indexed, prefixIndex, bucketCount, isV2, treeActions, street]);

  const goRoot = useCallback(() => {
    treeActions.setHistoryKey('');
    treeActions.setStreet('F');
  }, [treeActions]);

  return {
    prefix,
    sampleEntry,
    numActions,
    actionLabels,
    childActions,
    navigateTo,
    goBack,
    goRoot,
  };
}
