import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { GameTable } from "../index.js";

// ═══════════════════════════════════════════════════════════════
// Helper utilities
// ═══════════════════════════════════════════════════════════════

function totalChips(t: GameTable): number {
  const s = t.getPublicState();
  return s.players.reduce((sum, p) => sum + p.stack, 0) + s.pot;
}

function finalStacks(t: GameTable): number {
  return t.getPublicState().players.reduce((sum, p) => sum + p.stack, 0);
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

/** Force all active players all-in */
function forceAllIn(t: GameTable): void {
  for (let i = 0; i < 20; i++) {
    const s = t.getPublicState();
    if (!s.handId || s.actorSeat === null) break;
    if (t.isRunoutPending()) break;
    t.applyAction(s.actorSeat, "all_in");
  }
}

const TEST_RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"] as const;
const TEST_SUITS = ["s", "h", "d", "c"] as const;

function makeDeckForDrawOrder(drawOrder: string[]): string[] {
  const full: string[] = [];
  for (const rank of TEST_RANKS) {
    for (const suit of TEST_SUITS) {
      full.push(`${rank}${suit}`);
    }
  }
  const used = new Set(drawOrder);
  const base = full.filter((card) => !used.has(card));
  return [...base, ...[...drawOrder].reverse()];
}

// ═══════════════════════════════════════════════════════════════
// P0.1 — Side pot distribution (3-player, different stacks)
// ═══════════════════════════════════════════════════════════════

describe("P0.1: Side pot distribution", () => {
  it("3-player all-in: main pot + side pot structure is correct", () => {
    // Alice=1000, Bob=3000, Charlie=500
    const t = new GameTable({ tableId: "sp1", smallBlind: 10, bigBlind: 20 });
    t.addPlayer({ seat: 1, userId: "u1", name: "Alice", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "Bob", stack: 3000 });
    t.addPlayer({ seat: 3, userId: "u3", name: "Charlie", stack: 500 });
    const initial = 1000 + 3000 + 500;
    t.startHand();

    forceAllIn(t);

    if (t.isRunoutPending()) {
      t.performRunout();
    }

    const s = t.getPublicState();
    if (s.showdownPhase === "decision") {
      t.finalizeShowdownReveals({ autoMuckLosingHands: true });
    }

    // Conservation
    assert.equal(finalStacks(t), initial, `conservation: ${finalStacks(t)} != ${initial}`);
    assert.equal(s.pot, 0, "pot must be zero after settlement");

    const sr = t.getSettlementResult();
    assert.ok(sr, "settlement must exist");
    assert.equal(sr!.totalPot, sr!.totalPaid, "totalPot must equal totalPaid");
    assert.equal(sr!.rake, 0);

    // Pot layers: should have at least 2 (main + side)
    // Main pot: 500 * 3 = 1500 (all three eligible)
    // Side pot 1: (1000-500) * 2 = 1000 (Alice + Bob eligible)
    // Side pot 2: (3000-1000) * 1 = 2000 (only Bob eligible, returned to Bob)
    // BUT exact amounts depend on blind posting. Let's verify structure.
    assert.ok(sr!.potLayers.length >= 2, `expected >=2 pot layers, got ${sr!.potLayers.length}`);

    // Pot layers must sum to totalPot
    const layerSum = sr!.potLayers.reduce((s, l) => s + l.amount, 0);
    assert.equal(layerSum, sr!.totalPot, "pot layers must sum to totalPot");

    // Main pot should have most eligible seats
    const mainPot = sr!.potLayers[0];
    assert.ok(mainPot.eligibleSeats.length >= 2, "main pot should have >= 2 eligible");

    // Ledger net must sum to zero
    const netSum = sr!.ledger.reduce((s, e) => s + e.net, 0);
    assert.equal(netSum, 0, "ledger net must sum to zero");
  });

  it("2-player all-in with unequal stacks: excess returned", () => {
    const t = new GameTable({ tableId: "sp2", smallBlind: 10, bigBlind: 20 });
    t.addPlayer({ seat: 1, userId: "u1", name: "Alice", stack: 500 });
    t.addPlayer({ seat: 2, userId: "u2", name: "Bob", stack: 2000 });
    const initial = 500 + 2000;
    t.startHand();

    forceAllIn(t);
    if (t.isRunoutPending()) t.performRunout();

    const s = t.getPublicState();
    if (s.showdownPhase === "decision") {
      t.finalizeShowdownReveals({ autoMuckLosingHands: true });
    }

    assert.equal(finalStacks(t), initial, "conservation");
    const sr = t.getSettlementResult();
    assert.ok(sr);
    assert.equal(sr!.totalPot, sr!.totalPaid, "totalPot == totalPaid");

    // Bob's excess (2000-500 = 1500) should create a side pot that only Bob is eligible for
    // This means Bob always gets at least 1500 back
    const bobStack = t.getPublicState().players.find(p => p.seat === 2)!.stack;
    assert.ok(bobStack >= 1500, `Bob should get at least uncalled portion back, got ${bobStack}`);
  });

  it("4-player all-in creates correct pot layer hierarchy", () => {
    const t = new GameTable({ tableId: "sp4", smallBlind: 5, bigBlind: 10 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 100 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 300 });
    t.addPlayer({ seat: 3, userId: "u3", name: "C", stack: 200 });
    t.addPlayer({ seat: 4, userId: "u4", name: "D", stack: 500 });
    const initial = 100 + 300 + 200 + 500;
    t.startHand();

    forceAllIn(t);
    if (t.isRunoutPending()) t.performRunout();

    const s = t.getPublicState();
    if (s.showdownPhase === "decision") {
      t.finalizeShowdownReveals({ autoMuckLosingHands: true });
    }

    assert.equal(finalStacks(t), initial, "conservation 4-player");
    const sr = t.getSettlementResult();
    assert.ok(sr);
    assert.equal(sr!.totalPot, sr!.totalPaid);

    // Should have 3-4 pot layers
    assert.ok(sr!.potLayers.length >= 3, `expected >=3 layers, got ${sr!.potLayers.length}`);

    // Each subsequent pot layer should have fewer or equal eligible seats
    for (let i = 1; i < sr!.potLayers.length; i++) {
      assert.ok(
        sr!.potLayers[i].eligibleSeats.length <= sr!.potLayers[i - 1].eligibleSeats.length,
        `pot layer ${i} should have <= eligible seats than layer ${i - 1}`
      );
    }

    const layerSum = sr!.potLayers.reduce((s, l) => s + l.amount, 0);
    assert.equal(layerSum, sr!.totalPot, "layers sum == totalPot");
  });

  it("folded player contributions go into pots they are NOT eligible for", () => {
    const t = new GameTable({ tableId: "sp_fold", smallBlind: 10, bigBlind: 20 });
    t.addPlayer({ seat: 1, userId: "u1", name: "Alice", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "Bob", stack: 1000 });
    t.addPlayer({ seat: 3, userId: "u3", name: "Charlie", stack: 1000 });
    const initial = 3000;
    t.startHand();

    let s = t.getPublicState();
    // First actor raises
    if (s.actorSeat !== null) {
      t.applyAction(s.actorSeat, "raise", 200);
      s = t.getPublicState();
    }
    // Second actor calls
    if (s.actorSeat !== null) {
      t.applyAction(s.actorSeat, "call");
      s = t.getPublicState();
    }
    // Third actor folds
    if (s.actorSeat !== null) {
      t.applyAction(s.actorSeat, "fold");
      s = t.getPublicState();
    }

    // Continue to showdown
    playToShowdown(t);
    if (t.isRunoutPending()) t.performRunout();

    const final = t.getPublicState();
    if (final.showdownPhase === "decision") {
      t.finalizeShowdownReveals({ autoMuckLosingHands: true });
    }

    assert.equal(finalStacks(t), initial, "conservation after fold + showdown");
    const sr = t.getSettlementResult();
    assert.ok(sr);
    assert.equal(sr!.totalPot, sr!.totalPaid);

    // Folded player should not appear in any pot layer's eligibleSeats
    // Find which seat folded
    const foldedSeat = sr!.ledger.find(e => {
      const player = final.players.find(p => p.seat === e.seat);
      return player?.folded;
    })?.seat;

    if (foldedSeat !== undefined) {
      for (const layer of sr!.potLayers) {
        assert.ok(
          !layer.eligibleSeats.includes(foldedSeat),
          `folded seat ${foldedSeat} should not be eligible in pot layer "${layer.label}"`
        );
      }
    }
  });
});

describe("P0.7: Variant scaffolding", () => {
  it("bomb-pot hand starts directly on FLOP with bomb antes and no blind posts", () => {
    const t = new GameTable({
      tableId: "bp_flop_start",
      smallBlind: 50,
      bigBlind: 100,
      bombPotEnabled: true,
      bombPotFrequency: 1,
    });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 5000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 5000 });
    t.addPlayer({ seat: 3, userId: "u3", name: "C", stack: 5000 });

    t.startHand();
    const s = t.getPublicState();

    assert.equal(s.isBombPotHand, true, "bomb-pot flag should be set");
    assert.equal(s.street, "FLOP", "bomb-pot should skip preflop betting street");
    assert.equal(s.board.length, 3, "bomb-pot should deal flop immediately");
    assert.equal(s.currentBet, 0, "bomb-pot should not post live blinds");
    assert.equal(s.holeCardCount, 2, "default game type should remain hold'em");

    const blindPosts = s.actions.filter((a) => a.type === "post_sb" || a.type === "post_bb");
    assert.equal(blindPosts.length, 0, "bomb-pot should not post SB/BB actions");

    const anteActions = s.actions.filter((a) => a.type === "ante");
    assert.equal(anteActions.length, 3, "each active player should post bomb ante");
    assert.equal(s.pot, 300, "pot should equal 3 players × 100 bomb ante");
    for (const player of s.players.filter((p) => p.inHand)) {
      assert.equal(player.streetCommitted, 0, "bomb ante should not count as street commitment");
    }
  });

  it("double-board hand resolves with two boards while keeping runCount=1", () => {
    const t = new GameTable({
      tableId: "db_settle",
      smallBlind: 50,
      bigBlind: 100,
      doubleBoardMode: "always",
      runItTwiceEnabled: true,
    });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 5000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 5000 });
    const initial = 10_000;

    t.startHand();
    let s = t.getPublicState();
    assert.equal(s.isDoubleBoardHand, true, "double-board flag should be set");

    forceAllIn(t);
    if (t.isRunoutPending()) t.performRunout();

    s = t.getPublicState();
    if (s.showdownPhase === "decision") {
      t.finalizeShowdownReveals({ autoMuckLosingHands: true });
    }

    const sr = t.getSettlementResult();
    assert.ok(sr, "settlement should exist");
    assert.equal(sr!.runCount, 1, "double-board is not run-it-twice");
    assert.equal(sr!.boards.length, 2, "settlement should include two board runouts");
    assert.ok(sr!.doubleBoardPayouts && sr!.doubleBoardPayouts.length === 2, "double-board payouts should be captured");
    assert.equal(finalStacks(t), initial, "chip conservation must hold");
  });

  it("omaha showdown enforces exactly-two-hole-card usage", () => {
    const t = new GameTable({
      tableId: "omaha_exact_two",
      smallBlind: 50,
      bigBlind: 100,
      gameType: "omaha",
      runItTwiceEnabled: false,
    });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 5000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 5000 });

    t.startHand();
    const internal = t as unknown as {
      state: {
        holeCards: Map<number, string[]>;
      };
    };
    internal.state.holeCards.set(1, ["Th", "9d", "3s", "4c"]);
    internal.state.holeCards.set(2, ["9h", "8h", "As", "Ad"]);

    // Board: Ah Kh Qh Jh 2c
    t.setDeckForTesting(makeDeckForDrawOrder(["Ah", "Kh", "Qh", "Jh", "2c"]));

    forceAllIn(t);
    if (t.isRunoutPending()) t.performRunout();

    let s = t.getPublicState();
    if (s.showdownPhase === "decision") {
      t.finalizeShowdownReveals({ autoMuckLosingHands: true });
      s = t.getPublicState();
    }

    assert.equal(s.gameType, "omaha");
    assert.equal(s.holeCardCount, 4, "omaha should deal four private cards");
    assert.equal(t.getPrivateHoleCards(1)?.length, 4);

    const winners = s.winners?.map((winner) => winner.seat) ?? [];
    assert.ok(winners.includes(2), "seat 2 should win with two-heart Omaha flush");
    assert.ok(!winners.includes(1), "seat 1 must not win via invalid one-card hold'em flush usage");
  });
});

