import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { GameTable } from "../index.js";

// ═══════════════════════════════════════════════════════════════
// Helper utilities
// ═══════════════════════════════════════════════════════════════

function finalStacks(t: GameTable): number {
  return t.getPublicState().players.reduce((sum, p) => sum + p.stack, 0);
}

/** Force all active players all-in */
function forceAllIn(t: GameTable): void {
  for (let i = 0; i < 30; i++) {
    const s = t.getPublicState();
    if (!s.handId || s.actorSeat === null) break;
    if (t.isRunoutPending()) break;
    t.applyAction(s.actorSeat, "all_in");
  }
}

/** Play check/call to showdown, handling showdown decision phase */
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
    if (la.canCheck) {
      t.applyAction(s.actorSeat, "check");
    } else if (la.canCall) {
      t.applyAction(s.actorSeat, "call");
    } else {
      t.applyAction(s.actorSeat, "fold");
    }
  }
  const final = t.getPublicState();
  if (final.showdownPhase === "decision") {
    t.finalizeShowdownReveals({ autoMuckLosingHands: true });
  }
}

/** Settle a hand that has gone all-in: perform runout and finalize showdown */
function settleAllIn(t: GameTable): void {
  if (t.isRunoutPending()) {
    t.performRunout();
  }
  const s = t.getPublicState();
  if (s.showdownPhase === "decision") {
    t.finalizeShowdownReveals({ autoMuckLosingHands: true });
  }
}

// ═══════════════════════════════════════════════════════════════
// 1. Equal stack all-in — 3 players with identical stacks
// ═══════════════════════════════════════════════════════════════

describe("Side-pot edge: Equal stack all-in", () => {
  it("3 players all-in with same stack produces exactly 1 main pot of 300", () => {
    const t = new GameTable({ tableId: "eq_allin", smallBlind: 1, bigBlind: 2 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 100 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 100 });
    t.addPlayer({ seat: 3, userId: "u3", name: "C", stack: 100 });
    const initial = 300;
    t.startHand();

    forceAllIn(t);
    settleAllIn(t);

    assert.equal(finalStacks(t), initial, "conservation: all chips accounted for");

    const sr = t.getSettlementResult();
    assert.ok(sr, "settlement must exist");
    assert.equal(sr!.totalPot, initial, "totalPot must be all chips (300)");
    assert.equal(sr!.totalPot, sr!.totalPaid + sr!.collectedFee, "totalPot = totalPaid + rake");

    // All three players contributed the same amount, so there should be
    // exactly one pot layer (main pot) with all 3 eligible.
    // NOTE: blind posting means SB contributes differently per-street, but
    // total contributions are still 100 each, so one level.
    const layers = sr!.potLayers;
    // Verify all pot layers sum to totalPot
    const layerSum = layers.reduce((s, l) => s + l.amount, 0);
    assert.equal(layerSum, sr!.totalPot, "pot layers must sum to totalPot");

    // Since all stacks are equal (100), there should be no side pots —
    // just a single main pot. Every player contributes exactly 100.
    assert.equal(layers.length, 1, `expected exactly 1 pot layer (main pot), got ${layers.length}`);
    assert.equal(layers[0].eligibleSeats.length, 3, "main pot should have all 3 players eligible");
    assert.equal(layers[0].amount, initial, "main pot should be 300");

    // Ledger net must sum to zero
    const netSum = sr!.ledger.reduce((s, e) => s + e.net, 0);
    assert.equal(netSum, 0, "ledger net must sum to zero");
  });
});

// ═══════════════════════════════════════════════════════════════
// 2. Single all-in vs one caller — heads-up
// ═══════════════════════════════════════════════════════════════

