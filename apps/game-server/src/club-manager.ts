import { randomUUID } from "node:crypto";
import type {
  Club,
  ClubMember,
  ClubInvite,
  ClubRuleset,
  ClubTable,
  ClubAuditLogEntry,
  ClubDetail,
  ClubListItem,
  ClubRules,
  ClubRole,
  ClubMemberStatus,
  ClubVisibility,
  ClubTableStatus,
} from "@cardpilot/shared-types";
import { canPerformClubAction, hasClubPermission, DEFAULT_CLUB_RULES } from "@cardpilot/shared-types";
import { logError, logInfo, logWarn } from "./logger";

// ── In-memory store (mirrors DB; authoritative for real-time) ──

interface ClubState {
  club: Club;
  members: Map<string, ClubMember>; // userId -> member
  invites: Map<string, ClubInvite>; // inviteId -> invite
  rulesets: Map<string, ClubRuleset>; // rulesetId -> ruleset
  tables: Map<string, ClubTable>; // clubTableId -> table
  auditLog: ClubAuditLogEntry[];
}

const CLUB_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
const INVITE_CODE_CHARS = "abcdefghjkmnpqrstuvwxyz23456789";

function generateCode(len: number, chars: string): string {
  let code = "";
  for (let i = 0; i < len; i++) {
    code += chars[Math.floor(Math.random() * chars.length)];
  }
  return code;
}

export class ClubManager {
  private clubs = new Map<string, ClubState>(); // clubId -> state
  private clubByCode = new Map<string, string>(); // club code -> clubId
  private inviteCodeToClub = new Map<string, string>(); // invite code -> clubId
  private userClubs = new Map<string, Set<string>>(); // userId -> set of clubIds

  // ═══════════════ CLUB LIFECYCLE ═══════════════

  createClub(params: {
    ownerUserId: string;
    ownerDisplayName: string;
    name: string;
    description?: string;
    visibility?: ClubVisibility;
    requireApprovalToJoin?: boolean;
    badgeColor?: string;
  }): Club {
    const clubId = randomUUID();
    let code = generateCode(6, CLUB_CODE_CHARS);
    while (this.clubByCode.has(code)) {
      code = generateCode(6, CLUB_CODE_CHARS);
    }

    const now = new Date().toISOString();
    const club: Club = {
      id: clubId,
      code,
      name: params.name.trim().slice(0, 80),
      description: (params.description ?? "").trim().slice(0, 500),
      ownerUserId: params.ownerUserId,
      visibility: params.visibility ?? "private",
      defaultRulesetId: null,
      isArchived: false,
      requireApprovalToJoin: params.requireApprovalToJoin ?? true,
      badgeColor: params.badgeColor ?? null,
      logoUrl: null,
      createdAt: now,
      updatedAt: now,
    };

    const ownerMember: ClubMember = {
      clubId,
      userId: params.ownerUserId,
      role: "owner",
      status: "active",
      nicknameInClub: null,
      createdAt: now,
      lastSeenAt: now,
      displayName: params.ownerDisplayName,
    };

    const state: ClubState = {
      club,
      members: new Map([[params.ownerUserId, ownerMember]]),
      invites: new Map(),
      rulesets: new Map(),
      tables: new Map(),
      auditLog: [],
    };

    this.clubs.set(clubId, state);
    this.clubByCode.set(code, clubId);
    this.addUserClub(params.ownerUserId, clubId);
    this.writeAudit(clubId, params.ownerUserId, "club_created", { name: club.name });

    logInfo({ event: "club.created", clubId, code, owner: params.ownerUserId });
    return club;
  }

  updateClub(
    clubId: string,
    actorUserId: string,
    updates: {
      name?: string;
      description?: string;
      visibility?: ClubVisibility;
      requireApprovalToJoin?: boolean;
      badgeColor?: string;
      logoUrl?: string | null;
    },
  ): Club | null {
    const state = this.clubs.get(clubId);
    if (!state) return null;

    const actor = state.members.get(actorUserId);
    if (!actor || actor.status !== "active" || !hasClubPermission(actor.role, "admin")) {
      return null;
    }

    const club = state.club;
    if (updates.name !== undefined) club.name = updates.name.trim().slice(0, 80);
    if (updates.description !== undefined) club.description = updates.description.trim().slice(0, 500);
    if (updates.visibility !== undefined) club.visibility = updates.visibility;
    if (updates.requireApprovalToJoin !== undefined) club.requireApprovalToJoin = updates.requireApprovalToJoin;
    if (updates.badgeColor !== undefined) club.badgeColor = updates.badgeColor;
    if (updates.logoUrl !== undefined) club.logoUrl = updates.logoUrl;
    club.updatedAt = new Date().toISOString();

    this.writeAudit(clubId, actorUserId, "club_updated", updates);
    return { ...club };
  }