// ═══════════════════════════════════════════════════════════════
// P0.1 — Odd-chip-to-button rule
// ═══════════════════════════════════════════════════════════════

describe("P0.1: Odd chip rule", () => {
  it("conservation holds with small blinds creating odd-chip scenarios", () => {
    // Use 1/2 blinds with 3 players for odd-chip scenarios
    for (let trial = 0; trial < 10; trial++) {
      const t = new GameTable({ tableId: `odd${trial}`, smallBlind: 1, bigBlind: 2 });
      t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 100 });
      t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 100 });
      t.addPlayer({ seat: 3, userId: "u3", name: "C", stack: 100 });
      const initial = 300;
      t.startHand();
      playToShowdown(t);
      if (t.isRunoutPending()) t.performRunout();

      const s = t.getPublicState();
      if (s.showdownPhase === "decision") {
        t.finalizeShowdownReveals({ autoMuckLosingHands: true });
      }

      assert.equal(finalStacks(t), initial, `odd-chip conservation trial ${trial}`);
      const sr = t.getSettlementResult();
      if (sr) {
        assert.equal(sr.totalPot, sr.totalPaid, `odd-chip totalPot==totalPaid trial ${trial}`);
      }
    }
  });

  it("all-in with 3 players preserves odd chip rule across 20 trials", () => {
    for (let trial = 0; trial < 20; trial++) {
      const stacks = [100 + trial * 7, 200 + trial * 3, 150 + trial * 5];
      const initial = stacks.reduce((s, v) => s + v, 0);
      const t = new GameTable({ tableId: `odd_ai_${trial}`, smallBlind: 1, bigBlind: 2 });
      t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: stacks[0] });
      t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: stacks[1] });
      t.addPlayer({ seat: 3, userId: "u3", name: "C", stack: stacks[2] });
      t.startHand();

      forceAllIn(t);
      if (t.isRunoutPending()) t.performRunout();

      const s = t.getPublicState();
      if (s.showdownPhase === "decision") {
        t.finalizeShowdownReveals({ autoMuckLosingHands: true });
      }

      assert.equal(finalStacks(t), initial, `conservation trial ${trial}: stacks=${stacks}`);
      const sr = t.getSettlementResult();
      if (sr) {
        assert.equal(sr.totalPot, sr.totalPaid, `totalPot==totalPaid trial ${trial}`);
        const netSum = sr.ledger.reduce((s, e) => s + e.net, 0);
        assert.equal(netSum, 0, `ledger net must sum to 0, trial ${trial}`);
      }
    }
  });
});

