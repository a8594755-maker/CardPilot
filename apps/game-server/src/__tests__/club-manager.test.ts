import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { ClubManager } from "../club-manager.js";
import { DEFAULT_CLUB_RULES } from "@cardpilot/shared-types";
import { requireActiveClubMember } from "../services/club-service.js";

describe("ClubManager — club lifecycle", () => {
  it("creates a club and owner is an active member with owner role", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "u1",
      ownerDisplayName: "Alice",
      name: "Test Club",
      description: "A test club",
    });

    assert.ok(club.id);
    assert.ok(club.code);
    assert.equal(club.name, "Test Club");
    assert.equal(club.ownerUserId, "u1");
    assert.equal(club.visibility, "private");
    assert.equal(club.requireApprovalToJoin, true);

    const member = mgr.getMember(club.id, "u1");
    assert.ok(member);
    assert.equal(member!.role, "owner");
    assert.equal(member!.status, "active");
  });

  it("lists clubs for a user", () => {
    const mgr = new ClubManager();
    mgr.createClub({ ownerUserId: "u1", ownerDisplayName: "Alice", name: "Club A" });
    mgr.createClub({ ownerUserId: "u1", ownerDisplayName: "Alice", name: "Club B" });

    const list = mgr.listMyClubs("u1");
    assert.equal(list.length, 2);
    assert.ok(list.some((c) => c.name === "Club A"));
    assert.ok(list.some((c) => c.name === "Club B"));
  });

  it("updates club settings with admin permission", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({ ownerUserId: "u1", ownerDisplayName: "Alice", name: "Old Name" });

    const updated = mgr.updateClub(club.id, "u1", { name: "New Name", description: "Updated" });
    assert.ok(updated);
    assert.equal(updated!.name, "New Name");
    assert.equal(updated!.description, "Updated");
  });

  it("rejects club update from non-admin", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({ ownerUserId: "u1", ownerDisplayName: "Alice", name: "Club" });

    // Add a regular member
    mgr.requestJoin(club.code, "u2", "Bob");
    // Bob is auto-joined since requireApprovalToJoin is true, so he's pending
    // He can't update
    const result = mgr.updateClub(club.id, "u2", { name: "Hacked" });
    assert.equal(result, null);
  });
});

describe("Club membership gates — server integration contracts", () => {
  it("non-member is denied by join_room_code gate for club tables", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "owner",
      ownerDisplayName: "Owner",
      name: "Gate Club",
      requireApprovalToJoin: false,
    });
    const table = mgr.createTable(club.id, "owner", "Main")!;
    mgr.setTableRoomCode(club.id, table.clubTable.id, "CLB001");

    const clubInfo = mgr.getClubForTable("CLB001");
    assert.ok(clubInfo);
    assert.equal(mgr.isActiveMember(clubInfo!.clubId, "stranger"), false);
  });

  it("active member is allowed by join_table gate for club tables", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "owner",
      ownerDisplayName: "Owner",
      name: "Gate Club",
      requireApprovalToJoin: false,
    });
    mgr.requestJoin(club.code, "member1", "Member One");

    const table = mgr.createTable(club.id, "owner", "Main")!;
    mgr.setTableRoomCode(club.id, table.clubTable.id, "CLB002");
    const clubInfo = mgr.getClubForTable("CLB002");

    assert.ok(clubInfo);
    assert.equal(mgr.isActiveMember(clubInfo!.clubId, "member1"), true);
  });

  it("pending member is denied by join gates until approved", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "owner",
      ownerDisplayName: "Owner",
      name: "Approval Club",
      requireApprovalToJoin: true,
    });
    mgr.requestJoin(club.code, "u2", "Pending User");

    const table = mgr.createTable(club.id, "owner", "Main")!;
    mgr.setTableRoomCode(club.id, table.clubTable.id, "CLB003");
    const clubInfo = mgr.getClubForTable("CLB003");

    assert.ok(clubInfo);
    assert.equal(mgr.isActiveMember(clubInfo!.clubId, "u2"), false);
  });

  it("public lobby snapshot contract excludes private/club tables", () => {
    const source = readFileSync(resolve(process.cwd(), "src/server.ts"), "utf-8");
    assert.match(source, /\.filter\(\(room\) => room\.status === "OPEN" && room\.visibility === "public"\)/);
  });
});

