import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { describeHandStrength } from "../hand-strength.js";

describe("describeHandStrength", () => {
  it("returns 'No hand data' for insufficient hole cards", () => {
    assert.equal(describeHandStrength([], ["Ah", "Kd", "Qs"]), "No hand data");
    assert.equal(describeHandStrength(["Ah"], ["Kd", "Qs", "Jc"]), "No hand data");
  });

  it("returns 'No board yet' when board is empty", () => {
    assert.equal(describeHandStrength(["Ah", "Kd"], []), "No board yet");
  });

  it("detects Royal Flush", () => {
    const result = describeHandStrength(["Ah", "Kh"], ["Qh", "Jh", "Th"]);
    assert.equal(result, "Royal Flush");
  });

  it("detects Straight Flush", () => {
    const result = describeHandStrength(["9h", "8h"], ["7h", "6h", "5h"]);
    assert.equal(result, "Straight Flush (Nine-high)");
  });

  it("detects Four of a Kind", () => {
    const result = describeHandStrength(["Qs", "Qh"], ["Qd", "Qc", "2s"]);
    assert.equal(result, "Four of a Kind (Queens)");
  });

  it("detects Full House with qualifier", () => {
    const result = describeHandStrength(["Jh", "Js"], ["Jd", "4c", "4s"]);
    assert.equal(result, "Full House (Jacks full of Fours)");
  });

  it("detects Flush with high card", () => {
    const result = describeHandStrength(["Kh", "9h"], ["7h", "4h", "2h"]);
    assert.equal(result, "Flush (King-high)");
  });

  it("detects Straight with high card", () => {
    const result = describeHandStrength(["Ts", "9h"], ["8d", "7c", "6s"]);
    assert.equal(result, "Straight (Ten-high)");
  });

  it("detects Set (pocket pair hitting board)", () => {
    const result = describeHandStrength(["Qs", "Qh"], ["Qd", "7c", "2s"]);
    assert.equal(result, "Set of Queens");
  });

  it("detects Trips (one hole card + two board)", () => {
    const result = describeHandStrength(["Qs", "7h"], ["Qd", "Qc", "2s"]);
    assert.equal(result, "Trips (Queens)");
  });

  it("detects Two Pair with qualifiers", () => {
    const result = describeHandStrength(["Ah", "Ts"], ["Ad", "Tc", "3h"]);
    assert.equal(result, "Two Pair (Aces and Tens)");
  });

  it("detects Top Pair", () => {
    const result = describeHandStrength(["Ah", "7s"], ["Ad", "Kc", "3h"]);
    // A pairs with board top (A)
    assert.match(result, /Top Pair|Pair of Aces/);
  });

  it("detects Pocket Pair", () => {
    const result = describeHandStrength(["Kh", "Ks"], ["Ad", "Qc", "3h"]);
    assert.equal(result, "Pocket Kings");
  });

  it("detects Bottom Pair", () => {
    const result = describeHandStrength(["3h", "7s"], ["Ad", "Kc", "3d"]);
    assert.equal(result, "Bottom Pair (Threes)");
  });

  it("detects Flush draw on flop", () => {
    const result = describeHandStrength(["Ah", "Kh"], ["7h", "4h", "2s"]);
    assert.match(result, /Flush draw/);
  });

  it("detects Open-ended straight draw", () => {
    const result = describeHandStrength(["9s", "8h"], ["7d", "6c", "2s"]);
    assert.match(result, /straight draw/i);
  });

  it("detects High Card with qualifier", () => {
    const result = describeHandStrength(["Ah", "Ks"], ["7d", "4c", "2s", "9h", "3d"]);
    assert.equal(result, "High Card (Ace)");
  });

  it("handles 7-card evaluation (5 board cards)", () => {
    const result = describeHandStrength(["Ah", "Kh"], ["Qh", "Jh", "Th", "2s", "3d"]);
    assert.equal(result, "Royal Flush");
  });

  it("works with RIT split boards (different results per board)", () => {
    const hole = ["Ah", "Kh"];
    const board1 = ["Qh", "Jh", "Th", "2s", "3d"]; // Royal Flush
    const board2 = ["7d", "4c", "2s", "9h", "3d"]; // High Card

    const desc1 = describeHandStrength(hole, board1);
    const desc2 = describeHandStrength(hole, board2);

    assert.equal(desc1, "Royal Flush");
    assert.equal(desc2, "High Card (Ace)");
    assert.notEqual(desc1, desc2, "different boards should produce different results");
  });
});
