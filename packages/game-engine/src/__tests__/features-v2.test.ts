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

function playToShowdown(t: GameTable): void {
  for (let i = 0; i < 60; i++) {
    const s = t.getPublicState();
    if (s.street === "SHOWDOWN") return;
    if (s.showdownPhase === "decision") {
      // showdown decision phase — just return, engine will finalize
      return;
    }
    if (s.actorSeat == null) return;
    const legal = s.legalActions;
    if (!legal) return;
    if (legal.canCheck) {
      t.applyAction(s.actorSeat, "check");
    } else if (legal.canCall) {
      t.applyAction(s.actorSeat, "call");
    } else {
      t.applyAction(s.actorSeat, "fold");
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// A) BOMB POT — TRIGGER MODES
// ═══════════════════════════════════════════════════════════════

describe("Bomb Pot Trigger Modes", () => {
  it("frequency mode: triggers every N hands", () => {
    const t = new GameTable({
      tableId: "bp_freq",
      smallBlind: 1,
      bigBlind: 2,
      bombPotEnabled: true,
      bombPotTriggerMode: "frequency",
      bombPotFrequency: 3,
    });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 1000 });

    // Hand 1: not bomb pot (counter=1, 1%3≠0)
    // But we need to clear hands between starts
    const results: boolean[] = [];
    for (let i = 0; i < 6; i++) {
      t.startHand();
      const s = t.getPublicState();
      results.push(!!s.isBombPotHand);
      playToShowdown(t);
      t.clearHand();
    }
    // handCounter: 1,2,3,4,5,6 → bomb at 3,6
    assert.deepEqual(results, [false, false, true, false, false, true],
      "bomb pot should trigger every 3rd hand");
  });

  it("probability mode: deterministic seeded RNG (same seed → same result)", () => {
    // Two tables with same tableId should produce same bomb pot decisions
    const makeTable = () => {
      const t = new GameTable({
        tableId: "bp_prob_seed",
        smallBlind: 1,
        bigBlind: 2,
        bombPotEnabled: true,
        bombPotTriggerMode: "probability",
        bombPotProbability: 50,
      });
      t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 10000 });
      t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 10000 });
      return t;
    };

    const t1 = makeTable();
    const t2 = makeTable();
    const results1: boolean[] = [];
    const results2: boolean[] = [];

    for (let i = 0; i < 10; i++) {
      t1.startHand();
      results1.push(!!t1.getPublicState().isBombPotHand);
      playToShowdown(t1);
      t1.clearHand();

      t2.startHand();
      results2.push(!!t2.getPublicState().isBombPotHand);
      playToShowdown(t2);
      t2.clearHand();
    }

    assert.deepEqual(results1, results2,
      "same tableId + same handCounter should produce identical bomb pot decisions");
  });

  it("manual mode: only triggers when forceNextBombPot is set", () => {
    const t = new GameTable({
      tableId: "bp_manual",
      smallBlind: 1,
      bigBlind: 2,
      bombPotEnabled: true,
      bombPotTriggerMode: "manual",
    });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 1000 });

    // Hand 1: not bomb pot
    t.startHand();
    assert.equal(t.getPublicState().isBombPotHand, false, "manual mode should not auto-trigger");
    playToShowdown(t);
    t.clearHand();

    // Queue bomb pot
    t.queueBombPotNextHand();
    assert.equal(t.isBombPotQueued(), true, "should be queued");

    // Hand 2: bomb pot
    t.startHand();
    assert.equal(t.getPublicState().isBombPotHand, true, "queued bomb pot should trigger");
    assert.equal(t.isBombPotQueued(), false, "queue should reset after use");
    playToShowdown(t);
    t.clearHand();

    // Hand 3: not bomb pot (queue was consumed)
    t.startHand();
    assert.equal(t.getPublicState().isBombPotHand, false, "should not trigger again without re-queue");
    playToShowdown(t);
    t.clearHand();
  });

  it("manual trigger works even when bombPotEnabled is false", () => {
    const t = new GameTable({
      tableId: "bp_manual_override",
      smallBlind: 1,
      bigBlind: 2,
      bombPotEnabled: false,
    });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 1000 });

    t.queueBombPotNextHand();
    t.startHand();
    assert.equal(t.getPublicState().isBombPotHand, true,
      "manual queue should override bombPotEnabled=false");
  });
});

