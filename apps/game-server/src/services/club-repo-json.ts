/**
 * JSON-file fallback persistence for clubs — used in dev mode when Supabase is not configured.
 * Writes all club state to a single JSON file on disk.
 * NOT suitable for production (no concurrency, no ACID).
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import type {
  Club,
  ClubMember,
  ClubInvite,
  ClubRuleset,
  ClubTable,
  ClubAuditLogEntry,
  ClubRole,
  ClubMemberStatus,
  ClubTableStatus,
} from "@cardpilot/shared-types";
import { logInfo, logWarn } from "../logger";

interface JsonStore {
  clubs: Club[];
  members: ClubMember[];
  invites: ClubInvite[];
  rulesets: ClubRuleset[];
  tables: ClubTable[];
  auditLog: Array<Omit<ClubAuditLogEntry, "id"> & { id?: number }>;
}

const EMPTY_STORE: JsonStore = { clubs: [], members: [], invites: [], rulesets: [], tables: [], auditLog: [] };

export class ClubRepoJson {
  private readonly filePath: string;
  private store: JsonStore;
  private writeTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(filePath?: string) {
    this.filePath = filePath ?? resolve(process.cwd(), ".data", "clubs.json");
    const dir = dirname(this.filePath);
    if (!existsSync(dir)) mkdirSync(dir, { recursive: true });

    if (existsSync(this.filePath)) {
      try {
        this.store = JSON.parse(readFileSync(this.filePath, "utf-8")) as JsonStore;
        logInfo({ event: "club_repo_json.loaded", message: `Loaded ${this.store.clubs.length} clubs from ${this.filePath}` });
      } catch (e) {
        logWarn({ event: "club_repo_json.load_failed", message: (e as Error).message });
        this.store = { ...EMPTY_STORE };
      }
    } else {
      this.store = { ...EMPTY_STORE };
      logInfo({ event: "club_repo_json.init", message: `New JSON store at ${this.filePath}` });
    }
  }

  enabled(): boolean { return true; }

  private scheduleSave(): void {
    if (this.writeTimer) return;
    this.writeTimer = setTimeout(() => {
      this.writeTimer = null;
      try {
        writeFileSync(this.filePath, JSON.stringify(this.store, null, 2), "utf-8");
      } catch (e) {
        logWarn({ event: "club_repo_json.save_failed", message: (e as Error).message });
      }
    }, 200); // debounce writes
  }

  // ═══════════════ CLUBS ═══════════════

  async createClub(club: Club): Promise<void> {
    this.store.clubs.push(club);
    this.scheduleSave();
  }

  async updateClub(club: Club): Promise<void> {
    const idx = this.store.clubs.findIndex((c) => c.id === club.id);
    if (idx >= 0) this.store.clubs[idx] = club;
    this.scheduleSave();
  }

  async fetchClubById(clubId: string): Promise<Club | null> {
    return this.store.clubs.find((c) => c.id === clubId) ?? null;
  }

  async fetchClubByCode(code: string): Promise<Club | null> {
    return this.store.clubs.find((c) => c.code === code.toUpperCase()) ?? null;
  }

  async fetchClubsByUser(userId: string): Promise<Club[]> {
    const memberClubIds = this.store.members
      .filter((m) => m.userId === userId && m.status === "active")
      .map((m) => m.clubId);
    return this.store.clubs.filter((c) => memberClubIds.includes(c.id));
  }

  async isCodeUnique(code: string): Promise<boolean> {
    return !this.store.clubs.some((c) => c.code === code);
  }

  // ═══════════════ MEMBERS ═══════════════

  async upsertMember(member: ClubMember): Promise<void> {
    const idx = this.store.members.findIndex((m) => m.clubId === member.clubId && m.userId === member.userId);
    if (idx >= 0) this.store.members[idx] = member;
    else this.store.members.push(member);
    this.scheduleSave();
  }

  async updateMemberStatus(clubId: string, userId: string, status: ClubMemberStatus): Promise<void> {
    const m = this.store.members.find((m) => m.clubId === clubId && m.userId === userId);
    if (m) { m.status = status; m.lastSeenAt = new Date().toISOString(); }
    this.scheduleSave();
  }

  async updateMemberRole(clubId: string, userId: string, role: ClubRole): Promise<void> {
    const m = this.store.members.find((m) => m.clubId === clubId && m.userId === userId);
    if (m) { m.role = role; m.lastSeenAt = new Date().toISOString(); }
    this.scheduleSave();
  }

  async deleteMember(clubId: string, userId: string): Promise<void> {
    this.store.members = this.store.members.filter((m) => !(m.clubId === clubId && m.userId === userId));
    this.scheduleSave();
  }

  async fetchMembers(clubId: string): Promise<ClubMember[]> {
    return this.store.members.filter((m) => m.clubId === clubId);
  }

  async fetchMember(clubId: string, userId: string): Promise<ClubMember | null> {
    return this.store.members.find((m) => m.clubId === clubId && m.userId === userId) ?? null;
  }

  async touchMemberLastSeen(clubId: string, userId: string): Promise<void> {
    const m = this.store.members.find((m) => m.clubId === clubId && m.userId === userId);
    if (m) m.lastSeenAt = new Date().toISOString();
    this.scheduleSave();
  }

  // ═══════════════ INVITES ═══════════════

  async createInvite(invite: ClubInvite): Promise<void> {
    this.store.invites.push(invite);
    this.scheduleSave();
  }

  async revokeInvite(inviteId: string): Promise<void> {
    const inv = this.store.invites.find((i) => i.id === inviteId);
    if (inv) inv.revoked = true;
    this.scheduleSave();
  }

  async incrementInviteUses(inviteId: string): Promise<void> {
    const inv = this.store.invites.find((i) => i.id === inviteId);
    if (inv) inv.usesCount += 1;
    this.scheduleSave();
  }

  async fetchInvites(clubId: string): Promise<ClubInvite[]> {
    return this.store.invites.filter((i) => i.clubId === clubId && !i.revoked);
  }

  async fetchInviteByCode(inviteCode: string): Promise<ClubInvite | null> {
    return this.store.invites.find((i) => i.inviteCode === inviteCode && !i.revoked) ?? null;
  }

  async isInviteCodeUnique(code: string): Promise<boolean> {
    return !this.store.invites.some((i) => i.inviteCode === code);
  }

  // ═══════════════ RULESETS ═══════════════

  async createRuleset(rs: ClubRuleset): Promise<void> {
    this.store.rulesets.push(rs);
    this.scheduleSave();
  }

  async updateRuleset(rs: ClubRuleset): Promise<void> {
    const idx = this.store.rulesets.findIndex((r) => r.id === rs.id);
    if (idx >= 0) this.store.rulesets[idx] = rs;
    this.scheduleSave();
  }

  async clearDefaultRuleset(clubId: string): Promise<void> {
    for (const rs of this.store.rulesets) {
      if (rs.clubId === clubId) rs.isDefault = false;
    }
    this.scheduleSave();
  }

  async fetchRulesets(clubId: string): Promise<ClubRuleset[]> {
    return this.store.rulesets.filter((r) => r.clubId === clubId);
  }

  // ═══════════════ TABLES ═══════════════

  async createTable(ct: ClubTable): Promise<void> {
    this.store.tables.push(ct);
    this.scheduleSave();
  }

  async updateTableStatus(clubTableId: string, status: ClubTableStatus): Promise<void> {
    const t = this.store.tables.find((t) => t.id === clubTableId);
    if (t) t.status = status;
    this.scheduleSave();
  }

  async setTableRoomCode(clubTableId: string, roomCode: string): Promise<void> {
    const t = this.store.tables.find((t) => t.id === clubTableId);
    if (t) t.roomCode = roomCode;
    this.scheduleSave();
  }

  async fetchTables(clubId: string): Promise<ClubTable[]> {
    return this.store.tables.filter((t) => t.clubId === clubId && t.status !== "closed");
  }

  async fetchTableByRoomCode(roomCode: string): Promise<ClubTable | null> {
    return this.store.tables.find((t) => t.roomCode === roomCode && t.status !== "closed") ?? null;
  }

  // ═══════════════ AUDIT LOG ═══════════════

  async appendAudit(entry: Omit<ClubAuditLogEntry, "id">): Promise<void> {
    this.store.auditLog.push({ ...entry, id: this.store.auditLog.length + 1 });
    // Keep only last 1000 entries on disk
    if (this.store.auditLog.length > 1000) this.store.auditLog = this.store.auditLog.slice(-1000);
    this.scheduleSave();
  }

  async fetchAuditLog(clubId: string, limit = 100): Promise<ClubAuditLogEntry[]> {
    return this.store.auditLog
      .filter((e) => e.clubId === clubId)
      .slice(-limit)
      .map((e, i) => ({ ...e, id: e.id ?? i + 1 })) as ClubAuditLogEntry[];
  }

  // ═══════════════ BULK HYDRATION ═══════════════

  async hydrateAll(): Promise<{
    clubs: Club[];
    members: ClubMember[];
    invites: ClubInvite[];
    rulesets: ClubRuleset[];
    tables: ClubTable[];
  }> {
    return {
      clubs: this.store.clubs.filter((c) => !c.isArchived),
      members: this.store.members,
      invites: this.store.invites.filter((i) => !i.revoked),
      rulesets: this.store.rulesets,
      tables: this.store.tables.filter((t) => t.status !== "closed"),
    };
  }
}
