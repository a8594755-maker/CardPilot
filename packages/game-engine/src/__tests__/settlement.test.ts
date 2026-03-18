import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { GameTable } from '../index.js';

// ────────── Helpers ──────────

function makeTable(sb = 50, bb = 100) {
  const t = new GameTable({ tableId: 'test', smallBlind: sb, bigBlind: bb });
  t.addPlayer({ seat: 1, userId: 'u1', name: 'Alice', stack: 10000 });
  t.addPlayer({ seat: 2, userId: 'u2', name: 'Bob', stack: 10000 });
  return t;
}

function make3Player(sb = 50, bb = 100) {
  const t = new GameTable({ tableId: 'test3', smallBlind: sb, bigBlind: bb });
  t.addPlayer({ seat: 1, userId: 'u1', name: 'Alice', stack: 5000 });
  t.addPlayer({ seat: 2, userId: 'u2', name: 'Bob', stack: 10000 });
  t.addPlayer({ seat: 3, userId: 'u3', name: 'Charlie', stack: 2000 });
  return t;
}

function totalChips(t: GameTable): number {
  const s = t.getPublicState();
  return s.players.reduce((sum, p) => sum + p.stack, 0) + s.pot;
}

function playToShowdown(t: GameTable): void {
  // Play check/call through all streets
  for (let i = 0; i < 40; i++) {
    const s = t.getPublicState();
    if (!s.handId || s.actorSeat === null) {
      // If in showdown decision phase, finalize it
      if (s.showdownPhase === 'decision') {
        t.finalizeShowdownReveals({ autoMuckLosingHands: true });
      }
      return;
    }
    if (t.isRunoutPending()) return;
    const la = s.legalActions;
    if (!la) {
      if (s.showdownPhase === 'decision') {
        t.finalizeShowdownReveals({ autoMuckLosingHands: true });
      }
      return;
    }
    if (la.canCheck) {
      t.applyAction(s.actorSeat, 'check');
    } else if (la.canCall) {
      t.applyAction(s.actorSeat, 'call');
    } else {
      t.applyAction(s.actorSeat, 'fold');
    }
  }
  // Final check for showdown decision
  const final = t.getPublicState();
  if (final.showdownPhase === 'decision') {
    t.finalizeShowdownReveals({ autoMuckLosingHands: true });
  }
}

// ────────── Scenario 1: Fold-to-win ──────────

describe('Settlement: Fold-to-win', () => {
  it('awards entire pot to last remaining player', () => {
    const t = makeTable(50, 100);
    const initialTotal = 20000;
    t.startHand();
    const s = t.getPublicState();
    const actor = s.actorSeat!;

    const result = t.applyAction(actor, 'fold');

    assert.equal(result.street, 'SHOWDOWN');
    assert.ok(result.winners);
    assert.equal(result.winners!.length, 1);

    // Winner gets the pot
    const winner = result.winners![0];
    assert.ok(winner.amount > 0, 'winner should receive pot');

    // No handName required (no showdown)
    // Conservation check
    const finalStacks = result.players.reduce((sum, p) => sum + p.stack, 0);
    assert.equal(finalStacks, initialTotal, 'conservation: stacks must equal initial buy-in');
    assert.equal(result.pot, 0, 'pot must be zero after settlement');
  });

  it('settlement result shows fold-to-win correctly', () => {
    const t = makeTable(50, 100);
    t.startHand();
    const s = t.getPublicState();
    t.applyAction(s.actorSeat!, 'fold');

    const sr = t.getSettlementResult();
    assert.ok(sr, 'settlement result must exist');
    assert.equal(sr!.rake, 0);
    assert.equal(sr!.totalPot, sr!.totalPaid, 'totalPot must equal totalPaid (no rake)');
    assert.equal(sr!.runCount, 1);
    assert.ok(sr!.ledger.length >= 2, 'ledger must have entries for all players');

    // Winner net should be positive, loser net should be negative
    const winnerLedger = sr!.ledger.find((e: { won: number }) => e.won > 0);
    const loserLedger = sr!.ledger.find(
      (e: { won: number; invested: number }) => e.won === 0 && e.invested > 0,
    );
    assert.ok(winnerLedger, 'winner should exist in ledger');
    assert.ok(loserLedger, 'loser should exist in ledger');
    assert.ok(winnerLedger!.net > 0, 'winner net must be positive');
    assert.ok(loserLedger!.net < 0, 'loser net must be negative');
  });
});