describe("Side-pot edge: Single all-in vs one caller (heads-up)", () => {
  it("P1 all-in 100, P2 calls 100 → single pot 200", () => {
    const t = new GameTable({ tableId: "hu_allin", smallBlind: 1, bigBlind: 2 });
    t.addPlayer({ seat: 1, userId: "u1", name: "P1", stack: 100 });
    t.addPlayer({ seat: 2, userId: "u2", name: "P2", stack: 100 });
    const initial = 200;
    t.startHand();

    forceAllIn(t);
    settleAllIn(t);

    assert.equal(finalStacks(t), initial, "conservation: 200 total chips");

    const sr = t.getSettlementResult();
    assert.ok(sr, "settlement must exist");
    assert.equal(sr!.totalPot, initial, "totalPot must be 200");
    assert.equal(sr!.totalPot, sr!.totalPaid + sr!.collectedFee, "totalPot = totalPaid + rake");

    // Single pot layer: both players contribute 100
    const layers = sr!.potLayers;
    const layerSum = layers.reduce((s, l) => s + l.amount, 0);
    assert.equal(layerSum, sr!.totalPot, "pot layers must sum to totalPot");
    assert.equal(layers.length, 1, "expected exactly 1 pot layer");
    assert.equal(layers[0].eligibleSeats.length, 2, "both players eligible");

    // One player wins 200, the other gets 0
    const netSum = sr!.ledger.reduce((s, e) => s + e.net, 0);
    assert.equal(netSum, 0, "ledger net must sum to zero");
  });

  it("P1 all-in 100 vs P2 with 500 → excess 400 returned to P2", () => {
    const t = new GameTable({ tableId: "hu_unequal", smallBlind: 1, bigBlind: 2 });
    t.addPlayer({ seat: 1, userId: "u1", name: "P1", stack: 100 });
    t.addPlayer({ seat: 2, userId: "u2", name: "P2", stack: 500 });
    const initial = 600;
    t.startHand();

    forceAllIn(t);
    settleAllIn(t);

    assert.equal(finalStacks(t), initial, "conservation: 600 total chips");

    const sr = t.getSettlementResult();
    assert.ok(sr, "settlement must exist");

    // P2's excess (500-100 = 400) is uncalled, so P2 gets at least 400 back
    const p2Stack = t.getPublicState().players.find(p => p.seat === 2)!.stack;
    assert.ok(p2Stack >= 400, `P2 should get at least uncalled portion back, got ${p2Stack}`);

    const netSum = sr!.ledger.reduce((s, e) => s + e.net, 0);
    assert.equal(netSum, 0, "ledger net must sum to zero");
  });
});

// ═══════════════════════════════════════════════════════════════
// 3. All-in less than BB — micro-stack edge case
// ═══════════════════════════════════════════════════════════════

describe("Side-pot edge: All-in less than BB", () => {
  it("player with 5 chips (less than BB of 10) goes all-in, main pot capped correctly", () => {
    // P1 has only 5 chips (< BB of 10), P2 has 500, P3 has 500
    const t = new GameTable({ tableId: "micro_allin", smallBlind: 5, bigBlind: 10 });
    t.addPlayer({ seat: 1, userId: "u1", name: "Micro", stack: 5 });
    t.addPlayer({ seat: 2, userId: "u2", name: "Big1", stack: 500 });
    t.addPlayer({ seat: 3, userId: "u3", name: "Big2", stack: 500 });
    const initial = 1005;
    t.startHand();

    forceAllIn(t);
    settleAllIn(t);

    assert.equal(finalStacks(t), initial, "conservation: all chips accounted for");

    const sr = t.getSettlementResult();
    assert.ok(sr, "settlement must exist");
    assert.equal(sr!.totalPot, sr!.totalPaid + sr!.collectedFee, "totalPot = totalPaid + rake");

    // The micro player (seat 1) contributed 5 chips. The main pot should
    // include 5 from each of the 3 players = 15 max, and seat 1 is eligible.
    const layers = sr!.potLayers;
    assert.ok(layers.length >= 2, `expected >= 2 pot layers, got ${layers.length}`);

    // Main pot: smallest contributor level * number of participants
    const mainPot = layers[0];
    assert.ok(mainPot.eligibleSeats.includes(1), "micro player (seat 1) must be eligible for main pot");

    // Side pot(s) should NOT include seat 1
    for (let i = 1; i < layers.length; i++) {
      assert.ok(
        !layers[i].eligibleSeats.includes(1),
        `micro player (seat 1) should NOT be eligible for side pot ${i}`
      );
    }

    // Pot layers must sum to totalPot
    const layerSum = layers.reduce((s, l) => s + l.amount, 0);
    assert.equal(layerSum, sr!.totalPot, "pot layers must sum to totalPot");

    // Ledger conservation
    const netSum = sr!.ledger.reduce((s, e) => s + e.net, 0);
    assert.equal(netSum, 0, "ledger net must sum to zero");
  });

  it("player with 1 chip (extreme micro-stack) can go all-in", () => {
    const t = new GameTable({ tableId: "micro_1", smallBlind: 5, bigBlind: 10 });
    t.addPlayer({ seat: 1, userId: "u1", name: "OneChip", stack: 1 });
    t.addPlayer({ seat: 2, userId: "u2", name: "Normal", stack: 1000 });
    const initial = 1001;
    t.startHand();

    forceAllIn(t);
    settleAllIn(t);

    assert.equal(finalStacks(t), initial, "conservation");

    const sr = t.getSettlementResult();
    assert.ok(sr, "settlement must exist");
    assert.equal(sr!.totalPot, sr!.totalPaid + sr!.collectedFee, "totalPot = totalPaid + rake");

    const netSum = sr!.ledger.reduce((s, e) => s + e.net, 0);
    assert.equal(netSum, 0, "ledger net must sum to zero");
  });
});

