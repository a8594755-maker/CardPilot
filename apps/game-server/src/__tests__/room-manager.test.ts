import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { RoomManager } from "../room-manager.js";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

describe("RoomManager timer behavior", () => {
  it("time bank should decrease over elapsed time once main timer expires", async () => {
    const events: Array<{ event: string; data: unknown }> = [];
    const manager = new RoomManager((_tableId, event, data) => {
      events.push({ event, data });
    });

    manager.createRoom({
      tableId: "tbl_timer",
      roomCode: "TMR001",
      roomName: "Timer Test",
      ownerId: "owner-1",
      ownerName: "Owner",
      settings: {
        actionTimerSeconds: 1,
        timeBankSeconds: 3,
        timeBankRefillPerHand: 0,
      },
    });

    let timedOut = false;
    manager.startActionTimer("tbl_timer", 0, "u0", () => {
      timedOut = true;
    });

    // Wait until main timer expires and time bank starts.
    await sleep(1300);

    const state = manager.getFullState("tbl_timer");
    assert.ok(state?.timer, "timer should still be active in time bank phase");
    assert.equal(state?.timer?.usingTimeBank, true, "should enter time bank after main timer");

    // Wait for at least 1 second of bank tick.
    await sleep(1100);
    const stateAfterTick = manager.getFullState("tbl_timer");

    assert.ok(
      (stateAfterTick?.timer?.timeBankRemaining ?? 0) < 3,
      "time bank remaining should decrease over time"
    );

    // Cleanup for deterministic test end.
    manager.clearActionTimer("tbl_timer");
    assert.equal(timedOut, false, "timeout callback should not fire after manual clear");
    assert.ok(events.some((e) => e.event === "timer_update"), "timer_update events should be emitted");
  });
});
