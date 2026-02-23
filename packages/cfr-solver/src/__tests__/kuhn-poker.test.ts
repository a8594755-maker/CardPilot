// Kuhn Poker CFR+ verification test
//
// Kuhn Poker is a simplified poker game with known Nash equilibrium.
// It has 3 cards (J, Q, K), 1 card each, 1 round of betting.
// Player 0 acts first: check or bet(1).
// After check: Player 1 can check (showdown) or bet(1).
// After bet: opponent can fold or call.
//
// Nash equilibrium (known):
// Player 0 strategy:
//   J: bet with prob α (where α ∈ [0, 1/3]), check with prob 1-α
//     After check and facing bet: always fold
//   Q: always check
//     After check and facing bet: call with prob 1/3 + α, fold with prob 2/3 - α
//   K: bet with prob 3α, check with prob 1-3α
//     After check and facing bet: always call
//
// Game value: -1/18 for Player 0 (Player 1 has slight advantage)
//
// For the canonical equilibrium with α = 0:
// P0 with J: always check, after facing bet: always fold
// P0 with Q: always check, after facing bet: call 1/3
// P0 with K: always check, after facing bet: always call
// P1 with J: after check: bet 1/3, otherwise fold
// P1 with Q: after check: always check
// P1 with K: after check: always bet

import { test, describe } from 'node:test';
import * as assert from 'node:assert/strict';
import { InfoSetStore } from '../engine/info-set-store.js';

// Kuhn Poker implementation using CFR+
type KuhnCard = 0 | 1 | 2; // J=0, Q=1, K=2
const CARD_NAMES = ['J', 'Q', 'K'];

interface KuhnNode {
  type: 'action' | 'terminal';
}

interface KuhnActionNode extends KuhnNode {
  type: 'action';
  player: 0 | 1;
  history: string;
}

interface KuhnTerminalNode extends KuhnNode {
  type: 'terminal';
  history: string;
}

function kuhnCFR(
  store: InfoSetStore,
  p0Card: KuhnCard,
  p1Card: KuhnCard,
  history: string,
  reachP0: number,
  reachP1: number,
  traverser: 0 | 1,
): number {
  // Terminal states
  if (history === 'xx') {
    // Both check → showdown
    return showdownPayoff(p0Card, p1Card, 1) * (traverser === 0 ? 1 : -1);
  }
  if (history === 'xbf') {
    // P0 checks, P1 bets, P0 folds → P1 wins ante (1)
    return traverser === 0 ? -1 : 1;
  }
  if (history === 'xbc') {
    // P0 checks, P1 bets, P0 calls → showdown for pot of 4 (ante 1 + bet 1 each)
    return showdownPayoff(p0Card, p1Card, 2) * (traverser === 0 ? 1 : -1);
  }
  if (history === 'bf') {
    // P0 bets, P1 folds → P0 wins ante (1)
    return traverser === 0 ? 1 : -1;
  }
  if (history === 'bc') {
    // P0 bets, P1 calls → showdown for pot of 4
    return showdownPayoff(p0Card, p1Card, 2) * (traverser === 0 ? 1 : -1);
  }

  // Determine acting player
  const player: 0 | 1 = history.length === 0 || history === 'xb' ? 0 :
                         history === 'x' || history === 'b' ? 1 : 0;
  const isSecondActionP0 = history === 'xb'; // P0 faces a bet after checking

  const playerCard = player === 0 ? p0Card : p1Card;
  const infoKey = `${CARD_NAMES[playerCard]}|${history}`;

  // Actions: depends on position in tree
  let actions: string[];
  if (history === '' || history === 'x') {
    actions = ['x', 'b']; // check or bet
  } else if (history === 'b' || history === 'xb') {
    actions = ['f', 'c']; // fold or call
  } else {
    throw new Error(`Unexpected history: ${history}`);
  }

  const numActions = actions.length;
  const strategy = store.getCurrentStrategy(infoKey, numActions);
  const actionValues = new Float32Array(numActions);
  let nodeValue = 0;

  for (let a = 0; a < numActions; a++) {
    const newHistory = history + actions[a];
    const newReachP0 = player === 0 ? reachP0 * strategy[a] : reachP0;
    const newReachP1 = player === 1 ? reachP1 * strategy[a] : reachP1;

    actionValues[a] = kuhnCFR(
      store, p0Card, p1Card, newHistory,
      newReachP0, newReachP1, traverser,
    );
    nodeValue += strategy[a] * actionValues[a];
  }

  if (player === traverser) {
    const opponentReach = player === 0 ? reachP1 : reachP0;
    const playerReach = player === 0 ? reachP0 : reachP1;

    for (let a = 0; a < numActions; a++) {
      const regret = actionValues[a] - nodeValue;
      store.updateRegret(infoKey, a, opponentReach * regret, numActions);
      store.addStrategyWeight(infoKey, a, playerReach * strategy[a], numActions);
    }
  }

  return nodeValue;
}

