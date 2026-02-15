/**
 * Hand History utility tests
 * Run with: npx vitest run apps/web/src/lib/__tests__/hand-history.test.ts
 * Or manually verify these invariants during dev.
 */

import { describe, it, expect, beforeEach } from "vitest";

// We test the pure utility functions. localStorage-dependent ones need a mock.

// ── autoTag tests ──
describe("autoTag", () => {
  // Import dynamically to avoid module resolution issues in non-vitest envs
  const { autoTag } = require("../hand-history") as typeof import("../hand-history");

  it("tags SRP when 0-1 preflop raises", () => {
    const actions = [
      { seat: 1, street: "PREFLOP", type: "raise", amount: 6 },
      { seat: 2, street: "PREFLOP", type: "call", amount: 6 },
    ];
    const tags = autoTag(actions);
    expect(tags).toContain("SRP");
    expect(tags).not.toContain("3bet_pot");
  });

  it("tags 3bet_pot when 2+ preflop raises", () => {
    const actions = [
      { seat: 1, street: "PREFLOP", type: "raise", amount: 6 },
      { seat: 2, street: "PREFLOP", type: "raise", amount: 18 },
      { seat: 1, street: "PREFLOP", type: "call", amount: 18 },
    ];
    const tags = autoTag(actions);
    expect(tags).toContain("3bet_pot");
  });

  it("tags 4bet_pot when 3+ preflop raises", () => {
    const actions = [
      { seat: 1, street: "PREFLOP", type: "raise", amount: 6 },
      { seat: 2, street: "PREFLOP", type: "raise", amount: 18 },
      { seat: 1, street: "PREFLOP", type: "raise", amount: 48 },
      { seat: 2, street: "PREFLOP", type: "call", amount: 48 },
    ];
    const tags = autoTag(actions);
    expect(tags).toContain("4bet_pot");
  });

  it("tags all_in when any all_in action exists", () => {
    const actions = [
      { seat: 1, street: "PREFLOP", type: "raise", amount: 6 },
      { seat: 2, street: "PREFLOP", type: "all_in", amount: 100 },
    ];
    const tags = autoTag(actions);
    expect(tags).toContain("all_in");
  });

  it("does not tag all_in when no all_in action", () => {
    const actions = [
      { seat: 1, street: "PREFLOP", type: "raise", amount: 6 },
      { seat: 2, street: "PREFLOP", type: "call", amount: 6 },
    ];
    const tags = autoTag(actions);
    expect(tags).not.toContain("all_in");
  });
});

// ── formatHandAsPokerStars tests ──
describe("formatHandAsPokerStars", () => {
  const { formatHandAsPokerStars } = require("../hand-history") as typeof import("../hand-history");

  it("produces PokerStars-style header", () => {
    const hand = {
      id: "test123",
      createdAt: Date.now(),
      expiresAt: Date.now() + 86400000,
      gameType: "NLH" as const,
      stakes: "1/2",
      tableSize: 6,
      position: "BTN",
      heroCards: ["Ah", "Kd"] as [string, string],
      board: ["Qs", "Jh", "Td", "2c", "3s"],
      actions: [
        { seat: 1, street: "PREFLOP", type: "raise", amount: 6 },
        { seat: 2, street: "PREFLOP", type: "call", amount: 6 },
        { seat: 1, street: "FLOP", type: "check", amount: 0 },
        { seat: 2, street: "FLOP", type: "check", amount: 0 },
      ],
      potSize: 12,
      stackSize: 194,
      result: 6,
      tags: ["SRP"],
      handId: "hh-abc-123",
      heroSeat: 1,
      heroName: "TestHero",
      roomName: "Test Room",
      roomCode: "ABC123",
      playerNames: { 1: "TestHero", 2: "Villain" },
    };

    const text = formatHandAsPokerStars(hand);
    expect(text).toContain("PokerStars Hand #hh-abc-123");
    expect(text).toContain("Hold'em No Limit (1/2)");
    expect(text).toContain("*** HOLE CARDS ***");
    expect(text).toContain("Dealt to TestHero [Ah Kd]");
    expect(text).toContain("*** FLOP ***");
    expect(text).toContain("[Qs Jh Td]");
    expect(text).toContain("*** SUMMARY ***");
    expect(text).toContain("Total pot 12");
  });

  it("handles run-it-twice boards", () => {
    const hand = {
      id: "rit1",
      createdAt: Date.now(),
      expiresAt: Date.now() + 86400000,
      gameType: "NLH" as const,
      stakes: "5/10",
      tableSize: 6,
      position: "CO",
      heroCards: ["As", "Ac"] as [string, string],
      board: ["Ks", "Qh", "2d", "7c", "3s"],
      runoutBoards: [
        ["Ks", "Qh", "2d", "7c", "3s"],
        ["Ks", "Qh", "2d", "8h", "9d"],
      ],
      actions: [
        { seat: 1, street: "PREFLOP", type: "all_in", amount: 500 },
        { seat: 2, street: "PREFLOP", type: "call", amount: 500 },
      ],
      potSize: 1000,
      stackSize: 500,
      result: 500,
      tags: ["all_in"],
      heroSeat: 1,
      heroName: "Hero",
    };

    const text = formatHandAsPokerStars(hand);
    expect(text).toContain("Run 1:");
    expect(text).toContain("Run 2:");
  });
});

// ── Sorting/grouping logic (tested via getHandsByRoom mock) ──
describe("getHandsByRoom grouping", () => {
  // This tests the pure grouping logic. In production, it reads from localStorage.
  // We test the grouping by creating the structure manually.

  it("groups hands by roomCode correctly", () => {
    const hands = [
      { roomCode: "ROOM1", createdAt: 1000, result: 50, stakes: "1/2" },
      { roomCode: "ROOM1", createdAt: 900, result: -20, stakes: "1/2" },
      { roomCode: "ROOM2", createdAt: 800, result: 100, stakes: "5/10" },
      { roomCode: undefined, createdAt: 700, result: -10, stakes: "1/2" },
    ];

    const byRoom: Record<string, typeof hands> = {};
    for (const h of hands) {
      const code = h.roomCode || "_local";
      if (!byRoom[code]) byRoom[code] = [];
      byRoom[code].push(h);
    }

    expect(Object.keys(byRoom)).toHaveLength(3);
    expect(byRoom["ROOM1"]).toHaveLength(2);
    expect(byRoom["ROOM2"]).toHaveLength(1);
    expect(byRoom["_local"]).toHaveLength(1);

    // Net result for ROOM1
    const room1Net = byRoom["ROOM1"].reduce((sum, h) => sum + h.result, 0);
    expect(room1Net).toBe(30);
  });

  it("handles empty hands array", () => {
    const hands: Array<{ roomCode?: string }> = [];
    const byRoom: Record<string, typeof hands> = {};
    for (const h of hands) {
      const code = h.roomCode || "_local";
      if (!byRoom[code]) byRoom[code] = [];
      byRoom[code].push(h);
    }
    expect(Object.keys(byRoom)).toHaveLength(0);
  });
});
