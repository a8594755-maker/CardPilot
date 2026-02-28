#!/usr/bin/env node
// ===== Offline regression testing for bot decision pipeline =====
// Runs predefined scenarios thousands of times to verify strategy correctness.
// Usage: pnpm --filter bot-client regression

import { decide, quickHandStrength } from './decision.js';
import { getProfile } from './profiles.js';
import { generatePersona } from './persona.js';
import type { TableState, LegalActions, HandAction } from './types.js';

// ===== Scenario definition =====
interface RegressionScenario {
  name: string;
  profileId: string;
  heroCards: [string, string];
  board: string[];
  street: 'PREFLOP' | 'FLOP' | 'TURN' | 'RIVER';
  pot: number;
  bigBlind: number;
  legalActions: LegalActions;
  actions: HandAction[];
  positions: Record<number, string>;
  heroSeat: number;
  players: { seat: number; stack: number; inHand: boolean; folded: boolean }[];
  expected: {
    minRaiseFreq?: number;
    maxRaiseFreq?: number;
    minCallFreq?: number;
    maxCallFreq?: number;
    minFoldFreq?: number;
    maxFoldFreq?: number;
  };
}

interface ScenarioResult {
  scenario: string;
  profileId: string;
  iterations: number;
  raiseFreq: number;
  callFreq: number;
  foldFreq: number;
  checkFreq: number;
  avgRaiseAmount: number;
  passed: boolean;
  violations: string[];
}

// ===== Build a TableState from scenario params =====
function buildTableState(s: RegressionScenario): TableState {
  return {
    tableId: 'regression-test',
    smallBlind: s.bigBlind / 2,
    bigBlind: s.bigBlind,
    buttonSeat: 0,
    street: s.street,
    board: s.board,
    pot: s.pot,
    currentBet: s.legalActions.callAmount,
    minRaiseTo: s.legalActions.minRaise,
    lastFullRaiseSize: 0,
    lastFullBet: 0,
    actorSeat: s.heroSeat,
    handId: `regtest-${Date.now()}`,
    players: s.players.map(p => ({
      seat: p.seat,
      userId: `player-${p.seat}`,
      name: `Player ${p.seat}`,
      stack: p.stack,
      inHand: p.inHand,
      folded: p.folded,
      allIn: false,
      streetCommitted: 0,
      status: 'active' as const,
      isNewPlayer: false,
    })),
    actions: s.actions,
    legalActions: s.legalActions,
    mode: 'CASUAL',
    positions: s.positions,
  };
}

// ===== Run a single scenario =====
function runScenario(scenario: RegressionScenario, iterations: number): ScenarioResult {
  const counts = { raise: 0, call: 0, fold: 0, check: 0 };
  let totalRaiseAmount = 0;
  let raiseCount = 0;

  for (let i = 0; i < iterations; i++) {
    const state = buildTableState(scenario);
    state.handId = `regtest-${i}`;

    const profile = getProfile(scenario.profileId);
    const persona = generatePersona(scenario.profileId, `regression-${i}`);

    const result = decide({
      state,
      profile,
      advice: null,
      holeCards: scenario.heroCards,
      mySeat: scenario.heroSeat,
      persona,
      handNumber: i + 1,
    });

    if (result.action === 'raise') { counts.raise++; totalRaiseAmount += result.amount ?? 0; raiseCount++; }
    else if (result.action === 'call') counts.call++;
    else if (result.action === 'fold') counts.fold++;
    else if (result.action === 'check') counts.check++;
  }

  const total = iterations;
  const raiseFreq = counts.raise / total;
  const callFreq = (counts.call + counts.check) / total;
  const foldFreq = counts.fold / total;
  const checkFreq = counts.check / total;
  const avgRaiseAmount = raiseCount > 0 ? totalRaiseAmount / raiseCount : 0;

  const violations: string[] = [];
  const e = scenario.expected;
  if (e.minRaiseFreq != null && raiseFreq < e.minRaiseFreq) violations.push(`raise freq ${(raiseFreq * 100).toFixed(1)}% < min ${(e.minRaiseFreq * 100).toFixed(1)}%`);
  if (e.maxRaiseFreq != null && raiseFreq > e.maxRaiseFreq) violations.push(`raise freq ${(raiseFreq * 100).toFixed(1)}% > max ${(e.maxRaiseFreq * 100).toFixed(1)}%`);
  if (e.minCallFreq != null && callFreq < e.minCallFreq) violations.push(`call freq ${(callFreq * 100).toFixed(1)}% < min ${(e.minCallFreq * 100).toFixed(1)}%`);
  if (e.maxCallFreq != null && callFreq > e.maxCallFreq) violations.push(`call freq ${(callFreq * 100).toFixed(1)}% > max ${(e.maxCallFreq * 100).toFixed(1)}%`);
  if (e.minFoldFreq != null && foldFreq < e.minFoldFreq) violations.push(`fold freq ${(foldFreq * 100).toFixed(1)}% < min ${(e.minFoldFreq * 100).toFixed(1)}%`);
  if (e.maxFoldFreq != null && foldFreq > e.maxFoldFreq) violations.push(`fold freq ${(foldFreq * 100).toFixed(1)}% > max ${(e.maxFoldFreq * 100).toFixed(1)}%`);

  return {
    scenario: scenario.name,
    profileId: scenario.profileId,
    iterations,
    raiseFreq,
    callFreq,
    foldFreq,
    checkFreq,
    avgRaiseAmount,
    passed: violations.length === 0,
    violations,
  };
}