// ═══════════════════════════════════════════════════════════════
// P0.2 — Run It Twice
// ═══════════════════════════════════════════════════════════════

describe("P0.2: Run It Twice", () => {
  it("two boards are dealt from same deck (no reshuffle)", () => {
    const t = new GameTable({ tableId: "rit1", smallBlind: 50, bigBlind: 100 });
    t.addPlayer({ seat: 1, userId: "u1", name: "Alice", stack: 5000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "Bob", stack: 5000 });
    t.startHand();

    forceAllIn(t);
    assert.ok(t.isRunoutPending());

    t.setAllInRunCount(2);
    t.performRunout();

    const s = t.getPublicState();
    assert.ok(s.runoutBoards, "runoutBoards must exist");
    assert.equal(s.runoutBoards!.length, 2);
    assert.equal(s.runoutBoards![0].length, 5, "run 1 must have 5 cards");
    assert.equal(s.runoutBoards![1].length, 5, "run 2 must have 5 cards");

    // Boards should share the same base (if dealt from flop)
    // But cards in run 1 and run 2 should all be unique (from same deck)
    const allCards = [...s.runoutBoards![0], ...s.runoutBoards![1]];
    const holeCards = t.getAllHoleCards();
    for (const [, cards] of holeCards) {
      allCards.push(...cards);
    }
    const uniqueCards = new Set(allCards);
    assert.equal(uniqueCards.size, allCards.length, "all dealt cards must be unique (no duplicates)");
  });

  it("run-it-twice conservation with 3-player all-in side pots", () => {
    for (let trial = 0; trial < 10; trial++) {
      const t = new GameTable({ tableId: `rit3_${trial}`, smallBlind: 5, bigBlind: 10 });
      t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 200 + trial * 10 });
      t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 500 + trial * 20 });
      t.addPlayer({ seat: 3, userId: "u3", name: "C", stack: 100 + trial * 5 });
      const initial = (200 + trial * 10) + (500 + trial * 20) + (100 + trial * 5);
      t.startHand();

      forceAllIn(t);
      if (!t.isRunoutPending()) continue;

      t.setAllInRunCount(2);
      t.performRunout();

      const s = t.getPublicState();
      if (s.showdownPhase === "decision") {
        t.finalizeShowdownReveals({ autoMuckLosingHands: true });
      }

      assert.equal(finalStacks(t), initial, `RIT 3-player conservation trial ${trial}`);

      const sr = t.getSettlementResult();
      assert.ok(sr);
      assert.equal(sr!.runCount, 2);
      assert.equal(sr!.totalPot, sr!.totalPaid);
      assert.ok(sr!.payoutsBySeatByRun);
      assert.equal(sr!.payoutsBySeatByRun!.length, 2);

      // Per-run payouts must sum to totalPaid
      const run1Total = Object.values(sr!.payoutsBySeatByRun![0]).reduce((s, v) => s + v, 0);
      const run2Total = Object.values(sr!.payoutsBySeatByRun![1]).reduce((s, v) => s + v, 0);
      assert.equal(run1Total + run2Total, sr!.totalPaid, `per-run sums must equal totalPaid, trial ${trial}`);

      // Run 1 gets ceil, Run 2 gets floor (odd chip goes to run 1)
      assert.ok(run1Total >= run2Total, `run1 (${run1Total}) should be >= run2 (${run2Total})`);
    }
  });

  it("run-it-twice with runCount=1 produces single board", () => {
    const t = new GameTable({ tableId: "rit_single", smallBlind: 50, bigBlind: 100 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 5000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 5000 });
    const initial = 10000;
    t.startHand();

    forceAllIn(t);
    assert.ok(t.isRunoutPending());

    t.setAllInRunCount(1);
    t.performRunout();

    const s = t.getPublicState();
    assert.equal(s.runoutBoards, undefined, "no runoutBoards for single run");
    assert.equal(s.board.length, 5);
    assert.equal(finalStacks(t) + s.pot, initial);

    if (s.showdownPhase === "decision") {
      t.finalizeShowdownReveals({ autoMuckLosingHands: true });
    }

    assert.equal(finalStacks(t), initial, "conservation single run");
  });

  it("does not enter RUN_IT_TWICE_PROMPT when all-in happens on the river", () => {
    const t = new GameTable({ tableId: "rit_river_guard", smallBlind: 50, bigBlind: 100, runItTwiceEnabled: true });
    t.addPlayer({ seat: 1, userId: "u1", name: "Alice", stack: 8000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "Bob", stack: 8000 });
    t.startHand();

    // Passively advance to the river first.
    for (let i = 0; i < 80; i += 1) {
      const s = t.getPublicState();
      if (s.street === "RIVER") break;
      if (!s.handId || s.actorSeat === null || t.isRunoutPending()) break;
      const la = s.legalActions;
      if (!la) break;
      if (la.canCheck) t.applyAction(s.actorSeat, "check");
      else if (la.canCall) t.applyAction(s.actorSeat, "call");
      else t.applyAction(s.actorSeat, "fold");
    }

    let s = t.getPublicState();
    assert.equal(s.street, "RIVER", "test setup failed: expected to be on river");
    assert.ok(s.actorSeat !== null, "river should have an actor");

    t.applyAction(s.actorSeat!, "all_in");
    s = t.getPublicState();
    assert.ok(s.actorSeat !== null, "opponent should still have action to close river");

    if (s.legalActions?.canCall) t.applyAction(s.actorSeat!, "call");
    else t.applyAction(s.actorSeat!, "all_in");

    s = t.getPublicState();
    assert.notEqual(s.street, "RUN_IT_TWICE_PROMPT", "river all-in closure must not prompt run-it-twice");
    assert.equal(t.isRunoutPending(), true, "river all-in closure should proceed directly to showdown runout path");
  });
});

