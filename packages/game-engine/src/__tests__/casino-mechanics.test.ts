import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { GameTable } from '../index.js';

function makeHeadsUpTable(params?: {
  ante?: number;
  rakeEnabled?: boolean;
  rakePercent?: number;
  rakeCap?: number;
}) {
  const t = new GameTable({
    tableId: 'casino',
    smallBlind: 50,
    bigBlind: 100,
    ante: params?.ante ?? 0,
    rakeEnabled: params?.rakeEnabled,
    rakePercent: params?.rakePercent ?? 0,
    rakeCap: params?.rakeCap,
  });
  t.addPlayer({ seat: 1, userId: 'u1', name: 'Alice', stack: 1000 });
  t.addPlayer({ seat: 2, userId: 'u2', name: 'Bob', stack: 1000 });
  return t;
}

function playToShowdown(table: GameTable): void {
  for (let i = 0; i < 40; i += 1) {
    const state = table.getPublicState();
    if (!state.handId || state.actorSeat === null) break;
    if (table.isRunoutPending()) {
      table.performRunout();
      break;
    }
    const legal = state.legalActions;
    if (!legal) break;
    if (legal.canCheck) {
      table.applyAction(state.actorSeat, 'check');
    } else if (legal.canCall) {
      table.applyAction(state.actorSeat, 'call');
    } else {
      table.applyAction(state.actorSeat, 'fold');
    }
  }

  if (table.isRunoutPending()) {
    table.performRunout();
  }
}

describe('Casino mechanics', () => {
  it('collects ante from all active players before blinds', () => {
    const t = makeHeadsUpTable({ ante: 25 });
    t.startHand();
    const state = t.getPublicState();
    assert.equal(state.pot, 200, 'pot should include antes + blinds (25+25+50+100)');
    const anteActions = state.actions.filter((action) => action.type === 'ante');
    assert.equal(anteActions.length, 2, 'all active players should post ante');
    assert.equal(
      anteActions.every((action) => action.amount === 25),
      true,
    );
    const firstBlindIdx = state.actions.findIndex(
      (action) => action.type === 'post_sb' || action.type === 'post_bb',
    );
    const lastAnteIdx = state.actions.reduce(
      (idx, action, i) => (action.type === 'ante' ? i : idx),
      -1,
    );
    assert.ok(firstBlindIdx > lastAnteIdx, 'ante actions must be logged before blind postings');
    const totalStacks = state.players.reduce((sum, player) => sum + player.stack, 0);
    assert.equal(totalStacks + state.pot, 2000, 'chip conservation at hand start');
  });

  it('reveals mandatory showdown hands while keeping non-mandatory losers private', () => {
    const t = makeHeadsUpTable();
    t.startHand();
    playToShowdown(t);

    const state = t.getPublicState();
    const shownSeats = Object.keys(state.shownCards).map((key) => Number(key));
    assert.equal(
      state.showdownPhase,
      'decision',
      'non-mandatory showdown should enter reveal decision state',
    );
    const winnerSeats = (state.winners ?? []).map((winner) => winner.seat);
    assert.ok(winnerSeats.length > 0, 'showdown should produce at least one winner');
    for (const winnerSeat of winnerSeats) {
      assert.ok(shownSeats.includes(winnerSeat), `winner seat ${winnerSeat} must be auto-revealed`);
    }
    assert.deepEqual(state.shownHands, state.shownCards, 'shownHands should mirror shownCards');
  });

  it('deducts rake before payout and reports collectedFee', () => {
    const t = makeHeadsUpTable({ rakePercent: 10, rakeCap: 50 });
    t.startHand();

    let state = t.getPublicState();
    t.applyAction(state.actorSeat!, 'all_in');
    state = t.getPublicState();
    if (state.actorSeat !== null) {
      t.applyAction(state.actorSeat, 'all_in');
    }

    assert.ok(t.isRunoutPending(), 'all-in runout should be pending');
    t.performRunout();

    const settlement = t.getSettlementResult();
    assert.ok(settlement, 'settlement should exist');
    assert.equal(settlement!.totalPot, 2000);
    assert.equal(settlement!.collectedFee, 50, 'fee should respect rake cap');
    assert.equal(settlement!.rake, 50, 'rake alias should match collectedFee');
    assert.equal(settlement!.totalPaid, 1950, 'payout should be pot minus fee');

    const sumStacks = t.getPublicState().players.reduce((sum, player) => sum + player.stack, 0);
    assert.equal(sumStacks + settlement!.collectedFee, 2000, 'stack conservation with rake');
  });

  it('skips rake when rakeEnabled is false', () => {
    const t = makeHeadsUpTable({ rakeEnabled: false, rakePercent: 10, rakeCap: 50 });
    t.startHand();

    let state = t.getPublicState();
    t.applyAction(state.actorSeat!, 'all_in');
    state = t.getPublicState();
    if (state.actorSeat !== null) {
      t.applyAction(state.actorSeat, 'all_in');
    }

    assert.ok(t.isRunoutPending(), 'all-in runout should be pending');
    t.performRunout();

    const settlement = t.getSettlementResult();
    assert.ok(settlement, 'settlement should exist');
    assert.equal(settlement!.totalPot, 2000);
    assert.equal(settlement!.collectedFee, 0, 'no rake should be collected when disabled');
    assert.equal(settlement!.totalPaid, 2000, 'full pot should be paid when rake is disabled');
  });
});
