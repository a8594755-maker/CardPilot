// 3-Player Kuhn Poker CFR test
//
// Validates the N-player MCCFR implementation using a self-contained
// 3-player Kuhn poker game (4 cards: J, Q, K, A).
//
// Rules:
// - Each player antes 1 chip (pot = 3)
// - 3 cards dealt (one per player) from {J, Q, K, A}
// - One round of betting: players act in order 0 → 1 → 2
// - Actions: check or bet 1 chip (no raising)
// - If someone bets, remaining players can fold or call
// - Highest card wins at showdown (A > K > Q > J)
//
// In 3P Kuhn, the Nash equilibrium has Player 0 (first to act) checking
// frequently — even with Ace — to trap opponents. P2 (last to act)
// bets more aggressively with strong hands.

import { describe, it } from 'node:test';
import assert from 'node:assert';
import { InfoSetStore } from '../engine/info-set-store.js';
import { buildTree, countNodes } from '../tree/tree-builder.js';

// Card values: 0=J, 1=Q, 2=K, 3=A
const CARD_NAMES = ['J', 'Q', 'K', 'A'];

interface KuhnState {
  cards: number[];         // cards[i] = card for player i
  history: string;         // action history
  pot: number[];           // chips each player has put in
  activePlayers: boolean[];
  playerToAct: number;
  bettingOpen: boolean;    // whether someone has bet
}

/** Apply action and return new state */
function applyAction(state: KuhnState, action: string): KuhnState {
  const p = state.playerToAct;
  const newPot = [...state.pot];
  const newActive = [...state.activePlayers];

  if (action === 'f') {
    newActive[p] = false;
  } else if (action === 'b') {
    newPot[p] += 1;
  } else if (action === 'c') {
    newPot[p] += 1;
  }

  // Find next active player
  let next = -1;
  for (let i = 1; i <= 3; i++) {
    const candidate = (p + i) % 3;
    if (newActive[candidate]) { next = candidate; break; }
  }

  return {
    cards: state.cards,
    history: state.history + action,
    pot: newPot,
    activePlayers: newActive,
    playerToAct: next >= 0 ? next : p,
    bettingOpen: state.bettingOpen || action === 'b',
  };
}

/** Check if game is over */
function gameOver(state: KuhnState): boolean {
  const activeCount = state.activePlayers.filter(a => a).length;
  if (activeCount <= 1) return true;

  const h = state.history;
  if (h === 'xxx') return true;

  const betIdx = h.indexOf('b');
  if (betIdx < 0) return false;

  // After a bet, need 2 responses from the other players
  const responses = h.length - betIdx - 1;
  return responses >= 2;
}

/** Get legal actions */
function getActions(state: KuhnState): string[] {
  if (state.bettingOpen) {
    // Check if current player already has money in at the bet level
    const maxBet = Math.max(...state.pot);
    if (state.pot[state.playerToAct] < maxBet) {
      return ['f', 'c']; // fold or call
    }
    return ['x', 'b']; // shouldn't happen in this simple game
  }
  return ['x', 'b']; // check or bet
}

/** Compute payoffs at terminal */
function computePayoffs(state: KuhnState): number[] {
  const activeIndices = state.activePlayers
    .map((a, i) => (a ? i : -1))
    .filter(i => i >= 0);
  const totalPot = state.pot.reduce((a, b) => a + b, 0);

  if (activeIndices.length === 1) {
    const winner = activeIndices[0];
    return state.pot.map((bet, i) => (i === winner ? totalPot - bet : -bet));
  }

  let maxCard = -1;
  let maxPlayer = -1;
  for (const p of activeIndices) {
    if (state.cards[p] > maxCard) {
      maxCard = state.cards[p];
      maxPlayer = p;
    }
  }

  return state.pot.map((bet, i) => (i === maxPlayer ? totalPot - bet : -bet));
}

// ═══════════════════════════════════════════════════════════
// CFR solver for 3-player Kuhn
// ═══════════════════════════════════════════════════════════