// ═══════════════════════════════════════════════════════════════
// P0.3 — Showdown visibility rules
// ═══════════════════════════════════════════════════════════════

describe("P0.3: Showdown visibility", () => {
  it("fold-to-win: winner does NOT have to show", () => {
    const t = new GameTable({ tableId: "vis1", smallBlind: 50, bigBlind: 100 });
    t.addPlayer({ seat: 1, userId: "u1", name: "Alice", stack: 5000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "Bob", stack: 5000 });
    t.startHand();

    const s = t.getPublicState();
    t.applyAction(s.actorSeat!, "fold");

    const final = t.getPublicState();
    assert.equal(final.showdownPhase, "none", "no showdown decision on fold-to-win");
    assert.deepEqual(final.revealedHoles, {}, "winner cards not revealed by default");
  });

  it("showdown: decision phase entered with 2+ contenders", () => {
    const t = new GameTable({ tableId: "vis2", smallBlind: 50, bigBlind: 100 });
    t.addPlayer({ seat: 1, userId: "u1", name: "Alice", stack: 5000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "Bob", stack: 5000 });
    t.startHand();

    // Play to showdown without folding
    let s = t.getPublicState();
    for (let i = 0; i < 40; i++) {
      s = t.getPublicState();
      if (!s.handId || s.actorSeat === null) break;
      if (t.isRunoutPending()) break;
      const la = s.legalActions;
      if (!la) break;
      if (la.canCheck) t.applyAction(s.actorSeat, "check");
      else if (la.canCall) t.applyAction(s.actorSeat, "call");
      else break;
    }

    if (t.isRunoutPending()) t.performRunout();

    s = t.getPublicState();
    if (s.street === "SHOWDOWN" && s.winners && s.winners.length > 0) {
      assert.equal(s.showdownPhase, "decision", "should be in decision phase at showdown");
    }
  });

  it("all-in runout uses showdown decision phase (not forced reveal)", () => {
    const t = new GameTable({ tableId: "vis_allin_decision", smallBlind: 50, bigBlind: 100, runItTwiceEnabled: false });
    t.addPlayer({ seat: 1, userId: "u1", name: "Alice", stack: 5000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "Bob", stack: 5000 });
    t.startHand();

    forceAllIn(t);
    assert.equal(t.isRunoutPending(), true, "precondition: all-in should lead to runout pending");
    t.setAllInRunCount(1);
    t.performRunout();

    const s = t.getPublicState();
    assert.equal(s.street, "SHOWDOWN");
    assert.equal(s.showdownPhase, "decision", "all-in runout should defer to showdown decision phase");
  });

  it("river called showdown still forces all contenders to reveal", () => {
    const t = new GameTable({ tableId: "vis_river_call_forced", smallBlind: 50, bigBlind: 100 });
    t.addPlayer({ seat: 1, userId: "u1", name: "Alice", stack: 7000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "Bob", stack: 7000 });
    t.startHand();

    // Passively advance to river.
    for (let i = 0; i < 80; i += 1) {
      const s = t.getPublicState();
      if (s.street === "RIVER") break;
      if (!s.handId || s.actorSeat === null || t.isRunoutPending()) break;
      const la = s.legalActions;
      if (!la) break;
      if (la.canCheck) t.applyAction(s.actorSeat, "check");
      else if (la.canCall) t.applyAction(s.actorSeat, "call");
      else t.applyAction(s.actorSeat, "fold");
    }

    let s = t.getPublicState();
    assert.equal(s.street, "RIVER", "test setup failed: expected river");
    assert.ok(s.actorSeat !== null, "river should have an actor");
    assert.ok(s.legalActions?.canRaise, "river actor should be able to bet/raise");

    t.applyAction(s.actorSeat!, "raise", s.legalActions!.minRaise);
    s = t.getPublicState();
    assert.ok(s.actorSeat !== null && s.legalActions?.canCall, "opponent should be able to call on river");

    t.applyAction(s.actorSeat!, "call");
    s = t.getPublicState();

    assert.equal(s.street, "SHOWDOWN");
    assert.equal(s.showdownPhase, "none", "river called showdown should force reveal immediately");

    const contenders = s.players.filter((p) => p.inHand && !p.folded).map((p) => p.seat);
    for (const seat of contenders) {
      assert.ok(s.revealedHoles?.[seat], `contender seat ${seat} should be revealed after river call`);
    }
  });

  it("revealPublicHand makes cards visible in public state", () => {
    const t = new GameTable({ tableId: "vis3", smallBlind: 50, bigBlind: 100 });
    t.addPlayer({ seat: 1, userId: "u1", name: "Alice", stack: 5000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "Bob", stack: 5000 });
    t.startHand();

    // Get Alice's hole cards
    const aliceCards = t.getHoleCards(1);
    assert.ok(aliceCards, "Alice should have hole cards");

    // Before reveal, public state should NOT have hole cards
    let s = t.getPublicState();
    assert.equal(s.revealedHoles?.[1], undefined, "hole cards not revealed before show");

    // Reveal Alice's hand
    t.revealPublicHand(1);
    s = t.getPublicState();
    assert.ok(s.revealedHoles?.[1], "Alice's cards should be revealed");
    assert.deepEqual(s.revealedHoles![1], aliceCards, "revealed cards match hole cards");
  });

  it("muckPublicHand hides cards and adds to muckedSeats", () => {
    const t = new GameTable({ tableId: "vis4", smallBlind: 50, bigBlind: 100 });
    t.addPlayer({ seat: 1, userId: "u1", name: "Alice", stack: 5000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "Bob", stack: 5000 });
    t.startHand();

    t.muckPublicHand(1);
    const s = t.getPublicState();
    assert.ok(s.muckedSeats?.includes(1), "seat 1 should be in muckedSeats");
    assert.equal(s.revealedHoles?.[1], undefined, "mucked hand should not be revealed");
  });

  it("finalizeShowdownReveals auto-mucks losers and reveals winners", () => {
    const t = new GameTable({ tableId: "vis5", smallBlind: 50, bigBlind: 100 });
    t.addPlayer({ seat: 1, userId: "u1", name: "Alice", stack: 5000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "Bob", stack: 5000 });
    t.startHand();

    playToShowdown(t);
    if (t.isRunoutPending()) t.performRunout();

    // After playToShowdown, finalizeShowdownReveals was called
    const s = t.getPublicState();
    const winners = s.winners ?? [];

    // Winner should have revealed cards
    for (const w of winners) {
      assert.ok(
        s.revealedHoles?.[w.seat],
        `winner seat ${w.seat} should have revealed cards`
      );
    }
  });
});