// ═══════════════════════════════════════════════════════════════
// B) BOMB POT — ANTE MODES
// ═══════════════════════════════════════════════════════════════

describe("Bomb Pot Ante Modes", () => {
  it("bb_multiplier mode: ante = bigBlind × multiplier", () => {
    const t = new GameTable({
      tableId: "bp_ante_bb",
      smallBlind: 5,
      bigBlind: 10,
      bombPotEnabled: true,
      bombPotTriggerMode: "frequency",
      bombPotFrequency: 1,
      bombPotAnteMode: "bb_multiplier",
      bombPotAnteValue: 3,
    });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 1000 });
    t.addPlayer({ seat: 3, userId: "u3", name: "C", stack: 1000 });

    t.startHand();
    const s = t.getPublicState();
    assert.equal(s.isBombPotHand, true);
    // Ante = 10 × 3 = 30 per player, 3 players = 90
    assert.equal(s.pot, 90, "pot should be 3 × (10 × 3) = 90");
    for (const p of s.players.filter((pl) => pl.inHand)) {
      assert.equal(p.stack, 970, "each player should have 1000 - 30 = 970");
    }
  });

  it("fixed mode: ante = fixed chip amount", () => {
    const t = new GameTable({
      tableId: "bp_ante_fixed",
      smallBlind: 5,
      bigBlind: 10,
      bombPotEnabled: true,
      bombPotTriggerMode: "frequency",
      bombPotFrequency: 1,
      bombPotAnteMode: "fixed",
      bombPotAnteValue: 25,
    });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 1000 });

    t.startHand();
    const s = t.getPublicState();
    assert.equal(s.isBombPotHand, true);
    // Ante = 25 per player, 2 players = 50
    assert.equal(s.pot, 50, "pot should be 2 × 25 = 50");
    for (const p of s.players.filter((pl) => pl.inHand)) {
      assert.equal(p.stack, 975, "each player should have 1000 - 25 = 975");
    }
  });

  it("bomb pot ante does not count as street commitment", () => {
    const t = new GameTable({
      tableId: "bp_ante_street",
      smallBlind: 1,
      bigBlind: 2,
      bombPotEnabled: true,
      bombPotTriggerMode: "frequency",
      bombPotFrequency: 1,
      bombPotAnteMode: "bb_multiplier",
      bombPotAnteValue: 2,
    });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 500 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 500 });

    t.startHand();
    const s = t.getPublicState();
    for (const p of s.players.filter((pl) => pl.inHand)) {
      assert.equal(p.streetCommitted, 0, "bomb ante should not count as street commitment");
    }
  });

  it("conservation holds through bomb pot hand", () => {
    const t = new GameTable({
      tableId: "bp_conserve",
      smallBlind: 5,
      bigBlind: 10,
      bombPotEnabled: true,
      bombPotTriggerMode: "frequency",
      bombPotFrequency: 1,
      bombPotAnteMode: "bb_multiplier",
      bombPotAnteValue: 2,
    });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 1000 });
    t.addPlayer({ seat: 3, userId: "u3", name: "C", stack: 1000 });

    const chipsBefore = 3000;
    t.startHand();
    assert.equal(totalChips(t), chipsBefore, "chips conserved after bomb ante");
    playToShowdown(t);
    const chipsAfter = t.getPublicState().players.reduce((s, p) => s + p.stack, 0);
    assert.equal(chipsAfter, chipsBefore, "chips conserved after showdown");
  });
});

// ═══════════════════════════════════════════════════════════════
// C) BOMB POT — DOUBLE BOARD INTERACTION
// ═══════════════════════════════════════════════════════════════

