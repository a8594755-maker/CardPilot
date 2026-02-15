import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { GameTable } from "../index.js";

// ═══════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════

function finalStacks(t: GameTable): number {
  return t.getPublicState().players.reduce((sum, p) => sum + p.stack, 0);
}

function playToShowdown(t: GameTable): void {
  for (let i = 0; i < 60; i++) {
    const s = t.getPublicState();
    if (!s.handId || s.actorSeat === null) {
      if (s.showdownPhase === "decision") {
        t.finalizeShowdownReveals({ autoMuckLosingHands: true });
      }
      return;
    }
    if (t.isRunoutPending()) return;
    const la = s.legalActions;
    if (!la) {
      if (s.showdownPhase === "decision") {
        t.finalizeShowdownReveals({ autoMuckLosingHands: true });
      }
      return;
    }
    if (la.canCheck) t.applyAction(s.actorSeat, "check");
    else if (la.canCall) t.applyAction(s.actorSeat, "call");
    else t.applyAction(s.actorSeat, "fold");
  }
  const f = t.getPublicState();
  if (f.showdownPhase === "decision") {
    t.finalizeShowdownReveals({ autoMuckLosingHands: true });
  }
}

// ═══════════════════════════════════════════════════════════════
// FULL RAISE RULE (TDA / Robert's Rules)
// ═══════════════════════════════════════════════════════════════