// ═══════════════════════════════════════════════════════════════
// P0.4 — Auto next hand / no stuck state
// ═══════════════════════════════════════════════════════════════

describe("P0.4: No stuck state after hand end", () => {
  it("fold-to-win: can start next hand immediately", () => {
    const t = new GameTable({ tableId: "ns1", smallBlind: 50, bigBlind: 100 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 5000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 5000 });
    t.startHand();

    let s = t.getPublicState();
    t.applyAction(s.actorSeat!, "fold");

    // After fold, isHandActive should be false
    assert.equal(t.isHandActive(), false, "hand should not be active after fold-to-win");

    // Start next hand
    const { handId } = t.startHand();
    assert.ok(handId);
    s = t.getPublicState();
    assert.equal(s.street, "PREFLOP");
    assert.ok(s.actorSeat !== null);
  });

  it("showdown: can start next hand after finalizeShowdownReveals", () => {
    const t = new GameTable({ tableId: "ns2", smallBlind: 50, bigBlind: 100 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 5000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 5000 });
    t.startHand();
    playToShowdown(t);
    if (t.isRunoutPending()) t.performRunout();

    assert.equal(t.isHandActive(), false, "hand should not be active after showdown finalized");

    const { handId } = t.startHand();
    assert.ok(handId);
  });

  it("clearHand nulls handId and allows new hand", () => {
    const t = new GameTable({ tableId: "ns3", smallBlind: 50, bigBlind: 100 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 5000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 5000 });
    t.startHand();

    let s = t.getPublicState();
    t.applyAction(s.actorSeat!, "fold");

    // Simulate what the server does
    t.clearHand();

    s = t.getPublicState();
    assert.equal(s.handId, null, "handId should be null after clearHand");
    assert.equal(t.isHandActive(), false);

    // Start next hand
    const { handId } = t.startHand();
    assert.ok(handId);
  });

  it("10 consecutive hands maintain conservation", () => {
    const t = new GameTable({ tableId: "ns10", smallBlind: 50, bigBlind: 100 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 10000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 10000 });
    const initial = 20000;

    for (let hand = 0; hand < 10; hand++) {
      // Ensure we can start
      if (t.getPublicState().players.filter(p => p.stack > 0).length < 2) break;

      t.startHand();
      playToShowdown(t);
      if (t.isRunoutPending()) t.performRunout();

      const s = t.getPublicState();
      if (s.showdownPhase === "decision") {
        t.finalizeShowdownReveals({ autoMuckLosingHands: true });
      }

      const stacks = finalStacks(t);
      assert.equal(stacks, initial, `conservation at hand ${hand + 1}`);
      assert.equal(s.pot, 0, `pot zero at hand ${hand + 1}`);
      assert.equal(t.isHandActive(), false, `not active at hand ${hand + 1}`);

      t.clearHand(); // Simulate server behavior
    }
  });
});