describe("ClubManager — membership flows", () => {
  it("join without approval when requireApprovalToJoin=false", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "u1",
      ownerDisplayName: "Alice",
      name: "Open Club",
      requireApprovalToJoin: false,
    });

    const result = mgr.requestJoin(club.code, "u2", "Bob");
    assert.equal(result.status, "joined");
    assert.ok(mgr.isActiveMember(club.id, "u2"));
  });

  it("join with approval required — member starts as pending", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "u1",
      ownerDisplayName: "Alice",
      name: "Private Club",
      requireApprovalToJoin: true,
    });

    const result = mgr.requestJoin(club.code, "u2", "Bob");
    assert.equal(result.status, "pending");
    assert.equal(mgr.isActiveMember(club.id, "u2"), false);

    const member = mgr.getMember(club.id, "u2");
    assert.equal(member!.status, "pending");
  });

  it("approve join request", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "u1",
      ownerDisplayName: "Alice",
      name: "Approval Club",
    });

    mgr.requestJoin(club.code, "u2", "Bob");
    const approved = mgr.approveJoin(club.id, "u1", "u2");
    assert.ok(approved);
    assert.equal(approved!.status, "active");
    assert.ok(mgr.isActiveMember(club.id, "u2"));
  });

  it("reject join request", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "u1",
      ownerDisplayName: "Alice",
      name: "Rejection Club",
    });

    mgr.requestJoin(club.code, "u2", "Bob");
    const rejected = mgr.rejectJoin(club.id, "u1", "u2");
    assert.equal(rejected, true);
    assert.equal(mgr.getMember(club.id, "u2"), null);
  });

  it("join via invite code bypasses approval", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "u1",
      ownerDisplayName: "Alice",
      name: "Invite Club",
      requireApprovalToJoin: true,
    });

    const invite = mgr.createInvite(club.id, "u1", 10, 24);
    assert.ok(invite);

    const result = mgr.requestJoin(club.code, "u2", "Bob", invite!.inviteCode);
    assert.equal(result.status, "joined");
    assert.ok(mgr.isActiveMember(club.id, "u2"));
  });

  it("cannot join if banned", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "u1",
      ownerDisplayName: "Alice",
      name: "Ban Club",
      requireApprovalToJoin: false,
    });

    mgr.requestJoin(club.code, "u2", "Bob");
    mgr.banMember(club.id, "u1", "u2", "Test ban");

    const result = mgr.requestJoin(club.code, "u2", "Bob");
    assert.equal(result.status, "error");
    assert.ok(result.message.includes("banned"));
  });

  it("already a member returns error", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "u1",
      ownerDisplayName: "Alice",
      name: "Dupe Club",
      requireApprovalToJoin: false,
    });

    mgr.requestJoin(club.code, "u2", "Bob");
    const result = mgr.requestJoin(club.code, "u2", "Bob");
    assert.equal(result.status, "error");
    assert.ok(result.message.includes("Already"));
  });
});

