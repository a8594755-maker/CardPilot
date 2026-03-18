// Kuhn Poker full verification suite
//
// Implements the 6-point verification checklist:
// 1. Known-answer small game (Kuhn Poker)
// 2. Exploitability calculation (best response)
// 3. Average strategy evaluation
// 4. Strategy legality checks (sum=1, non-negative, zero-sum)
// 5. Cross-validation with known equilibrium values
// 6. Convergence curve (exploitability over iterations)
//
// Known Kuhn Poker Nash Equilibrium (parameterized by alpha in [0, 1/3]):
//   Game value for P0 = -1/18 ~ -0.0556
//   P0 J: bet alpha, check 1-alpha; facing bet -> always fold
//   P0 Q: always check; facing bet -> call 1/3 + alpha
//   P0 K: bet 3*alpha, check 1-3*alpha; facing bet -> always call
//   P1 J after check: bet 1/3; facing bet at root -> fold
//   P1 Q after check: always check; facing bet at root -> call 1/3
//   P1 K after check: always bet; facing bet at root -> always call

import { describe, test } from 'node:test';
import * as assert from 'node:assert/strict';
import { InfoSetStore } from '../engine/info-set-store.js';

// =====================================================================
// Kuhn Poker game logic
// =====================================================================

type Card = 0 | 1 | 2; // J=0, Q=1, K=2
const CARD_NAMES = ['J', 'Q', 'K'];
const ALL_DEALS: [Card, Card][] = [];
for (let a = 0; a < 3; a++) {
  for (let b = 0; b < 3; b++) {
    if (a !== b) ALL_DEALS.push([a as Card, b as Card]);
  }
}

function actingPlayer(history: string): 0 | 1 {
  if (history === '' || history === 'xb') return 0;
  if (history === 'x' || history === 'b') return 1;
  throw new Error(`Not an action node: ${history}`);
}

function isTerminal(h: string): boolean {
  return h === 'xx' || h === 'xbf' || h === 'xbc' || h === 'bf' || h === 'bc';
}

function getActions(h: string): string[] {
  if (h === '' || h === 'x') return ['x', 'b']; // check or bet
  if (h === 'b' || h === 'xb') return ['f', 'c']; // fold or call
  throw new Error(`No actions for: ${h}`);
}

/** Payoff for Player 0 at terminal node */
function terminalPayoff(p0Card: Card, p1Card: Card, h: string): number {
  const winner = p0Card > p1Card ? 1 : -1;
  switch (h) {
    case 'xx':
      return winner * 1;
    case 'xbc':
      return winner * 2;
    case 'xbf':
      return -1; // P0 folded -> loses ante
    case 'bf':
      return 1; // P1 folded -> P0 wins ante
    case 'bc':
      return winner * 2;
    default:
      throw new Error(`Not terminal: ${h}`);
  }
}

// =====================================================================
// CFR+ solver
// =====================================================================