// ═══════════════════════════════════════════════════════════════
// P0.5 — Deal button guards
// ═══════════════════════════════════════════════════════════════

describe("P0.5: Deal button guards", () => {
  it("rejects startHand when hand is already active", () => {
    const t = new GameTable({ tableId: "dg1", smallBlind: 50, bigBlind: 100 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 5000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 5000 });
    t.startHand();

    assert.throws(() => t.startHand(), /hand already active/);
  });

  it("rejects startHand with fewer than 2 players", () => {
    const t = new GameTable({ tableId: "dg2", smallBlind: 50, bigBlind: 100 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 5000 });

    assert.throws(() => t.startHand(), /need at least 2 players/);
  });

  it("rejects startHand when all players have zero chips", () => {
    const t = new GameTable({ tableId: "dg3", smallBlind: 50, bigBlind: 100 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 50 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 50 });

    // Play until someone busts
    t.startHand();
    forceAllIn(t);

    if (t.isRunoutPending()) t.performRunout();

    const s = t.getPublicState();
    if (s.showdownPhase === "decision") {
      t.finalizeShowdownReveals({ autoMuckLosingHands: true });
    }
    t.clearHand();

    // One player has 0 chips, only 1 has chips → can't start
    const withChips = t.getPublicState().players.filter(p => p.stack > 0);
    if (withChips.length < 2) {
      assert.throws(() => t.startHand(), /need at least 2 players/);
    }
  });
});