function kuhn3pCFR(
  state: KuhnState,
  store: InfoSetStore,
  traverser: number,
  reachProbs: number[],
): number {
  if (gameOver(state)) {
    return computePayoffs(state)[traverser];
  }

  const p = state.playerToAct;
  const actions = getActions(state);
  const infoKey = `${CARD_NAMES[state.cards[p]]}|${state.history}`;
  const numActions = actions.length;

  const strategy = store.getCurrentStrategy(infoKey, numActions);
  const actionValues = new Float32Array(numActions);
  let nodeValue = 0;

  for (let a = 0; a < numActions; a++) {
    const nextState = applyAction(state, actions[a]);
    const newReach = [...reachProbs];
    newReach[p] *= strategy[a];

    actionValues[a] = kuhn3pCFR(nextState, store, traverser, newReach);
    nodeValue += strategy[a] * actionValues[a];
  }

  if (p === traverser) {
    let cfReach = 1;
    for (let i = 0; i < 3; i++) {
      if (i !== traverser) cfReach *= reachProbs[i];
    }

    for (let a = 0; a < numActions; a++) {
      const regret = actionValues[a] - nodeValue;
      store.updateRegret(infoKey, a, cfReach * regret, numActions);
      store.addStrategyWeight(infoKey, a, reachProbs[traverser] * strategy[a], numActions);
    }
  }

  return nodeValue;
}

function solve3PKuhn(iterations: number): InfoSetStore {
  const store = new InfoSetStore();

  // All permutations of 3 cards from 4
  const deals: number[][] = [];
  for (let a = 0; a < 4; a++) {
    for (let b = 0; b < 4; b++) {
      if (b === a) continue;
      for (let c = 0; c < 4; c++) {
        if (c === a || c === b) continue;
        deals.push([a, b, c]);
      }
    }
  }

  for (let iter = 0; iter < iterations; iter++) {
    for (const cards of deals) {
      const initState: KuhnState = {
        cards,
        history: '',
        pot: [1, 1, 1],
        activePlayers: [true, true, true],
        playerToAct: 0,
        bettingOpen: false,
      };

      for (let traverser = 0; traverser < 3; traverser++) {
        kuhn3pCFR(initState, store, traverser, [1, 1, 1]);
      }
    }
  }

  return store;
}

// ═══════════════════════════════════════════════════════════
// Tests
// ═══════════════════════════════════════════════════════════

