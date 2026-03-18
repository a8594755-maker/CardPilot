import { describe, test } from 'node:test';
import * as assert from 'node:assert/strict';

import {
  defaultPositionsForPlayers,
  type PreflopSolveConfig,
  type PreflopActionNode,
} from '../preflop/preflop-types.js';
import { buildPreflopTree } from '../preflop/preflop-tree.js';

function mustActionNode(node: unknown, label: string): PreflopActionNode {
  assert.ok(node && typeof node === 'object', `${label}: node missing`);
  const typed = node as PreflopActionNode | { type: string };
  assert.equal(typed.type, 'action', `${label}: expected action node`);
  return typed as PreflopActionNode;
}

function baseConfig(overrides: Partial<PreflopSolveConfig> = {}): PreflopSolveConfig {
  return {
    name: 'test_cfg',
    players: 6,
    positionLabels: ['UTG', 'HJ', 'CO', 'BTN', 'SB', 'BB'],
    stackSize: 100,
    sbSize: 0.5,
    bbSize: 1,
    ante: 0,
    openSize: 2.5,
    threeBetIPMultiplier: 3.0,
    threeBetOOPMultiplier: 3.5,
    fourBetMultiplier: 2.25,
    reRaiseMultiplier: 2.0,
    maxRaiseLevel: 4,
    allowSmallBlindComplete: true,
    autoFoldUninvolvedAfterThreeBet: false,
    iterations: 1000,
    realizationIP: 1.0,
    realizationOOP: 0.7,
    ...overrides,
  };
}

describe('Generic preflop tree', () => {
  test('default positions support 9-max', () => {
    const labels = defaultPositionsForPlayers(9);
    assert.equal(labels.length, 9);
    assert.equal(labels[labels.length - 3], 'BTN');
    assert.equal(labels[labels.length - 2], 'SB');
    assert.equal(labels[labels.length - 1], 'BB');
  });

  test('auto-fold simplification can be disabled', () => {
    const cfgNoAutoFold = baseConfig({
      autoFoldUninvolvedAfterThreeBet: false,
      maxRaiseLevel: 2,
    });
    const root = buildPreflopTree(cfgNoAutoFold);

    const afterOpen = mustActionNode(root.children.get('open_2.5'), 'after open');
    const afterCall = mustActionNode(afterOpen.children.get('call'), 'after call');
    const squeeze = afterCall.actions.find(
      (a) => a.startsWith('squeeze_') || a.startsWith('3bet_'),
    );
    assert.ok(squeeze, 'expected squeeze/3bet action');
    const afterSqueeze = mustActionNode(afterCall.children.get(squeeze!), 'after squeeze');

    // Uninvolved players should still be active when auto-fold is disabled.
    assert.ok(afterSqueeze.activePlayers.has(3), 'BTN should remain active');
    assert.ok(afterSqueeze.activePlayers.has(4), 'SB should remain active');
    assert.ok(afterSqueeze.activePlayers.has(5), 'BB should remain active');
  });

  test('auto-fold simplification remains available for legacy mode', () => {
    const cfgAutoFold = baseConfig({
      autoFoldUninvolvedAfterThreeBet: true,
      maxRaiseLevel: 2,
    });
    const root = buildPreflopTree(cfgAutoFold);

    const afterOpen = mustActionNode(root.children.get('open_2.5'), 'after open');
    const afterCall = mustActionNode(afterOpen.children.get('call'), 'after call');
    const squeeze = afterCall.actions.find(
      (a) => a.startsWith('squeeze_') || a.startsWith('3bet_'),
    );
    assert.ok(squeeze, 'expected squeeze/3bet action');
    const afterSqueeze = mustActionNode(afterCall.children.get(squeeze!), 'after squeeze');

    assert.ok(!afterSqueeze.activePlayers.has(3), 'BTN should be auto-folded');
    assert.ok(!afterSqueeze.activePlayers.has(4), 'SB should be auto-folded');
    assert.ok(!afterSqueeze.activePlayers.has(5), 'BB should be auto-folded');
  });

  test('maxRaiseLevel supports 5bet/6bet action generation', () => {
    const cfgHeadsUp = baseConfig({
      players: 2,
      positionLabels: ['SB', 'BB'],
      maxRaiseLevel: 6,
      autoFoldUninvolvedAfterThreeBet: false,
    });
    const root = buildPreflopTree(cfgHeadsUp);
    assert.equal(root.position, 'SB');

    const afterOpen = mustActionNode(root.children.get('open_2.5'), 'after open');
    const threeBetAction = afterOpen.actions.find(
      (a) => a.startsWith('3bet_') || a.startsWith('squeeze_'),
    );
    assert.ok(threeBetAction, 'expected 3bet action');
    const afterThreeBet = mustActionNode(afterOpen.children.get(threeBetAction!), 'after 3bet');

    const fourBetAction = afterThreeBet.actions.find((a) => a.startsWith('4bet_'));
    assert.ok(fourBetAction, 'expected 4bet action');
    const afterFourBet = mustActionNode(afterThreeBet.children.get(fourBetAction!), 'after 4bet');

    const fiveBetAction = afterFourBet.actions.find((a) => a.startsWith('5bet_'));
    assert.ok(fiveBetAction, 'expected 5bet action');
    const afterFiveBet = mustActionNode(afterFourBet.children.get(fiveBetAction!), 'after 5bet');

    const sixBetAction = afterFiveBet.actions.find((a) => a.startsWith('6bet_'));
    assert.ok(sixBetAction, 'expected 6bet action');
  });
});