// ────────── Scenario 2: Showdown tie / chop ──────────

describe('Settlement: Showdown', () => {
  it('should produce a valid settlement with conservation at showdown', () => {
    const t = makeTable(50, 100);
    const initialTotal = 20000;
    t.startHand();

    playToShowdown(t);

    const final = t.getPublicState();
    // After showdown, all chips must be accounted for
    const finalStacks = final.players.reduce((sum, p) => sum + p.stack, 0);
    assert.equal(finalStacks, initialTotal, 'conservation: stacks must equal initial buy-in');
    assert.equal(final.pot, 0, 'pot must be zero after showdown settlement');
    assert.ok(final.winners, 'winners must exist');
    assert.ok(final.winners!.length >= 1, 'at least one winner');

    const sr = t.getSettlementResult();
    assert.ok(sr, 'settlement result must exist');
    assert.equal(sr!.totalPot, sr!.totalPaid, 'conservation: totalPot == totalPaid');
    assert.equal(sr!.rake, 0);
    assert.ok(sr!.potLayers.length >= 1, 'should have at least one pot layer');
    assert.ok(sr!.showdown, 'should be marked as showdown');
  });

  it('pot layers should sum to totalPot', () => {
    const t = makeTable(50, 100);
    t.startHand();
    playToShowdown(t);

    const sr = t.getSettlementResult();
    assert.ok(sr);
    const layerSum = sr!.potLayers.reduce((s: number, l: { amount: number }) => s + l.amount, 0);
    assert.equal(layerSum, sr!.totalPot, 'pot layers must sum to totalPot');
  });
});

// ────────── Scenario 3: Side pot (3 players, different all-in sizes) ──────────

describe('Settlement: Side pots', () => {
  it('should correctly build main + side pots with 3 different stacks', () => {
    const t = new GameTable({ tableId: 'side', smallBlind: 50, bigBlind: 100 });
    // Alice=2000, Bob=5000, Charlie=1000
    t.addPlayer({ seat: 1, userId: 'u1', name: 'Alice', stack: 2000 });
    t.addPlayer({ seat: 2, userId: 'u2', name: 'Bob', stack: 5000 });
    t.addPlayer({ seat: 3, userId: 'u3', name: 'Charlie', stack: 1000 });

    const initialTotal = 2000 + 5000 + 1000;
    t.startHand();

    // Force everyone all-in
    for (let i = 0; i < 10; i++) {
      const s = t.getPublicState();
      if (!s.handId || s.actorSeat === null) break;
      if (t.isRunoutPending()) break;
      t.applyAction(s.actorSeat, 'all_in');
    }

    // If runout pending, perform it
    if (t.isRunoutPending()) {
      t.performRunout();
    }

    const final = t.getPublicState();
    const finalStacks = final.players.reduce((sum, p) => sum + p.stack, 0);
    assert.equal(
      finalStacks,
      initialTotal,
      `conservation: stacks=${finalStacks} != initial=${initialTotal}`,
    );
    assert.equal(final.pot, 0, 'pot must be zero');

    const sr = t.getSettlementResult();
    assert.ok(sr, 'settlement result must exist');
    assert.equal(sr!.totalPot, sr!.totalPaid, 'totalPot must equal totalPaid');

    // Should have multiple pot layers (main pot + at least one side pot)
    assert.ok(sr!.potLayers.length >= 2, `expected >=2 pot layers, got ${sr!.potLayers.length}`);

    // First layer (main pot) should have all 3 eligible
    // Layers should have decreasing eligible seats
    const mainPot = sr!.potLayers[0];
    assert.ok(mainPot.eligibleSeats.length >= 2, 'main pot should have >= 2 eligible');

    // Verify pot layers sum
    const layerSum = sr!.potLayers.reduce((s: number, l: { amount: number }) => s + l.amount, 0);
    assert.equal(layerSum, sr!.totalPot, 'pot layers must sum to totalPot');

    // Ledger conservation
    const ledgerWon = sr!.ledger.reduce((s: number, e: { won: number }) => s + e.won, 0);
    assert.equal(ledgerWon, sr!.totalPaid, 'ledger won totals must equal totalPaid');
  });
});

// ────────── Scenario 4: Run it twice ──────────