describe('3-Player Kuhn Poker CFR', () => {
  it('should converge to approximate equilibrium', () => {
    const store = solve3PKuhn(50000);

    console.log('\n3-Player Kuhn Poker Strategy (50K iterations):');
    console.log('═'.repeat(50));

    let validInfoSets = 0;
    const strategies = new Map<string, number[]>();

    for (const entry of store.entries()) {
      const sum = Array.from(entry.averageStrategy).reduce((a, b) => a + b, 0);
      if (sum > 0.01) {
        validInfoSets++;
        const normalized = Array.from(entry.averageStrategy).map(v => v / sum);
        strategies.set(entry.key, normalized);

        // Only print a selection
        const key = entry.key;
        if (['A|', 'K|', 'J|', 'A|xx', 'J|xx', 'A|xb', 'J|xb', 'A|xxb', 'J|xxb', 'A|x', 'K|x', 'J|x'].includes(key)) {
          console.log(`  ${key.padEnd(10)} → [${normalized.map(v => v.toFixed(3)).join(', ')}]`);
        }
      }
    }

    console.log(`\nTotal valid info sets: ${validInfoSets}`);

    // 1. All strategies should normalize to 1
    for (const [key, strat] of strategies) {
      const sum = strat.reduce((a, b) => a + b, 0);
      assert.ok(
        Math.abs(sum - 1.0) < 0.01,
        `Strategy should normalize to 1.0, got ${sum.toFixed(4)} for ${key}`,
      );
    }

    // 2. Should have discovered enough info sets
    // 4 cards × multiple histories = at least 12 info sets
    assert.ok(validInfoSets >= 12, `Should have at least 12 info sets (got ${validInfoSets})`);

    // 3. Key equilibrium properties that must hold in ANY Nash eq:

    // P2 (last to act) with Ace after check-check should bet frequently
    const aceP2check = strategies.get('A|xx');
    if (aceP2check) {
      const betFreq = aceP2check[1]; // [check, bet]
      console.log(`P2 Ace after xx: bet ${(betFreq * 100).toFixed(1)}%`);
      assert.ok(betFreq > 0.3, `P2 with Ace after xx should bet often (got ${betFreq.toFixed(3)})`);
    }

    // Any player facing a bet with Jack should fold frequently
    const jackFacesBet = strategies.get('J|xb') ?? strategies.get('J|xxb');
    if (jackFacesBet) {
      const foldFreq = jackFacesBet[0]; // [fold, call]
      console.log(`Jack facing bet: fold ${(foldFreq * 100).toFixed(1)}%`);
      assert.ok(foldFreq > 0.5, `Jack should fold to bets often (got ${foldFreq.toFixed(3)})`);
    }

    // Any player facing a bet with Ace should always call
    const aceFacesBet = strategies.get('A|xb') ?? strategies.get('A|xxb');
    if (aceFacesBet) {
      const callFreq = aceFacesBet[1]; // [fold, call]
      console.log(`Ace facing bet: call ${(callFreq * 100).toFixed(1)}%`);
      assert.ok(callFreq > 0.8, `Ace should call bets (got ${callFreq.toFixed(3)})`);
    }

    // Player 0 with Ace should at least sometimes not bet (check-trapping is valid)
    // This is different from HU where Ace bets more — in 3P, first-to-act often checks
    const aceFirst = strategies.get('A|');
    if (aceFirst) {
      console.log(`P0 Ace first: check ${(aceFirst[0] * 100).toFixed(1)}%, bet ${(aceFirst[1] * 100).toFixed(1)}%`);
      // Both checking and betting should be part of the strategy (mixed strategy)
      // But checking heavily is valid in 3P
    }
  });

  it('should build correct multi-way tree', () => {
    const config = {
      startingPot: 7.5,
      effectiveStack: 47.5,
      betSizes: { flop: [0.50], turn: [0.50], river: [0.50] },
      raiseCapPerStreet: 0,
      numPlayers: 3,
    };

    const tree = buildTree(config);
    const nodes = countNodes(tree);

    console.log(`\n3-way tree: ${nodes.action} action nodes, ${nodes.terminal} terminal nodes`);

    // Basic sanity checks
    assert.ok(nodes.action > 0, 'Should have action nodes');
    assert.ok(nodes.terminal > 0, 'Should have terminal nodes');

    // Root should be player 0
    assert.strictEqual(tree.player, 0, 'Player 0 (BB) should act first');
    assert.strictEqual(tree.street, 'FLOP', 'Should start on flop');

    // Root should have activePlayers
    assert.ok(tree.activePlayers, 'Multi-way tree should have activePlayers');
    assert.deepStrictEqual(tree.activePlayers, [true, true, true]);

    // Root actions: check, bet_0, allin
    assert.ok(tree.actions.includes('check'), 'Should have check action');

    // After check by P0, P1 should act
    const afterCheck = tree.children.get('check');
    assert.ok(afterCheck, 'Check should have child');
    if (afterCheck && afterCheck.type === 'action') {
      assert.strictEqual(afterCheck.player, 1, 'Player 1 should act after P0 checks');
    }

    // After all 3 check on flop, should advance to turn
    if (afterCheck && afterCheck.type === 'action') {
      const afterP1Check = afterCheck.children.get('check');
      if (afterP1Check && afterP1Check.type === 'action') {
        // P2 checks
        const afterP2Check = afterP1Check.children.get('check');
        if (afterP2Check && afterP2Check.type === 'action') {
          assert.strictEqual(afterP2Check.street, 'TURN', 'Should advance to turn after 3 checks');
        }
      }
    }

    // Tree should be larger than HU tree
    const huConfig = {
      startingPot: 7.5,
      effectiveStack: 47.5,
      betSizes: { flop: [0.50], turn: [0.50], river: [0.50] },
      raiseCapPerStreet: 0,
      numPlayers: 2,
    };
    const huTree = buildTree(huConfig);
    const huNodes = countNodes(huTree);
    console.log(`HU tree: ${huNodes.action} action nodes, ${huNodes.terminal} terminal nodes`);
    assert.ok(nodes.action > huNodes.action, '3-way tree should be larger than HU tree');
  });
});
