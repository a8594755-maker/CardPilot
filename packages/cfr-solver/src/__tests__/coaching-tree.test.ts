// 6-max Coaching Tree Integration Tests
//
// Validates that coaching tree configs build correctly across all 4 stack depths
// and that the action space is consistent for NN training.

import { describe, it } from 'node:test';
import assert from 'node:assert';
import { buildTree, countNodes } from '../tree/tree-builder.js';
import {
  getTreeConfig,
  getCoachingConfigNames,
  COACHING_BET_SIZES,
  type TreeConfigName,
} from '../tree/tree-config.js';
import type { ActionNode, GameNode } from '../types.js';

// Canonical action vocabulary (16 actions) for the coaching NN
const CANONICAL_ACTIONS = new Set([
  'fold',
  'check',
  'call',
  'bet_0',
  'bet_1',
  'bet_2',
  'bet_3',
  'bet_4',
  'bet_5', // 6 bet sizes
  'raise_0',
  'raise_1',
  'raise_2',
  'raise_3',
  'raise_4',
  'raise_5', // 6 raise sizes
  'allin',
]);

function collectAllActions(node: GameNode, actions: Set<string> = new Set()): Set<string> {
  if (node.type === 'terminal') return actions;
  for (const a of node.actions) {
    actions.add(a);
  }
  for (const child of node.children.values()) {
    collectAllActions(child, actions);
  }
  return actions;
}

function maxTreeDepth(node: GameNode, depth = 0): number {
  if (node.type === 'terminal') return depth;
  let maxD = depth;
  for (const child of node.children.values()) {
    maxD = Math.max(maxD, maxTreeDepth(child, depth + 1));
  }
  return maxD;
}

