import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { formatChips, formatDelta } from "../format-chips.js";

describe("formatChips", () => {
  it("chips mode: formats with locale separators", () => {
    const opts = { mode: "chips" as const, bbSize: 10 };
    assert.equal(formatChips(0, opts), "0");
    assert.equal(formatChips(1500, opts), "1,500");
    assert.equal(formatChips(100, opts), "100");
  });

  it("bb mode: 1 decimal for <10 BB", () => {
    const opts = { mode: "bb" as const, bbSize: 100 };
    assert.equal(formatChips(0, opts), "0 BB");
    assert.equal(formatChips(100, opts), "1.0 BB");
    assert.equal(formatChips(250, opts), "2.5 BB");
    assert.equal(formatChips(750, opts), "7.5 BB");
    assert.equal(formatChips(950, opts), "9.5 BB");
  });

  it("bb mode: 0 decimals for ≥10 BB (unless .5)", () => {
    const opts = { mode: "bb" as const, bbSize: 100 };
    assert.equal(formatChips(1000, opts), "10 BB");
    assert.equal(formatChips(2000, opts), "20 BB");
    assert.equal(formatChips(1050, opts), "10.5 BB");
    assert.equal(formatChips(5000, opts), "50 BB");
  });

  it("bb mode: handles fractional BB values", () => {
    const opts = { mode: "bb" as const, bbSize: 3 };
    // 7.5 / 3 = 2.5 BB → <10 → 1 decimal
    assert.equal(formatChips(7.5, opts), "2.5 BB");
  });

  it("bb mode: handles bbSize=0 gracefully (falls back to 1)", () => {
    const opts = { mode: "bb" as const, bbSize: 0 };
    // 100 / 1 = 100 BB → ≥10 → 0 decimals
    assert.equal(formatChips(100, opts), "100 BB");
    // Small value: 5 / 1 = 5 BB → <10 → 1 decimal
    assert.equal(formatChips(5, opts), "5.0 BB");
  });
});

describe("formatDelta", () => {
  it("positive delta shows +", () => {
    const opts = { mode: "chips" as const, bbSize: 10 };
    assert.equal(formatDelta(500, opts), "+500");
  });

  it("negative delta shows −", () => {
    const opts = { mode: "chips" as const, bbSize: 10 };
    assert.equal(formatDelta(-500, opts), "−500");
  });

  it("zero delta shows no sign", () => {
    const opts = { mode: "chips" as const, bbSize: 10 };
    assert.equal(formatDelta(0, opts), "0");
  });

  it("bb mode delta", () => {
    const opts = { mode: "bb" as const, bbSize: 100 };
    assert.equal(formatDelta(250, opts), "+2.5 BB");
    assert.equal(formatDelta(-1000, opts), "−10 BB");
  });
});
