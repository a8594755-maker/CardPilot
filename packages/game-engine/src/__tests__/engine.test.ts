import { describe, it, before } from "node:test";
import assert from "node:assert/strict";
import { GameTable } from "../index.js";

function makeTable(sb = 50, bb = 100) {
  const t = new GameTable({ tableId: "test", smallBlind: sb, bigBlind: bb });
  t.addPlayer({ seat: 1, userId: "u1", name: "Alice", stack: 10000 });
  t.addPlayer({ seat: 2, userId: "u2", name: "Bob", stack: 10000 });
  return t;
}

function make6Max(sb = 50, bb = 100) {
  const t = new GameTable({ tableId: "test6", smallBlind: sb, bigBlind: bb });
  for (let i = 1; i <= 6; i++) {
    t.addPlayer({ seat: i, userId: `u${i}`, name: `P${i}`, stack: 10000 });
  }
  return t;
}

// ────────── Basic setup ──────────

describe("GameTable setup", () => {
  it("should require at least 2 players to start", () => {
    const t = new GameTable({ tableId: "t", smallBlind: 50, bigBlind: 100 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 10000 });
    assert.throws(() => t.startHand(), /need at least 2 players/);
  });

  it("should not allow duplicate seats", () => {
    const t = makeTable();
    assert.throws(() => t.addPlayer({ seat: 1, userId: "u3", name: "C", stack: 5000 }), /seat already occupied/);
  });

  it("should start hand and set PREFLOP", () => {
    const t = makeTable();
    const { handId } = t.startHand();
    const s = t.getPublicState();
    assert.ok(handId);
    assert.equal(s.street, "PREFLOP");
    assert.equal(s.handId, handId);
  });

  it("should deal hole cards to each player", () => {
    const t = makeTable();
    t.startHand();
    assert.ok(t.getHoleCards(1));
    assert.ok(t.getHoleCards(2));
    assert.equal(t.getHoleCards(1)!.length, 2);
    assert.equal(t.getHoleCards(2)!.length, 2);
  });
});

// ────────── Blinds ──────────

describe("Blinds", () => {
  it("should post SB and BB correctly", () => {
    const t = makeTable(50, 100);
    t.startHand();
    const s = t.getPublicState();
    assert.equal(s.pot, 150); // SB(50) + BB(100)
    const totalStacks = s.players.reduce((sum, p) => sum + p.stack, 0);
    assert.equal(totalStacks + s.pot, 20000);
  });

  it("should handle short-stacked blind (player cannot cover)", () => {
    const t = new GameTable({ tableId: "t", smallBlind: 50, bigBlind: 100 });
    t.addPlayer({ seat: 1, userId: "u1", name: "A", stack: 30 }); // can't cover blind
    t.addPlayer({ seat: 2, userId: "u2", name: "B", stack: 10000 });
    t.startHand();
    const s = t.getPublicState();
    // One player posts what they can (30), other posts their blind
    assert.ok(s.pot > 0, "pot should be positive");
    const shortPlayer = s.players.find(p => p.stack === 0);
    assert.ok(shortPlayer, "short-stacked player should be all-in with 0 stack");
    assert.ok(shortPlayer.allIn);
    // Total chips conserved
    const totalStacks = s.players.reduce((sum, p) => sum + p.stack, 0);
    assert.equal(totalStacks + s.pot, 10030);
  });
});

// ────────── Legal actions ──────────

describe("Legal actions", () => {
  it("should provide legal actions for the actor", () => {
    const t = makeTable();
    t.startHand();
    const s = t.getPublicState();
    assert.ok(s.legalActions, "legalActions should not be null when there is an actor");
    assert.ok(s.actorSeat);
  });

  it("should allow fold, call, raise preflop for the first actor", () => {
    const t = makeTable(50, 100);
    t.startHand();
    const s = t.getPublicState();
    const la = s.legalActions!;
    assert.ok(la.canFold);
    assert.ok(la.canCall || la.canCheck);
    assert.ok(la.canRaise);
  });

  it("should have no legal actions when hand is not active", () => {
    const t = makeTable();
    const s = t.getPublicState();
    assert.equal(s.legalActions, null);
  });

  it("should not allow check when facing a bet (SB preflop)", () => {
    // In HU, seat 2 is SB. After BB (seat 1) checks, the hand advances.
    // We need a scenario where a player faces a bet. Let's use 6-max.
    const t = make6Max(50, 100);
    t.startHand();
    let s = t.getPublicState();
    // First actor in 6-max preflop is UTG (seat after BB). They face a bet (BB=100).
    const actor = s.actorSeat!;
    // UTG faces currentBet=100 and has streetCommitted=0 → cannot check
    assert.throws(() => t.applyAction(actor, "check"), /cannot check/);
  });
});