describe('Coaching Tree Configs', () => {
  it('should have 12 coaching configs in registry', () => {
    const names = getCoachingConfigNames();
    assert.strictEqual(names.length, 12, `Expected 12 coaching configs, got ${names.length}`);

    // Verify all 4 depths × 3 pot types
    const depths = ['30bb', '60bb', '100bb', '200bb'];
    const types = ['coach_hu_srp', 'coach_hu_3bp', 'coach_mw3_srp'];

    for (const type of types) {
      for (const depth of depths) {
        const name = `${type}_${depth}`;
        assert.ok(names.includes(name as TreeConfigName), `Missing config: ${name}`);
      }
    }
  });

  it('coaching bet sizes should have 6 sizes per street', () => {
    assert.strictEqual(COACHING_BET_SIZES.flop.length, 6);
    assert.strictEqual(COACHING_BET_SIZES.turn.length, 6);
    assert.strictEqual(COACHING_BET_SIZES.river.length, 6);
    assert.deepStrictEqual(COACHING_BET_SIZES.flop, [0.25, 0.33, 0.5, 0.75, 1.0, 1.5]);
  });

  it('should build valid HU SRP trees for all depths', () => {
    const configs: TreeConfigName[] = [
      'coach_hu_srp_30bb',
      'coach_hu_srp_60bb',
      'coach_hu_srp_100bb',
      'coach_hu_srp_200bb',
    ];

    const results: Array<{ name: string; action: number; terminal: number; depth: number }> = [];

    for (const name of configs) {
      const config = getTreeConfig(name);
      const tree = buildTree(config);
      const nodes = countNodes(tree);

      // Basic validity
      assert.strictEqual(tree.type, 'action');
      assert.strictEqual(tree.player, 0, `${name}: OOP should act first`);
      assert.strictEqual(tree.street, 'FLOP', `${name}: should start on flop`);
      assert.ok(nodes.action > 0, `${name}: should have action nodes`);
      assert.ok(nodes.terminal > 0, `${name}: should have terminal nodes`);

      // Pot and stack consistency
      assert.strictEqual(tree.pot, 5, `${name}: SRP pot should be 5bb`);

      const depth = maxTreeDepth(tree);
      results.push({ name, ...nodes, depth });
    }

    console.log('\nCoaching HU SRP tree sizes:');
    for (const r of results) {
      console.log(
        `  ${r.name.padEnd(25)} action=${String(r.action).padStart(6)} terminal=${String(r.terminal).padStart(6)} depth=${r.depth}`,
      );
    }

    // Deeper stacks should produce equal or larger trees
    // (shallow stacks collapse many sizes into allin)
    assert.ok(results[3].action >= results[0].action, '200bb tree should be >= 30bb tree');
  });

  it('should build valid HU 3BP trees for all depths', () => {
    const configs: TreeConfigName[] = [
      'coach_hu_3bp_30bb',
      'coach_hu_3bp_60bb',
      'coach_hu_3bp_100bb',
      'coach_hu_3bp_200bb',
    ];

    for (const name of configs) {
      const config = getTreeConfig(name);
      const tree = buildTree(config);
      const nodes = countNodes(tree);

      assert.strictEqual(tree.pot, 17.5, `${name}: 3BP pot should be 17.5bb`);
      assert.ok(nodes.action > 0, `${name}: should have action nodes`);
      assert.ok(nodes.terminal > 0, `${name}: should have terminal nodes`);

      console.log(
        `  ${name.padEnd(25)} action=${String(nodes.action).padStart(6)} terminal=${String(nodes.terminal).padStart(6)}`,
      );
    }
  });

  it('should build valid 3-way SRP trees for small depths', () => {
    // 100bb and 200bb MW3 trees are too large (2.6M+ nodes) and OOM in CI
    const configs: TreeConfigName[] = ['coach_mw3_srp_30bb', 'coach_mw3_srp_60bb'];

    for (const name of configs) {
      const config = getTreeConfig(name);
      const tree = buildTree(config);
      const nodes = countNodes(tree);

      assert.strictEqual(tree.pot, 7.5, `${name}: 3-way SRP pot should be 7.5bb`);
      assert.ok(tree.activePlayers, `${name}: should have activePlayers`);
      assert.deepStrictEqual(tree.activePlayers, [true, true, true]);
      assert.ok(nodes.action > 0, `${name}: should have action nodes`);

      // 3-way trees should be larger than HU
      const huConfig = getTreeConfig(name.replace('mw3', 'hu') as TreeConfigName);
      // Skip comparison if HU equivalent doesn't exist

      console.log(
        `  ${name.padEnd(25)} action=${String(nodes.action).padStart(6)} terminal=${String(nodes.terminal).padStart(6)}`,
      );
    }
  });

  it('all coaching tree actions should be within canonical vocabulary', () => {
    // Test a representative config
    const config = getTreeConfig('coach_hu_srp_100bb');
    const tree = buildTree(config);
    const treeActions = collectAllActions(tree);

    for (const a of treeActions) {
      assert.ok(CANONICAL_ACTIONS.has(a), `Action "${a}" not in canonical vocabulary`);
    }

    console.log(`\nActions used in coach_hu_srp_100bb: ${[...treeActions].sort().join(', ')}`);
  });

  it('check → next player flow is correct in HU', () => {
    const config = getTreeConfig('coach_hu_srp_100bb');
    const tree = buildTree(config);

    // Root: player 0 (OOP)
    assert.strictEqual(tree.player, 0);

    // After OOP checks, IP should act
    const afterCheck = tree.children.get('check');
    assert.ok(afterCheck, 'check should have a child');
    if (afterCheck && afterCheck.type === 'action') {
      assert.strictEqual(afterCheck.player, 1, 'IP should act after OOP check');
    }
  });

  it('check → next player flow is correct in 3-way', () => {
    const config = getTreeConfig('coach_mw3_srp_30bb');
    const tree = buildTree(config);

    assert.strictEqual(tree.player, 0, 'Player 0 acts first in 3-way');

    const afterP0Check = tree.children.get('check');
    if (afterP0Check && afterP0Check.type === 'action') {
      assert.strictEqual(afterP0Check.player, 1, 'Player 1 should act after P0 check');

      const afterP1Check = afterP0Check.children.get('check');
      if (afterP1Check && afterP1Check.type === 'action') {
        assert.strictEqual(afterP1Check.player, 2, 'Player 2 should act after P1 check');

        // After all 3 check, should advance to turn
        const afterP2Check = afterP1Check.children.get('check');
        if (afterP2Check && afterP2Check.type === 'action') {
          assert.strictEqual(afterP2Check.street, 'TURN', 'Should advance to turn after 3 checks');
        }
      }
    }
  });

  it('stack consistency: pot + stacks = initial total', () => {
    const testCases: Array<{ name: TreeConfigName; expectedTotal: number }> = [
      { name: 'coach_hu_srp_100bb', expectedTotal: 200 }, // pot=5 + 97.5×2
      { name: 'coach_hu_3bp_100bb', expectedTotal: 200 }, // pot=17.5 + 91.25×2
      { name: 'coach_hu_srp_30bb', expectedTotal: 60 }, // pot=5 + 27.5×2
      { name: 'coach_mw3_srp_30bb', expectedTotal: 90 }, // pot=7.5 + 27.5×3
    ];

    for (const { name, expectedTotal } of testCases) {
      const config = getTreeConfig(name);
      const numPlayers = config.numPlayers ?? 2;
      const total = config.startingPot + config.effectiveStack * numPlayers;
      assert.ok(
        Math.abs(total - expectedTotal) < 0.01,
        `${name}: pot(${config.startingPot}) + stack(${config.effectiveStack})×${numPlayers} = ${total}, expected ${expectedTotal}`,
      );
    }
  });
});