  // ═══════════════ MEMBERSHIP ═══════════════

  requestJoin(
    clubCode: string,
    userId: string,
    displayName: string,
    inviteCode?: string,
  ): { status: "joined" | "pending" | "error"; message: string; clubId?: string } {
    // Resolve club by invite code first, then club code
    let clubId: string | undefined;
    let usedInvite: ClubInvite | undefined;

    if (inviteCode) {
      const invClubId = this.inviteCodeToClub.get(inviteCode);
      if (invClubId) {
        const state = this.clubs.get(invClubId);
        if (state) {
          for (const inv of state.invites.values()) {
            if (inv.inviteCode === inviteCode && !inv.revoked) {
              if (inv.expiresAt && new Date(inv.expiresAt) < new Date()) {
                return { status: "error", message: "Invite code has expired" };
              }
              if (inv.maxUses != null && inv.usesCount >= inv.maxUses) {
                return { status: "error", message: "Invite code has reached max uses" };
              }
              usedInvite = inv;
              clubId = invClubId;
              break;
            }
          }
        }
      }
    }

    if (!clubId) {
      clubId = this.clubByCode.get(clubCode.toUpperCase());
    }

    if (!clubId) {
      return { status: "error", message: "Club not found" };
    }

    const state = this.clubs.get(clubId);
    if (!state) return { status: "error", message: "Club not found" };

    if (state.club.isArchived) {
      return { status: "error", message: "Club is archived" };
    }

    // Check if already a member
    const existing = state.members.get(userId);
    if (existing) {
      if (existing.status === "active") return { status: "error", message: "Already a member" };
      if (existing.status === "banned") return { status: "error", message: "You are banned from this club" };
      if (existing.status === "pending") return { status: "pending", message: "Your join request is pending approval", clubId };
    }

    const now = new Date().toISOString();
    const skipApproval = !!usedInvite || !state.club.requireApprovalToJoin;

    const member: ClubMember = {
      clubId,
      userId,
      role: "member",
      status: skipApproval ? "active" : "pending",
      nicknameInClub: null,
      createdAt: now,
      lastSeenAt: now,
      displayName,
    };

    state.members.set(userId, member);

    if (usedInvite) {
      usedInvite.usesCount += 1;
    }

    if (skipApproval) {
      this.addUserClub(userId, clubId);
      this.writeAudit(clubId, userId, "member_joined", { displayName, inviteUsed: !!usedInvite });
      return { status: "joined", message: `Welcome to ${state.club.name}!`, clubId };
    } else {
      this.writeAudit(clubId, userId, "join_requested", { displayName });
      return { status: "pending", message: "Your join request has been submitted for approval", clubId };
    }
  }

  approveJoin(clubId: string, actorUserId: string, targetUserId: string): ClubMember | null {
    const state = this.clubs.get(clubId);
    if (!state) return null;

    const actor = state.members.get(actorUserId);
    if (!actor || actor.status !== "active" || !canPerformClubAction(actor.role, "approve_joins")) {
      return null;
    }

    const target = state.members.get(targetUserId);
    if (!target || target.status !== "pending") return null;

    target.status = "active";
    target.lastSeenAt = new Date().toISOString();
    this.addUserClub(targetUserId, clubId);
    this.writeAudit(clubId, actorUserId, "join_approved", { targetUserId, targetName: target.displayName });
    return { ...target };
  }

  rejectJoin(clubId: string, actorUserId: string, targetUserId: string): boolean {
    const state = this.clubs.get(clubId);
    if (!state) return false;

    const actor = state.members.get(actorUserId);
    if (!actor || actor.status !== "active" || !canPerformClubAction(actor.role, "approve_joins")) {
      return false;
    }

    const target = state.members.get(targetUserId);
    if (!target || target.status !== "pending") return false;

    state.members.delete(targetUserId);
    this.writeAudit(clubId, actorUserId, "join_rejected", { targetUserId, targetName: target.displayName });
    return true;
  }