describe("ClubManager — permission enforcement", () => {
  function setupClubWithMembers() {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "owner",
      ownerDisplayName: "Owner",
      name: "Permission Club",
      requireApprovalToJoin: false,
    });

    mgr.requestJoin(club.code, "admin1", "Admin");
    mgr.updateMemberRole(club.id, "owner", "admin1", "admin");

    mgr.requestJoin(club.code, "mod1", "Mod");
    mgr.updateMemberRole(club.id, "owner", "mod1", "mod");

    mgr.requestJoin(club.code, "host1", "Host");
    mgr.updateMemberRole(club.id, "owner", "host1", "host");

    mgr.requestJoin(club.code, "member1", "Member");

    return { mgr, club };
  }

  it("owner can promote to admin", () => {
    const { mgr, club } = setupClubWithMembers();
    const updated = mgr.updateMemberRole(club.id, "owner", "member1", "admin");
    assert.ok(updated);
    assert.equal(updated!.role, "admin");
  });

  it("admin cannot promote to admin (only owner can)", () => {
    const { mgr, club } = setupClubWithMembers();
    const updated = mgr.updateMemberRole(club.id, "admin1", "member1", "admin");
    assert.equal(updated, null);
  });

  it("admin can promote to mod/host", () => {
    const { mgr, club } = setupClubWithMembers();
    const updated = mgr.updateMemberRole(club.id, "admin1", "member1", "mod");
    assert.ok(updated);
    assert.equal(updated!.role, "mod");
  });

  it("mod cannot change roles", () => {
    const { mgr, club } = setupClubWithMembers();
    const updated = mgr.updateMemberRole(club.id, "mod1", "member1", "host");
    assert.equal(updated, null);
  });

  it("member cannot kick anyone", () => {
    const { mgr, club } = setupClubWithMembers();
    const ok = mgr.kickMember(club.id, "member1", "mod1");
    assert.equal(ok, false);
  });

  it("mod can kick member", () => {
    const { mgr, club } = setupClubWithMembers();
    const ok = mgr.kickMember(club.id, "mod1", "member1");
    assert.equal(ok, true);
    assert.equal(mgr.isActiveMember(club.id, "member1"), false);
  });

  it("mod cannot kick admin (higher rank)", () => {
    const { mgr, club } = setupClubWithMembers();
    const ok = mgr.kickMember(club.id, "mod1", "admin1");
    assert.equal(ok, false);
  });

  it("cannot kick owner", () => {
    const { mgr, club } = setupClubWithMembers();
    const ok = mgr.kickMember(club.id, "admin1", "owner");
    assert.equal(ok, false);
  });

  it("ban and unban flow", () => {
    const { mgr, club } = setupClubWithMembers();
    const banned = mgr.banMember(club.id, "admin1", "member1", "Bad behavior");
    assert.equal(banned, true);
    assert.equal(mgr.isBanned(club.id, "member1"), true);

    const unbanned = mgr.unbanMember(club.id, "admin1", "member1");
    assert.equal(unbanned, true);
    assert.equal(mgr.isBanned(club.id, "member1"), false);
  });

  it("host can create tables", () => {
    const { mgr, club } = setupClubWithMembers();
    const result = mgr.createTable(club.id, "host1", "Host Table");
    assert.ok(result);
    assert.equal(result!.clubTable.name, "Host Table");
  });

  it("member cannot create tables", () => {
    const { mgr, club } = setupClubWithMembers();
    const result = mgr.createTable(club.id, "member1", "Illegal Table");
    assert.equal(result, null);
  });

  it("non-member cannot access club detail", () => {
    const { mgr, club } = setupClubWithMembers();
    const detail = mgr.getClubDetail(club.id, "stranger");
    assert.equal(detail, null);
  });

  it("pending member cannot access club detail", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "owner",
      ownerDisplayName: "Owner",
      name: "Pending Test",
      requireApprovalToJoin: true,
    });

    mgr.requestJoin(club.code, "pending_user", "Pending");
    const detail = mgr.getClubDetail(club.id, "pending_user");
    assert.equal(detail, null);
  });
});

describe("ClubManager — rulesets", () => {
  it("creates a ruleset and sets as default", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({ ownerUserId: "u1", ownerDisplayName: "Alice", name: "Rules Club" });

    const ruleset = mgr.createRuleset(club.id, "u1", "Standard", { ...DEFAULT_CLUB_RULES }, true);
    assert.ok(ruleset);
    assert.equal(ruleset!.isDefault, true);
    assert.equal(ruleset!.name, "Standard");

    // Club should point to this ruleset
    const detail = mgr.getClubDetail(club.id, "u1");
    assert.ok(detail);
    assert.equal(detail!.detail.defaultRuleset?.id, ruleset!.id);
  });

  it("enforces preventDealMidHand=true invariant", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({ ownerUserId: "u1", ownerDisplayName: "Alice", name: "Invariant Club" });

    const rules = { ...DEFAULT_CLUB_RULES, dealing: { ...DEFAULT_CLUB_RULES.dealing, preventDealMidHand: false } };
    const ruleset = mgr.createRuleset(club.id, "u1", "Bad Rules", rules);
    assert.ok(ruleset);
    // Server must enforce this invariant
    assert.equal(ruleset!.rulesJson.dealing.preventDealMidHand, true);
  });

  it("enforces maxSeats 2-9 range", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({ ownerUserId: "u1", ownerDisplayName: "Alice", name: "Seats Club" });

    const rules = { ...DEFAULT_CLUB_RULES, maxSeats: 15 };
    const ruleset = mgr.createRuleset(club.id, "u1", "Too Many Seats", rules);
    assert.ok(ruleset);
    assert.equal(ruleset!.rulesJson.maxSeats, 9);
  });
});