// ═══════════════════════════════════════════════════════════════
// 4. 6-player cascading all-in — multiple side pot layers
// ═══════════════════════════════════════════════════════════════

describe("Side-pot edge: 6-player cascading all-in", () => {
  it("6 players with stacks 50,100,150,200,250,300 all-in → correct layer structure", () => {
    const t = new GameTable({ tableId: "cascade6", smallBlind: 1, bigBlind: 2 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 50 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 100 });
    t.addPlayer({ seat: 3, userId: "u3", name: "C", stack: 150 });
    t.addPlayer({ seat: 4, userId: "u4", name: "D", stack: 200 });
    t.addPlayer({ seat: 5, userId: "u5", name: "E", stack: 250 });
    t.addPlayer({ seat: 6, userId: "u6", name: "F", stack: 300 });
    const initial = 50 + 100 + 150 + 200 + 250 + 300; // 1050
    t.startHand();

    forceAllIn(t);
    settleAllIn(t);

    assert.equal(finalStacks(t), initial, `conservation: ${finalStacks(t)} != ${initial}`);

    const sr = t.getSettlementResult();
    assert.ok(sr, "settlement must exist");
    assert.equal(sr!.totalPot, sr!.totalPaid + sr!.collectedFee, "totalPot = totalPaid + rake");

    const layers = sr!.potLayers;
    // With 6 distinct contribution levels (50, 100, 150, 200, 250, 300),
    // we should get up to 6 pot layers. At minimum 5 side pot layers.
    assert.ok(layers.length >= 5, `expected >= 5 pot layers, got ${layers.length}`);

    // Each subsequent pot layer should have fewer or equal eligible seats
    for (let i = 1; i < layers.length; i++) {
      assert.ok(
        layers[i].eligibleSeats.length <= layers[i - 1].eligibleSeats.length,
        `pot layer ${i} (${layers[i].eligibleSeats.length} eligible) should have ` +
        `<= eligible seats than layer ${i - 1} (${layers[i - 1].eligibleSeats.length} eligible)`
      );
    }

    // The smallest-stack player (seat 1, 50 chips) should only be eligible
    // for the main pot (layer 0).
    assert.ok(layers[0].eligibleSeats.includes(1), "seat 1 must be eligible for main pot");
    for (let i = 1; i < layers.length; i++) {
      assert.ok(
        !layers[i].eligibleSeats.includes(1),
        `seat 1 (50 chips) should NOT be in side pot ${i}`
      );
    }

    // The largest-stack player (seat 6, 300 chips) should be eligible for all pots
    for (let i = 0; i < layers.length; i++) {
      assert.ok(
        layers[i].eligibleSeats.includes(6),
        `seat 6 (300 chips) should be eligible for pot layer ${i}`
      );
    }

    // Pot layers must sum to totalPot
    const layerSum = layers.reduce((s, l) => s + l.amount, 0);
    assert.equal(layerSum, sr!.totalPot, "pot layers must sum to totalPot");

    // Verify expected pot layer amounts:
    // Layer 0 (main pot): 50 * 6 = 300 (all 6 eligible)
    // Layer 1: (100-50) * 5 = 250 (seats 2-6 eligible)
    // Layer 2: (150-100) * 4 = 200 (seats 3-6 eligible)
    // Layer 3: (200-150) * 3 = 150 (seats 4-6 eligible)
    // Layer 4: (250-200) * 2 = 100 (seats 5-6 eligible)
    // Layer 5: (300-250) * 1 = 50 (seat 6 only eligible, returned)
    // Total = 300+250+200+150+100+50 = 1050
    const expectedAmounts = [300, 250, 200, 150, 100, 50];
    const expectedEligibleCounts = [6, 5, 4, 3, 2, 1];
    for (let i = 0; i < Math.min(layers.length, expectedAmounts.length); i++) {
      assert.equal(
        layers[i].amount, expectedAmounts[i],
        `pot layer ${i} amount: expected ${expectedAmounts[i]}, got ${layers[i].amount}`
      );
      assert.equal(
        layers[i].eligibleSeats.length, expectedEligibleCounts[i],
        `pot layer ${i} eligible count: expected ${expectedEligibleCounts[i]}, got ${layers[i].eligibleSeats.length}`
      );
    }

    // Ledger conservation
    const netSum = sr!.ledger.reduce((s, e) => s + e.net, 0);
    assert.equal(netSum, 0, "ledger net must sum to zero");
  });
});