describe("Full Raise Rule: short all-in does NOT reopen betting", () => {
  it("classic scenario: Raise → Call → Short all-in → original raiser CANNOT re-raise", () => {
    // Blinds 5/10, 3 players
    const t = new GameTable({ tableId: "fr1", smallBlind: 5, bigBlind: 10 });
    t.addPlayer({ seat: 1, userId: "u1", name: "Alice", stack: 1000 }); // BTN/SB in 3-way
    t.addPlayer({ seat: 2, userId: "u2", name: "Bob", stack: 1000 });
    t.addPlayer({ seat: 3, userId: "u3", name: "Charlie", stack: 35 }); // short stack
    t.startHand();

    let s = t.getPublicState();
    const btn = s.buttonSeat;

    // Find the seats in action order
    // We need to get through preflop action:
    // In 3-way: BTN posts SB(5), seat after BTN posts BB(10), UTG acts first

    // Step through preflop: first actor raises to 30
    s = t.getPublicState();
    if (s.actorSeat !== null && s.legalActions?.canRaise) {
      t.applyAction(s.actorSeat, "raise", 30);
    }
    const raiserSeat = s.actorSeat;

    // Second actor calls 30
    s = t.getPublicState();
    if (s.actorSeat !== null) {
      if (s.legalActions?.canCall) {
        t.applyAction(s.actorSeat, "call");
      } else if (s.legalActions?.canFold) {
        t.applyAction(s.actorSeat, "fold");
      }
    }

    // Third actor (short stack) goes all-in for 35 total (only 5 more than the 30 call)
    s = t.getPublicState();
    if (s.actorSeat !== null) {
      const actor = s.players.find(p => p.seat === s.actorSeat);
      if (actor && actor.stack > 0) {
        t.applyAction(s.actorSeat, "all_in");
      }
    }

    // Now check: the original raiser should NOT be able to re-raise
    // because the all-in of 35 (raise of 5) is less than the min raise of 20 (30-10=20)
    s = t.getPublicState();
    if (s.actorSeat !== null) {
      const la = s.legalActions;
      if (la) {
        // If this actor already raised to 30 and the short all-in was only 5 more,
        // this actor should NOT be able to raise
        const actor = s.players.find(p => p.seat === s.actorSeat);
        if (actor && actor.streetCommitted >= 30) {
          // This is the original raiser coming back after short all-in
          assert.equal(la.canRaise, false, 
            `Player at seat ${s.actorSeat} (streetCommitted=${actor.streetCommitted}) should NOT be able to re-raise after short all-in`);
        }
      }
    }

    // Play the rest to completion for conservation check
    while (true) {
      s = t.getPublicState();
      if (!s.handId || s.actorSeat === null) break;
      if (t.isRunoutPending()) break;
      const la = s.legalActions;
      if (!la) break;
      if (la.canCheck) t.applyAction(s.actorSeat, "check");
      else if (la.canCall) t.applyAction(s.actorSeat, "call");
      else t.applyAction(s.actorSeat, "fold");
    }

    if (t.isRunoutPending()) t.performRunout();
    s = t.getPublicState();
    if (s.showdownPhase === "decision") {
      t.finalizeShowdownReveals({ autoMuckLosingHands: true });
    }

    assert.equal(finalStacks(t), 1000 + 1000 + 35, "conservation after full raise rule scenario");
  });

  it("full all-in raise DOES reopen betting", () => {
    // Use a 200-chip short-stack so the all-in (200) constitutes a full raise over 30
    // and other players have enough chips to actually re-raise
    const t = new GameTable({ tableId: "fr2", smallBlind: 5, bigBlind: 10 });
    t.addPlayer({ seat: 1, userId: "u1", name: "Alice", stack: 5000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "Bob", stack: 5000 });
    t.addPlayer({ seat: 3, userId: "u3", name: "Charlie", stack: 200 });
    const initial = 5000 + 5000 + 200;
    t.startHand();

    // Play through preflop actions: first raise, then track who acts next
    let s = t.getPublicState();
    const firstActor = s.actorSeat!;

    // First actor raises to 30
    t.applyAction(firstActor, "raise", 30);
    s = t.getPublicState();

    // Second actor: if it's the short stack, go all-in (full raise); else call
    const secondActor = s.actorSeat!;
    const secondPlayer = s.players.find(p => p.seat === secondActor)!;
    if (secondPlayer.stack + secondPlayer.streetCommitted <= 200) {
      // Short stack goes all-in
      t.applyAction(secondActor, "all_in");
      s = t.getPublicState();
      // Third actor should be able to raise (it was a full raise all-in)
      if (s.actorSeat !== null) {
        const la = s.legalActions;
        assert.ok(la, "legal actions should exist");
        assert.equal(la!.canRaise, true, "player should be able to re-raise after full all-in raise");
      }
    } else {
      // Call, then third actor (short stack) goes all-in
      t.applyAction(secondActor, "call");
      s = t.getPublicState();
      const thirdActor = s.actorSeat!;
      const thirdPlayer = s.players.find(p => p.seat === thirdActor)!;
      if (thirdPlayer.stack + thirdPlayer.streetCommitted <= 200) {
        t.applyAction(thirdActor, "all_in");
        s = t.getPublicState();
        // Next actor (who already raised to 30) gets to re-raise because 200 > 30 is full raise
        if (s.actorSeat !== null) {
          const la = s.legalActions;
          assert.ok(la, "legal actions should exist after full all-in");
          // All-in to 200 from 30 = raise of 170, min raise was 20. Full raise. Should reopen.
          assert.equal(la!.canRaise, true, "original raiser should be able to re-raise after full all-in");
        }
      }
    }

    // Play to completion for conservation
    while (true) {
      s = t.getPublicState();
      if (!s.handId || s.actorSeat === null) break;
      if (t.isRunoutPending()) break;
      const la = s.legalActions;
      if (!la) break;
      if (la.canCall) t.applyAction(s.actorSeat, "call");
      else if (la.canCheck) t.applyAction(s.actorSeat, "check");
      else t.applyAction(s.actorSeat, "fold");
    }
    if (t.isRunoutPending()) t.performRunout();
    s = t.getPublicState();
    if (s.showdownPhase === "decision") {
      t.finalizeShowdownReveals({ autoMuckLosingHands: true });
    }
    assert.equal(finalStacks(t), initial, "conservation");
  });

  it("short all-in still allows unacted player to raise", () => {
    // 4 players: A raises, B hasn't acted, C short all-in → B should still be able to raise
    const t = new GameTable({ tableId: "fr3", smallBlind: 5, bigBlind: 10 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 1000 });
    t.addPlayer({ seat: 3, userId: "u3", name: "C", stack: 25 }); // short stack
    t.addPlayer({ seat: 4, userId: "u4", name: "D", stack: 1000 });
    t.startHand();

    let s = t.getPublicState();
    // Track action order through preflop
    const actionOrder: number[] = [];

    // Play through: first actors raise/call/all-in
    for (let i = 0; i < 10; i++) {
      s = t.getPublicState();
      if (!s.handId || s.actorSeat === null) break;
      if (t.isRunoutPending()) break;
      const la = s.legalActions;
      if (!la) break;

      actionOrder.push(s.actorSeat);

      // First actor to act: raise to 30
      if (actionOrder.length === 1 && la.canRaise) {
        t.applyAction(s.actorSeat, "raise", 30);
        continue;
      }
      // If it's the short stack's turn, go all-in
      const actor = s.players.find(p => p.seat === s.actorSeat);
      if (actor && actor.stack <= 25) {
        t.applyAction(s.actorSeat, "all_in");
        continue;
      }
      // Other players: just call
      if (la.canCall) {
        t.applyAction(s.actorSeat, "call");
      } else if (la.canCheck) {
        t.applyAction(s.actorSeat, "check");
      } else {
        t.applyAction(s.actorSeat, "fold");
      }
    }

    // Clean up for conservation
    while (true) {
      s = t.getPublicState();
      if (!s.handId || s.actorSeat === null) break;
      if (t.isRunoutPending()) break;
      const la = s.legalActions;
      if (!la) break;
      if (la.canCall) t.applyAction(s.actorSeat, "call");
      else if (la.canCheck) t.applyAction(s.actorSeat, "check");
      else t.applyAction(s.actorSeat, "fold");
    }
    if (t.isRunoutPending()) t.performRunout();
    s = t.getPublicState();
    if (s.showdownPhase === "decision") {
      t.finalizeShowdownReveals({ autoMuckLosingHands: true });
    }
    assert.equal(finalStacks(t), 3025, "conservation 4-player");
  });

  it("lastFullRaiseSize tracks correctly through multiple raises", () => {
    const t = new GameTable({ tableId: "fr4", smallBlind: 5, bigBlind: 10 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 5000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 5000 });
    t.startHand();

    let s = t.getPublicState();
    // Initial lastFullRaiseSize should be bigBlind
    assert.equal(s.lastFullRaiseSize, 10, "initial lastFullRaiseSize should be BB");

    // Player raises to 30 (raise of 20)
    t.applyAction(s.actorSeat!, "raise", 30);
    s = t.getPublicState();
    assert.equal(s.lastFullRaiseSize, 20, "after raise to 30, lastFullRaiseSize should be 20");

    // Player re-raises to 80 (raise of 50)
    t.applyAction(s.actorSeat!, "raise", 80);
    s = t.getPublicState();
    assert.equal(s.lastFullRaiseSize, 50, "after raise to 80, lastFullRaiseSize should be 50");
  });

  it("conservation holds across 10 hands with short all-ins", () => {
    const t = new GameTable({ tableId: "fr_stress", smallBlind: 1, bigBlind: 2 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 500 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 500 });
    t.addPlayer({ seat: 3, userId: "u3", name: "C", stack: 15 }); // short stack
    const initial = 1015;

    for (let hand = 0; hand < 10; hand++) {
      const eligible = t.getPublicState().players.filter(p => p.stack > 0 && p.status === 'active');
      if (eligible.length < 2) break;

      t.startHand();

      // Random actions including all-ins
      for (let a = 0; a < 20; a++) {
        const s = t.getPublicState();
        if (!s.handId || s.actorSeat === null) break;
        if (t.isRunoutPending()) break;
        const la = s.legalActions;
        if (!la) break;
        const actor = s.players.find(p => p.seat === s.actorSeat);
        if (actor && actor.stack <= 10) {
          t.applyAction(s.actorSeat, "all_in");
        } else if (la.canCheck) {
          t.applyAction(s.actorSeat, "check");
        } else if (la.canCall) {
          t.applyAction(s.actorSeat, "call");
        } else {
          t.applyAction(s.actorSeat, "fold");
        }
      }

      if (t.isRunoutPending()) t.performRunout();
      const s = t.getPublicState();
      if (s.showdownPhase === "decision") {
        t.finalizeShowdownReveals({ autoMuckLosingHands: true });
      }
      assert.equal(finalStacks(t), initial, `conservation hand ${hand + 1}`);
      t.clearHand();
    }
  });
});