describe("ClubManager — invites", () => {
  it("creates and revokes invites", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({ ownerUserId: "u1", ownerDisplayName: "Alice", name: "Invite Club" });

    const invite = mgr.createInvite(club.id, "u1", 5, 48);
    assert.ok(invite);
    assert.ok(invite!.inviteCode);
    assert.equal(invite!.maxUses, 5);
    assert.equal(invite!.usesCount, 0);

    const revoked = mgr.revokeInvite(club.id, "u1", invite!.id);
    assert.equal(revoked, true);
  });

  it("member cannot create invites", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "u1",
      ownerDisplayName: "Alice",
      name: "Restricted Invite",
      requireApprovalToJoin: false,
    });

    mgr.requestJoin(club.code, "u2", "Bob"); // joins as member
    const invite = mgr.createInvite(club.id, "u2");
    assert.equal(invite, null);
  });

  it("expired invite code is rejected", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "u1",
      ownerDisplayName: "Alice",
      name: "Expired Invite Club",
      requireApprovalToJoin: true,
    });

    // Create an invite that expired in the past
    const invite = mgr.createInvite(club.id, "u1", 10, -1); // negative hours = already expired
    assert.ok(invite);

    const result = mgr.requestJoin(club.code, "u2", "Bob", invite!.inviteCode);
    assert.equal(result.status, "error");
    assert.ok(result.message.includes("expired"));
  });
});

describe("ClubManager — tables", () => {
  it("creates a table and can close it", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({ ownerUserId: "u1", ownerDisplayName: "Alice", name: "Table Club" });

    const result = mgr.createTable(club.id, "u1", "Main Table");
    assert.ok(result);
    assert.equal(result!.clubTable.status, "open");

    const closed = mgr.closeTable(club.id, "u1", result!.clubTable.id);
    assert.equal(closed, true);
  });

  it("pause table", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({ ownerUserId: "u1", ownerDisplayName: "Alice", name: "Pause Club" });

    const result = mgr.createTable(club.id, "u1", "Pausable");
    assert.ok(result);

    const paused = mgr.pauseTable(club.id, "u1", result!.clubTable.id);
    assert.equal(paused, true);
  });

  it("getClubForTable resolves by room code", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({ ownerUserId: "u1", ownerDisplayName: "Alice", name: "Lookup Club" });

    const result = mgr.createTable(club.id, "u1", "Lookup Table");
    assert.ok(result);

    mgr.setTableRoomCode(club.id, result!.clubTable.id, "ROOM123");
    const found = mgr.getClubForTable("ROOM123");
    assert.ok(found);
    assert.equal(found!.clubId, club.id);
  });

  it("isActiveMember correctly checks club membership for table access", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "u1",
      ownerDisplayName: "Alice",
      name: "Access Club",
      requireApprovalToJoin: true,
    });

    // Non-member cannot access
    assert.equal(mgr.isActiveMember(club.id, "stranger"), false);

    // Pending member cannot access
    mgr.requestJoin(club.code, "u2", "Bob");
    assert.equal(mgr.isActiveMember(club.id, "u2"), false);

    // Approved member can access
    mgr.approveJoin(club.id, "u1", "u2");
    assert.equal(mgr.isActiveMember(club.id, "u2"), true);

    // Banned member cannot access
    mgr.banMember(club.id, "u1", "u2", "Banned");
    assert.equal(mgr.isActiveMember(club.id, "u2"), false);
  });
});

