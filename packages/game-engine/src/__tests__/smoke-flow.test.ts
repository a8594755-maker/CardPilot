import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { GameTable } from "../index.js";

function sumStacks(table: GameTable): number {
  return table.getPublicState().players.reduce((sum, player) => sum + player.stack, 0);
}

function advanceHand(table: GameTable): void {
  for (let i = 0; i < 80; i += 1) {
    const state = table.getPublicState();

    if (state.showdownPhase === "decision") {
      table.finalizeShowdownReveals({ autoMuckLosingHands: true });
      continue;
    }

    if (!state.handId || state.actorSeat == null) {
      return;
    }

    if (table.isRunoutPending()) {
      table.performRunout();
      continue;
    }

    const legal = state.legalActions;
    assert.ok(legal, "legal actions must be available while actor is set");

    if (legal.canCheck) {
      table.applyAction(state.actorSeat, "check");
      continue;
    }

    if (legal.canCall) {
      table.applyAction(state.actorSeat, "call");
      continue;
    }

    if (legal.canRaise) {
      table.applyAction(state.actorSeat, "raise", legal.minRaise);
      continue;
    }

    table.applyAction(state.actorSeat, "fold");
  }
}

describe("Smoke: hand lifecycle invariants", () => {
  it("runs one hand from start to settlement without breaking pot conservation", () => {
    const table = new GameTable({ tableId: "smoke", smallBlind: 50, bigBlind: 100 });
    table.addPlayer({ seat: 1, userId: "u1", name: "Alice", stack: 8_000 });
    table.addPlayer({ seat: 2, userId: "u2", name: "Bob", stack: 8_000 });
    table.addPlayer({ seat: 3, userId: "u3", name: "Carol", stack: 8_000 });

    const initialTotal = sumStacks(table);
    const { handId } = table.startHand();
    assert.ok(handId, "hand should start with a hand id");

    advanceHand(table);

    const after = table.getPublicState();
    if (after.showdownPhase === "decision") {
      table.finalizeShowdownReveals({ autoMuckLosingHands: true });
    }

    const finalState = table.getPublicState();
    const settlement = table.getSettlementResult();

    assert.ok(settlement, "settlement result should exist");
    assert.equal(finalState.pot, 0, "pot should be fully distributed");
    assert.equal(sumStacks(table), initialTotal, "chip conservation must hold");
    assert.equal(settlement!.totalPot, settlement!.totalPaid, "total paid should match total pot (no rake)");
  });
});
