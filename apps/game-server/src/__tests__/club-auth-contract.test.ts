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

function readWebSource(): string {
  try {
    return readFileSync(resolve(process.cwd(), "../web/src/App.tsx"), "utf-8");
  } catch {
    return readFileSync(resolve(process.cwd(), "apps/web/src/App.tsx"), "utf-8");
  }
}

describe("Club authentication contracts", () => {
  const serverSource = readServerSource();
  const webSource = readWebSource();

  it("emits a consistent 401-style unauthorized error for club access", () => {
    assert.match(serverSource, /const CLUB_AUTH_REQUIRED_MESSAGE = "401 Unauthorized: authentication required for club access";/);
    assert.match(serverSource, /function emitClubUnauthorized\(socket: Socket, reason\?: string\): void \{[\s\S]*CLUB_AUTH_REQUIRED_MESSAGE[\s\S]*code: "UNAUTHORIZED"/);
  });

  it("guards club API handlers behind requireClubAuth", () => {
    assert.match(serverSource, /socket\.on\("club_create"[\s\S]*if \(!requireClubAuth\(\)\) return;/);
    assert.match(serverSource, /socket\.on\("club_wallet_admin_adjust"[\s\S]*if \(!requireClubAuth\(\)\) return;/);
    assert.match(serverSource, /socket\.on\("club_leaderboard_get"[\s\S]*if \(!requireClubAuth\(\)\) return;/);
  });

  it("guards join/observe APIs when the target table belongs to a club", () => {
    assert.match(serverSource, /socket\.on\("join_room_code"[\s\S]*if \(clubInfo && !requireClubAuth\(\)\) \{/);
    assert.match(serverSource, /socket\.on\("join_table"[\s\S]*if \(clubInfo && !requireClubAuth\(\)\) \{/);
    assert.match(serverSource, /socket\.on\("request_table_snapshot"[\s\S]*if \(clubInfo && !requireClubAuth\(\)\) \{/);
    assert.match(serverSource, /socket\.on\("request_room_state"[\s\S]*if \(clubInfo && !requireClubAuth\(\)\) \{/);
  });

  it("gates /clubs in the UI and disables guest entry for club routes", () => {
    assert.match(webSource, /const canAccessClubs = .*Boolean\(authSession && !authSession\.isGuest\);/);
    assert.match(webSource, /if \(!authSession\) \{[\s\S]*disableGuest=\{.*location\.pathname\.startsWith\("\/clubs"\)\}/);
    assert.match(webSource, /if \(view === "clubs" && !canAccessClubs\) \{[\s\S]*<AuthScreen[\s\S]*disableGuest[\s\S]*gateMessage="Club access requires a logged-in account\."/);
  });
});