// ────────── Actions ──────────

describe("Fold", () => {
  it("should end hand when one player folds in heads-up", () => {
    const t = makeTable();
    t.startHand();
    const s = t.getPublicState();
    const actor = s.actorSeat!;
    const result = t.applyAction(actor, "fold");
    assert.equal(result.street, "SHOWDOWN");
    assert.equal(result.actorSeat, null);
    assert.ok(result.winners);
    assert.equal(result.winners!.length, 1);
  });
});

describe("Call", () => {
  it("should move chips to pot on call", () => {
    // Use 6-max so UTG is first to act and can call
    const t = make6Max(50, 100);
    t.startHand();
    const s = t.getPublicState();
    const actor = s.actorSeat!;
    const before = s.pot;
    const result = t.applyAction(actor, "call");
    assert.ok(result.pot > before, `pot should increase: was ${before}, now ${result.pot}`);
  });
});

describe("Raise", () => {
  it("should enforce minimum raise", () => {
    const t = makeTable(50, 100);
    t.startHand();
    const s = t.getPublicState();
    const actor = s.actorSeat!;
    // min raise to is 200 (BB*2)
    assert.throws(() => t.applyAction(actor, "raise", 150), /raise must be at least/);
  });

  it("should allow valid raise and update currentBet", () => {
    const t = makeTable(50, 100);
    t.startHand();
    const s = t.getPublicState();
    const actor = s.actorSeat!;
    const result = t.applyAction(actor, "raise", 300);
    assert.equal(result.currentBet, 300);
  });

  it("should update minRaiseTo after a raise", () => {
    const t = makeTable(50, 100);
    t.startHand();
    const s = t.getPublicState();
    const actor = s.actorSeat!;
    const result = t.applyAction(actor, "raise", 300);
    // minRaiseTo = 300 + (300 - 100) = 500
    assert.equal(result.minRaiseTo, 500);
  });
});

describe("All-in", () => {
  it("should allow all-in action", () => {
    const t = makeTable(50, 100);
    t.startHand();
    const s = t.getPublicState();
    const actor = s.actorSeat!;
    const result = t.applyAction(actor, "all_in");
    const p = result.players.find(pl => pl.seat === actor)!;
    assert.equal(p.stack, 0);
    assert.ok(p.allIn);
  });
});

// ────────── Street advancement ──────────

describe("Street advancement", () => {
  it("should advance to FLOP after preflop action completes", () => {
    const t = makeTable(50, 100);
    t.startHand();
    let s = t.getPublicState();
    // Player 1 (SB/BTN) calls
    t.applyAction(s.actorSeat!, "call");
    s = t.getPublicState();
    // Player 2 (BB) checks
    const result = t.applyAction(s.actorSeat!, "check");
    assert.equal(result.street, "FLOP");
    assert.equal(result.board.length, 3);
  });

  it("should advance through all streets to showdown", () => {
    const t = makeTable(50, 100);
    t.startHand();
    let s = t.getPublicState();

    // PREFLOP: call + check
    t.applyAction(s.actorSeat!, "call");
    s = t.getPublicState();
    t.applyAction(s.actorSeat!, "check");
    s = t.getPublicState();
    assert.equal(s.street, "FLOP");
    assert.equal(s.board.length, 3);

    // FLOP: check + check
    t.applyAction(s.actorSeat!, "check");
    s = t.getPublicState();
    t.applyAction(s.actorSeat!, "check");
    s = t.getPublicState();
    assert.equal(s.street, "TURN");
    assert.equal(s.board.length, 4);

    // TURN: check + check
    t.applyAction(s.actorSeat!, "check");
    s = t.getPublicState();
    t.applyAction(s.actorSeat!, "check");
    s = t.getPublicState();
    assert.equal(s.street, "RIVER");
    assert.equal(s.board.length, 5);

    // RIVER: check + check → showdown
    t.applyAction(s.actorSeat!, "check");
    s = t.getPublicState();
    const result = t.applyAction(s.actorSeat!, "check");
    assert.equal(result.street, "SHOWDOWN");
    assert.equal(result.actorSeat, null);
    assert.ok(result.winners);
  });
});