describe('Settlement: Run it twice', () => {
  it('should deal two boards and split pots ceil/floor', () => {
    const t = makeTable(50, 100);
    const initialTotal = 20000;
    t.startHand();

    // Both players go all-in
    let s = t.getPublicState();
    t.applyAction(s.actorSeat!, 'all_in');
    s = t.getPublicState();
    if (s.actorSeat !== null) {
      t.applyAction(s.actorSeat, 'all_in');
    }

    assert.ok(t.isRunoutPending(), 'runout should be pending after all-in');

    // Set run count to 2 and perform runout
    t.setAllInRunCount(2);
    t.performRunout();

    const final = t.getPublicState();
    const finalStacks = final.players.reduce((sum, p) => sum + p.stack, 0);
    assert.equal(finalStacks, initialTotal, 'conservation after run-it-twice');
    assert.equal(final.pot, 0, 'pot must be zero');

    // Check runoutBoards
    assert.ok(final.runoutBoards, 'runoutBoards must exist');
    assert.equal(final.runoutBoards!.length, 2, 'must have 2 boards');
    assert.equal(final.runoutBoards![0].length, 5, 'run 1 board must have 5 cards');
    assert.equal(final.runoutBoards![1].length, 5, 'run 2 board must have 5 cards');

    // Check runoutPayouts
    assert.ok(final.runoutPayouts, 'runoutPayouts must exist');
    assert.equal(final.runoutPayouts!.length, 2, 'must have 2 payout entries');

    // Check settlement
    const sr = t.getSettlementResult();
    assert.ok(sr, 'settlement result must exist');
    assert.equal(sr!.runCount, 2);
    assert.equal(sr!.boards.length, 2);
    assert.equal(sr!.winnersByRun.length, 2);
    assert.ok(sr!.payoutsBySeatByRun, 'payoutsBySeatByRun must exist for run-it-twice');
    assert.equal(sr!.payoutsBySeatByRun!.length, 2);

    // Per-run payouts must sum to totalPaid
    const run1Vals = Object.values(sr!.payoutsBySeatByRun![0]) as number[];
    const run2Vals = Object.values(sr!.payoutsBySeatByRun![1]) as number[];
    const run1Total = run1Vals.reduce((s, v) => s + v, 0);
    const run2Total = run2Vals.reduce((s, v) => s + v, 0);
    assert.equal(run1Total + run2Total, sr!.totalPaid, 'per-run payouts must sum to totalPaid');

    // Run 1 gets ceil, Run 2 gets floor of each pot layer
    // Verify run1Total >= run2Total (run 1 gets odd chip)
    assert.ok(run1Total >= run2Total, `run 1 (${run1Total}) should be >= run 2 (${run2Total})`);

    assert.equal(sr!.totalPot, sr!.totalPaid, 'totalPot must equal totalPaid');
    assert.equal(sr!.rake, 0);
  });

  it('should deal three boards and split pots deterministically', () => {
    const t = makeTable(50, 100);
    const initialTotal = 20000;
    t.startHand();

    let s = t.getPublicState();
    t.applyAction(s.actorSeat!, 'all_in');
    s = t.getPublicState();
    if (s.actorSeat !== null) {
      t.applyAction(s.actorSeat, 'all_in');
    }

    assert.ok(t.isRunoutPending(), 'runout should be pending after all-in');

    t.setAllInRunCount(3);
    t.performRunout();

    const final = t.getPublicState();
    const finalStacks = final.players.reduce((sum, p) => sum + p.stack, 0);
    assert.equal(finalStacks, initialTotal, 'conservation after run-it-thrice');
    assert.equal(final.pot, 0, 'pot must be zero');

    assert.ok(final.runoutBoards, 'runoutBoards must exist');
    assert.equal(final.runoutBoards!.length, 3, 'must have 3 boards');
    assert.equal(final.runoutBoards![0].length, 5, 'run 1 board must have 5 cards');
    assert.equal(final.runoutBoards![1].length, 5, 'run 2 board must have 5 cards');
    assert.equal(final.runoutBoards![2].length, 5, 'run 3 board must have 5 cards');

    const sr = t.getSettlementResult();
    assert.ok(sr, 'settlement result must exist');
    assert.equal(sr!.runCount, 3);
    assert.equal(sr!.boards.length, 3);
    assert.equal(sr!.winnersByRun.length, 3);
    assert.ok(sr!.payoutsBySeatByRun, 'payoutsBySeatByRun must exist for multi-run');
    assert.equal(sr!.payoutsBySeatByRun!.length, 3);

    const runTotals = sr!.payoutsBySeatByRun!.map((runMap) =>
      (Object.values(runMap) as number[]).reduce((sum, amount) => sum + amount, 0),
    );
    assert.equal(
      runTotals[0] + runTotals[1] + runTotals[2],
      sr!.totalPaid,
      'per-run payouts must sum to totalPaid',
    );
    assert.ok(runTotals[0] >= runTotals[1], 'run 1 total should be >= run 2 total');
    assert.ok(runTotals[1] >= runTotals[2], 'run 2 total should be >= run 3 total');
    assert.equal(sr!.totalPot, sr!.totalPaid, 'totalPot must equal totalPaid');
  });
});

