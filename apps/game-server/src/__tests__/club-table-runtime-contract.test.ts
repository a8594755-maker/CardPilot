import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function readServerSource(): string {
  try {
    return readFileSync(resolve(process.cwd(), "src/server.ts"), "utf-8");
  } catch {
    return readFileSync(resolve(process.cwd(), "apps/game-server/src/server.ts"), "utf-8");
  }
}

describe("Club runtime contracts", () => {
  const source = readServerSource();

  it("suspends idle club table runtime instead of keeping it open forever", () => {
    // Club tables route to handleClubTableIdleSuspend instead of a no-op
    assert.match(source, /if \(isPersistentClubTable\(tableId\)\) \{[\s\S]*handleClubTableIdleSuspend\(tableId\)/);
    // handleRoomAutoClose still guards against accidental full-close of club tables
    assert.match(source, /function handleRoomAutoClose\(tableId: string\): void \{[\s\S]*if \(isPersistentClubTable\(tableId\)\) \{[\s\S]*return;/);
  });

  it("has suspendClubTableRuntime that frees resources without closing", () => {
    assert.match(source, /function suspendClubTableRuntime\(tableId: string\): void \{/);
    // Must NOT call closeRoomSessionIfOpen or touchRoom("CLOSED")
    const fnStart = source.indexOf("function suspendClubTableRuntime(tableId: string): void {");
    const fnSlice = source.slice(fnStart, fnStart + 2000);
    assert.doesNotMatch(fnSlice, /closeRoomSessionIfOpen/);
    assert.doesNotMatch(fnSlice, /touchRoom\(tableId, "CLOSED"\)/);
  });

  it("allows active club member to reopen closed club room by code", () => {
    assert.match(source, /if \(room\.status === "CLOSED"\) \{[\s\S]*if \(clubInfo\) \{[\s\S]*clubManager\.isActiveMember\(clubInfo\.clubId, identity\.userId\)/);
  });

  it("bypasses seat approval queue for club tables", () => {
    assert.match(source, /socket\.on\("seat_request"[\s\S]*if \(clubInfo\) \{[\s\S]*await seatPlayerDirect\(/);
  });

  it("auto-approves rebuys for club tables", () => {
    assert.match(source, /const autoApprove = !!clubInfo \|\| roomManager\.isHostOrCoHost\(payload\.tableId, identity\.userId\)/);
  });

  it("rejects rebuys that exceed stack cap or club funds", () => {
    assert.match(source, /if \(player\.stack \+ pendingForSeat \+ payload\.amount > buyInMax\) \{/);
    assert.match(source, /if \(walletBalance < payload\.amount \+ pendingForUser\) \{/);
    assert.match(source, /Club has insufficient funds/);
  });

  it("applies approved rebuys by debiting club wallet then crediting table stack", () => {
    assert.match(source, /type: "buy_in"[\s\S]*amount: -Math\.trunc\(deposit\.amount\)/);
    assert.match(source, /await emitWalletBalanceToUser\(clubInfo\.clubId, deposit\.userId, tx\.newBalance, "chips"\)/);
    assert.match(source, /table\.addStack\(deposit\.seat, deposit\.amount\)/);
  });

  it("supports club_table_update with runtime safeguards", () => {
    assert.match(source, /socket\.on\("club_table_update"/);
    assert.match(source, /Cannot update table while a hand is active/);
    assert.match(source, /Cannot reduce seats below occupied count/);
    assert.match(source, /roomManager\.updateSettings\(serverTableId/);
  });
});