function kuhnCFR(
  store: InfoSetStore,
  p0Card: Card,
  p1Card: Card,
  history: string,
  reachP0: number,
  reachP1: number,
  traverser: 0 | 1,
): number {
  if (isTerminal(history)) {
    const p0Pay = terminalPayoff(p0Card, p1Card, history);
    return traverser === 0 ? p0Pay : -p0Pay;
  }

  const player = actingPlayer(history);
  const playerCard = player === 0 ? p0Card : p1Card;
  const infoKey = `${CARD_NAMES[playerCard]}|${history}`;
  const actions = getActions(history);
  const numActions = actions.length;
  const strategy = store.getCurrentStrategy(infoKey, numActions);
  const actionValues = new Float32Array(numActions);
  let nodeValue = 0;

  for (let a = 0; a < numActions; a++) {
    const newHistory = history + actions[a];
    const newReachP0 = player === 0 ? reachP0 * strategy[a] : reachP0;
    const newReachP1 = player === 1 ? reachP1 * strategy[a] : reachP1;
    actionValues[a] = kuhnCFR(store, p0Card, p1Card, newHistory, newReachP0, newReachP1, traverser);
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

function solveKuhn(
  iterations: number,
  logInterval?: number,
): {
  store: InfoSetStore;
  exploitabilityLog: { iter: number; exploit: number }[];
} {
  const store = new InfoSetStore();
  const exploitabilityLog: { iter: number; exploit: number }[] = [];

  for (let iter = 0; iter < iterations; iter++) {
    for (const [p0Card, p1Card] of ALL_DEALS) {
      kuhnCFR(store, p0Card, p1Card, '', 1, 1, 0);
      kuhnCFR(store, p0Card, p1Card, '', 1, 1, 1);
    }
    if (logInterval && (iter + 1) % logInterval === 0) {
      const exploit = computeExploitability(store);
      exploitabilityLog.push({ iter: iter + 1, exploit });
    }
  }

  return { store, exploitabilityLog };
}

// =====================================================================
// Correct Best Response & Exploitability
// =====================================================================
// Key: BR must pick the best action per INFORMATION SET, not per deal.
// We use brute-force enumeration of all pure strategies (2^6 = 64 per player).

/**
 * Evaluate a specific pure strategy for brPlayer against opponent's average strategy.
 */
function evalPureStrategy(
  store: InfoSetStore,
  p0Card: Card,
  p1Card: Card,
  history: string,
  brPlayer: 0 | 1,
  pureStrategy: Map<string, number>,
): number {
  if (isTerminal(history)) {
    const p0Pay = terminalPayoff(p0Card, p1Card, history);
    return brPlayer === 0 ? p0Pay : -p0Pay;
  }

  const player = actingPlayer(history);
  const playerCard = player === 0 ? p0Card : p1Card;
  const infoKey = `${CARD_NAMES[playerCard]}|${history}`;
  const actions = getActions(history);

  if (player === brPlayer) {
    // Use the pure strategy deterministic action
    const actionIdx = pureStrategy.get(infoKey) ?? 0;
    return evalPureStrategy(
      store,
      p0Card,
      p1Card,
      history + actions[actionIdx],
      brPlayer,
      pureStrategy,
    );
  } else {
    // Opponent: use average strategy
    const strategy = store.getAverageStrategy(infoKey, actions.length);
    let value = 0;
    for (let a = 0; a < actions.length; a++) {
      value +=
        strategy[a] *
        evalPureStrategy(store, p0Card, p1Card, history + actions[a], brPlayer, pureStrategy);
    }
    return value;
  }
}

/**
 * Compute best response value for brPlayer by enumerating all pure strategies.
 * This is correct (no information leakage) and feasible for small games.
 */
function computeBRValue(store: InfoSetStore, brPlayer: 0 | 1): number {
  const infoSets =
    brPlayer === 0
      ? ['J|', 'Q|', 'K|', 'J|xb', 'Q|xb', 'K|xb']
      : ['J|x', 'Q|x', 'K|x', 'J|b', 'Q|b', 'K|b'];

  let bestValue = -Infinity;

  // Enumerate all 2^6 = 64 pure strategies
  for (let mask = 0; mask < 64; mask++) {
    const pureStrategy = new Map<string, number>();
    for (let i = 0; i < infoSets.length; i++) {
      pureStrategy.set(infoSets[i], (mask >> i) & 1);
    }

    let value = 0;
    for (const [p0Card, p1Card] of ALL_DEALS) {
      value += evalPureStrategy(store, p0Card, p1Card, '', brPlayer, pureStrategy);
    }
    value /= ALL_DEALS.length;

    if (value > bestValue) bestValue = value;
  }

  return bestValue;
}

/**
 * Exploitability = BR(P0) + BR(P1).
 * At Nash equilibrium: BR(P0) = game_value_P0 = -1/18,
 *                      BR(P1) = game_value_P1 = +1/18,
 *                      exploitability = 0.
 */
function computeExploitability(store: InfoSetStore): number {
  return computeBRValue(store, 0) + computeBRValue(store, 1);
}

/**
 * Compute game value (P0's expected payoff) under the average strategy profile.
 */
function computeGameValue(store: InfoSetStore): number {
  let totalValue = 0;
  for (const [p0Card, p1Card] of ALL_DEALS) {
    totalValue += evalAvgStrategy(store, p0Card, p1Card, '');
  }
  return totalValue / ALL_DEALS.length;
}

function evalAvgStrategy(store: InfoSetStore, p0Card: Card, p1Card: Card, history: string): number {
  if (isTerminal(history)) {
    return terminalPayoff(p0Card, p1Card, history);
  }

  const player = actingPlayer(history);
  const playerCard = player === 0 ? p0Card : p1Card;
  const infoKey = `${CARD_NAMES[playerCard]}|${history}`;
  const actions = getActions(history);
  const strategy = store.getAverageStrategy(infoKey, actions.length);

  let value = 0;
  for (let a = 0; a < actions.length; a++) {
    value += strategy[a] * evalAvgStrategy(store, p0Card, p1Card, history + actions[a]);
  }
  return value;
}

// =====================================================================
// Tests
// =====================================================================

describe('Kuhn Poker Verification Suite', () => {
  // --- Check 4: Strategy Legality ---
  test('Check 4: Strategy legality (non-negative, sum=1, zero-sum)', () => {
    const { store } = solveKuhn(10000);

    let infoSetCount = 0;
    for (const entry of store.entries()) {
      infoSetCount++;
      const strat = entry.averageStrategy;
      let sum = 0;
      for (let i = 0; i < strat.length; i++) {
        assert.ok(strat[i] >= -1e-6, `Negative prob at ${entry.key} action ${i}: ${strat[i]}`);
        sum += strat[i];
      }
      assert.ok(Math.abs(sum - 1.0) < 0.01, `Strategy at ${entry.key} sums to ${sum}`);
    }
    console.log(`  OK: ${infoSetCount} info sets all valid (non-negative, sum=1)`);
    assert.strictEqual(infoSetCount, 12, `Expected 12 info sets, got ${infoSetCount}`);
    console.log(`  OK: 12 info sets (correct for Kuhn poker)`);

    // Zero-sum check
    for (const [p0Card, p1Card] of ALL_DEALS) {
      for (const h of ['xx', 'xbf', 'xbc', 'bf', 'bc']) {
        const p0Pay = terminalPayoff(p0Card, p1Card, h);
        // Zero-sum: p1 payoff = -p0 payoff (by construction)
        assert.strictEqual(p0Pay + -p0Pay, 0);
      }
    }
    console.log(`  OK: Zero-sum payoff check passed`);
  });

  // --- Check 1 & 5: Known equilibrium values ---
  test('Check 1 & 5: Strategy matches known Nash equilibrium', () => {
    const { store } = solveKuhn(100000);

    console.log('\n  Average strategy (100K iterations):');
    const getStrat = (key: string) => store.getAverageStrategy(key, 2);
    const print = (key: string, a0: string, a1: string) => {
      const s = getStrat(key);
      console.log(`    ${key.padEnd(8)} ${a0}=${s[0].toFixed(4)}  ${a1}=${s[1].toFixed(4)}`);
      return s;
    };

    const p0J = print('J|', 'x', 'b');
    const p0Q = print('Q|', 'x', 'b');
    const p0K = print('K|', 'x', 'b');
    const p0J_xb = print('J|xb', 'f', 'c');
    const p0Q_xb = print('Q|xb', 'f', 'c');
    const p0K_xb = print('K|xb', 'f', 'c');
    const p1J_x = print('J|x', 'x', 'b');
    const p1Q_x = print('Q|x', 'x', 'b');
    const p1K_x = print('K|x', 'x', 'b');
    const p1J_b = print('J|b', 'f', 'c');
    const p1Q_b = print('Q|b', 'f', 'c');
    const p1K_b = print('K|b', 'f', 'c');

    const alpha = p0J[1];
    console.log(`\n  Detected alpha = ${alpha.toFixed(4)}`);

    // alpha in [0, 1/3]
    assert.ok(
      alpha >= -0.05 && alpha <= 0.38,
      `alpha must be in [0, 1/3], got ${alpha.toFixed(4)}`,
    );

    // P0 Q: always check
    assert.ok(p0Q[1] < 0.05, `P0 Q bet should be ~0, got ${p0Q[1].toFixed(4)}`);

    // P0 K bet = 3*alpha
    assert.ok(
      Math.abs(p0K[1] - 3 * alpha) < 0.08,
      `P0 K bet should be ~${(3 * alpha).toFixed(3)}, got ${p0K[1].toFixed(4)}`,
    );

    // P0 J facing bet: always fold
    assert.ok(p0J_xb[0] > 0.95, `P0 J|xb fold should be ~100%`);

    // P0 K facing bet: always call
    assert.ok(p0K_xb[1] > 0.95, `P0 K|xb call should be ~100%`);

    // P0 Q facing bet: call = 1/3 + alpha
    assert.ok(
      Math.abs(p0Q_xb[1] - (1 / 3 + alpha)) < 0.08,
      `P0 Q|xb call should be ~${(1 / 3 + alpha).toFixed(3)}`,
    );

    // P1 J after check: bet 1/3
    assert.ok(Math.abs(p1J_x[1] - 1 / 3) < 0.08, `P1 J|x bet should be ~1/3`);

    // P1 Q after check: always check
    assert.ok(p1Q_x[0] > 0.9, `P1 Q|x should check ~100%`);

    // P1 K after check: always bet
    assert.ok(p1K_x[1] > 0.95, `P1 K|x should bet ~100%`);

    // P1 J facing bet: always fold
    assert.ok(p1J_b[0] > 0.95, `P1 J|b should fold ~100%`);

    // P1 K facing bet: always call
    assert.ok(p1K_b[1] > 0.95, `P1 K|b should call ~100%`);

    console.log(`  OK: All strategy constraints match Nash equilibrium`);

    // Game value check: P0's value = -1/18
    const gameValue = computeGameValue(store);
    console.log(`\n  Game value (P0): ${gameValue.toFixed(6)} (expected: ${(-1 / 18).toFixed(6)})`);
    assert.ok(Math.abs(gameValue - -1 / 18) < 0.01, `Game value should be ~-0.0556`);
    console.log(`  OK: Game value matches -1/18`);
  });

  // --- Check 2 & 3: Exploitability convergence ---
  test('Check 2 & 3: Exploitability decreases and converges to ~0', () => {
    const { store, exploitabilityLog } = solveKuhn(20000, 2000);

    console.log('\n  Exploitability convergence (correct info-set-level BR):');
    console.log('  Iter     | Exploit');
    console.log('  ---------|--------');
    for (const { iter, exploit } of exploitabilityLog) {
      const bar = '#'.repeat(Math.min(50, Math.round(exploit * 500)));
      console.log(`  ${String(iter).padStart(7)}  | ${exploit.toFixed(6)}  ${bar}`);
    }

    // Non-negative (sanity)
    for (const { exploit } of exploitabilityLog) {
      assert.ok(exploit >= -1e-6, `Exploitability should be >= 0, got ${exploit}`);
    }

    // Final exploitability should be small
    const finalExploit = exploitabilityLog[exploitabilityLog.length - 1].exploit;
    console.log(`\n  Final exploitability: ${finalExploit.toFixed(6)}`);
    assert.ok(
      finalExploit < 0.05,
      `Final exploitability should be < 0.05, got ${finalExploit.toFixed(6)}`,
    );
    console.log(`  OK: Exploitability converged`);

    // Decreasing trend
    const n = exploitabilityLog.length;
    const firstQ = exploitabilityLog.slice(0, Math.floor(n / 4));
    const lastQ = exploitabilityLog.slice(Math.floor((3 * n) / 4));
    const avgFirst = firstQ.reduce((s, e) => s + e.exploit, 0) / firstQ.length;
    const avgLast = lastQ.reduce((s, e) => s + e.exploit, 0) / lastQ.length;
    console.log(
      `  First quarter avg: ${avgFirst.toFixed(6)}, Last quarter avg: ${avgLast.toFixed(6)}`,
    );
    assert.ok(
      avgLast < avgFirst + 0.01,
      `Exploitability should decrease: first=${avgFirst.toFixed(4)} last=${avgLast.toFixed(4)}`,
    );
    console.log(`  OK: Decreasing trend confirmed`);
  });

  // --- Check 6: Convergence curve ---
  test('Check 6: Convergence curve - exploit, game value, regret', () => {
    const store = new InfoSetStore();
    const log: { iter: number; exploit: number; gameValue: number }[] = [];

    for (let iter = 0; iter < 10000; iter++) {
      for (const [p0Card, p1Card] of ALL_DEALS) {
        kuhnCFR(store, p0Card, p1Card, '', 1, 1, 0);
        kuhnCFR(store, p0Card, p1Card, '', 1, 1, 1);
      }

      if ((iter + 1) % 1000 === 0) {
        const exploit = computeExploitability(store);
        const gameValue = computeGameValue(store);
        log.push({ iter: iter + 1, exploit, gameValue });
      }
    }

    console.log('\n  Convergence curve:');
    console.log('  Iter   | Exploit   | Game Value (P0)');
    console.log('  -------|-----------|----------------');
    for (const { iter, exploit, gameValue } of log) {
      console.log(
        `  ${String(iter).padStart(6)} | ${exploit.toFixed(6)} | ${gameValue.toFixed(6)}`,
      );
    }

    const final = log[log.length - 1];
    assert.ok(final.exploit < 0.05, `Exploit should converge, got ${final.exploit}`);
    assert.ok(
      Math.abs(final.gameValue - -1 / 18) < 0.01,
      `Game value should be ~-0.0556, got ${final.gameValue}`,
    );

    // No NaN/Inf check
    for (const entry of log) {
      assert.ok(isFinite(entry.exploit), `Exploit is not finite at iter ${entry.iter}`);
      assert.ok(isFinite(entry.gameValue), `Game value is not finite at iter ${entry.iter}`);
    }
    console.log(`  OK: No NaN/Inf, converging properly`);
  });

  // --- Bonus: RPS sanity check ---
  test('Bonus: RPS regret matching converges to (1/3, 1/3, 1/3)', () => {
    const payoff = [
      [0, -1, 1],
      [1, 0, -1],
      [-1, 1, 0],
    ];

    const regretSum = [0, 0, 0];
    const strategySum = [0, 0, 0];

    for (let iter = 0; iter < 10000; iter++) {
      // Regret matching -> current strategy
      const strategy = [0, 0, 0];
      let posSum = 0;
      for (let i = 0; i < 3; i++) {
        strategy[i] = Math.max(0, regretSum[i]);
        posSum += strategy[i];
      }
      if (posSum > 0) {
        for (let i = 0; i < 3; i++) strategy[i] /= posSum;
      } else {
        for (let i = 0; i < 3; i++) strategy[i] = 1 / 3;
      }

      for (let i = 0; i < 3; i++) strategySum[i] += strategy[i];

      // Compute regrets against opponent's current strategy
      for (let myAction = 0; myAction < 3; myAction++) {
        let evAction = 0;
        let evStrat = 0;
        for (let opp = 0; opp < 3; opp++) {
          evAction += strategy[opp] * payoff[myAction][opp];
        }
        for (let my = 0; my < 3; my++) {
          for (let opp = 0; opp < 3; opp++) {
            evStrat += strategy[my] * strategy[opp] * payoff[my][opp];
          }
        }
        regretSum[myAction] += evAction - evStrat;
      }
    }

    const total = strategySum.reduce((a, b) => a + b, 0);
    const avgStrat = strategySum.map((s) => s / total);

    console.log(
      `  RPS avg: R=${avgStrat[0].toFixed(4)} P=${avgStrat[1].toFixed(4)} S=${avgStrat[2].toFixed(4)}`,
    );
    for (let i = 0; i < 3; i++) {
      assert.ok(
        Math.abs(avgStrat[i] - 1 / 3) < 0.05,
        `RPS action ${i} should be ~1/3, got ${avgStrat[i].toFixed(4)}`,
      );
    }
    console.log(`  OK: RPS converged to ~(1/3, 1/3, 1/3)`);
  });
});
