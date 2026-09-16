import assert from 'node:assert/strict';
import { test } from 'node:test';
import { buildTree } from '../tree/tree-builder.js';
import type { GameNode, TreeConfig } from '../types.js';

test('heads-up tree never offers a raise after the opponent is all-in', () => {
  const config: TreeConfig = {
    startingPot: 5,
    effectiveStack: 20,
    betSizes: { flop: [0.33], turn: [0.5], river: [0.5] },
    raiseCapPerStreet: 1,
  };
  const stack: GameNode[] = [buildTree(config)];
  const violations: Array<{ history: string; actions: string[]; stacks: number[] }> = [];
  while (stack.length) {
    const node = stack.pop()!;
    if (node.type !== 'action') continue;
    const segment = node.historyKey.split('/').at(-1) ?? '';
    if (segment.endsWith('A') && node.actions.length !== 2) {
      violations.push({ history: node.historyKey, actions: node.actions, stacks: node.stacks });
    }
    for (const child of node.children.values()) stack.push(child);
  }
  assert.deepEqual(violations, []);
});
