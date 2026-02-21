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
  ClubWalletBalance,
  ClubWalletTransaction,
  ClubWalletTxType,
  ClubLeaderboardEntry,
  ClubLeaderboardMetric,
  ClubLeaderboardRange,
  ClubRole,
  ClubMemberStatus,
  ClubVisibility,
  ClubTableStatus,
  ClubRules,
} from "@cardpilot/shared-types";
import { normalizeClubRole } from "@cardpilot/shared-types";
import { logInfo, logWarn } from "../logger";

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
    role: normalizeClubRole(typeof r.role === "string" ? r.role : null),
    status: (r.status as ClubMemberStatus) ?? "active",
    nicknameInClub: r.nickname_in_club ? String(r.nickname_in_club) : null,
    balance: Number(r.balance ?? 0),
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

function rowToWalletTx(r: Record<string, unknown>): ClubWalletTransaction {
  return {
    id: String(r.id),
    clubId: String(r.club_id),
    userId: String(r.user_id),
    type: String(r.type) as ClubWalletTxType,
    amount: Number(r.amount ?? 0),
    currency: String(r.currency ?? "chips"),
    refType: r.ref_type ? String(r.ref_type) : null,
    refId: r.ref_id ? String(r.ref_id) : null,
    createdAt: String(r.created_at),
    createdBy: r.created_by ? String(r.created_by) : null,
    note: r.note ? String(r.note) : null,
    metaJson: (r.meta_json as Record<string, unknown>) ?? {},
    idempotencyKey: r.idempotency_key ? String(r.idempotency_key) : null,
  };
}

export interface AppendWalletTxInput {
  clubId: string;
  userId: string;
  type: ClubWalletTxType;
  amount: number;
  currency?: string;
  refType?: string | null;
  refId?: string | null;
  createdBy?: string | null;
  note?: string | null;
  metaJson?: Record<string, unknown>;
  idempotencyKey?: string | null;
}

export interface AppendWalletTxResult {
  tx: ClubWalletTransaction;
  newBalance: number;
  wasDuplicate: boolean;
}

function dayFromRange(range: ClubLeaderboardRange): string {
  if (range === "all") {
    return "1970-01-01";
  }
  const now = new Date();
  const dayCount = range === "day" ? 1 : range === "month" ? 30 : 7;
  const from = new Date(now.getTime() - (dayCount - 1) * 24 * 60 * 60 * 1000);
  return from.toISOString().slice(0, 10);
}