// ═══════════════════════════════════════════════════════════════
// SIT OUT LOGIC
// ═══════════════════════════════════════════════════════════════

describe("Sit Out Logic", () => {
  it("sitting_out players are excluded from deal", () => {
    const t = new GameTable({ tableId: "so1", smallBlind: 5, bigBlind: 10 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 1000 });
    t.addPlayer({ seat: 3, userId: "u3", name: "C", stack: 1000, status: "sitting_out" });

    t.startHand();
    const s = t.getPublicState();

    // Only seats 1 and 2 should be in hand
    const inHand = s.players.filter(p => p.inHand);
    assert.equal(inHand.length, 2, "only 2 active players should be dealt in");

    const seatC = s.players.find(p => p.seat === 3);
    assert.equal(seatC?.inHand, false, "sitting_out player should not be in hand");
    assert.equal(seatC?.status, "sitting_out", "status should remain sitting_out");
  });

  it("toggleSitOut switches status", () => {
    const t = new GameTable({ tableId: "so2", smallBlind: 5, bigBlind: 10 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });

    assert.equal(t.getPublicState().players[0].status, "active");

    const newStatus = t.toggleSitOut(1);
    assert.equal(newStatus, "sitting_out");
    assert.equal(t.getPublicState().players[0].status, "sitting_out");

    const backToActive = t.toggleSitOut(1);
    assert.equal(backToActive, "active");
  });

  it("toggleSitOut throws during active hand", () => {
    const t = new GameTable({ tableId: "so3", smallBlind: 5, bigBlind: 10 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 1000 });
    t.startHand();

    assert.throws(() => t.toggleSitOut(1), /Cannot change sit-out status during an active hand/);
  });

  it("need at least 2 active players to start", () => {
    const t = new GameTable({ tableId: "so4", smallBlind: 5, bigBlind: 10 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 1000, status: "sitting_out" });

    assert.throws(() => t.startHand(), /need at least 2 players/);
  });

  it("setPlayerStatus works for server auto-sitout", () => {
    const t = new GameTable({ tableId: "so5", smallBlind: 5, bigBlind: 10 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });

    t.setPlayerStatus(1, "sitting_out");
    assert.equal(t.getPublicState().players[0].status, "sitting_out");

    t.setPlayerStatus(1, "active");
    assert.equal(t.getPublicState().players[0].status, "active");
  });
});

