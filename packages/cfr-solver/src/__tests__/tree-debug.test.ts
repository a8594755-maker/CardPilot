import { test } from 'node:test';
import { buildTree, countNodes } from '../tree/tree-builder.js';
import { V1_TREE_CONFIG } from '../tree/tree-config.js';

test('tree structure verification', () => {
  const tree = buildTree(V1_TREE_CONFIG);
  const counts = countNodes(tree);
  console.log(`Tree: ${counts.action} action, ${counts.terminal} terminal`);

  console.log('\nRoot:');
  console.log('  player:', tree.player, '(0=OOP)');
  console.log('  actions:', tree.actions);
  console.log('  pot:', tree.pot);
  console.log('  stacks:', tree.stacks);
  console.log('  history:', JSON.stringify(tree.historyKey));

  // After OOP checks
  const afterCheck = tree.children.get('check')!;
  if (afterCheck.type === 'action') {
    console.log('\nAfter OOP check:');
    console.log('  player:', afterCheck.player, '(1=IP)');
    console.log('  actions:', afterCheck.actions);
    console.log('  history:', JSON.stringify(afterCheck.historyKey));

    // After both check → advance to turn
    const afterCheckCheck = afterCheck.children.get('check')!;
    console.log('\nAfter check-check (should be turn):');
    console.log('  type:', afterCheckCheck.type);
    if (afterCheckCheck.type === 'action') {
      console.log('  street:', afterCheckCheck.street);
      console.log('  player:', afterCheckCheck.player);
      console.log('  actions:', afterCheckCheck.actions);
      console.log('  history:', JSON.stringify(afterCheckCheck.historyKey));
    }

    // After IP bets small
    const afterBetSmall = afterCheck.children.get('bet_small')!;
    if (afterBetSmall.type === 'action') {
      console.log('\nAfter check -> IP bet_small:');
      console.log('  player:', afterBetSmall.player, '(0=OOP faces bet)');
      console.log('  actions:', afterBetSmall.actions);
      console.log('  pot:', afterBetSmall.pot);
    }
  }

  // After OOP bets small
  const afterBetSmall = tree.children.get('bet_small')!;
  if (afterBetSmall.type === 'action') {
    console.log('\nAfter OOP bet_small:');
    console.log('  player:', afterBetSmall.player, '(1=IP faces bet)');
    console.log('  actions:', afterBetSmall.actions);
    console.log('  pot:', afterBetSmall.pot);
    console.log('  history:', JSON.stringify(afterBetSmall.historyKey));
  }
});