describe("ClubManager — club table access enforcement", () => {
  it("creating a club generates unique code and creates OWNER membership", () => {
    const mgr = new ClubManager();
    const club1 = mgr.createClub({ ownerUserId: "u1", ownerDisplayName: "Alice", name: "Club 1" });
    const club2 = mgr.createClub({ ownerUserId: "u2", ownerDisplayName: "Bob", name: "Club 2" });

    assert.ok(club1.code);
    assert.ok(club2.code);
    assert.notEqual(club1.code, club2.code, "Club codes must be unique");
    assert.equal(club1.code.length, 6);

    const owner1 = mgr.getMember(club1.id, "u1");
    assert.ok(owner1);
    assert.equal(owner1!.role, "owner");
    assert.equal(owner1!.status, "active");
  });

  it("joining by code creates MEMBER row idempotently", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "u1",
      ownerDisplayName: "Alice",
      name: "Idempotent Join Club",
      requireApprovalToJoin: false,
    });

    const result1 = mgr.requestJoin(club.code, "u2", "Bob");
    assert.equal(result1.status, "joined");

    // Second join attempt should return error (already member) — idempotent safety
    const result2 = mgr.requestJoin(club.code, "u2", "Bob");
    assert.equal(result2.status, "error");
    assert.ok(result2.message.includes("Already"));

    const member = mgr.getMember(club.id, "u2");
    assert.equal(member!.role, "member");
  });

  it("non-member cannot list club tables (via getClubDetail)", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "u1",
      ownerDisplayName: "Alice",
      name: "Table Access Club",
    });

    mgr.createTable(club.id, "u1", "Owner Table");

    // Non-member trying to get club detail (which includes tables)
    const detail = mgr.getClubDetail(club.id, "stranger");
    assert.equal(detail, null, "Non-member should not get club detail or table list");
  });

  it("non-admin/non-host cannot create club table", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "u1",
      ownerDisplayName: "Alice",
      name: "Restricted Table Club",
      requireApprovalToJoin: false,
    });

    mgr.requestJoin(club.code, "u2", "Bob"); // joins as member

    // Regular member cannot create table (requires host+ role)
    const result = mgr.createTable(club.id, "u2", "Illegal Table");
    assert.equal(result, null, "Regular member should not be able to create a table");

    // Non-member cannot create table
    const result2 = mgr.createTable(club.id, "stranger", "Outsider Table");
    assert.equal(result2, null, "Non-member should not be able to create a table");
  });

  it("club tables should be identifiable via getClubForTable after setting room code", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "u1",
      ownerDisplayName: "Alice",
      name: "Isolation Club",
    });

    const result = mgr.createTable(club.id, "u1", "Private Table");
    assert.ok(result);

    // Before room code set — not findable
    const before = mgr.getClubForTable("ROOM_XYZ");
    assert.equal(before, null);

    // After room code set — findable
    mgr.setTableRoomCode(club.id, result!.clubTable.id, "ROOM_XYZ");
    const after = mgr.getClubForTable("ROOM_XYZ");
    assert.ok(after);
    assert.equal(after!.clubId, club.id);

    // isActiveMember correctly gates access
    assert.equal(mgr.isActiveMember(club.id, "u1"), true, "Owner should be active member");
    assert.equal(mgr.isActiveMember(club.id, "stranger"), false, "Non-member should not be active");
  });
});