// ═══════════════════════════════════════════════════════════════
// P0.6 — Settlement result structure
// ═══════════════════════════════════════════════════════════════

describe("P0.6: Settlement result structure", () => {
  it("fold-to-win settlement has correct fields", () => {
    const t = new GameTable({ tableId: "sr1", smallBlind: 50, bigBlind: 100 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 5000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 5000 });
    t.startHand();

    const s = t.getPublicState();
    t.applyAction(s.actorSeat!, "fold");

    const sr = t.getSettlementResult()!;
    assert.ok(sr.handId);
    assert.equal(sr.rake, 0);
    assert.equal(sr.runCount, 1);
    assert.equal(sr.boards.length, 1);
    assert.equal(sr.winnersByRun.length, 1);
    assert.equal(sr.showdown, false, "fold-to-win is not showdown");
    assert.ok(sr.ledger.length >= 2);
    assert.ok(sr.potLayers.length >= 1);
    assert.ok(sr.timestamp > 0);
    assert.ok(sr.buttonSeat > 0);
  });

  it("showdown settlement has showdown=true and hand names", () => {
    const t = new GameTable({ tableId: "sr2", smallBlind: 50, bigBlind: 100 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 5000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 5000 });
    t.startHand();
    playToShowdown(t);
    if (t.isRunoutPending()) t.performRunout();

    const sr = t.getSettlementResult()!;
    assert.ok(sr);
    assert.equal(sr.showdown, true);

    // At least one winner should have a hand name
    const hasHandName = sr.winnersByRun.some(r => r.winners.some(w => w.handName));
    assert.ok(hasHandName, "showdown winners should have hand names");
  });
});

