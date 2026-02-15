/**
 * Club persistence adapter — Supabase-backed CRUD for all club entities.
 * Uses the service-role client (same pattern as SupabasePersistence).
 *
 * Every public method is a no-op when Supabase is not configured,
 * allowing the server to run in offline / dev mode.
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import type {
  Club,
  ClubMember,
  ClubInvite,
  ClubRuleset,
  ClubTable,
  ClubAuditLogEntry,
  ClubRole,
  ClubMemberStatus,
  ClubVisibility,
  ClubTableStatus,
  ClubRules,
} from "@cardpilot/shared-types";
import { logError, logInfo, logWarn } from "../logger";

// ── Row ↔ Domain mappers ──────────────────────────────────────────

function rowToClub(r: Record<string, unknown>): Club {
  return {
    id: String(r.id),
    code: String(r.code),
    name: String(r.name),
    description: String(r.description ?? ""),
    ownerUserId: String(r.owner_user_id),
    visibility: (r.visibility as ClubVisibility) ?? "private",
    defaultRulesetId: r.default_ruleset_id ? String(r.default_ruleset_id) : null,
    isArchived: Boolean(r.is_archived),
    requireApprovalToJoin: Boolean(r.require_approval_to_join),
    badgeColor: r.badge_color ? String(r.badge_color) : null,
    logoUrl: r.logo_url ? String(r.logo_url) : null,
    createdAt: String(r.created_at),
    updatedAt: String(r.updated_at),
  };
}

function rowToMember(r: Record<string, unknown>): ClubMember {
  return {
    clubId: String(r.club_id),
    userId: String(r.user_id),
    role: (r.role as ClubRole) ?? "member",
    status: (r.status as ClubMemberStatus) ?? "active",
    nicknameInClub: r.nickname_in_club ? String(r.nickname_in_club) : null,
    createdAt: String(r.created_at),
    lastSeenAt: String(r.last_seen_at),
    displayName: r.display_name ? String(r.display_name) : undefined,
  };
}

function rowToInvite(r: Record<string, unknown>): ClubInvite {
  return {
    id: String(r.id),
    clubId: String(r.club_id),
    inviteCode: String(r.invite_code),
    createdBy: String(r.created_by),
    expiresAt: r.expires_at ? String(r.expires_at) : null,
    maxUses: r.max_uses != null ? Number(r.max_uses) : null,
    usesCount: Number(r.uses_count ?? 0),
    revoked: Boolean(r.revoked),
    createdAt: String(r.created_at),
  };
}

function rowToRuleset(r: Record<string, unknown>): ClubRuleset {
  return {
    id: String(r.id),
    clubId: String(r.club_id),
    name: String(r.name),
    rulesJson: (r.rules_json as ClubRules) ?? ({} as ClubRules),
    createdBy: String(r.created_by),
    isDefault: Boolean(r.is_default),
    createdAt: String(r.created_at),
  };
}

function rowToTable(r: Record<string, unknown>): ClubTable {
  return {
    id: String(r.id),
    clubId: String(r.club_id),
    roomCode: r.room_code ? String(r.room_code) : null,
    name: String(r.name),
    rulesetId: r.ruleset_id ? String(r.ruleset_id) : null,
    status: (r.status as ClubTableStatus) ?? "open",
    createdBy: String(r.created_by),
    createdAt: String(r.created_at),
  };
}

function rowToAudit(r: Record<string, unknown>): ClubAuditLogEntry {
  return {
    id: Number(r.id),
    clubId: String(r.club_id),
    actorUserId: r.actor_user_id ? String(r.actor_user_id) : null,
    actionType: String(r.action_type),
    payloadJson: (r.payload_json as Record<string, unknown>) ?? {},
    createdAt: String(r.created_at),
  };
}

// ── ClubRepo ──────────────────────────────────────────────────────

export class ClubRepo {
  private readonly db: SupabaseClient | null;

  constructor() {
    const url = process.env.SUPABASE_URL;
    const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
    this.db = url && serviceKey
      ? createClient(url, serviceKey, { auth: { persistSession: false } })
      : null;

    logInfo({
      event: "club_repo.init",
      message: this.db ? "ClubRepo connected to Supabase" : "ClubRepo running in offline mode (no Supabase)",
    });
  }

  enabled(): boolean {
    return this.db !== null;
  }

  // ═══════════════ CLUBS ═══════════════

  async createClub(club: Club): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("clubs").insert({
      id: club.id,
      code: club.code,
      name: club.name,
      description: club.description,
      owner_user_id: club.ownerUserId,
      visibility: club.visibility,
      default_ruleset_id: club.defaultRulesetId,
      is_archived: club.isArchived,
      require_approval_to_join: club.requireApprovalToJoin,
      badge_color: club.badgeColor,
      logo_url: club.logoUrl,
      created_at: club.createdAt,
      updated_at: club.updatedAt,
    });
    if (error) logWarn({ event: "club_repo.createClub.failed", message: error.message });
  }

  async updateClub(club: Club): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("clubs").update({
      name: club.name,
      description: club.description,
      visibility: club.visibility,
      default_ruleset_id: club.defaultRulesetId,
      is_archived: club.isArchived,
      require_approval_to_join: club.requireApprovalToJoin,
      badge_color: club.badgeColor,
      logo_url: club.logoUrl,
      updated_at: new Date().toISOString(),
    }).eq("id", club.id);
    if (error) logWarn({ event: "club_repo.updateClub.failed", message: error.message });
  }

  async fetchClubById(clubId: string): Promise<Club | null> {
    if (!this.db) return null;
    const { data, error } = await this.db.from("clubs").select("*").eq("id", clubId).maybeSingle();
    if (error) { logWarn({ event: "club_repo.fetchClubById.failed", message: error.message }); return null; }
    return data ? rowToClub(data) : null;
  }

  async fetchClubByCode(code: string): Promise<Club | null> {
    if (!this.db) return null;
    const { data, error } = await this.db.from("clubs").select("*").eq("code", code.toUpperCase()).maybeSingle();
    if (error) { logWarn({ event: "club_repo.fetchClubByCode.failed", message: error.message }); return null; }
    return data ? rowToClub(data) : null;
  }

  async fetchClubsByUser(userId: string): Promise<Club[]> {
    if (!this.db) return [];
    const { data, error } = await this.db
      .from("club_members")
      .select("club_id, clubs(*)")
      .eq("user_id", userId)
      .eq("status", "active");
    if (error) { logWarn({ event: "club_repo.fetchClubsByUser.failed", message: error.message }); return []; }
    return (data ?? [])
      .map((row: any) => row.clubs)
      .filter(Boolean)
      .map(rowToClub);
  }

  async isCodeUnique(code: string): Promise<boolean> {
    if (!this.db) return true;
    const { count, error } = await this.db.from("clubs").select("id", { count: "exact", head: true }).eq("code", code);
    if (error) return true; // optimistic fallback
    return (count ?? 0) === 0;
  }

  // ═══════════════ MEMBERS ═══════════════

  async upsertMember(member: ClubMember): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("club_members").upsert({
      club_id: member.clubId,
      user_id: member.userId,
      role: member.role,
      status: member.status,
      nickname_in_club: member.nicknameInClub,
      created_at: member.createdAt,
      last_seen_at: member.lastSeenAt,
    }, { onConflict: "club_id,user_id" });
    if (error) logWarn({ event: "club_repo.upsertMember.failed", message: error.message });
  }

  async updateMemberStatus(clubId: string, userId: string, status: ClubMemberStatus): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("club_members").update({
      status,
      last_seen_at: new Date().toISOString(),
    }).eq("club_id", clubId).eq("user_id", userId);
    if (error) logWarn({ event: "club_repo.updateMemberStatus.failed", message: error.message });
  }

  async updateMemberRole(clubId: string, userId: string, role: ClubRole): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("club_members").update({
      role,
      last_seen_at: new Date().toISOString(),
    }).eq("club_id", clubId).eq("user_id", userId);
    if (error) logWarn({ event: "club_repo.updateMemberRole.failed", message: error.message });
  }

  async deleteMember(clubId: string, userId: string): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("club_members").delete().eq("club_id", clubId).eq("user_id", userId);
    if (error) logWarn({ event: "club_repo.deleteMember.failed", message: error.message });
  }

  async fetchMembers(clubId: string): Promise<ClubMember[]> {
    if (!this.db) return [];
    const { data, error } = await this.db
      .from("club_members")
      .select("*, player_profiles(display_name)")
      .eq("club_id", clubId);
    if (error) { logWarn({ event: "club_repo.fetchMembers.failed", message: error.message }); return []; }
    return (data ?? []).map((row: any) => {
      const m = rowToMember(row);
      if (row.player_profiles?.display_name) {
        m.displayName = String(row.player_profiles.display_name);
      }
      return m;
    });
  }

  async fetchMember(clubId: string, userId: string): Promise<ClubMember | null> {
    if (!this.db) return null;
    const { data, error } = await this.db
      .from("club_members")
      .select("*")
      .eq("club_id", clubId)
      .eq("user_id", userId)
      .maybeSingle();
    if (error) { logWarn({ event: "club_repo.fetchMember.failed", message: error.message }); return null; }
    return data ? rowToMember(data) : null;
  }

  async touchMemberLastSeen(clubId: string, userId: string): Promise<void> {
    if (!this.db) return;
    await this.db.from("club_members").update({
      last_seen_at: new Date().toISOString(),
    }).eq("club_id", clubId).eq("user_id", userId);
  }

  // ═══════════════ INVITES ═══════════════

  async createInvite(invite: ClubInvite): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("club_invites").insert({
      id: invite.id,
      club_id: invite.clubId,
      invite_code: invite.inviteCode,
      created_by: invite.createdBy,
      expires_at: invite.expiresAt,
      max_uses: invite.maxUses,
      uses_count: invite.usesCount,
      revoked: invite.revoked,
      created_at: invite.createdAt,
    });
    if (error) logWarn({ event: "club_repo.createInvite.failed", message: error.message });
  }

  async revokeInvite(inviteId: string): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("club_invites").update({ revoked: true }).eq("id", inviteId);
    if (error) logWarn({ event: "club_repo.revokeInvite.failed", message: error.message });
  }

  async incrementInviteUses(inviteId: string): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.rpc("increment_invite_uses", { p_invite_id: inviteId });
    if (error) {
      // Fallback: read-then-write
      const { data } = await this.db.from("club_invites").select("uses_count").eq("id", inviteId).maybeSingle();
      if (data) {
        await this.db.from("club_invites").update({ uses_count: Number(data.uses_count) + 1 }).eq("id", inviteId);
      }
    }
  }

  async fetchInvites(clubId: string): Promise<ClubInvite[]> {
    if (!this.db) return [];
    const { data, error } = await this.db
      .from("club_invites")
      .select("*")
      .eq("club_id", clubId)
      .eq("revoked", false)
      .order("created_at", { ascending: false });
    if (error) { logWarn({ event: "club_repo.fetchInvites.failed", message: error.message }); return []; }
    return (data ?? []).map(rowToInvite);
  }

  async fetchInviteByCode(inviteCode: string): Promise<ClubInvite | null> {
    if (!this.db) return null;
    const { data, error } = await this.db
      .from("club_invites")
      .select("*")
      .eq("invite_code", inviteCode)
      .eq("revoked", false)
      .maybeSingle();
    if (error) { logWarn({ event: "club_repo.fetchInviteByCode.failed", message: error.message }); return null; }
    return data ? rowToInvite(data) : null;
  }

  async isInviteCodeUnique(code: string): Promise<boolean> {
    if (!this.db) return true;
    const { count, error } = await this.db.from("club_invites").select("id", { count: "exact", head: true }).eq("invite_code", code);
    if (error) return true;
    return (count ?? 0) === 0;
  }

  // ═══════════════ RULESETS ═══════════════

  async createRuleset(rs: ClubRuleset): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("club_rulesets").insert({
      id: rs.id,
      club_id: rs.clubId,
      name: rs.name,
      rules_json: rs.rulesJson,
      created_by: rs.createdBy,
      is_default: rs.isDefault,
      created_at: rs.createdAt,
    });
    if (error) logWarn({ event: "club_repo.createRuleset.failed", message: error.message });
  }

  async updateRuleset(rs: ClubRuleset): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("club_rulesets").update({
      name: rs.name,
      rules_json: rs.rulesJson,
      is_default: rs.isDefault,
    }).eq("id", rs.id);
    if (error) logWarn({ event: "club_repo.updateRuleset.failed", message: error.message });
  }

  async clearDefaultRuleset(clubId: string): Promise<void> {
    if (!this.db) return;
    await this.db.from("club_rulesets").update({ is_default: false }).eq("club_id", clubId);
  }

  async fetchRulesets(clubId: string): Promise<ClubRuleset[]> {
    if (!this.db) return [];
    const { data, error } = await this.db
      .from("club_rulesets")
      .select("*")
      .eq("club_id", clubId)
      .order("created_at", { ascending: false });
    if (error) { logWarn({ event: "club_repo.fetchRulesets.failed", message: error.message }); return []; }
    return (data ?? []).map(rowToRuleset);
  }

  // ═══════════════ TABLES ═══════════════

  async createTable(ct: ClubTable): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("club_tables").insert({
      id: ct.id,
      club_id: ct.clubId,
      room_code: ct.roomCode,
      name: ct.name,
      ruleset_id: ct.rulesetId,
      status: ct.status,
      created_by: ct.createdBy,
      created_at: ct.createdAt,
    });
    if (error) logWarn({ event: "club_repo.createTable.failed", message: error.message });
  }

  async updateTableStatus(clubTableId: string, status: ClubTableStatus): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("club_tables").update({ status }).eq("id", clubTableId);
    if (error) logWarn({ event: "club_repo.updateTableStatus.failed", message: error.message });
  }

  async setTableRoomCode(clubTableId: string, roomCode: string): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("club_tables").update({ room_code: roomCode }).eq("id", clubTableId);
    if (error) logWarn({ event: "club_repo.setTableRoomCode.failed", message: error.message });
  }

  async fetchTables(clubId: string): Promise<ClubTable[]> {
    if (!this.db) return [];
    const { data, error } = await this.db
      .from("club_tables")
      .select("*")
      .eq("club_id", clubId)
      .neq("status", "closed")
      .order("created_at", { ascending: false });
    if (error) { logWarn({ event: "club_repo.fetchTables.failed", message: error.message }); return []; }
    return (data ?? []).map(rowToTable);
  }

  async fetchTableByRoomCode(roomCode: string): Promise<ClubTable | null> {
    if (!this.db) return null;
    const { data, error } = await this.db
      .from("club_tables")
      .select("*")
      .eq("room_code", roomCode)
      .neq("status", "closed")
      .maybeSingle();
    if (error) { logWarn({ event: "club_repo.fetchTableByRoomCode.failed", message: error.message }); return null; }
    return data ? rowToTable(data) : null;
  }

  // ═══════════════ AUDIT LOG ═══════════════

  async appendAudit(entry: Omit<ClubAuditLogEntry, "id">): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("club_audit_log").insert({
      club_id: entry.clubId,
      actor_user_id: entry.actorUserId,
      action_type: entry.actionType,
      payload_json: entry.payloadJson,
      created_at: entry.createdAt,
    });
    if (error) logWarn({ event: "club_repo.appendAudit.failed", message: error.message });
  }

  async fetchAuditLog(clubId: string, limit = 100): Promise<ClubAuditLogEntry[]> {
    if (!this.db) return [];
    const { data, error } = await this.db
      .from("club_audit_log")
      .select("*")
      .eq("club_id", clubId)
      .order("created_at", { ascending: false })
      .limit(limit);
    if (error) { logWarn({ event: "club_repo.fetchAuditLog.failed", message: error.message }); return []; }
    return (data ?? []).map(rowToAudit);
  }

  // ═══════════════ BULK HYDRATION ═══════════════

  /**
   * Load all active clubs + their members/invites/rulesets/tables for server startup hydration.
   * Returns raw data for ClubManager to ingest.
   */
  async hydrateAll(): Promise<{
    clubs: Club[];
    members: ClubMember[];
    invites: ClubInvite[];
    rulesets: ClubRuleset[];
    tables: ClubTable[];
  }> {
    if (!this.db) return { clubs: [], members: [], invites: [], rulesets: [], tables: [] };

    const [clubsRes, membersRes, invitesRes, rulesetsRes, tablesRes] = await Promise.all([
      this.db.from("clubs").select("*").eq("is_archived", false),
      this.db.from("club_members").select("*, player_profiles(display_name)"),
      this.db.from("club_invites").select("*").eq("revoked", false),
      this.db.from("club_rulesets").select("*"),
      this.db.from("club_tables").select("*").neq("status", "closed"),
    ]);

    if (clubsRes.error) logWarn({ event: "club_repo.hydrateAll.clubs.failed", message: clubsRes.error.message });
    if (membersRes.error) logWarn({ event: "club_repo.hydrateAll.members.failed", message: membersRes.error.message });
    if (invitesRes.error) logWarn({ event: "club_repo.hydrateAll.invites.failed", message: invitesRes.error.message });
    if (rulesetsRes.error) logWarn({ event: "club_repo.hydrateAll.rulesets.failed", message: rulesetsRes.error.message });
    if (tablesRes.error) logWarn({ event: "club_repo.hydrateAll.tables.failed", message: tablesRes.error.message });

    const clubs = (clubsRes.data ?? []).map(rowToClub);
    const members = (membersRes.data ?? []).map((row: any) => {
      const m = rowToMember(row);
      if (row.player_profiles?.display_name) m.displayName = String(row.player_profiles.display_name);
      return m;
    });
    const invites = (invitesRes.data ?? []).map(rowToInvite);
    const rulesets = (rulesetsRes.data ?? []).map(rowToRuleset);
    const tables = (tablesRes.data ?? []).map(rowToTable);

    logInfo({
      event: "club_repo.hydrateAll.complete",
      message: `Loaded ${clubs.length} clubs, ${members.length} members, ${invites.length} invites, ${rulesets.length} rulesets, ${tables.length} tables`,
    });

    return { clubs, members, invites, rulesets, tables };
  }
}