// ═══════════════════════════════════════════════════════════════
// 5. Rake exceeds smallest side pot — no negative pot amounts
// ═══════════════════════════════════════════════════════════════

describe("Side-pot edge: Rake exceeds smallest side pot", () => {
  it("large rake does not produce negative pot amounts", () => {
    // Set up a scenario with a very small main pot and high rake.
    // P1 has 10 chips, P2 has 500 chips — 50% rake with no cap.
    // This means the main pot (10*2=20) after 50% rake = 10,
    // and the side pot is only P2's excess which gets returned.
    const t = new GameTable({
      tableId: "rake_exceed",
      smallBlind: 1,
      bigBlind: 2,
      rakePercent: 50,
      rakeCap: 0, // uncapped
    });
    t.addPlayer({ seat: 1, userId: "u1", name: "Small", stack: 10 });
    t.addPlayer({ seat: 2, userId: "u2", name: "Big", stack: 500 });
    const initial = 510;
    t.startHand();

    forceAllIn(t);
    settleAllIn(t);

    // With rake, conservation: stacks + collectedFee = initial
    const sr = t.getSettlementResult();
    assert.ok(sr, "settlement must exist");
    assert.equal(
      finalStacks(t) + sr!.collectedFee, initial,
      "conservation with rake: stacks + fee = initial"
    );

    // Verify NO pot layer has negative amount
    for (const layer of sr!.potLayers) {
      assert.ok(layer.amount >= 0, `pot layer "${layer.label}" has negative amount: ${layer.amount}`);
    }

    // Verify rake was collected correctly
    assert.ok(sr!.collectedFee > 0, "some rake should have been collected");
    assert.equal(sr!.totalPot, sr!.totalPaid + sr!.collectedFee, "totalPot = totalPaid + rake");

    // Ledger net should sum to negative of the rake (the house takes it)
    const netSum = sr!.ledger.reduce((s, e) => s + e.net, 0);
    assert.equal(netSum, -sr!.collectedFee, "ledger net must sum to negative of rake");
  });

  it("rake applied across multiple side pots does not leave negative layers", () => {
    // 3 players with small stacks and 30% rake
    const t = new GameTable({
      tableId: "rake_multi",
      smallBlind: 1,
      bigBlind: 2,
      rakePercent: 30,
      rakeCap: 0,
    });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 15 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 30 });
    t.addPlayer({ seat: 3, userId: "u3", name: "C", stack: 60 });
    const initial = 105;
    t.startHand();

    forceAllIn(t);
    settleAllIn(t);

    const sr = t.getSettlementResult();
    assert.ok(sr, "settlement must exist");
    assert.equal(
      finalStacks(t) + sr!.collectedFee, initial,
      "conservation with rake"
    );

    for (const layer of sr!.potLayers) {
      assert.ok(layer.amount >= 0, `layer "${layer.label}" amount must be >= 0, got ${layer.amount}`);
    }

    assert.equal(sr!.totalPot, sr!.totalPaid + sr!.collectedFee, "totalPot = totalPaid + rake");
  });
});