async function loadDisplayNames(
  db: SupabaseClient,
  userIds: string[],
  warnEvent: string,
): Promise<Map<string, string>> {
  const uniqIds = [...new Set(userIds.filter((id) => id.length > 0))];
  const names = new Map<string, string>();
  if (uniqIds.length === 0) return names;

  const { data, error } = await db
    .from("player_profiles")
    .select("user_id, display_name")
    .in("user_id", uniqIds);
  if (error) {
    logWarn({ event: warnEvent, message: error.message });
    return names;
  }

  for (const row of data ?? []) {
    const userId = String((row as any).user_id ?? "");
    const displayName = String((row as any).display_name ?? "");
    if (!userId || !displayName) continue;
    names.set(userId, displayName);
  }
  return names;
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
    if (error) {
      logWarn({ event: "club_repo.createClub.failed", message: error.message });
      throw new Error(`Failed to persist club: ${error.message}`);
    }
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
    if (error) {
      logWarn({ event: "club_repo.updateClub.failed", message: error.message });
      throw new Error(`Failed to update club: ${error.message}`);
    }
  }

  async fetchClubById(clubId: string): Promise<Club | null> {
    if (!this.db) return null;
    const { data, error } = await this.db.from("clubs").select("*").eq("id", clubId).maybeSingle();
    if (error) {
      logWarn({ event: "club_repo.fetchClubById.failed", message: error.message });
      throw new Error(`Failed to fetch club: ${error.message}`);
    }
    return data ? rowToClub(data) : null;
  }

  async fetchClubByCode(code: string): Promise<Club | null> {
    if (!this.db) return null;
    const { data, error } = await this.db.from("clubs").select("*").eq("code", code.toUpperCase()).maybeSingle();
    if (error) {
      logWarn({ event: "club_repo.fetchClubByCode.failed", message: error.message });
      throw new Error(`Failed to fetch club by code: ${error.message}`);
    }
    return data ? rowToClub(data) : null;
  }

  async fetchClubsByUser(userId: string): Promise<Club[]> {
    if (!this.db) return [];
    const { data, error } = await this.db
      .from("club_members")
      .select("club_id, clubs(*)")
      .eq("user_id", userId)
      .eq("status", "active");
    if (error) {
      logWarn({ event: "club_repo.fetchClubsByUser.failed", message: error.message });
      throw new Error(`Failed to fetch user clubs: ${error.message}`);
    }
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
    if (error) {
      logWarn({ event: "club_repo.upsertMember.failed", message: error.message });
      throw new Error(`Failed to persist member: ${error.message}`);
    }
  }

  async updateMemberStatus(clubId: string, userId: string, status: ClubMemberStatus): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("club_members").update({
      status,
      last_seen_at: new Date().toISOString(),
    }).eq("club_id", clubId).eq("user_id", userId);
    if (error) {
      logWarn({ event: "club_repo.updateMemberStatus.failed", message: error.message });
      throw new Error(`Failed to update member status: ${error.message}`);
    }
  }

  async updateMemberRole(clubId: string, userId: string, role: ClubRole): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("club_members").update({
      role,
      last_seen_at: new Date().toISOString(),
    }).eq("club_id", clubId).eq("user_id", userId);
    if (error) {
      logWarn({ event: "club_repo.updateMemberRole.failed", message: error.message });
      throw new Error(`Failed to update member role: ${error.message}`);
    }
  }

  async deleteMember(clubId: string, userId: string): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("club_members").delete().eq("club_id", clubId).eq("user_id", userId);
    if (error) {
      logWarn({ event: "club_repo.deleteMember.failed", message: error.message });
      throw new Error(`Failed to delete member: ${error.message}`);
    }
  }

  async fetchMembers(clubId: string): Promise<ClubMember[]> {
    if (!this.db) return [];
    const { data, error } = await this.db
      .from("club_members")
      .select("*")
      .eq("club_id", clubId);
    if (error) {
      logWarn({ event: "club_repo.fetchMembers.failed", message: error.message });
      throw new Error(`Failed to fetch members: ${error.message}`);
    }
    const members = (data ?? []).map((row: any) => rowToMember(row));
    const displayNames = await loadDisplayNames(
      this.db,
      members.map((member) => member.userId),
      "club_repo.fetchMembers.player_profiles.failed",
    );

    for (const member of members) {
      const displayName = displayNames.get(member.userId);
      if (displayName) member.displayName = displayName;
    }
    return members;
  }

  async fetchMember(clubId: string, userId: string): Promise<ClubMember | null> {
    if (!this.db) return null;
    const { data, error } = await this.db
      .from("club_members")
      .select("*")
      .eq("club_id", clubId)
      .eq("user_id", userId)
      .maybeSingle();
    if (error) {
      logWarn({ event: "club_repo.fetchMember.failed", message: error.message });
      throw new Error(`Failed to fetch member: ${error.message}`);
    }
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
    if (error) {
      logWarn({ event: "club_repo.createInvite.failed", message: error.message });
      throw new Error(`Failed to create invite: ${error.message}`);
    }
  }

  async revokeInvite(inviteId: string): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("club_invites").update({ revoked: true }).eq("id", inviteId);
    if (error) {
      logWarn({ event: "club_repo.revokeInvite.failed", message: error.message });
      throw new Error(`Failed to revoke invite: ${error.message}`);
    }
  }

  async incrementInviteUses(inviteId: string): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.rpc("increment_invite_uses", { p_invite_id: inviteId });
    if (error) {
      logWarn({ event: "club_repo.incrementInviteUses.failed", message: error.message });
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
    if (error) {
      logWarn({ event: "club_repo.fetchInvites.failed", message: error.message });
      throw new Error(`Failed to fetch invites: ${error.message}`);
    }
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
    if (error) {
      logWarn({ event: "club_repo.fetchInviteByCode.failed", message: error.message });
      throw new Error(`Failed to fetch invite: ${error.message}`);
    }
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
    if (error) {
      logWarn({ event: "club_repo.createRuleset.failed", message: error.message });
      throw new Error(`Failed to create ruleset: ${error.message}`);
    }
  }

  async updateRuleset(rs: ClubRuleset): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("club_rulesets").update({
      name: rs.name,
      rules_json: rs.rulesJson,
      is_default: rs.isDefault,
    }).eq("id", rs.id);
    if (error) {
      logWarn({ event: "club_repo.updateRuleset.failed", message: error.message });
      throw new Error(`Failed to update ruleset: ${error.message}`);
    }
  }

  async clearDefaultRuleset(clubId: string): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("club_rulesets").update({ is_default: false }).eq("club_id", clubId);
    if (error) {
      logWarn({ event: "club_repo.clearDefaultRuleset.failed", message: error.message });
      throw new Error(`Failed to clear default ruleset: ${error.message}`);
    }
  }

  async fetchRulesets(clubId: string): Promise<ClubRuleset[]> {
    if (!this.db) return [];
    const { data, error } = await this.db
      .from("club_rulesets")
      .select("*")
      .eq("club_id", clubId)
      .order("created_at", { ascending: false });
    if (error) {
      logWarn({ event: "club_repo.fetchRulesets.failed", message: error.message });
      throw new Error(`Failed to fetch rulesets: ${error.message}`);
    }
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
    if (error) {
      logWarn({ event: "club_repo.createTable.failed", message: error.message });
      throw new Error(`Failed to create table: ${error.message}`);
    }
  }

  async updateTableStatus(clubTableId: string, status: ClubTableStatus): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("club_tables").update({ status }).eq("id", clubTableId);
    if (error) {
      logWarn({ event: "club_repo.updateTableStatus.failed", message: error.message });
      throw new Error(`Failed to update table status: ${error.message}`);
    }
  }

  async setTableRoomCode(clubTableId: string, roomCode: string): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.from("club_tables").update({ room_code: roomCode }).eq("id", clubTableId);
    if (error) {
      logWarn({ event: "club_repo.setTableRoomCode.failed", message: error.message });
      throw new Error(`Failed to set table room code: ${error.message}`);
    }
  }

  async updateTable(clubTableId: string, updates: { name?: string; rulesetId?: string | null }): Promise<void> {
    if (!this.db) return;
    const payload: Record<string, unknown> = {};
    if (updates.name !== undefined) payload.name = updates.name;
    if (updates.rulesetId !== undefined) payload.ruleset_id = updates.rulesetId;
    if (Object.keys(payload).length === 0) return;
    const { error } = await this.db.from("club_tables").update(payload).eq("id", clubTableId);
    if (error) {
      logWarn({ event: "club_repo.updateTable.failed", message: error.message });
      throw new Error(`Failed to update table: ${error.message}`);
    }
  }

  async fetchTables(clubId: string): Promise<ClubTable[]> {
    if (!this.db) return [];
    const { data, error } = await this.db
      .from("club_tables")
      .select("*")
      .eq("club_id", clubId)
      .neq("status", "closed")
      .order("created_at", { ascending: false });
    if (error) {
      logWarn({ event: "club_repo.fetchTables.failed", message: error.message });
      throw new Error(`Failed to fetch tables: ${error.message}`);
    }
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
    if (error) {
      logWarn({ event: "club_repo.fetchTableByRoomCode.failed", message: error.message });
      throw new Error(`Failed to fetch table by code: ${error.message}`);
    }
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
    if (error) {
      logWarn({ event: "club_repo.appendAudit.failed", message: error.message });
    }
  }

  async fetchAuditLog(clubId: string, limit = 100): Promise<ClubAuditLogEntry[]> {
    if (!this.db) return [];
    const { data, error } = await this.db
      .from("club_audit_log")
      .select("*")
      .eq("club_id", clubId)
      .order("created_at", { ascending: false })
      .limit(limit);
    if (error) {
      logWarn({ event: "club_repo.fetchAuditLog.failed", message: error.message });
      throw new Error(`Failed to fetch audit log: ${error.message}`);
    }
    return (data ?? []).map(rowToAudit);
  }

  // ═══════════════ WALLET LEDGER ═══════════════

  async appendWalletTx(input: AppendWalletTxInput): Promise<AppendWalletTxResult | null> {
    if (!this.db) return null;

    const {
      clubId,
      userId,
      type,
      amount,
      currency = "chips",
      refType = null,
      refId = null,
      createdBy = null,
      note = null,
      metaJson = {},
      idempotencyKey = null,
    } = input;

    const MAX_RPC_RETRIES = 3;
    const BASE_DELAY_MS = 300;
    let lastRpcError: { message?: string; details?: string; hint?: string; code?: string } | null = null;

    for (let attempt = 0; attempt < MAX_RPC_RETRIES; attempt++) {
      const { data, error } = await this.db.rpc("club_wallet_append_tx", {
        _club_id: clubId,
        _user_id: userId,
        _type: type,
        _amount: Math.trunc(amount),
        _currency: currency,
        _ref_type: refType,
        _ref_id: refId,
        _created_by: createdBy,
        _note: note,
        _meta_json: metaJson,
        _idempotency_key: idempotencyKey,
      });

      if (!error) {
        const row = Array.isArray(data) ? data[0] : null;
        if (!row?.tx_id) {
          logWarn({ event: "club_repo.appendWalletTx.invalid_response", message: "Missing tx_id from RPC" });
          return null;
        }

        const txId = String(row.tx_id);
        const newBalance = Number(row.current_balance ?? 0);
        const wasDuplicate = Boolean(row.was_duplicate ?? false);

        const { data: txRow, error: txError } = await this.db
          .from("club_wallet_transactions")
          .select("*")
          .eq("id", txId)
          .maybeSingle();

        if (txError || !txRow) {
          if (txError) {
            logWarn({ event: "club_repo.appendWalletTx.fetch_tx_failed", message: txError.message });
          }
          const fallbackTx: ClubWalletTransaction = {
            id: txId, clubId, userId, type, amount, currency, refType, refId,
            createdAt: new Date().toISOString(), createdBy, note, metaJson, idempotencyKey,
          };
          return { tx: fallbackTx, newBalance, wasDuplicate };
        }

        return { tx: rowToWalletTx(txRow), newBalance, wasDuplicate };
      }

      lastRpcError = error;
      logWarn({
        event: "club_repo.appendWalletTx.rpc_retry",
        attempt: attempt + 1,
        maxRetries: MAX_RPC_RETRIES,
        message: error.message,
        code: error.code,
        clubId, userId, type, amount,
      });

      if (attempt < MAX_RPC_RETRIES - 1) {
        const delay = BASE_DELAY_MS * Math.pow(2, attempt);
        await new Promise(resolve => setTimeout(resolve, delay));
        continue;
      }
    }

    // All retries exhausted — fall back to manual method
    logWarn({
      event: "club_repo.appendWalletTx.rpc_failed",
      message: lastRpcError?.message,
      details: lastRpcError?.details,
      hint: lastRpcError?.hint,
      code: lastRpcError?.code,
      clubId, userId, type, amount,
    });
    try {
      const fallback = await this.appendWalletTxManual(input);
      if (fallback) {
        logInfo({ event: "club_repo.appendWalletTx.fallback_ok", clubId, userId, type, amount });
      }
      return fallback;
    } catch (manualErr) {
      logWarn({ event: "club_repo.appendWalletTx.fallback_failed", message: (manualErr as Error).message });
      throw manualErr;
    }
  }

  private async appendWalletTxManual(input: AppendWalletTxInput): Promise<AppendWalletTxResult | null> {
    if (!this.db) return null;

    const {
      clubId,
      userId,
      type,
      amount,
      currency = "chips",
      refType = null,
      refId = null,
      createdBy = null,
      note = null,
      metaJson = {},
    } = input;

    const truncatedAmount = Math.trunc(amount);

    // Idempotency check
    if (input.idempotencyKey) {
      const { data: existing } = await this.db
        .from("club_wallet_transactions")
        .select("id, created_at")
        .eq("club_id", clubId)
        .eq("user_id", userId)
        .eq("currency", currency)
        .eq("idempotency_key", input.idempotencyKey)
        .maybeSingle();

      if (existing) {
        const { data: balanceData } = await this.db
          .from("club_wallet_accounts")
          .select("current_balance")
          .eq("club_id", clubId)
          .eq("user_id", userId)
          .eq("currency", currency)
          .maybeSingle();

        return {
          tx: rowToWalletTx(existing as Record<string, unknown>),
          newBalance: balanceData?.current_balance ?? 0,
          wasDuplicate: true,
        };
      }
    }

    // Step 1: Insert the transaction record
    const txData = {
      club_id: clubId,
      user_id: userId,
      type,
      amount: truncatedAmount,
      currency,
      ref_type: refType,
      ref_id: refId,
      created_by: createdBy,
      note,
      meta_json: metaJson,
      idempotency_key: input.idempotencyKey ?? null,
    };

    const { data: insertedTx, error: insertError } = await this.db
      .from("club_wallet_transactions")
      .insert(txData)
      .select()
      .single();

    if (insertError || !insertedTx) {
      const msg = insertError?.message || "Unknown DB error during insert";
      logWarn({ event: "club_repo.appendWalletTxManual.insert_failed", message: msg, details: insertError?.details, code: insertError?.code });
      throw new Error(`Wallet DB insert failed: ${msg}`);
    }

    // Step 2: Atomic balance increment via helper RPC (avoids read-then-write race)
    const { data: incrementResult, error: incrementError } = await this.db
      .rpc("club_wallet_atomic_increment", {
        _club_id: clubId,
        _user_id: userId,
        _currency: currency,
        _delta: truncatedAmount,
      });

    if (incrementError) {
      // Balance update failed — attempt to clean up the inserted transaction
      logWarn({ event: "club_repo.appendWalletTxManual.increment_failed", message: incrementError.message, clubId, userId, amount: truncatedAmount });
      await this.db.from("club_wallet_transactions").delete().eq("id", (insertedTx as Record<string, unknown>).id);
      throw new Error(`Insufficient funds or balance update failed: ${incrementError.message}`);
    }

    const newBalance = Number(incrementResult ?? 0);
    return {
      tx: rowToWalletTx(insertedTx as Record<string, unknown>),
      newBalance,
      wasDuplicate: false,
    };
  }

  async getWalletBalance(clubId: string, userId: string, currency = "chips"): Promise<number> {
    if (!this.db) return 0;

    const { data: account, error: accountError } = await this.db
      .from("club_wallet_accounts")
      .select("current_balance")
      .eq("club_id", clubId)
      .eq("user_id", userId)
      .eq("currency", currency)
      .maybeSingle();

    if (accountError) {
      logWarn({ event: "club_repo.getWalletBalance.failed", message: accountError.message });
      throw new Error(`Failed to fetch wallet balance: ${accountError.message}`);
    }

    if (account) {
      return Number(account.current_balance ?? 0);
    }

    // Fallback to ledger only if account row missing (rare)
    const { data: txRows, error: txError } = await this.db
      .from("club_wallet_transactions")
      .select("amount")
      .eq("club_id", clubId)
      .eq("user_id", userId)
      .eq("currency", currency);

    if (txError) {
      logWarn({ event: "club_repo.getWalletBalance.ledger_fallback_failed", message: txError.message });
      throw new Error(`Failed to fetch wallet balance (ledger): ${txError.message}`);
    }

    return (txRows ?? []).reduce((sum, row) => sum + Number((row as any).amount ?? 0), 0);
  }

  async getWalletBalances(clubId: string, userIds: string[], currency = "chips"): Promise<Map<string, number>> {
    const result = new Map<string, number>();
    if (!this.db) return result;
    if (userIds.length === 0) return result;

    const uniqUserIds = [...new Set(userIds)];
    const { data, error } = await this.db
      .from("club_wallet_accounts")
      .select("user_id, current_balance")
      .eq("club_id", clubId)
      .eq("currency", currency)
      .in("user_id", uniqUserIds);

    if (error) {
      logWarn({ event: "club_repo.getWalletBalances.failed", message: error.message });
      throw new Error(`Failed to fetch wallet balances: ${error.message}`);
    } else {
      for (const row of data ?? []) {
        result.set(String((row as any).user_id), Number((row as any).current_balance ?? 0));
      }
    }

    // Ensure all requested ids are present (fallback to 0 when account row is missing).
    for (const userId of uniqUserIds) {
      if (!result.has(userId)) result.set(userId, 0);
    }
    return result;
  }

  async listWalletTxs(
    clubId: string,
    userId: string,
    currency = "chips",
    limit = 50,
    offset = 0,
  ): Promise<ClubWalletTransaction[]> {
    if (!this.db) return [];
    const safeLimit = Math.max(1, Math.min(limit, 200));
    const safeOffset = Math.max(0, offset);
    const from = safeOffset;
    const to = safeOffset + safeLimit - 1;

    const { data, error } = await this.db
      .from("club_wallet_transactions")
      .select("*")
      .eq("club_id", clubId)
      .eq("user_id", userId)
      .eq("currency", currency)
      .order("created_at", { ascending: false })
      .range(from, to);

    if (error) {
      logWarn({ event: "club_repo.listWalletTxs.failed", message: error.message });
      throw new Error(`Failed to list wallet transactions: ${error.message}`);
    }
    return (data ?? []).map((row) => rowToWalletTx(row as Record<string, unknown>));
  }

  async recordClubHandStats(
    clubId: string,
    userId: string,
    handsDelta: number,
    netDelta: number,
    rakeDelta = 0,
  ): Promise<void> {
    if (!this.db) return;
    const { error } = await this.db.rpc("club_record_hand_stats", {
      _club_id: clubId,
      _user_id: userId,
      _hands_delta: Math.trunc(handsDelta),
      _net_delta: Math.trunc(netDelta),
      _rake_delta: Math.trunc(rakeDelta),
    });
    if (error) {
      logWarn({ event: "club_repo.recordClubHandStats.failed", message: error.message });
    }
  }

  async getClubLeaderboard(
    clubId: string,
    timeRange: ClubLeaderboardRange = "week",
    metric: ClubLeaderboardMetric = "net",
    limit = 50,
  ): Promise<ClubLeaderboardEntry[]> {
    if (!this.db) return [];

    const { data, error } = await this.db.rpc("club_get_leaderboard", {
      _club_id: clubId,
      _day_from: dayFromRange(timeRange),
      _metric: metric,
      _limit: Math.max(1, Math.min(limit, 200)),
    });

    if (error) {
      logWarn({ event: "club_repo.getClubLeaderboard.failed", message: error.message });
      throw new Error(`Failed to fetch leaderboard: ${error.message}`);
    }

    const rows = (data ?? []).map((row: any) => ({
      rank: Number(row.rank ?? 0),
      clubId: String(row.club_id ?? clubId),
      userId: String(row.user_id),
      displayName: row.display_name ? String(row.display_name) : undefined,
      metric,
      metricValue: Number(row.metric_value ?? 0),
      balance: 0,
      hands: Number(row.hands ?? 0),
      buyIn: Number(row.buy_in ?? 0),
      cashOut: Number(row.cash_out ?? 0),
      deposits: Number(row.deposits ?? 0),
      net: Number(row.net ?? 0),
    }));

    // If fetching balances fails here, it will throw, ensuring consistent failure behavior.
    const balances = await this.getWalletBalances(
      clubId,
      rows.map((row: ClubLeaderboardEntry) => row.userId),
      "chips",
    );
    return rows.map((row: ClubLeaderboardEntry) => ({
      ...row,
      balance: balances.get(row.userId) ?? 0,
    }));
  }

  async hydrateAll(): Promise<{
    clubs: Club[];
    members: ClubMember[];
    invites: ClubInvite[];
    rulesets: ClubRuleset[];
    tables: ClubTable[];
  }> {
    if (!this.db) return { clubs: [], members: [], invites: [], rulesets: [], tables: [] };

    const [clubsRes, membersRes, invitesRes, rulesetsRes, tablesRes, walletAccountsRes] = await Promise.all([
      this.db.from("clubs").select("*").eq("is_archived", false),
      this.db.from("club_members").select("*"),
      this.db.from("club_invites").select("*").eq("revoked", false),
      this.db.from("club_rulesets").select("*"),
      this.db.from("club_tables").select("*").neq("status", "closed"),
      this.db.from("club_wallet_accounts").select("club_id, user_id, currency, current_balance"),
    ]);

    // Throw on any failure to prevent partial/ghost state
    if (clubsRes.error) throw new Error(`Hydration failed (clubs): ${clubsRes.error.message}`);
    if (membersRes.error) throw new Error(`Hydration failed (members): ${membersRes.error.message}`);
    if (invitesRes.error) throw new Error(`Hydration failed (invites): ${invitesRes.error.message}`);
    if (rulesetsRes.error) throw new Error(`Hydration failed (rulesets): ${rulesetsRes.error.message}`);
    if (tablesRes.error) throw new Error(`Hydration failed (tables): ${tablesRes.error.message}`);
    if (walletAccountsRes.error) throw new Error(`Hydration failed (wallet): ${walletAccountsRes.error.message}`);

    const clubs = (clubsRes.data ?? []).map(rowToClub);
    const walletBalanceByClubUser = new Map<string, number>();
    for (const row of walletAccountsRes.data ?? []) {
      if ((row as any).currency && String((row as any).currency) !== "chips") continue;
      walletBalanceByClubUser.set(
        `${String((row as any).club_id)}:${String((row as any).user_id)}`,
        Number((row as any).current_balance ?? 0),
      );
    }
    const displayNames = await loadDisplayNames(
      this.db,
      (membersRes.data ?? []).map((row: any) => String(row.user_id ?? "")),
      "club_repo.hydrateAll.player_profiles.failed",
    );

    const members = (membersRes.data ?? []).map((row: any) => {
      const m = rowToMember(row);
      const displayName = displayNames.get(m.userId);
      if (displayName) m.displayName = displayName;
      m.balance = walletBalanceByClubUser.get(`${m.clubId}:${m.userId}`) ?? 0;
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