// ===== Default scenario helpers =====
const defaultPlayers = (heroSeat: number) => [
  { seat: heroSeat, stack: 1000, inHand: true, folded: false },
  { seat: (heroSeat + 1) % 6, stack: 1000, inHand: true, folded: false },
  { seat: (heroSeat + 2) % 6, stack: 1000, inHand: true, folded: false },
];

const defaultPositions = (heroSeat: number): Record<number, string> => ({
  [heroSeat]: 'BTN',
  [(heroSeat + 1) % 6]: 'SB',
  [(heroSeat + 2) % 6]: 'BB',
  [(heroSeat + 3) % 6]: 'UTG',
  [(heroSeat + 4) % 6]: 'CO',
  [(heroSeat + 5) % 6]: 'MP',
});

// ===== Built-in scenarios =====
const SCENARIOS: RegressionScenario[] = [
  // 1. Monster hand facing c-bet on dry flop (AA on 2-7-Q rainbow)
  {
    name: 'Monster: AA on dry flop facing c-bet',
    profileId: 'gto_balanced',
    heroCards: ['As', 'Ah'],
    board: ['2d', '7c', 'Qh'],
    street: 'FLOP',
    pot: 60,
    bigBlind: 10,
    legalActions: { canFold: true, canCheck: false, canCall: true, callAmount: 20, canRaise: true, minRaise: 40, maxRaise: 1000 },
    actions: [
      { seat: 3, street: 'PREFLOP', type: 'raise', amount: 25, at: 1 },
      { seat: 0, street: 'PREFLOP', type: 'call', amount: 25, at: 2 },
      { seat: 3, street: 'FLOP', type: 'raise', amount: 20, at: 3 },
    ],
    positions: defaultPositions(0),
    heroSeat: 0,
    players: defaultPlayers(0),
    expected: { maxFoldFreq: 0.15, minRaiseFreq: 0.25 }, // AA as overpair scores 0.72 (strong tier)
  },

  // 2. Trash hand facing big raise preflop (72o vs 10bb open)
  {
    name: 'Trash: 72o facing 10bb preflop raise',
    profileId: 'gto_balanced',
    heroCards: ['7d', '2c'],
    board: [],
    street: 'PREFLOP',
    pot: 115,
    bigBlind: 10,
    legalActions: { canFold: true, canCheck: false, canCall: true, callAmount: 100, canRaise: true, minRaise: 200, maxRaise: 1000 },
    actions: [
      { seat: 3, street: 'PREFLOP', type: 'raise', amount: 100, at: 1 },
    ],
    positions: defaultPositions(0),
    heroSeat: 0,
    players: defaultPlayers(0),
    expected: { minFoldFreq: 0.75 },
  },

  // 3. Top pair on wet board (AK on K-J-T two-tone)
  {
    name: 'Strong: AKs on wet K-J-T',
    profileId: 'gto_balanced',
    heroCards: ['As', 'Ks'],
    board: ['Kh', 'Jh', 'Td'],
    street: 'FLOP',
    pot: 50,
    bigBlind: 10,
    legalActions: { canFold: true, canCheck: false, canCall: true, callAmount: 25, canRaise: true, minRaise: 50, maxRaise: 1000 },
    actions: [
      { seat: 3, street: 'PREFLOP', type: 'raise', amount: 25, at: 1 },
      { seat: 0, street: 'PREFLOP', type: 'call', amount: 25, at: 2 },
      { seat: 3, street: 'FLOP', type: 'raise', amount: 25, at: 3 },
    ],
    positions: defaultPositions(0),
    heroSeat: 0,
    players: defaultPlayers(0),
    expected: { maxFoldFreq: 0.25 },
  },

  // 4. Flush draw facing small bet
  {
    name: 'Draw: flush draw facing 1/3 pot',
    profileId: 'gto_balanced',
    heroCards: ['Ah', 'Kh'],
    board: ['3h', '8h', 'Qd'],
    street: 'FLOP',
    pot: 50,
    bigBlind: 10,
    legalActions: { canFold: true, canCheck: false, canCall: true, callAmount: 15, canRaise: true, minRaise: 30, maxRaise: 1000 },
    actions: [
      { seat: 3, street: 'PREFLOP', type: 'raise', amount: 25, at: 1 },
      { seat: 0, street: 'PREFLOP', type: 'call', amount: 25, at: 2 },
      { seat: 3, street: 'FLOP', type: 'raise', amount: 15, at: 3 },
    ],
    positions: defaultPositions(0),
    heroSeat: 0,
    players: defaultPlayers(0),
    expected: { maxFoldFreq: 0.42 }, // draw bucket + persona variance pushes fold slightly
  },

  // 5. Overpair on dry board as aggressor (checking)
  {
    name: 'Value: overpair on dry board (can check/bet)',
    profileId: 'gto_balanced',
    heroCards: ['Qs', 'Qh'],
    board: ['2d', '7c', '9h'],
    street: 'FLOP',
    pot: 50,
    bigBlind: 10,
    legalActions: { canFold: false, canCheck: true, canCall: false, callAmount: 0, canRaise: true, minRaise: 10, maxRaise: 1000 },
    actions: [
      { seat: 0, street: 'PREFLOP', type: 'raise', amount: 25, at: 1 },
      { seat: 3, street: 'PREFLOP', type: 'call', amount: 25, at: 2 },
    ],
    positions: defaultPositions(0),
    heroSeat: 0,
    players: defaultPlayers(0),
    expected: { minRaiseFreq: 0.10 }, // should bet at least sometimes
  },

  // 6. Preflop open from BTN with KQs
  {
    name: 'Preflop: KQs from BTN unopened',
    profileId: 'gto_balanced',
    heroCards: ['Kd', 'Qd'],
    board: [],
    street: 'PREFLOP',
    pot: 15,
    bigBlind: 10,
    legalActions: { canFold: true, canCheck: true, canCall: false, callAmount: 0, canRaise: true, minRaise: 20, maxRaise: 1000 },
    actions: [],
    positions: defaultPositions(0),
    heroSeat: 0,
    players: defaultPlayers(0),
    expected: { minRaiseFreq: 0.40 }, // should open most of the time
  },

  // 7. Nit profile should fold more with marginal hand
  {
    name: 'Profile: nit should fold 98o facing UTG raise',
    profileId: 'nit',
    heroCards: ['9c', '8d'],
    board: [],
    street: 'PREFLOP',
    pot: 40,
    bigBlind: 10,
    legalActions: { canFold: true, canCheck: false, canCall: true, callAmount: 25, canRaise: true, minRaise: 50, maxRaise: 1000 },
    actions: [
      { seat: 3, street: 'PREFLOP', type: 'raise', amount: 25, at: 1 },
    ],
    positions: { ...defaultPositions(0), 3: 'UTG' },
    heroSeat: 0,
    players: defaultPlayers(0),
    expected: { minFoldFreq: 0.60 },
  },

  // 8. LAG profile should raise more with medium hand
  {
    name: 'Profile: LAG raises more with A9s',
    profileId: 'lag',
    heroCards: ['Ad', '9d'],
    board: [],
    street: 'PREFLOP',
    pot: 15,
    bigBlind: 10,
    legalActions: { canFold: true, canCheck: true, canCall: false, callAmount: 0, canRaise: true, minRaise: 20, maxRaise: 1000 },
    actions: [],
    positions: defaultPositions(0),
    heroSeat: 0,
    players: defaultPlayers(0),
    expected: { minRaiseFreq: 0.50 },
  },

  // 9. Facing 3-bet with marginal hand (T9s)
  {
    name: '3bet: T9s facing 3bet should fold often',
    profileId: 'gto_balanced',
    heroCards: ['Ts', '9s'],
    board: [],
    street: 'PREFLOP',
    pot: 95,
    bigBlind: 10,
    legalActions: { canFold: true, canCheck: false, canCall: true, callAmount: 55, canRaise: true, minRaise: 120, maxRaise: 1000 },
    actions: [
      { seat: 0, street: 'PREFLOP', type: 'raise', amount: 25, at: 1 },
      { seat: 3, street: 'PREFLOP', type: 'raise', amount: 80, at: 2 },
    ],
    positions: defaultPositions(0),
    heroSeat: 0,
    players: defaultPlayers(0),
    expected: { minFoldFreq: 0.30 }, // T9s suited has implied odds vs 3bet; ~35% fold is reasonable
  },

  // 10. River with missed draw (should occasionally bluff as LAG)
  {
    name: 'Bluff: LAG missed flush draw on river',
    profileId: 'lag',
    heroCards: ['Ah', 'Kh'],
    board: ['3h', '8h', 'Qd', '5c', '2s'],
    street: 'RIVER',
    pot: 100,
    bigBlind: 10,
    legalActions: { canFold: false, canCheck: true, canCall: false, callAmount: 0, canRaise: true, minRaise: 10, maxRaise: 1000 },
    actions: [
      { seat: 0, street: 'PREFLOP', type: 'raise', amount: 25, at: 1 },
      { seat: 3, street: 'PREFLOP', type: 'call', amount: 25, at: 2 },
    ],
    positions: defaultPositions(0),
    heroSeat: 0,
    players: defaultPlayers(0),
    expected: { minRaiseFreq: 0.05 }, // LAG should bluff at least some
  },

  // 11. Donk guardrail: BB with top pair should NOT donk bet against PFA
  {
    name: 'Donk guard: BB top pair vs PFA on dry flop',
    profileId: 'gto_balanced',
    heroCards: ['Ts', '9s'],
    board: ['Tc', '7d', '3h'], // top pair weak kicker, dry board
    street: 'FLOP',
    pot: 50,
    bigBlind: 10,
    legalActions: { canFold: false, canCheck: true, canCall: false, callAmount: 0, canRaise: true, minRaise: 10, maxRaise: 1000 },
    actions: [
      { seat: 4, street: 'PREFLOP', type: 'raise', amount: 25, at: 1 }, // CO raises
      { seat: 2, street: 'PREFLOP', type: 'call', amount: 25, at: 2 }, // BB calls (hero)
    ],
    positions: { 0: 'BTN', 1: 'SB', 2: 'BB', 3: 'UTG', 4: 'CO', 5: 'MP' },
    heroSeat: 2,
    players: [
      { seat: 2, stack: 1000, inHand: true, folded: false },
      { seat: 4, stack: 1000, inHand: true, folded: false },
    ],
    expected: { maxRaiseFreq: 0.20 }, // donk guardrail should suppress raise to ~20% or below
  },

  // 12. Donk guardrail EXEMPT: BB with set should still lead
  {
    name: 'Donk guard exempt: BB set on dry flop',
    profileId: 'gto_balanced',
    heroCards: ['7s', '7h'],
    board: ['7c', 'Td', '3h'], // flopped set, strength ~0.95
    street: 'FLOP',
    pot: 50,
    bigBlind: 10,
    legalActions: { canFold: false, canCheck: true, canCall: false, callAmount: 0, canRaise: true, minRaise: 10, maxRaise: 1000 },
    actions: [
      { seat: 4, street: 'PREFLOP', type: 'raise', amount: 25, at: 1 }, // CO raises
      { seat: 2, street: 'PREFLOP', type: 'call', amount: 25, at: 2 }, // BB calls (hero)
    ],
    positions: { 0: 'BTN', 1: 'SB', 2: 'BB', 3: 'UTG', 4: 'CO', 5: 'MP' },
    heroSeat: 2,
    players: [
      { seat: 2, stack: 1000, inHand: true, folded: false },
      { seat: 4, stack: 1000, inHand: true, folded: false },
    ],
    expected: { minRaiseFreq: 0.30 }, // exempt from guardrail: set should bet often
  },

  // 13. Preflop chart: UTG with 72o should fold (GTO chart: fold 100%)
  {
    name: 'Preflop chart: UTG 72o should fold',
    profileId: 'gto_balanced',
    heroCards: ['7d', '2c'],
    board: [],
    street: 'PREFLOP',
    pot: 15,
    bigBlind: 10,
    legalActions: { canFold: true, canCheck: true, canCall: false, callAmount: 0, canRaise: true, minRaise: 20, maxRaise: 1000 },
    actions: [],
    positions: { 0: 'BTN', 1: 'SB', 2: 'BB', 3: 'UTG', 4: 'CO', 5: 'MP' },
    heroSeat: 3,
    players: defaultPlayers(3),
    expected: { maxRaiseFreq: 0.10 }, // GTO chart: pure fold; personality may add tiny raise
  },

  // 14. Preflop chart: BTN with A5s should open (GTO chart: raise 80%)
  {
    name: 'Preflop chart: BTN A5s should open',
    profileId: 'gto_balanced',
    heroCards: ['Ah', '5h'],
    board: [],
    street: 'PREFLOP',
    pot: 15,
    bigBlind: 10,
    legalActions: { canFold: true, canCheck: true, canCall: false, callAmount: 0, canRaise: true, minRaise: 20, maxRaise: 1000 },
    actions: [],
    positions: defaultPositions(0),
    heroSeat: 0,
    players: defaultPlayers(0),
    expected: { minRaiseFreq: 0.45 }, // GTO chart: raise 80%, personality may lower
  },

  // 15. Preflop chart: BB vs BTN open with KJo should not always fold
  {
    name: 'Preflop chart: BB KJo vs BTN open defends',
    profileId: 'gto_balanced',
    heroCards: ['Kd', 'Jc'],
    board: [],
    street: 'PREFLOP',
    pot: 40,
    bigBlind: 10,
    legalActions: { canFold: true, canCheck: false, canCall: true, callAmount: 25, canRaise: true, minRaise: 50, maxRaise: 1000 },
    actions: [
      { seat: 0, street: 'PREFLOP', type: 'raise', amount: 25, at: 1 }, // BTN opens
    ],
    positions: { 0: 'BTN', 1: 'SB', 2: 'BB', 3: 'UTG', 4: 'CO', 5: 'MP' },
    heroSeat: 2,
    players: [
      { seat: 0, stack: 1000, inHand: true, folded: false },
      { seat: 2, stack: 1000, inHand: true, folded: false },
    ],
    expected: { maxFoldFreq: 0.55 }, // GTO chart: call 65% + raise 15% = 80% defend
  },
];

