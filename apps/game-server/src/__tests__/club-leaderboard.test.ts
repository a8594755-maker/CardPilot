import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { ClubRepoJson } from "../services/club-repo-json.js";

function createRepo(): ClubRepoJson {
  const dir = mkdtempSync(join(tmpdir(), "cardpilot-leaderboard-"));
  return new ClubRepoJson(join(dir, "clubs.json"));
}

describe("Club leaderboard aggregates", () => {
  it("ranks users by net and exposes reproducible stats", async () => {
    const repo = createRepo();
    const clubId = "club-lb";

    await repo.recordClubHandStats(clubId, "u1", 1, 120);
    await repo.recordClubHandStats(clubId, "u1", 1, -20);
    await repo.recordClubHandStats(clubId, "u2", 1, 40);
    await repo.recordClubHandStats(clubId, "u3", 1, -50);

    const rows = await repo.getClubLeaderboard(clubId, "week", "net", 10);
    assert.equal(rows.length, 3);
    assert.equal(rows[0].userId, "u1");
    assert.equal(rows[0].net, 100);
    assert.equal(rows[0].rank, 1);
    assert.equal(rows[1].userId, "u2");
    assert.equal(rows[1].net, 40);
    assert.equal(rows[2].userId, "u3");
    assert.equal(rows[2].net, -50);
  });

  it("supports all-time range and includes current balance", async () => {
    const repo = createRepo();
    const clubId = "club-lb-all";

    await repo.appendWalletTx({ clubId, userId: "u1", type: "deposit", amount: 1500, createdBy: "admin" });
    await repo.appendWalletTx({ clubId, userId: "u2", type: "deposit", amount: 400, createdBy: "admin" });
    await repo.recordClubHandStats(clubId, "u1", 2, 75);
    await repo.recordClubHandStats(clubId, "u2", 2, -25);

    const rows = await repo.getClubLeaderboard(clubId, "all", "net", 10);
    assert.equal(rows.length, 2);
    assert.equal(rows[0].userId, "u1");
    assert.equal(rows[0].balance, 1500);
    assert.equal(rows[1].userId, "u2");
    assert.equal(rows[1].balance, 400);
  });
});
