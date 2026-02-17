import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function readServerSource(): string {
  return readFileSync(resolve(process.cwd(), "src/server.ts"), "utf-8");
}

describe("Server round-flow regressions", () => {
  const source = readServerSource();

  it("uses showdown-speed based auto-start scheduling with explicit skip reasons", () => {
    assert.match(source, /SHOWDOWN_SPEED_DELAYS_MS\[room\.settings\.showdownSpeed\]/);
    assert.match(source, /getAutoStartSkipMessage\(tableId\)/);
    assert.match(source, /Auto-start skipped:/);
  });

  it("credits approved rebuys at hand start (not hand end)", () => {
    const startHandIdx = source.indexOf("function startHandFlow");
    const applyIdx = source.indexOf("applyApprovedRebuys(tableId);", startHandIdx);
    const tableStartIdx = source.indexOf("table.startHand()", startHandIdx);
    assert.ok(applyIdx > startHandIdx, "startHandFlow must apply approved rebuys");
    assert.ok(tableStartIdx > applyIdx, "approved rebuys must apply before table.startHand()");

    const finalizeIdx = source.indexOf("function finalizeHandEnd");
    const finalizeApplyIdx = source.indexOf("applyApprovedRebuys(tableId);", finalizeIdx);
    assert.equal(finalizeApplyIdx, -1, "finalizeHandEnd should not apply rebuys");
  });

  it("queues leave-after-hand and bust-out stand-up flows", () => {
    assert.match(source, /pendingStandUps/);
    assert.match(source, /Leaving after this hand\./);
    assert.match(source, /if \(p\.stack <= 0\)/);
    assert.match(source, /queueLeaveTableAfterHand\(payload\.tableId, socket\.id\)/);
  });

  it("has runout/showdown fail-safe finalization paths to prevent stalled hands", () => {
    assert.match(source, /async function handleSequentialRunout\(tableId: string, table: GameTable\): Promise<void> \{[\s\S]*try \{/);
    assert.match(source, /event: "runout\.sequence\.failed"/);
    assert.match(source, /if \(state\.showdownPhase === "decision"\) \{[\s\S]*settleShowdownDecision\(tableId, table, state\.handId\);/);
    assert.match(source, /finalizeHandEnd\(tableId, state\);/);
    assert.match(source, /if \(state\.showdownPhase !== "decision"\) \{[\s\S]*finalizeHandEnd\(tableId, state\);/);
  });

  it("enforces room-funds table-balance restoration window and minimum rejoin stack", () => {
    assert.match(source, /if \(!room\?\.settings\.roomFundsTracking\) return null;/);
    assert.match(source, /if \(ageMs > runtimeConfig\.tableBalanceRejoinWindowMs\) return null;/);
    assert.match(source, /if \(payload\.buyIn < restoredStack\) \{/);
    assert.match(source, /Table balance requires at least \$\{restoredStack\} chips to rejoin this room/);
  });

});