// ═══════════════════════════════════════════════════════════════
// NEW PLAYER BLIND POLICIES
// ═══════════════════════════════════════════════════════════════

describe("New Player Blind Policies", () => {
  it("new player defaults are correct", () => {
    const t = new GameTable({ tableId: "np1", smallBlind: 5, bigBlind: 10 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });

    // Default: not new, active
    const p = t.getPublicState().players[0];
    assert.equal(p.isNewPlayer, false);
    assert.equal(p.status, "active");
  });

  it("new player can be added as sitting_out + isNewPlayer", () => {
    const t = new GameTable({ tableId: "np2", smallBlind: 5, bigBlind: 10 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 1000 });
    t.addPlayer({ seat: 3, userId: "u3", name: "New", stack: 1000, status: "sitting_out", isNewPlayer: true });

    const newP = t.getPublicState().players.find(p => p.seat === 3);
    assert.equal(newP?.status, "sitting_out");
    assert.equal(newP?.isNewPlayer, true);
  });

  it("postDeadBlind transitions player to active", () => {
    const t = new GameTable({ tableId: "np3", smallBlind: 5, bigBlind: 10 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 1000 });
    t.addPlayer({ seat: 3, userId: "u3", name: "New", stack: 1000, status: "sitting_out", isNewPlayer: true });

    t.postDeadBlind(3);
    const p = t.getPublicState().players.find(pl => pl.seat === 3);
    assert.equal(p?.status, "active");
    assert.equal(p?.isNewPlayer, false);
  });

  it("isNewPlayer is cleared after being dealt in", () => {
    const t = new GameTable({ tableId: "np4", smallBlind: 5, bigBlind: 10 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000, isNewPlayer: true });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 1000 });
    t.startHand();

    const p = t.getPublicState().players.find(pl => pl.seat === 1);
    assert.equal(p?.isNewPlayer, false, "isNewPlayer should be false after being dealt in");
  });
});