  updateMemberRole(clubId: string, actorUserId: string, targetUserId: string, newRole: ClubRole): ClubMember | null {
    const state = this.clubs.get(clubId);
    if (!state) return null;

    const actor = state.members.get(actorUserId);
    if (!actor || actor.status !== "active" || !canPerformClubAction(actor.role, "manage_members")) {
      return null;
    }

    // Only owner can promote to admin; can't change owner role
    if (newRole === "owner") return null;
    if (newRole === "admin" && actor.role !== "owner") return null;

    const target = state.members.get(targetUserId);
    if (!target || target.status !== "active") return null;
    if (target.role === "owner") return null; // Can't demote owner

    const oldRole = target.role;
    target.role = newRole;
    this.writeAudit(clubId, actorUserId, "role_changed", {
      targetUserId,
      targetName: target.displayName,
      oldRole,
      newRole,
    });
    return { ...target };
  }

  kickMember(clubId: string, actorUserId: string, targetUserId: string): boolean {
    const state = this.clubs.get(clubId);
    if (!state) return false;

    const actor = state.members.get(actorUserId);
    if (!actor || actor.status !== "active" || !canPerformClubAction(actor.role, "ban")) {
      return false;
    }

    const target = state.members.get(targetUserId);
    if (!target || target.status !== "active") return false;
    if (target.role === "owner") return false;
    // Can't kick someone of equal or higher rank
    if (!hasClubPermission(actor.role, target.role)) return false;

    target.status = "left";
    this.removeUserClub(targetUserId, clubId);
    this.writeAudit(clubId, actorUserId, "member_kicked", { targetUserId, targetName: target.displayName });
    return true;
  }

  banMember(
    clubId: string,
    actorUserId: string,
    targetUserId: string,
    reason?: string,
    expiresInHours?: number,
  ): boolean {
    const state = this.clubs.get(clubId);
    if (!state) return false;

    const actor = state.members.get(actorUserId);
    if (!actor || actor.status !== "active" || !canPerformClubAction(actor.role, "ban")) {
      return false;
    }

    const target = state.members.get(targetUserId);
    if (!target) return false;
    if (target.role === "owner") return false;
    if (!hasClubPermission(actor.role, target.role)) return false;

    target.status = "banned";
    this.removeUserClub(targetUserId, clubId);
    this.writeAudit(clubId, actorUserId, "member_banned", {
      targetUserId,
      targetName: target.displayName,
      reason: reason ?? "",
      expiresInHours,
    });
    return true;
  }

  unbanMember(clubId: string, actorUserId: string, targetUserId: string): boolean {
    const state = this.clubs.get(clubId);
    if (!state) return false;

    const actor = state.members.get(actorUserId);
    if (!actor || actor.status !== "active" || !canPerformClubAction(actor.role, "ban")) {
      return false;
    }

    const target = state.members.get(targetUserId);
    if (!target || target.status !== "banned") return false;

    target.status = "left";
    this.writeAudit(clubId, actorUserId, "member_unbanned", { targetUserId, targetName: target.displayName });
    return true;
  }

  // ═══════════════ INVITES ═══════════════

  createInvite(
    clubId: string,
    actorUserId: string,
    maxUses?: number,
    expiresInHours?: number,
  ): ClubInvite | null {
    const state = this.clubs.get(clubId);
    if (!state) return null;

    const actor = state.members.get(actorUserId);
    if (!actor || actor.status !== "active" || !canPerformClubAction(actor.role, "create_invite")) {
      return null;
    }

    let inviteCode = generateCode(8, INVITE_CODE_CHARS);
    while (this.inviteCodeToClub.has(inviteCode)) {
      inviteCode = generateCode(8, INVITE_CODE_CHARS);
    }

    const invite: ClubInvite = {
      id: randomUUID(),
      clubId,
      inviteCode,
      createdBy: actorUserId,
      expiresAt: expiresInHours ? new Date(Date.now() + expiresInHours * 3600_000).toISOString() : null,
      maxUses: maxUses ?? null,
      usesCount: 0,
      revoked: false,
      createdAt: new Date().toISOString(),
    };

    state.invites.set(invite.id, invite);
    this.inviteCodeToClub.set(inviteCode, clubId);
    this.writeAudit(clubId, actorUserId, "invite_created", { inviteCode, maxUses, expiresInHours });
    return invite;
  }

