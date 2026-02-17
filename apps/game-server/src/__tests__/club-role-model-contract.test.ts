import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function readClubTypesSource(): string {
  try {
    return readFileSync(resolve(process.cwd(), "../../packages/shared-types/src/club-types.ts"), "utf-8");
  } catch {
    return readFileSync(resolve(process.cwd(), "packages/shared-types/src/club-types.ts"), "utf-8");
  }
}

describe("Club role model contracts", () => {
  const source = readClubTypesSource();

  it("uses strict owner/admin/member club roles", () => {
    assert.match(source, /export type ClubRole = 'owner' \| 'admin' \| 'member';/);
  });

  it("does not grant club admin permissions to removed legacy roles", () => {
    assert.doesNotMatch(source, /hasClubPermission\(actorRole, 'mod'\)/);
    assert.doesNotMatch(source, /\| 'host' \| 'mod'/);
  });
});
