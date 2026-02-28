// Hand matrix data computation hook.
// Computes cell data (color, probs) for the 13x13 hand grid.

import { useMemo } from 'react';
import type { HandMapData } from '../lib/cfr-api';
import { ALL_HAND_CLASSES } from '../lib/cfr-constants';
import { getAggregatedProbs } from '../lib/cfr-computations';
import { blendActionColors, computeAggression } from '../lib/cfr-colors';

export interface MatrixCellData {
  handClass: string;
  bucket: number | undefined;
  probs: number[] | null;
  bgColor: string;
  hasData: boolean;
}

interface HandMatrixInput {
  indexed: Map<string, number[]>;
  prefixIndex: Map<string, string[]>;
  handMap: HandMapData | null;
  player: number;
  prefix: string;
  isV2: boolean;
  bucketCount: number;
  heatmapMode: 'actions' | 'aggression' | 'strength';
  actionLabels: string[];
}

export function useHandMatrix(input: HandMatrixInput): MatrixCellData[] {
  const { indexed, prefixIndex, handMap, player, prefix, isV2, bucketCount, heatmapMode, actionLabels } = input;

  return useMemo(() => {
    if (!handMap || indexed.size === 0) {
      return ALL_HAND_CLASSES.map(hc => ({
        handClass: hc,
        bucket: undefined,
        probs: null,
        bgColor: '#1a2332',
        hasData: false,
      }));
    }

    const playerMap = player === 0 ? handMap.oop : handMap.ip;

    return ALL_HAND_CLASSES.map(hc => {
      const bucket = playerMap[hc];

      if (bucket === undefined || actionLabels.length === 0) {
        return { handClass: hc, bucket: undefined, probs: null, bgColor: '#1a2332', hasData: false };
      }

      const probs = getAggregatedProbs(indexed, prefix, bucket, isV2, prefixIndex);
      if (!probs) {
        return { handClass: hc, bucket, probs: null, bgColor: '#1a2332', hasData: false };
      }

      let bgColor: string;
      if (heatmapMode === 'aggression') {
        const aggFreq = computeAggression(probs, actionLabels);
        const r = Math.round(239 * aggFreq + 30 * (1 - aggFreq));
        const g = Math.round(68 * aggFreq + 100 * (1 - aggFreq));
        const b = Math.round(68 * aggFreq + 140 * (1 - aggFreq));
        const alpha = 0.3 + 0.6 * aggFreq;
        bgColor = `rgba(${r},${g},${b},${alpha})`;
      } else if (heatmapMode === 'strength') {
        const norm = bucketCount > 1 ? bucket / (bucketCount - 1) : 0.5;
        const r = Math.round(30 + 209 * norm);
        const g = Math.round(80 + 60 * (1 - Math.abs(norm - 0.5) * 2));
        const b = Math.round(200 * (1 - norm) + 40);
        bgColor = `rgba(${r},${g},${b},0.7)`;
      } else {
        bgColor = blendActionColors(probs, actionLabels);
      }

      return { handClass: hc, bucket, probs, bgColor, hasData: true };
    });
  }, [indexed, prefixIndex, handMap, player, prefix, isV2, bucketCount, heatmapMode, actionLabels]);
}