  revokeInvite(clubId: string, actorUserId: string, inviteId: string): boolean {
    const state = this.clubs.get(clubId);
    if (!state) return false;

    const actor = state.members.get(actorUserId);
    if (!actor || actor.status !== "active" || !canPerformClubAction(actor.role, "create_invite")) {
      return false;
    }

    const invite = state.invites.get(inviteId);
    if (!invite || invite.revoked) return false;

    invite.revoked = true;
    this.inviteCodeToClub.delete(invite.inviteCode);
    this.writeAudit(clubId, actorUserId, "invite_revoked", { inviteCode: invite.inviteCode });
    return true;
  }

  // ═══════════════ RULESETS ═══════════════

  createRuleset(
    clubId: string,
    actorUserId: string,
    name: string,
    rules: ClubRules,
    isDefault?: boolean,
  ): ClubRuleset | null {
    const state = this.clubs.get(clubId);
    if (!state) return null;

    const actor = state.members.get(actorUserId);
    if (!actor || actor.status !== "active" || !canPerformClubAction(actor.role, "manage_rulesets")) {
      return null;
    }

    // Enforce invariants
    rules.dealing.preventDealMidHand = true;
    rules.tableControls.canPauseMidHand = false;
    rules.tableControls.pauseAppliesAfterHand = true;
    rules.maxSeats = Math.min(9, Math.max(2, rules.maxSeats));

    const ruleset: ClubRuleset = {
      id: randomUUID(),
      clubId,
      name: name.trim().slice(0, 80),
      rulesJson: rules,
      createdBy: actorUserId,
      isDefault: isDefault ?? false,
      createdAt: new Date().toISOString(),
    };

    state.rulesets.set(ruleset.id, ruleset);

    if (ruleset.isDefault) {
      // Unset other defaults
      for (const rs of state.rulesets.values()) {
        if (rs.id !== ruleset.id) rs.isDefault = false;
      }
      state.club.defaultRulesetId = ruleset.id;
    }

    this.writeAudit(clubId, actorUserId, "ruleset_created", { rulesetId: ruleset.id, name: ruleset.name });
    return ruleset;
  }

  updateRuleset(
    clubId: string,
    actorUserId: string,
    rulesetId: string,
    updates: { name?: string; rules?: Partial<ClubRules> },
  ): ClubRuleset | null {
    const state = this.clubs.get(clubId);
    if (!state) return null;

    const actor = state.members.get(actorUserId);
    if (!actor || actor.status !== "active" || !canPerformClubAction(actor.role, "manage_rulesets")) {
      return null;
    }

    const ruleset = state.rulesets.get(rulesetId);
    if (!ruleset) return null;

    if (updates.name) ruleset.name = updates.name.trim().slice(0, 80);
    if (updates.rules) {
      ruleset.rulesJson = { ...ruleset.rulesJson, ...updates.rules };
      // Re-enforce invariants
      ruleset.rulesJson.dealing.preventDealMidHand = true;
      ruleset.rulesJson.tableControls.canPauseMidHand = false;
      ruleset.rulesJson.tableControls.pauseAppliesAfterHand = true;
      ruleset.rulesJson.maxSeats = Math.min(9, Math.max(2, ruleset.rulesJson.maxSeats));
    }

    this.writeAudit(clubId, actorUserId, "ruleset_updated", { rulesetId, name: ruleset.name });
    return { ...ruleset };
  }

  setDefaultRuleset(clubId: string, actorUserId: string, rulesetId: string): boolean {
    const state = this.clubs.get(clubId);
    if (!state) return false;

    const actor = state.members.get(actorUserId);
    if (!actor || actor.status !== "active" || !canPerformClubAction(actor.role, "manage_rulesets")) {
      return false;
    }

    const ruleset = state.rulesets.get(rulesetId);
    if (!ruleset) return false;

    for (const rs of state.rulesets.values()) {
      rs.isDefault = rs.id === rulesetId;
    }
    state.club.defaultRulesetId = rulesetId;
    this.writeAudit(clubId, actorUserId, "ruleset_set_default", { rulesetId, name: ruleset.name });
    return true;
  }

