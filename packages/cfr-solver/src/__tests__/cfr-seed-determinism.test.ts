import assert from 'node:assert/strict';
import { test } from 'node:test';

import { solveCFR } from '../engine/cfr-engine.js';
import { InfoSetStore } from '../engine/info-set-store.js';
import { buildTree } from '../tree/tree-builder.js';
import type { TreeConfig } from '../types.js';
import type { WeightedCombo } from '../integration/preflop-ranges.js';

function solve(seed: number) {
  const config: TreeConfig = {
    startingPot: 5,
    effectiveStack: 5,
    betSizes: { flop: [0.5], turn: [0.5], river: [0.5] },
    raiseCapPerStreet: 0,
  };
  const oopRange: WeightedCombo[] = [
    { combo: [48, 49], weight: 1 },
    { combo: [44, 45], weight: 1 },
    { combo: [40, 41], weight: 1 },
  ];
  const ipRange: WeightedCombo[] = [
    { combo: [48, 50], weight: 1 },
    { combo: [44, 46], weight: 1 },
    { combo: [40, 42], weight: 1 },
  ];
  const store = new InfoSetStore();
  solveCFR({
    root: buildTree(config),
    store,
    boardId: 0,
    flopCards: [0, 5, 10],
    oopRange,
    ipRange,
    iterations: 8,
    bucketCount: 2,
    seed,
  });
  return [...store.entries()]
    .map((entry) => [entry.key, [...entry.averageStrategy]] as const)
    .sort((left, right) => left[0].localeCompare(right[0]));
}

test('chance-sampled CFR is exactly reproducible for a fixed seed', () => {
  assert.deepEqual(solve(20260829), solve(20260829));
  assert.notDeepEqual(solve(20260829), solve(20260830));
});