// ===== Main runner =====
function main(): void {
  const iterations = parseInt(process.argv[2] ?? '1000', 10);
  console.log(`\n=== Bot Regression Test Suite ===`);
  console.log(`Running ${SCENARIOS.length} scenarios x ${iterations} iterations each\n`);

  let passed = 0;
  let failed = 0;
  const results: ScenarioResult[] = [];

  for (const scenario of SCENARIOS) {
    const result = runScenario(scenario, iterations);
    results.push(result);

    const status = result.passed ? 'PASS' : 'FAIL';
    const icon = result.passed ? '+' : 'X';
    console.log(`[${icon}] ${status} | ${result.scenario} (${result.profileId})`);
    console.log(`    Raise: ${(result.raiseFreq * 100).toFixed(1)}%  Call: ${(result.callFreq * 100).toFixed(1)}%  Fold: ${(result.foldFreq * 100).toFixed(1)}%${result.avgRaiseAmount > 0 ? `  AvgSize: ${result.avgRaiseAmount.toFixed(0)}` : ''}`);

    if (!result.passed) {
      for (const v of result.violations) {
        console.log(`    ! ${v}`);
      }
      failed++;
    } else {
      passed++;
    }
    console.log('');
  }

  console.log(`=== Results: ${passed} passed, ${failed} failed out of ${SCENARIOS.length} ===\n`);

  if (failed > 0) {
    process.exit(1);
  }
}

main();