// ═══════════════════════════════════════════════════════════════
// 6. Folded player dead money — contributions go to correct pots
// ═══════════════════════════════════════════════════════════════

describe("Side-pot edge: Folded player dead money", () => {
  it("P1 raises then folds, P2 and P3 all-in for different amounts — P1 money in correct pots", () => {
    const t = new GameTable({ tableId: "fold_dead", smallBlind: 5, bigBlind: 10 });
    t.addPlayer({ seat: 1, userId: "u1", name: "Folder", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "Short", stack: 200 });
    t.addPlayer({ seat: 3, userId: "u3", name: "Deep", stack: 800 });
    const initial = 2000;
    t.startHand();

    // Drive the action: first actor raises, then we need to get P1 to fold
    // after having put money in. The exact order depends on positions.
    let s = t.getPublicState();

    // Step 1: Each player acts preflop. We want P1 to put chips in then fold later.
    // First, let's get through preflop with raises.
    // The preflop action order depends on button position.
    // Let's raise with whoever is first to act, then call with the next,
    // then raise bigger with the third, then fold with the first.
    const actions: Array<{ action: string; amount?: number }> = [];

    // Play through preflop: first actor raises
    if (s.actorSeat !== null && s.legalActions) {
      if (s.legalActions.canRaise) {
        t.applyAction(s.actorSeat, "raise", s.legalActions.minRaise);
      } else if (s.legalActions.canCall) {
        t.applyAction(s.actorSeat, "call");
      }
    }
    s = t.getPublicState();

    // Second actor calls or raises
    if (s.actorSeat !== null && s.legalActions) {
      if (s.legalActions.canCall) {
        t.applyAction(s.actorSeat, "call");
      }
    }
    s = t.getPublicState();

    // Third actor raises if able, or calls
    if (s.actorSeat !== null && s.legalActions) {
      if (s.legalActions.canRaise) {
        t.applyAction(s.actorSeat, "raise", s.legalActions.minRaise);
      } else if (s.legalActions.canCall) {
        t.applyAction(s.actorSeat, "call");
      }
    }
    s = t.getPublicState();

    // Now fold one player and have the remaining two go all-in
    if (s.actorSeat !== null && s.legalActions) {
      t.applyAction(s.actorSeat, "fold");
    }
    s = t.getPublicState();

    // Remaining two: one calls, other goes all-in
    if (s.actorSeat !== null && s.legalActions) {
      t.applyAction(s.actorSeat, "all_in");
    }
    s = t.getPublicState();

    if (s.actorSeat !== null && s.legalActions) {
      if (s.legalActions.canCall) {
        t.applyAction(s.actorSeat, "call");
      } else {
        t.applyAction(s.actorSeat, "all_in");
      }
    }

    // Play to completion
    playToShowdown(t);
    settleAllIn(t);

    assert.equal(finalStacks(t), initial, "conservation: all chips accounted for");

    const sr = t.getSettlementResult();
    assert.ok(sr, "settlement must exist");
    assert.equal(sr!.totalPot, sr!.totalPaid + sr!.collectedFee, "totalPot = totalPaid + rake");

    // Verify the folded player contributed money (dead money)
    const foldedEntry = sr!.ledger.find(e => {
      const player = t.getPublicState().players.find(p => p.seat === e.seat);
      return player?.folded;
    });
    // There should be at least one player who has invested > 0 and won 0
    const deadMoneyPlayer = sr!.ledger.find(e => e.invested > 0 && e.won === 0);
    assert.ok(deadMoneyPlayer, "there should be a player who contributed but won nothing (dead money)");
    assert.ok(deadMoneyPlayer!.net < 0, "folded player's net must be negative");

    // Folded player should NOT be eligible in any pot layer
    if (foldedEntry) {
      for (const layer of sr!.potLayers) {
        assert.ok(
          !layer.eligibleSeats.includes(foldedEntry.seat),
          `folded seat ${foldedEntry.seat} should not be eligible in "${layer.label}"`
        );
      }
    }

    // Pot layers must sum to totalPot
    const layerSum = sr!.potLayers.reduce((s, l) => s + l.amount, 0);
    assert.equal(layerSum, sr!.totalPot, "pot layers must sum to totalPot");

    // Ledger conservation
    const netSum = sr!.ledger.reduce((s, e) => s + e.net, 0);
    assert.equal(netSum, 0, "ledger net must sum to zero");
  });

  it("dead money from folded player included in pot total across 10 trials", () => {
    for (let trial = 0; trial < 10; trial++) {
      const t = new GameTable({ tableId: `fold_trial_${trial}`, smallBlind: 5, bigBlind: 10 });
      t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 500 });
      t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 300 });
      t.addPlayer({ seat: 3, userId: "u3", name: "C", stack: 700 });
      const initial = 1500;
      t.startHand();

      let s = t.getPublicState();
      // First actor raises
      if (s.actorSeat !== null && s.legalActions?.canRaise) {
        t.applyAction(s.actorSeat, "raise", s.legalActions.minRaise);
        s = t.getPublicState();
      }
      // Second actor calls
      if (s.actorSeat !== null && s.legalActions?.canCall) {
        t.applyAction(s.actorSeat, "call");
        s = t.getPublicState();
      }
      // Third actor folds (puts in dead money from blind posting or call)
      if (s.actorSeat !== null) {
        t.applyAction(s.actorSeat, "fold");
        s = t.getPublicState();
      }

      // Continue: remaining two go all-in or play to showdown
      forceAllIn(t);
      settleAllIn(t);

      assert.equal(finalStacks(t), initial, `conservation trial ${trial}`);
      const sr = t.getSettlementResult();
      assert.ok(sr, `settlement must exist, trial ${trial}`);
      assert.equal(sr!.totalPot, sr!.totalPaid + sr!.collectedFee, `totalPot == totalPaid+fee trial ${trial}`);

      const netSum = sr!.ledger.reduce((s, e) => s + e.net, 0);
      assert.equal(netSum, 0, `ledger net must sum to 0, trial ${trial}`);
    }
  });
});