// ────────── Pot invariants ──────────

describe("Pot invariants", () => {
  it("pot + all stacks should equal total buy-in at all times", () => {
    const totalBuyIn = 20000;
    const t = makeTable(50, 100);
    t.startHand();

    // Play through a full hand
    let s = t.getPublicState();
    const checkInvariant = () => {
      const totalStacks = s.players.reduce((sum, p) => sum + p.stack, 0);
      assert.equal(totalStacks + s.pot, totalBuyIn, `invariant violated: stacks=${totalStacks} pot=${s.pot}`);
    };

    checkInvariant();

    // Preflop
    t.applyAction(s.actorSeat!, "call");
    s = t.getPublicState();
    checkInvariant();

    t.applyAction(s.actorSeat!, "check");
    s = t.getPublicState();
    checkInvariant();

    // Flop
    t.applyAction(s.actorSeat!, "check");
    s = t.getPublicState();
    checkInvariant();

    t.applyAction(s.actorSeat!, "check");
    s = t.getPublicState();
    checkInvariant();

    // Turn
    t.applyAction(s.actorSeat!, "check");
    s = t.getPublicState();
    checkInvariant();

    t.applyAction(s.actorSeat!, "check");
    s = t.getPublicState();
    checkInvariant();

    // River
    t.applyAction(s.actorSeat!, "check");
    s = t.getPublicState();
    checkInvariant();

    const final = t.applyAction(s.actorSeat!, "check");
    const totalStacks = final.players.reduce((sum, p) => sum + p.stack, 0);
    // After showdown, pot is awarded so total stacks should equal total buy-in
    // pot may still be in state but was already distributed
    assert.equal(totalStacks, totalBuyIn, `after showdown stacks should equal buy-in`);
  });

  it("stack should never go negative", () => {
    const t = makeTable(50, 100);
    t.startHand();
    let s = t.getPublicState();
    for (const p of s.players) {
      assert.ok(p.stack >= 0, `player ${p.seat} stack is negative: ${p.stack}`);
    }
    // Do some actions
    t.applyAction(s.actorSeat!, "raise", 500);
    s = t.getPublicState();
    for (const p of s.players) {
      assert.ok(p.stack >= 0, `player ${p.seat} stack is negative: ${p.stack}`);
    }
  });

  it("pot should never go negative", () => {
    const t = makeTable(50, 100);
    t.startHand();
    const s = t.getPublicState();
    assert.ok(s.pot >= 0);
    const result = t.applyAction(s.actorSeat!, "fold");
    assert.ok(result.pot >= 0);
  });
});

// ────────── Turn enforcement ──────────

describe("Turn enforcement", () => {
  it("should reject action from wrong seat", () => {
    const t = makeTable();
    t.startHand();
    const s = t.getPublicState();
    const wrongSeat = s.players.find(p => p.seat !== s.actorSeat)!.seat;
    assert.throws(() => t.applyAction(wrongSeat, "fold"), /not your turn/);
  });

  it("should reject action when no hand is active", () => {
    const t = makeTable();
    assert.throws(() => t.applyAction(1, "fold"), /no active hand/);
  });
});

// ────────── 6-max positions ──────────

describe("Positions", () => {
  it("should assign correct positions in heads-up", () => {
    const t = makeTable();
    t.startHand();
    const s = t.getPublicState();
    const pos1 = t.getPosition(1);
    const pos2 = t.getPosition(2);
    const positions = [pos1, pos2].sort();
    assert.deepEqual(positions, ["BB", "SB"]);
  });

  it("should assign positions in 6-max", () => {
    const t = make6Max();
    t.startHand();
    const positions = new Set<string>();
    for (let i = 1; i <= 6; i++) {
      positions.add(t.getPosition(i));
    }
    assert.equal(positions.size, 6);
    assert.ok(positions.has("SB"));
    assert.ok(positions.has("BB"));
    assert.ok(positions.has("BTN"));
  });
});

// ────────── Mode ──────────

describe("Mode", () => {
  it("should default to COACH mode", () => {
    const t = makeTable();
    assert.equal(t.getMode(), "COACH");
  });

  it("should allow setting mode", () => {
    const t = makeTable();
    t.setMode("REVIEW");
    assert.equal(t.getMode(), "REVIEW");
  });
});