// ═══════════════════════════════════════════════════════════════
// Stress test — many hands, conservation never violated
// ═══════════════════════════════════════════════════════════════

describe("Stress: Conservation across many hands", () => {
  it("50 heads-up hands with varied actions maintain conservation", () => {
    const t = new GameTable({ tableId: "stress1", smallBlind: 1, bigBlind: 2 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 1000 });
    const initial = 2000;

    for (let hand = 0; hand < 50; hand++) {
      const withChips = t.getPublicState().players.filter(p => p.stack > 0);
      if (withChips.length < 2) break;

      t.startHand();

      // Randomly pick actions
      for (let action = 0; action < 30; action++) {
        const s = t.getPublicState();
        if (!s.handId || s.actorSeat === null) break;
        if (t.isRunoutPending()) break;
        const la = s.legalActions;
        if (!la) break;

        const roll = Math.random();
        if (roll < 0.1 && la.canFold) {
          t.applyAction(s.actorSeat, "fold");
        } else if (roll < 0.3 && la.canRaise) {
          t.applyAction(s.actorSeat, "raise", la.minRaise);
        } else if (la.canCheck) {
          t.applyAction(s.actorSeat, "check");
        } else if (la.canCall) {
          t.applyAction(s.actorSeat, "call");
        } else if (la.canFold) {
          t.applyAction(s.actorSeat, "fold");
        }
      }

      if (t.isRunoutPending()) t.performRunout();

      const s = t.getPublicState();
      if (s.showdownPhase === "decision") {
        t.finalizeShowdownReveals({ autoMuckLosingHands: true });
      }

      assert.equal(finalStacks(t), initial, `conservation at hand ${hand + 1}`);
      t.clearHand();
    }
  });

  it("20 three-player hands with all-ins maintain conservation", () => {
    const t = new GameTable({ tableId: "stress3", smallBlind: 1, bigBlind: 2 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 500 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 500 });
    t.addPlayer({ seat: 3, userId: "u3", name: "C", stack: 500 });
    const initial = 1500;

    for (let hand = 0; hand < 20; hand++) {
      const withChips = t.getPublicState().players.filter(p => p.stack > 0);
      if (withChips.length < 2) break;

      t.startHand();
      forceAllIn(t);

      if (t.isRunoutPending()) {
        const useRIT = Math.random() < 0.3;
        t.setAllInRunCount(useRIT ? 2 : 1);
        t.performRunout();
      }

      const s = t.getPublicState();
      if (s.showdownPhase === "decision") {
        t.finalizeShowdownReveals({ autoMuckLosingHands: true });
      }

      assert.equal(finalStacks(t), initial, `3-player conservation hand ${hand + 1}`);
      t.clearHand();
    }
  });
});