describe("Bomb Pot Double Board Interaction", () => {
  it("doubleBoardMode=bomb_pot activates double board only on bomb pot hands", () => {
    const t = new GameTable({
      tableId: "bp_db_interaction",
      smallBlind: 1,
      bigBlind: 2,
      bombPotEnabled: true,
      bombPotTriggerMode: "frequency",
      bombPotFrequency: 2,
      doubleBoardMode: "bomb_pot",
    });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 1000 });

    // Hand 1: not bomb pot → no double board
    t.startHand();
    const s1 = t.getPublicState();
    assert.equal(s1.isBombPotHand, false);
    assert.equal(s1.isDoubleBoardHand, false);
    playToShowdown(t);
    t.clearHand();

    // Hand 2: bomb pot → double board
    t.startHand();
    const s2 = t.getPublicState();
    assert.equal(s2.isBombPotHand, true);
    assert.equal(s2.isDoubleBoardHand, true);
  });
});

// ═══════════════════════════════════════════════════════════════
// D) CONFIGURE VARIANT SETTINGS
// ═══════════════════════════════════════════════════════════════

describe("configureVariantSettings", () => {
  it("updates all bomb pot settings", () => {
    const t = new GameTable({
      tableId: "cfg_test",
      smallBlind: 1,
      bigBlind: 2,
    });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 1000 });

    t.configureVariantSettings({
      bombPotEnabled: true,
      bombPotTriggerMode: "probability",
      bombPotProbability: 75,
      bombPotAnteMode: "fixed",
      bombPotAnteValue: 50,
      bombPotFrequency: 5,
      doubleBoardMode: "bomb_pot",
    });

    // Verify by starting a hand — if probability triggers, it should use fixed ante
    // We can't easily verify internal state, but we can verify no errors
    t.startHand();
    const s = t.getPublicState();
    if (s.isBombPotHand) {
      // Fixed ante of 50 per player
      const anteActions = s.actions.filter((a) => a.type === "ante");
      for (const a of anteActions) {
        assert.equal(a.amount, 50, "fixed ante should be 50");
      }
    }
  });

  it("throws when updating during active hand", () => {
    const t = new GameTable({
      tableId: "cfg_active",
      smallBlind: 1,
      bigBlind: 2,
    });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 1000 });
    t.startHand();

    assert.throws(
      () => t.configureVariantSettings({ bombPotEnabled: true }),
      /cannot update variant settings during an active hand/
    );
  });
});

// ═══════════════════════════════════════════════════════════════
// F) CLEAR HAND — BOARD AND STATE RESET
// ═══════════════════════════════════════════════════════════════

describe("clearHand resets board and state", () => {
  it("clears board, pot, and hand-related state after hand ends", () => {
    const t = new GameTable({
      tableId: "clear_test",
      smallBlind: 1,
      bigBlind: 2,
    });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 1000 });

    t.startHand();
    const beforeClear = t.getPublicState();
    assert.ok(beforeClear.handId, "handId should exist before clearHand");

    // Play to showdown
    playToShowdown(t);

    // Clear the hand
    t.clearHand();

    const afterClear = t.getPublicState();
    assert.equal(afterClear.handId, null, "handId should be null after clearHand");
    assert.deepEqual(afterClear.board, [], "board should be empty after clearHand");
    assert.equal(afterClear.pot, 0, "pot should be 0 after clearHand");
    assert.equal(afterClear.street, "PREFLOP", "street should be PREFLOP after clearHand");
    assert.equal(afterClear.actorSeat, null, "actorSeat should be null after clearHand");
    assert.equal(afterClear.currentBet, 0, "currentBet should be 0 after clearHand");
  });

  it("clears bomb pot flags after hand ends", () => {
    const t = new GameTable({
      tableId: "clear_bp",
      smallBlind: 1,
      bigBlind: 2,
      bombPotEnabled: true,
      bombPotTriggerMode: "manual",
    });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 1000 });
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 1000 });

    // Queue a bomb pot
    t.queueBombPotNextHand();
    t.startHand();

    const duringHand = t.getPublicState();
    assert.equal(duringHand.isBombPotHand, true, "should be bomb pot hand");

    playToShowdown(t);
    t.clearHand();

    const afterClear = t.getPublicState();
    assert.equal(afterClear.isBombPotHand, false, "isBombPotHand should be false after clearHand");
    assert.equal(afterClear.isDoubleBoardHand, false, "isDoubleBoardHand should be false after clearHand");
  });
});