// ═══════════════════════════════════════════════════════════════
// 7. Run-it-twice conservation with 3-way side pot
// ═══════════════════════════════════════════════════════════════

describe("Side-pot edge: Run-it-twice conservation with 3-way side pot", () => {
  it("10 random trials verify sum of ledger net = 0", () => {
    for (let trial = 0; trial < 10; trial++) {
      const t = new GameTable({ tableId: `rit_3way_${trial}`, smallBlind: 5, bigBlind: 10 });
      // Varying stack sizes to ensure different side pot structures
      t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 100 + trial * 15 });
      t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 300 + trial * 20 });
      t.addPlayer({ seat: 3, userId: "u3", name: "C", stack: 500 + trial * 10 });
      const initial = (100 + trial * 15) + (300 + trial * 20) + (500 + trial * 10);
      t.startHand();

      forceAllIn(t);

      if (!t.isRunoutPending()) {
        // If not pending (e.g., fold), skip this trial
        settleAllIn(t);
        assert.equal(finalStacks(t), initial, `conservation trial ${trial} (no RIT)`);
        continue;
      }

      // Run it twice
      t.setAllInRunCount(2);
      t.performRunout();

      const s = t.getPublicState();
      if (s.showdownPhase === "decision") {
        t.finalizeShowdownReveals({ autoMuckLosingHands: true });
      }

      assert.equal(finalStacks(t), initial, `RIT 3-way conservation trial ${trial}`);

      const sr = t.getSettlementResult();
      assert.ok(sr, `settlement must exist, trial ${trial}`);
      assert.equal(sr!.runCount, 2, `runCount must be 2, trial ${trial}`);
      assert.equal(sr!.totalPot, sr!.totalPaid + sr!.collectedFee, `totalPot == totalPaid+fee, trial ${trial}`);

      // Core assertion: ledger net sums to zero
      const netSum = sr!.ledger.reduce((s, e) => s + e.net, 0);
      assert.equal(netSum, 0, `ledger net must sum to 0, trial ${trial}`);

      // Per-run payouts must sum to totalPaid
      assert.ok(sr!.payoutsBySeatByRun, `payoutsBySeatByRun must exist, trial ${trial}`);
      assert.equal(sr!.payoutsBySeatByRun!.length, 2, `should have 2 runs, trial ${trial}`);
      const run1Total = Object.values(sr!.payoutsBySeatByRun![0]).reduce((s, v) => s + v, 0);
      const run2Total = Object.values(sr!.payoutsBySeatByRun![1]).reduce((s, v) => s + v, 0);
      assert.equal(
        run1Total + run2Total, sr!.totalPaid,
        `per-run sums must equal totalPaid, trial ${trial}`
      );

      // Run 1 gets ceil, Run 2 gets floor (odd chip to run 1)
      assert.ok(
        run1Total >= run2Total,
        `run1 (${run1Total}) should be >= run2 (${run2Total}), trial ${trial}`
      );

      // Pot layers have correct structure
      const layers = sr!.potLayers;
      assert.ok(layers.length >= 2, `expected >= 2 pot layers with varying stacks, trial ${trial}`);
      for (let i = 1; i < layers.length; i++) {
        assert.ok(
          layers[i].eligibleSeats.length <= layers[i - 1].eligibleSeats.length,
          `layer ${i} eligible count should decrease, trial ${trial}`
        );
      }
    }
  });

  it("run-it-thrice with 3-way side pot also preserves conservation", () => {
    for (let trial = 0; trial < 5; trial++) {
      const t = new GameTable({ tableId: `rit3x_${trial}`, smallBlind: 5, bigBlind: 10 });
      t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 80 + trial * 10 });
      t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 200 + trial * 30 });
      t.addPlayer({ seat: 3, userId: "u3", name: "C", stack: 400 + trial * 20 });
      const initial = (80 + trial * 10) + (200 + trial * 30) + (400 + trial * 20);
      t.startHand();

      forceAllIn(t);

      if (!t.isRunoutPending()) {
        settleAllIn(t);
        assert.equal(finalStacks(t), initial, `conservation trial ${trial}`);
        continue;
      }

      t.setAllInRunCount(3);
      t.performRunout();

      const s = t.getPublicState();
      if (s.showdownPhase === "decision") {
        t.finalizeShowdownReveals({ autoMuckLosingHands: true });
      }

      assert.equal(finalStacks(t), initial, `RIT thrice conservation trial ${trial}`);

      const sr = t.getSettlementResult();
      assert.ok(sr, `settlement must exist, trial ${trial}`);
      assert.equal(sr!.runCount, 3);

      const netSum = sr!.ledger.reduce((s, e) => s + e.net, 0);
      assert.equal(netSum, 0, `ledger net must sum to 0, trial ${trial}`);
    }
  });
});