function showdownPayoff(p0Card: KuhnCard, p1Card: KuhnCard, stake: number): number {
  // Higher card wins (K > Q > J)
  if (p0Card > p1Card) return stake;
  if (p0Card < p1Card) return -stake;
  return 0; // tie (shouldn't happen in Kuhn with 3 cards)
}

function solveKuhn(iterations: number): InfoSetStore {
  const store = new InfoSetStore();
  const cards: KuhnCard[] = [0, 1, 2]; // J, Q, K

  for (let iter = 0; iter < iterations; iter++) {
    // Iterate over all 6 possible deals (permutations of 2 from 3)
    for (const p0Card of cards) {
      for (const p1Card of cards) {
        if (p0Card === p1Card) continue;
        // Traverse for player 0
        kuhnCFR(store, p0Card, p1Card, '', 1, 1, 0);
        // Traverse for player 1
        kuhnCFR(store, p0Card, p1Card, '', 1, 1, 1);
      }
    }
  }

  return store;
}

describe('Kuhn Poker CFR+', () => {
  test('should converge to known Nash equilibrium', () => {
    const store = solveKuhn(100000);

    // Check Player 0 strategies
    // P0 with J, first action: should mostly check (bet freq near 0)
    const p0J = store.getAverageStrategy('J|', 2);
    console.log(`P0 J: check=${p0J[0].toFixed(3)} bet=${p0J[1].toFixed(3)}`);
    assert.ok(p0J[1] < 0.4, `P0 J bet freq should be < 0.4, got ${p0J[1]}`);

    // P0 with Q, first action: should check
    const p0Q = store.getAverageStrategy('Q|', 2);
    console.log(`P0 Q: check=${p0Q[0].toFixed(3)} bet=${p0Q[1].toFixed(3)}`);
    assert.ok(p0Q[0] > 0.6, `P0 Q check freq should be > 0.6, got ${p0Q[0]}`);

    // P0 with K, first action: can bet or check (depends on α)
    const p0K = store.getAverageStrategy('K|', 2);
    console.log(`P0 K: check=${p0K[0].toFixed(3)} bet=${p0K[1].toFixed(3)}`);

    // P0 with J facing bet after checking: should fold
    const p0J_xb = store.getAverageStrategy('J|xb', 2);
    console.log(`P0 J|xb: fold=${p0J_xb[0].toFixed(3)} call=${p0J_xb[1].toFixed(3)}`);
    assert.ok(p0J_xb[0] > 0.7, `P0 J facing bet should fold > 0.7, got ${p0J_xb[0]}`);

    // P0 with K facing bet after checking: should call
    const p0K_xb = store.getAverageStrategy('K|xb', 2);
    console.log(`P0 K|xb: fold=${p0K_xb[0].toFixed(3)} call=${p0K_xb[1].toFixed(3)}`);
    assert.ok(p0K_xb[1] > 0.8, `P0 K facing bet should call > 0.8, got ${p0K_xb[1]}`);

    // P0 with Q facing bet: should call ~1/3
    const p0Q_xb = store.getAverageStrategy('Q|xb', 2);
    console.log(`P0 Q|xb: fold=${p0Q_xb[0].toFixed(3)} call=${p0Q_xb[1].toFixed(3)}`);
    assert.ok(p0Q_xb[1] > 0.15 && p0Q_xb[1] < 0.6,
      `P0 Q call freq should be ~0.33, got ${p0Q_xb[1]}`);

    // P1 with J after check: should bet ~1/3
    const p1J_x = store.getAverageStrategy('J|x', 2);
    console.log(`P1 J|x: check=${p1J_x[0].toFixed(3)} bet=${p1J_x[1].toFixed(3)}`);
    assert.ok(p1J_x[1] > 0.15 && p1J_x[1] < 0.55,
      `P1 J bet freq should be ~0.33, got ${p1J_x[1]}`);

    // P1 with K after check: should always bet
    const p1K_x = store.getAverageStrategy('K|x', 2);
    console.log(`P1 K|x: check=${p1K_x[0].toFixed(3)} bet=${p1K_x[1].toFixed(3)}`);
    assert.ok(p1K_x[1] > 0.7, `P1 K bet freq should be > 0.7, got ${p1K_x[1]}`);

    // P1 with J facing bet: should always fold
    const p1J_b = store.getAverageStrategy('J|b', 2);
    console.log(`P1 J|b: fold=${p1J_b[0].toFixed(3)} call=${p1J_b[1].toFixed(3)}`);
    assert.ok(p1J_b[0] > 0.8, `P1 J facing bet should fold > 0.8, got ${p1J_b[0]}`);

    // P1 with K facing bet: should always call
    const p1K_b = store.getAverageStrategy('K|b', 2);
    console.log(`P1 K|b: fold=${p1K_b[0].toFixed(3)} call=${p1K_b[1].toFixed(3)}`);
    assert.ok(p1K_b[1] > 0.8, `P1 K facing bet should call > 0.8, got ${p1K_b[1]}`);

    console.log(`\nTotal info sets: ${store.size}`);
  });
});
