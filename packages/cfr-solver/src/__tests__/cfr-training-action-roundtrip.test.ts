import assert from 'node:assert/strict';
import { test } from 'node:test';
import { buildTree } from '../tree/tree-builder.js';
import {
  deterministicSampleN,
  deploymentRaiseCountFromEvents,
  inferActionsFromHistory,
  mapCfrProbsToV55Actions,
  replayHistory,
  replayHistoryTrace,
} from '../scripts/cfr-to-training-data.js';
import {
  DEPLOYMENT_V55_BET_SIZES,
  getHURangeOptions,
  getHUPreflopContext,
  getTreeConfig,
} from '../tree/tree-config.js';
import type { GameNode, TreeConfig } from '../types.js';

test('CFR training converter action inference round-trips the corrected HU tree', () => {
  const config: TreeConfig = {
    startingPot: 5,
    effectiveStack: 20,
    betSizes: { flop: [0.33], turn: [0.5], river: [0.5] },
    raiseCapPerStreet: 1,
  };
  const stack: GameNode[] = [buildTree(config)];
  let checked = 0;
  while (stack.length) {
    const node = stack.pop()!;
    if (node.type !== 'action') continue;
    assert.deepEqual(
      inferActionsFromHistory(node.historyKey, config),
      node.actions,
      node.historyKey,
    );
    assert.deepEqual(
      replayHistoryTrace(node.historyKey, config).state,
      replayHistory(node.historyKey, config),
    );
    checked++;
    for (const child of node.children.values()) stack.push(child);
  }
  assert.ok(checked > 100);
});

test('Path-1 trace freezes the exact deep state and ordered semantic events', () => {
  const config: TreeConfig = {
    startingPot: 5,
    effectiveStack: 197.5,
    betSizes: { flop: [0.33, 0.67, 1.0], turn: [0.5, 0.75, 1.25], river: [0.5, 1.0, 1.5] },
    raiseCapPerStreet: 1,
  };
  const trace = replayHistoryTrace('x13c/2c/2', config);
  assert.equal(trace.state.pot, 124.52);
  assert.deepEqual(trace.state.stacks, [106.61000000000001, 168.86999999999998]);
  assert.deepEqual(trace.state.streetCommitted, [62.26, 0]);
  assert.equal(trace.state.facingBet, 62.26);
  assert.equal(trace.state.currentPlayer, 1);
  assert.equal(trace.state.street, 'RIVER');
  assert.ok(trace.events.length > 5);
  assert.deepEqual(trace.events.at(-1), {
    street: 'RIVER',
    player: 0,
    actionType: 'BET',
    additionalAmount: 62.26,
  });
});

test('CFR strategy mapping preserves all mass in v55 legal slot range', () => {
  const config: TreeConfig = {
    startingPot: 5,
    effectiveStack: 20,
    betSizes: { flop: [0.33, 0.67, 1.0], turn: [0.5, 0.75, 1.25], river: [0.5, 1.0, 1.5] },
    raiseCapPerStreet: 1,
  };
  const actions = inferActionsFromHistory('x', config);
  const probs = actions.map((_, i) => (i + 1) / 15);
  const target = mapCfrProbsToV55Actions('x', actions, probs, config);
  assert.equal(target.length, 9);
  assert.ok(target.every((p) => p >= 0));
  assert.ok(Math.abs(target.reduce((a, b) => a + b, 0) - 1) < 1e-12);
  assert.equal(target[1], probs[0]);
  assert.equal(target[8], probs.at(-1));
});

test('deployment configs expose the exact v55 six-slot grid and public topology', () => {
  assert.deepEqual(DEPLOYMENT_V55_BET_SIZES.flop, [0.33, 0.5, 0.67, 0.75, 1.0, 1.5]);
  assert.deepEqual(
    getHUPreflopContext('deployment_v55_srp_200bb'),
    { topology: 'single_raised', historyShape: 'BC' },
  );
  assert.deepEqual(
    getHUPreflopContext('deployment_v55_3bp_200bb'),
    { topology: 'three_bet', historyShape: 'BBC' },
  );

  const threeBetRanges = getHURangeOptions('deployment_v55_3bp_200bb');
  assert.equal(threeBetRanges.oopSpot, 'BB_vs_BTN_facing_open2.5x');
  assert.equal(threeBetRanges.oopAction, 'raise');
  assert.equal(threeBetRanges.ipSpot, 'BTN_vs_BB_facing_3bet');
  assert.equal(threeBetRanges.ipAction, 'call');

  const config = getTreeConfig('deployment_v55_srp_200bb');
  const actions = inferActionsFromHistory('', config);
  const legalMask = mapCfrProbsToV55Actions('', actions, actions.map(() => 1), config)
    .map((value) => (value > 0 ? 1 : 0));
  assert.deepEqual(legalMask, [0, 1, 1, 1, 1, 1, 1, 1, 1]);

  const cap2Srp = getTreeConfig('deployment_v55_srp_cap2_200bb');
  const cap2ThreeBet = getTreeConfig('deployment_v55_3bp_cap2_200bb');
  assert.equal(cap2Srp.raiseCapPerStreet, 2);
  assert.equal(cap2ThreeBet.raiseCapPerStreet, 2);
  assert.deepEqual(
    getHURangeOptions('deployment_v55_srp_cap2_200bb'),
    getHURangeOptions('deployment_v55_srp_200bb'),
  );
  assert.deepEqual(
    getHURangeOptions('deployment_v55_3bp_cap2_200bb'),
    getHURangeOptions('deployment_v55_3bp_200bb'),
  );
  assert.deepEqual(
    getHUPreflopContext('deployment_v55_srp_cap2_200bb'),
    { topology: 'single_raised', historyShape: 'BC' },
  );
  assert.deepEqual(
    getHUPreflopContext('deployment_v55_3bp_cap2_200bb'),
    { topology: 'three_bet', historyShape: 'BBC' },
  );
});

test('compact deployment raise count includes the opening bet', () => {
  const trace = replayHistoryTrace('x12', getTreeConfig('deployment_v55_srp_cap2_200bb'));
  assert.equal(trace.state.raiseCount, 1); // Solver convention: only the re-raise.
  assert.equal(deploymentRaiseCountFromEvents(trace.events, 'FLOP'), 2);
});

test('representative sampling is seed-stable and worker-order independent', () => {
  const values = Array.from({ length: 100 }, (_, i) => i);
  const first = deterministicSampleN(values, 12, '20260712|flop2|bucket17');
  const repeated = deterministicSampleN(values, 12, '20260712|flop2|bucket17');
  const otherSeed = deterministicSampleN(values, 12, '20260713|flop2|bucket17');
  assert.deepEqual(first, repeated);
  assert.notDeepEqual(first, otherSeed);
  assert.equal(new Set(first).size, 12);
  assert.deepEqual(
    values,
    Array.from({ length: 100 }, (_, i) => i),
  );
});