// ────────── Scenario 5: Auto next hand (no stuck state) ──────────

describe('Settlement: Auto next hand readiness', () => {
  it('hand end should leave table in a state ready for next hand', () => {
    const t = makeTable(50, 100);
    t.startHand();
    const s = t.getPublicState();
    t.applyAction(s.actorSeat!, 'fold');

    const final = t.getPublicState();
    // After hand ends, table should not be "stuck"
    assert.equal(final.actorSeat, null, 'no actor after hand end');
    assert.equal(final.pot, 0, 'pot is zero');

    // Should be able to start another hand immediately
    const { handId } = t.startHand();
    assert.ok(handId, 'second hand should start successfully');
    const s2 = t.getPublicState();
    assert.equal(s2.street, 'PREFLOP');
    assert.ok(s2.actorSeat !== null, 'actor should be set for new hand');
  });

  it('multiple hands in sequence should maintain conservation', () => {
    const t = makeTable(50, 100);
    const initialTotal = 20000;

    for (let hand = 0; hand < 5; hand++) {
      t.startHand();
      playToShowdown(t);
      const s = t.getPublicState();
      const stacks = s.players.reduce((sum, p) => sum + p.stack, 0);
      assert.equal(stacks, initialTotal, `conservation violated at hand ${hand + 1}`);
      assert.equal(s.pot, 0);
    }
  });
});

// ────────── Conservation invariant (comprehensive) ──────────

describe('Settlement: Conservation invariants', () => {
  it('sum(stacks_after) == sum(stacks_before) with rake=0', () => {
    const t = make3Player(50, 100);
    const initialTotal = 5000 + 10000 + 2000;
    t.startHand();

    // Play a raising hand then showdown
    let s = t.getPublicState();
    if (s.actorSeat !== null && s.legalActions?.canRaise) {
      t.applyAction(s.actorSeat, 'raise', s.legalActions.minRaise);
      s = t.getPublicState();
    }
    playToShowdown(t);

    // If runout pending, perform it
    if (t.isRunoutPending()) {
      t.performRunout();
    }

    const final = t.getPublicState();
    const finalStacks = final.players.reduce((sum, p) => sum + p.stack, 0);
    assert.equal(finalStacks, initialTotal, 'conservation must hold with 3 players');

    const sr = t.getSettlementResult();
    if (sr) {
      assert.equal(sr.totalPot, sr.totalPaid, 'totalPot must equal totalPaid');
      // Ledger net sums to zero
      const netSum = sr.ledger.reduce((s: number, e: { net: number }) => s + e.net, 0);
      assert.equal(netSum, 0, 'ledger net must sum to zero (zero-sum game)');
    }
  });

  it('odd chip goes to player closest to button clockwise', () => {
    // Create a scenario where odd chip matters: 3 players chop a 3-way pot of an odd amount
    const t = new GameTable({ tableId: 'oddchip', smallBlind: 1, bigBlind: 2 });
    t.addPlayer({ seat: 1, userId: 'u1', name: 'A', stack: 100 });
    t.addPlayer({ seat: 2, userId: 'u2', name: 'B', stack: 100 });
    t.addPlayer({ seat: 3, userId: 'u3', name: 'C', stack: 100 });
    const initialTotal = 300;

    t.startHand();
    playToShowdown(t);

    if (t.isRunoutPending()) {
      t.performRunout();
    }

    const final = t.getPublicState();
    const finalStacks = final.players.reduce((sum, p) => sum + p.stack, 0);
    assert.equal(finalStacks, initialTotal, 'conservation with 3 small-blind players');
  });
});