describe("ClubService — requireActiveClubMember gate", () => {
  it("returns NOT_CLUB_TABLE for non-club room codes", () => {
    const mgr = new ClubManager();
    const result = requireActiveClubMember(mgr, "RANDOM_CODE", "u1");
    assert.equal(result.allowed, false);
    if (!result.allowed) {
      assert.equal(result.code, "NOT_CLUB_TABLE");
    }
  });

  it("returns NOT_MEMBER for non-members on club tables", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "owner",
      ownerDisplayName: "Owner",
      name: "Gate Club",
      requireApprovalToJoin: true,
    });
    const table = mgr.createTable(club.id, "owner", "Gated Table")!;
    mgr.setTableRoomCode(club.id, table.clubTable.id, "GATE001");

    const result = requireActiveClubMember(mgr, "GATE001", "stranger");
    assert.equal(result.allowed, false);
    if (!result.allowed) {
      assert.equal(result.code, "NOT_MEMBER");
    }
  });

  it("returns PENDING for pending members", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "owner",
      ownerDisplayName: "Owner",
      name: "Pending Gate Club",
      requireApprovalToJoin: true,
    });
    mgr.requestJoin(club.code, "u2", "Pending User");
    const table = mgr.createTable(club.id, "owner", "Gated Table")!;
    mgr.setTableRoomCode(club.id, table.clubTable.id, "GATE002");

    const result = requireActiveClubMember(mgr, "GATE002", "u2");
    assert.equal(result.allowed, false);
    if (!result.allowed) {
      assert.equal(result.code, "PENDING");
    }
  });

  it("returns BANNED for banned members", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "owner",
      ownerDisplayName: "Owner",
      name: "Ban Gate Club",
      requireApprovalToJoin: false,
    });
    mgr.requestJoin(club.code, "u2", "User");
    mgr.banMember(club.id, "owner", "u2", "Test ban");
    const table = mgr.createTable(club.id, "owner", "Gated Table")!;
    mgr.setTableRoomCode(club.id, table.clubTable.id, "GATE003");

    const result = requireActiveClubMember(mgr, "GATE003", "u2");
    assert.equal(result.allowed, false);
    if (!result.allowed) {
      assert.equal(result.code, "BANNED");
    }
  });

  it("returns allowed:true for active members", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "owner",
      ownerDisplayName: "Owner",
      name: "Active Gate Club",
      requireApprovalToJoin: false,
    });
    mgr.requestJoin(club.code, "u2", "Active User");
    const table = mgr.createTable(club.id, "owner", "Gated Table")!;
    mgr.setTableRoomCode(club.id, table.clubTable.id, "GATE004");

    const result = requireActiveClubMember(mgr, "GATE004", "u2");
    assert.equal(result.allowed, true);
    if (result.allowed) {
      assert.equal(result.clubId, club.id);
      assert.equal(result.member.userId, "u2");
      assert.equal(result.member.status, "active");
    }
  });

  it("full approval workflow: pending -> approved -> can join table", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "owner",
      ownerDisplayName: "Owner",
      name: "Workflow Club",
      requireApprovalToJoin: true,
    });
    const table = mgr.createTable(club.id, "owner", "Workflow Table")!;
    mgr.setTableRoomCode(club.id, table.clubTable.id, "WFLOW01");

    // Step 1: Request join (pending)
    mgr.requestJoin(club.code, "u2", "Applicant");
    const r1 = requireActiveClubMember(mgr, "WFLOW01", "u2");
    assert.equal(r1.allowed, false);
    if (!r1.allowed) assert.equal(r1.code, "PENDING");

    // Step 2: Approve
    mgr.approveJoin(club.id, "owner", "u2");
    const r2 = requireActiveClubMember(mgr, "WFLOW01", "u2");
    assert.equal(r2.allowed, true);
  });
});

describe("ClubManager — hydrate/persist interface", () => {
  it("setRepo accepts a repo and hydrate runs without error when no repo", async () => {
    const mgr = new ClubManager();
    // hydrate without repo should be a no-op
    await mgr.hydrate();
    // Should still work as empty in-memory store
    const clubs = mgr.listMyClubs("anyone");
    assert.deepEqual(clubs, []);
  });

  it("setRepo + createClub triggers persistence (no error without real DB)", () => {
    const mgr = new ClubManager();
    // Create a mock repo that's disabled
    const mockRepo = { enabled: () => false, hydrateAll: async () => ({ clubs: [], members: [], invites: [], rulesets: [], tables: [] }), createClub: async () => {}, upsertMember: async () => {}, appendAudit: async () => {} } as any;
    mgr.setRepo(mockRepo);

    // Creating a club should not throw even with disabled repo
    const club = mgr.createClub({
      ownerUserId: "u1",
      ownerDisplayName: "Alice",
      name: "Persist Test Club",
    });
    assert.ok(club.id);
    assert.ok(club.code);
  });
});

describe("ClubManager — audit log", () => {
  it("records audit entries for club actions", () => {
    const mgr = new ClubManager();
    const club = mgr.createClub({
      ownerUserId: "u1",
      ownerDisplayName: "Alice",
      name: "Audit Club",
      requireApprovalToJoin: false,
    });

    mgr.requestJoin(club.code, "u2", "Bob");
    mgr.updateMemberRole(club.id, "u1", "u2", "mod");
    mgr.kickMember(club.id, "u1", "u2");

    const detail = mgr.getClubDetail(club.id, "u1");
    assert.ok(detail);
    // Should have: club_created, member_joined, role_changed, member_kicked
    assert.ok(detail!.auditLog.length >= 4);
    const types = detail!.auditLog.map((e) => e.actionType);
    assert.ok(types.includes("club_created"));
    assert.ok(types.includes("member_joined"));
    assert.ok(types.includes("role_changed"));
    assert.ok(types.includes("member_kicked"));
  });
});