  // ═══════════════ TABLES ═══════════════

  createTable(
    clubId: string,
    actorUserId: string,
    name: string,
    rulesetId?: string,
  ): { clubTable: ClubTable; rules: ClubRules } | null {
    const state = this.clubs.get(clubId);
    if (!state) return null;

    const actor = state.members.get(actorUserId);
    if (!actor || actor.status !== "active" || !canPerformClubAction(actor.role, "create_table")) {
      return null;
    }

    // Resolve ruleset
    let ruleset: ClubRuleset | undefined;
    if (rulesetId) {
      ruleset = state.rulesets.get(rulesetId);
    }
    if (!ruleset && state.club.defaultRulesetId) {
      ruleset = state.rulesets.get(state.club.defaultRulesetId);
    }

    const rules: ClubRules = ruleset?.rulesJson ?? { ...DEFAULT_CLUB_RULES };

    const clubTable: ClubTable = {
      id: randomUUID(),
      clubId,
      roomCode: null, // Will be set by server.ts when creating the actual game room
      name: name.trim().slice(0, 80) || "Club Table",
      rulesetId: ruleset?.id ?? null,
      status: "open",
      createdBy: actorUserId,
      createdAt: new Date().toISOString(),
    };

    state.tables.set(clubTable.id, clubTable);
    this.writeAudit(clubId, actorUserId, "table_created", { tableId: clubTable.id, name: clubTable.name });
    return { clubTable, rules };
  }

  setTableRoomCode(clubId: string, clubTableId: string, roomCode: string): void {
    const state = this.clubs.get(clubId);
    if (!state) return;
    const table = state.tables.get(clubTableId);
    if (table) table.roomCode = roomCode;
  }

  closeTable(clubId: string, actorUserId: string, clubTableId: string): boolean {
    const state = this.clubs.get(clubId);
    if (!state) return false;

    const actor = state.members.get(actorUserId);
    if (!actor || actor.status !== "active") return false;

    const table = state.tables.get(clubTableId);
    if (!table || table.status === "closed") return false;

    // Host can close their own tables, admin+ can close any
    if (table.createdBy !== actorUserId && !canPerformClubAction(actor.role, "manage_tables")) {
      return false;
    }

    table.status = "closed";
    this.writeAudit(clubId, actorUserId, "table_closed", { tableId: clubTableId, name: table.name });
    return true;
  }

  pauseTable(clubId: string, actorUserId: string, clubTableId: string): boolean {
    const state = this.clubs.get(clubId);
    if (!state) return false;

    const actor = state.members.get(actorUserId);
    if (!actor || actor.status !== "active") return false;

    const table = state.tables.get(clubTableId);
    if (!table || table.status !== "open") return false;

    if (table.createdBy !== actorUserId && !canPerformClubAction(actor.role, "manage_tables")) {
      return false;
    }

    table.status = "paused";
    this.writeAudit(clubId, actorUserId, "table_paused", { tableId: clubTableId, name: table.name });
    return true;
  }

  // ═══════════════ QUERIES ═══════════════

  getClub(clubId: string): Club | null {
    return this.clubs.get(clubId)?.club ?? null;
  }

  getClubByCode(code: string): Club | null {
    const clubId = this.clubByCode.get(code.toUpperCase());
    return clubId ? this.getClub(clubId) : null;
  }

  getMember(clubId: string, userId: string): ClubMember | null {
    return this.clubs.get(clubId)?.members.get(userId) ?? null;
  }

  isActiveMember(clubId: string, userId: string): boolean {
    const m = this.getMember(clubId, userId);
    return m?.status === "active";
  }

  isBanned(clubId: string, userId: string): boolean {
    const m = this.getMember(clubId, userId);
    return m?.status === "banned";
  }

  getMemberRole(clubId: string, userId: string): ClubRole | null {
    const m = this.getMember(clubId, userId);
    return m?.status === "active" ? m.role : null;
  }

  getClubForTable(roomCode: string): { clubId: string; clubTableId: string } | null {
    for (const [clubId, state] of this.clubs) {
      for (const [tableId, table] of state.tables) {
        if (table.roomCode === roomCode && table.status !== "closed") {
          return { clubId, clubTableId: tableId };
        }
      }
    }
    return null;
  }

