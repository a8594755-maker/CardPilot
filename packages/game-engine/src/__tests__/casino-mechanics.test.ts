import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { GameTable } from "../index.js";

function makeHeadsUpTable(params?: { ante?: number; rakePercent?: number; rakeCap?: number }) {
  const t = new GameTable({
    tableId: "casino",
    smallBlind: 50,
    bigBlind: 100,
    ante: params?.ante ?? 0,
    rakePercent: params?.rakePercent ?? 0,
    rakeCap: params?.rakeCap,
  });
  t.addPlayer({ seat: 1, userId: "u1", name: "Alice", stack: 1000 });
  t.addPlayer({ seat: 2, userId: "u2", name: "Bob", stack: 1000 });
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
      table.applyAction(state.actorSeat, "check");
    } else if (legal.canCall) {
      table.applyAction(state.actorSeat, "call");
    } else {
      table.applyAction(state.actorSeat, "fold");
    }
  }

  if (table.isRunoutPending()) {
    table.performRunout();
  }
}

describe("Casino mechanics", () => {
  it("collects ante from all active players before blinds", () => {
    const t = makeHeadsUpTable({ ante: 25 });
    t.startHand();
    const state = t.getPublicState();
    assert.equal(state.pot, 200, "pot should include antes + blinds (25+25+50+100)");
    const totalStacks = state.players.reduce((sum, player) => sum + player.stack, 0);
    assert.equal(totalStacks + state.pot, 2000, "chip conservation at hand start");
  });

  it("reveals showdown hands in public shownHands map", () => {
    const t = makeHeadsUpTable();
    t.startHand();
    playToShowdown(t);

    const state = t.getPublicState();
    const shownSeats = Object.keys(state.shownHands).map((key) => Number(key));
    assert.equal(shownSeats.length, 2, "all showdown contenders should be revealed");
    assert.ok(state.shownHands[1], "seat 1 should be shown");
    assert.ok(state.shownHands[2], "seat 2 should be shown");
  });

  it("deducts rake before payout and reports collectedFee", () => {
    const t = makeHeadsUpTable({ rakePercent: 10, rakeCap: 50 });
    t.startHand();

    let state = t.getPublicState();
    t.applyAction(state.actorSeat!, "all_in");
    state = t.getPublicState();
    if (state.actorSeat !== null) {
      t.applyAction(state.actorSeat, "all_in");
    }

    assert.ok(t.isRunoutPending(), "all-in runout should be pending");
    t.performRunout();

    const settlement = t.getSettlementResult();
    assert.ok(settlement, "settlement should exist");
    assert.equal(settlement!.totalPot, 2000);
    assert.equal(settlement!.collectedFee, 50, "fee should respect rake cap");
    assert.equal(settlement!.rake, 50, "rake alias should match collectedFee");
    assert.equal(settlement!.totalPaid, 1950, "payout should be pot minus fee");

    const sumStacks = t.getPublicState().players.reduce((sum, player) => sum + player.stack, 0);
    assert.equal(sumStacks + settlement!.collectedFee, 2000, "stack conservation with rake");
  });
});