// ═══════════════════════════════════════════════════════════════
// 8. Double-board + side pot — each pot split 50/50 between boards
// ═══════════════════════════════════════════════════════════════

describe("Side-pot edge: Double-board + side pot", () => {
  it("double-board splits each side pot 50/50 between two boards", () => {
    const t = new GameTable({
      tableId: "db_side",
      smallBlind: 5,
      bigBlind: 10,
      doubleBoardMode: "always",
    });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 200 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 500 });
    t.addPlayer({ seat: 3, userId: "u3", name: "C", stack: 100 });
    const initial = 800;
    t.startHand();

    const s = t.getPublicState();
    assert.equal(s.isDoubleBoardHand, true, "double-board flag should be set");

    forceAllIn(t);
    settleAllIn(t);

    assert.equal(finalStacks(t), initial, "conservation with double-board");

    const sr = t.getSettlementResult();
    assert.ok(sr, "settlement must exist");
    assert.equal(sr!.totalPot, sr!.totalPaid + sr!.collectedFee, "totalPot = totalPaid + rake");

    // Double-board payouts should exist with exactly 2 boards
    assert.ok(sr!.doubleBoardPayouts, "doubleBoardPayouts must exist");
    assert.equal(sr!.doubleBoardPayouts!.length, 2, "should have exactly 2 board payouts");

    // Board 1 and Board 2 should have different boards
    const board1 = sr!.doubleBoardPayouts![0].board;
    const board2 = sr!.doubleBoardPayouts![1].board;
    assert.equal(board1.length, 5, "board 1 must have 5 cards");
    assert.equal(board2.length, 5, "board 2 must have 5 cards");

    // The total paid across both boards should equal totalPaid
    const board1Paid = sr!.doubleBoardPayouts![0].winners.reduce((s, w) => s + w.amount, 0);
    const board2Paid = sr!.doubleBoardPayouts![1].winners.reduce((s, w) => s + w.amount, 0);
    assert.equal(
      board1Paid + board2Paid, sr!.totalPaid,
      "sum of both board payouts must equal totalPaid"
    );

    // Board 1 gets ceil, Board 2 gets floor for each pot layer
    // So board1Paid >= board2Paid overall
    assert.ok(
      board1Paid >= board2Paid,
      `board 1 total (${board1Paid}) should be >= board 2 total (${board2Paid})`
    );

    // Ledger conservation
    const netSum = sr!.ledger.reduce((s, e) => s + e.net, 0);
    assert.equal(netSum, 0, "ledger net must sum to zero");

    // Pot layers structure should still be valid
    const layers = sr!.potLayers;
    assert.ok(layers.length >= 2, "should have >= 2 pot layers with different stacks");
    const layerSum = layers.reduce((s, l) => s + l.amount, 0);
    assert.equal(layerSum, sr!.totalPot, "pot layers must sum to totalPot");
  });

  it("double-board with equal stacks: conservation across 10 trials", () => {
    for (let trial = 0; trial < 10; trial++) {
      const t = new GameTable({
        tableId: `db_eq_${trial}`,
        smallBlind: 5,
        bigBlind: 10,
        doubleBoardMode: "always",
      });
      t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 500 });
      t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 500 });
      const initial = 1000;
      t.startHand();

      assert.equal(t.getPublicState().isDoubleBoardHand, true, "double-board flag");

      forceAllIn(t);
      settleAllIn(t);

      assert.equal(finalStacks(t), initial, `double-board conservation trial ${trial}`);

      const sr = t.getSettlementResult();
      assert.ok(sr, `settlement must exist, trial ${trial}`);
      assert.ok(sr!.doubleBoardPayouts, `doubleBoardPayouts must exist, trial ${trial}`);
      assert.equal(sr!.doubleBoardPayouts!.length, 2, `2 boards, trial ${trial}`);

      const b1Paid = sr!.doubleBoardPayouts![0].winners.reduce((s, w) => s + w.amount, 0);
      const b2Paid = sr!.doubleBoardPayouts![1].winners.reduce((s, w) => s + w.amount, 0);
      assert.equal(
        b1Paid + b2Paid, sr!.totalPaid,
        `board payouts must sum to totalPaid, trial ${trial}`
      );

      const netSum = sr!.ledger.reduce((s, e) => s + e.net, 0);
      assert.equal(netSum, 0, `ledger net must sum to 0, trial ${trial}`);
    }
  });

  it("double-board + 3-way side pot: no chips lost or duplicated", () => {
    for (let trial = 0; trial < 5; trial++) {
      const t = new GameTable({
        tableId: `db_3way_${trial}`,
        smallBlind: 5,
        bigBlind: 10,
        doubleBoardMode: "always",
      });
      t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 50 + trial * 10 });
      t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 200 + trial * 30 });
      t.addPlayer({ seat: 3, userId: "u3", name: "C", stack: 400 + trial * 20 });
      const initial = (50 + trial * 10) + (200 + trial * 30) + (400 + trial * 20);
      t.startHand();

      forceAllIn(t);
      settleAllIn(t);

      assert.equal(finalStacks(t), initial, `DB 3-way conservation trial ${trial}`);

      const sr = t.getSettlementResult();
      assert.ok(sr, `settlement must exist, trial ${trial}`);
      assert.equal(sr!.totalPot, sr!.totalPaid + sr!.collectedFee, `totalPot == totalPaid+fee, trial ${trial}`);

      const netSum = sr!.ledger.reduce((s, e) => s + e.net, 0);
      assert.equal(netSum, 0, `ledger net must sum to 0, trial ${trial}`);
    }
  });
});