  getRulesForRoom(roomCode: string): ClubRules | null {
    const info = this.getClubForTable(roomCode);
    if (!info) return null;
    const state = this.clubs.get(info.clubId);
    if (!state) return null;
    const table = state.tables.get(info.clubTableId);
    if (!table) return null;

    if (table.rulesetId) {
      const rs = state.rulesets.get(table.rulesetId);
      if (rs) return rs.rulesJson;
    }
    if (state.club.defaultRulesetId) {
      const rs = state.rulesets.get(state.club.defaultRulesetId);
      if (rs) return rs.rulesJson;
    }
    return null;
  }

  listMyClubs(userId: string): ClubListItem[] {
    const clubIds = this.userClubs.get(userId);
    if (!clubIds) return [];

    const result: ClubListItem[] = [];
    for (const clubId of clubIds) {
      const state = this.clubs.get(clubId);
      if (!state) continue;
      const member = state.members.get(userId);
      if (!member || member.status !== "active") continue;

      const activeMembers = [...state.members.values()].filter((m) => m.status === "active").length;
      const openTables = [...state.tables.values()].filter((t) => t.status !== "closed").length;

      result.push({
        id: state.club.id,
        code: state.club.code,
        name: state.club.name,
        description: state.club.description,
        badgeColor: state.club.badgeColor,
        memberCount: activeMembers,
        tableCount: openTables,
        myRole: member.role,
        myStatus: member.status,
      });
    }
    return result;
  }

  getClubDetail(clubId: string, userId: string): {
    detail: ClubDetail;
    members: ClubMember[];
    invites: ClubInvite[];
    rulesets: ClubRuleset[];
    tables: ClubTable[];
    pendingMembers: ClubMember[];
    auditLog: ClubAuditLogEntry[];
  } | null {
    const state = this.clubs.get(clubId);
    if (!state) return null;

    const member = state.members.get(userId);
    if (!member || member.status !== "active") return null;

    const allMembers = [...state.members.values()];
    const activeMembers = allMembers.filter((m) => m.status === "active");
    const pendingMembers = allMembers.filter((m) => m.status === "pending");
    const openTables = [...state.tables.values()].filter((t) => t.status !== "closed");
    const invites = [...state.invites.values()].filter((i) => !i.revoked);
    const rulesets = [...state.rulesets.values()];

    let defaultRuleset: ClubRuleset | null = null;
    if (state.club.defaultRulesetId) {
      defaultRuleset = state.rulesets.get(state.club.defaultRulesetId) ?? null;
    }

    const canSeeAudit = canPerformClubAction(member.role, "view_audit_log");
    const auditLog = canSeeAudit ? state.auditLog.slice(-100) : [];

    return {
      detail: {
        club: { ...state.club },
        myMembership: { ...member },
        memberCount: activeMembers.length,
        pendingCount: pendingMembers.length,
        tableCount: openTables.length,
        defaultRuleset,
      },
      members: activeMembers.map((m) => ({ ...m })),
      invites: canPerformClubAction(member.role, "create_invite") ? invites : [],
      rulesets,
      tables: openTables.map((t) => ({ ...t })),
      pendingMembers: canPerformClubAction(member.role, "approve_joins") ? pendingMembers : [],
      auditLog,
    };
  }

  // ═══════════════ INTERNALS ═══════════════

  private addUserClub(userId: string, clubId: string): void {
    let set = this.userClubs.get(userId);
    if (!set) {
      set = new Set();
      this.userClubs.set(userId, set);
    }
    set.add(clubId);
  }

  private removeUserClub(userId: string, clubId: string): void {
    const set = this.userClubs.get(userId);
    if (set) set.delete(clubId);
  }

  private writeAudit(clubId: string, actorUserId: string, actionType: string, payload: Record<string, unknown>): void {
    const state = this.clubs.get(clubId);
    if (!state) return;

    const entry: ClubAuditLogEntry = {
      id: state.auditLog.length + 1,
      clubId,
      actorUserId,
      actionType,
      payloadJson: payload,
      createdAt: new Date().toISOString(),
    };

    state.auditLog.push(entry);
    // Keep only last 500 entries in memory
    if (state.auditLog.length > 500) {
      state.auditLog = state.auditLog.slice(-500);
    }
  }
}