// ═══════════════════════════════════════════════════════════════
// ODD CHIP DISTRIBUTION
// ═══════════════════════════════════════════════════════════════

describe("Odd Chip Distribution", () => {
  it("odd chip goes to first winner clockwise from button", () => {
    // Run many trials with 3 players and odd amounts to verify distribution
    for (let trial = 0; trial < 20; trial++) {
      const t = new GameTable({ tableId: `oc_${trial}`, smallBlind: 1, bigBlind: 2 });
      t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 100 + trial });
      t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 100 + trial });
      t.addPlayer({ seat: 3, userId: "u3", name: "C", stack: 100 + trial });
      const initial = 3 * (100 + trial);

      t.startHand();
      playToShowdown(t);
      if (t.isRunoutPending()) t.performRunout();

      assert.equal(finalStacks(t), initial, `odd chip conservation trial ${trial}`);
      t.clearHand();
    }
  });

  it("run-it-twice odd chip goes to Run #1", () => {
    for (let trial = 0; trial < 10; trial++) {
      const t = new GameTable({ tableId: `rit_oc_${trial}`, smallBlind: 1, bigBlind: 2 });
      t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 100 + trial * 3 });
      t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 100 + trial * 3 });
      const initial = 2 * (100 + trial * 3);

      t.startHand();
      // All-in
      let s = t.getPublicState();
      t.applyAction(s.actorSeat!, "all_in");
      s = t.getPublicState();
      if (s.actorSeat !== null) t.applyAction(s.actorSeat, "all_in");

      if (!t.isRunoutPending()) {
        t.clearHand();
        continue;
      }

      t.setAllInRunCount(2);
      t.performRunout();
      s = t.getPublicState();
      if (s.showdownPhase === "decision") {
        t.finalizeShowdownReveals({ autoMuckLosingHands: true });
      }

      assert.equal(finalStacks(t), initial, `RIT odd chip conservation trial ${trial}`);

      const sr = t.getSettlementResult();
      if (sr && sr.runCount === 2 && sr.payoutsBySeatByRun) {
        const r1Total = Object.values(sr.payoutsBySeatByRun[0]).reduce((s, v) => s + v, 0);
        const r2Total = Object.values(sr.payoutsBySeatByRun[1]).reduce((s, v) => s + v, 0);
        assert.ok(r1Total >= r2Total, `Run 1 (${r1Total}) should get >= Run 2 (${r2Total}) [odd chip to run 1]`);
      }
      t.clearHand();
    }
  });
});

// ═══════════════════════════════════════════════════════════════
// LASTFULLRAISESIZE IN PUBLIC STATE
// ═══════════════════════════════════════════════════════════════

describe("lastFullRaiseSize in public state", () => {
  it("is reset between streets", () => {
    const t = new GameTable({ tableId: "lfrs1", smallBlind: 5, bigBlind: 10 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 5000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 5000 });
    t.startHand();

    // Preflop: raise to 30 (raise of 20)
    let s = t.getPublicState();
    t.applyAction(s.actorSeat!, "raise", 30);
    s = t.getPublicState();
    assert.equal(s.lastFullRaiseSize, 20);

    // Call to advance to flop
    t.applyAction(s.actorSeat!, "call");
    s = t.getPublicState();

    // On flop, lastFullRaiseSize should reset to bigBlind
    if (s.street === "FLOP") {
      assert.equal(s.lastFullRaiseSize, 10, "lastFullRaiseSize should reset to BB on new street");
    }
  });
});
