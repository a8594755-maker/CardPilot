import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { extractDecisionPoints } from "../services/gto-analyzer.js";
import type { HistoryGTOHandRecord } from "@cardpilot/shared-types";

function baseHand(overrides: Partial<HistoryGTOHandRecord> = {}): HistoryGTOHandRecord {
  return {
    heroCards: ["Ah", "Kd"],
    board: ["Qs", "7h", "2d", "Tc", "9s"],
    heroSeat: 1,
    heroPosition: "BTN",
    stakes: "50/100",
    tableSize: 2,
    potSize: 0,
    stackSize: 10000,
    actions: [],
    ...overrides,
  };
}

describe("gto-analyzer decision point reconstruction", () => {
  it("reconstructs SRP line with turn/river actions using actionTimeline", () => {
    const hand = baseHand({
      buttonSeat: 1,
      positionsBySeat: { 1: "BTN", 2: "BB" },
      stacksBySeatAtStart: { 1: 10000, 2: 10000 },
      actions: [
        { seat: 1, street: "PREFLOP", type: "raise", amount: 250 },
        { seat: 2, street: "PREFLOP", type: "call", amount: 200 },
        { seat: 2, street: "FLOP", type: "check", amount: 0 },
        { seat: 1, street: "FLOP", type: "bet", amount: 300 },
        { seat: 2, street: "FLOP", type: "call", amount: 300 },
        { seat: 2, street: "TURN", type: "check", amount: 0 },
        { seat: 1, street: "TURN", type: "check", amount: 0 },
        { seat: 2, street: "RIVER", type: "bet", amount: 700 },
        { seat: 1, street: "RIVER", type: "raise", amount: 2100 },
        { seat: 2, street: "RIVER", type: "call", amount: 1400 },
      ],
      actionTimeline: [
        {
          idx: 2,
          street: "FLOP",
          seat: 2,
          type: "check",
          amount: 0,
          potBefore: 500,
          toCallBefore: 0,
          committedThisStreetBefore: 0,
          effectiveStackBefore: 9750,
        },
        {
          idx: 3,
          street: "FLOP",
          seat: 1,
          type: "bet",
          amount: 300,
          betTo: 300,
          potBefore: 500,
          toCallBefore: 0,
          committedThisStreetBefore: 0,
          effectiveStackBefore: 9750,
        },
        {
          idx: 4,
          street: "FLOP",
          seat: 2,
          type: "call",
          amount: 300,
          potBefore: 800,
          toCallBefore: 300,
          committedThisStreetBefore: 0,
          effectiveStackBefore: 9450,
        },
        {
          idx: 5,
          street: "TURN",
          seat: 2,
          type: "check",
          amount: 0,
          potBefore: 1100,
          toCallBefore: 0,
          committedThisStreetBefore: 0,
          effectiveStackBefore: 9450,
        },
        {
          idx: 6,
          street: "TURN",
          seat: 1,
          type: "check",
          amount: 0,
          potBefore: 1100,
          toCallBefore: 0,
          committedThisStreetBefore: 0,
          effectiveStackBefore: 9450,
        },
        {
          idx: 7,
          street: "RIVER",
          seat: 2,
          type: "bet",
          amount: 700,
          betTo: 700,
          potBefore: 1100,
          toCallBefore: 0,
          committedThisStreetBefore: 0,
          effectiveStackBefore: 9450,
        },
        {
          idx: 8,
          street: "RIVER",
          seat: 1,
          type: "raise",
          amount: 2100,
          raiseTo: 2100,
          potBefore: 1800,
          toCallBefore: 700,
          committedThisStreetBefore: 0,
          effectiveStackBefore: 9450,
        },
        {
          idx: 9,
          street: "RIVER",
          seat: 2,
          type: "call",
          amount: 1400,
          potBefore: 3900,
          toCallBefore: 1400,
          committedThisStreetBefore: 700,
          effectiveStackBefore: 8750,
        },
      ],
    });

    const points = extractDecisionPoints(hand);
    assert.equal(points.length, 3);

    assert.equal(points[0].street, "FLOP");
    assert.equal(points[0].pot, 500);
    assert.equal(points[0].toCall, 0);
    assert.equal(points[0].heroAction, "bet");

    assert.equal(points[1].street, "TURN");
    assert.equal(points[1].pot, 1100);
    assert.equal(points[1].toCall, 0);
    assert.equal(points[1].heroAction, "check");

    assert.equal(points[2].street, "RIVER");
    assert.equal(points[2].pot, 1800);
    assert.equal(points[2].toCall, 700);
    assert.equal(points[2].heroAction, "raise");
  });

  it("reconstructs multi-raise street semantics from actions fallback", () => {
    const hand = baseHand({
      buttonSeat: 1,
      positionsBySeat: { 1: "BTN", 2: "BB" },
      actions: [
        { seat: 1, street: "PREFLOP", type: "raise", amount: 300 },
        { seat: 2, street: "PREFLOP", type: "call", amount: 200 },
        { seat: 2, street: "FLOP", type: "bet", amount: 200 },
        { seat: 1, street: "FLOP", type: "raise", amount: 600 },
        { seat: 2, street: "FLOP", type: "raise", amount: 1400 },
        { seat: 1, street: "FLOP", type: "call", amount: 800 },
      ],
    });

    const points = extractDecisionPoints(hand);
    assert.equal(points.length, 2);

    assert.equal(points[0].street, "FLOP");
    assert.equal(points[0].heroAction, "raise");
    assert.equal(points[0].toCall, 200);
    assert.equal(points[0].pot, 700);

    assert.equal(points[1].street, "FLOP");
    assert.equal(points[1].heroAction, "call");
    assert.equal(points[1].toCall, 1000);
    assert.equal(points[1].pot, 2700);
  });
});
