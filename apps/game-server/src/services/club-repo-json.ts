/**
 * JSON-file fallback persistence for clubs — used in dev mode when Supabase is not configured.
 * Writes all club state to a single JSON file on disk.
 * NOT suitable for production (no concurrency, no ACID).
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { randomUUID } from 'node:crypto';
import type {
  Club,
  ClubMember,
  ClubInvite,
  ClubRuleset,
  ClubTable,
  ClubAuditLogEntry,
  ClubWalletTransaction,
  ClubWalletTxType,
  ClubLeaderboardEntry,
  ClubLeaderboardMetric,
  ClubLeaderboardRange,
  ClubRole,
  ClubMemberStatus,
  ClubTableStatus,
} from '@cardpilot/shared-types';
import { normalizeClubRole } from '@cardpilot/shared-types';
import { logInfo, logWarn } from '../logger';

interface AppendWalletTxInput {
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

interface AppendWalletTxResult {
  tx: ClubWalletTransaction;
  newBalance: number;
  wasDuplicate: boolean;
}

interface JsonStore {
  clubs: Club[];
  members: ClubMember[];
  invites: ClubInvite[];
  rulesets: ClubRuleset[];
  tables: ClubTable[];
  auditLog: Array<Omit<ClubAuditLogEntry, 'id'> & { id?: number }>;
  walletLedgerEntries: ClubWalletTransaction[];
  walletAccounts: Array<{
    clubId: string;
    userId: string;
    currency: string;
    currentBalance: number;
    updatedAt: string;
  }>;
  playerDailyStats: Array<{
    clubId: string;
    userId: string;
    day: string;
    hands: number;
    buyIn: number;
    cashOut: number;
    deposits: number;
    net: number;
    rake: number;
    updatedAt: string;
  }>;
}

const EMPTY_STORE: JsonStore = {
  clubs: [],
  members: [],
  invites: [],
  rulesets: [],
  tables: [],
  auditLog: [],
  walletLedgerEntries: [],
  walletAccounts: [],
  playerDailyStats: [],
};

export class ClubRepoJson {
  private readonly filePath: string;
  private store: JsonStore;
  private writeTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(filePath?: string) {
    this.filePath = filePath ?? resolve(process.cwd(), '.data', 'clubs.json');
    const dir = dirname(this.filePath);
    if (!existsSync(dir)) mkdirSync(dir, { recursive: true });

    if (existsSync(this.filePath)) {
      try {
        const parsed = JSON.parse(readFileSync(this.filePath, 'utf-8')) as Partial<JsonStore>;
        this.store = {
          ...EMPTY_STORE,
          ...parsed,
          clubs: parsed.clubs ?? [],
          members: (parsed.members ?? []).map((member) => ({
            ...member,
            role: normalizeClubRole((member as { role?: string }).role ?? null),
          })),
          invites: parsed.invites ?? [],
          rulesets: parsed.rulesets ?? [],
          tables: parsed.tables ?? [],
          auditLog: parsed.auditLog ?? [],
          walletLedgerEntries: parsed.walletLedgerEntries ?? [],
          walletAccounts: parsed.walletAccounts ?? [],
          playerDailyStats: parsed.playerDailyStats ?? [],
        };
        logInfo({
          event: 'club_repo_json.loaded',
          message: `Loaded ${this.store.clubs.length} clubs from ${this.filePath}`,
        });
      } catch (e) {
        logWarn({ event: 'club_repo_json.load_failed', message: (e as Error).message });
        this.store = { ...EMPTY_STORE };
      }
    } else {
      this.store = { ...EMPTY_STORE };
      logInfo({ event: 'club_repo_json.init', message: `New JSON store at ${this.filePath}` });
    }
  }

  enabled(): boolean {
    return true;
  }

  private scheduleSave(): void {
    if (this.writeTimer) return;
    this.writeTimer = setTimeout(() => {
      this.writeTimer = null;
      try {
        writeFileSync(this.filePath, JSON.stringify(this.store, null, 2), 'utf-8');
      } catch (e) {
        logWarn({ event: 'club_repo_json.save_failed', message: (e as Error).message });
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
      .filter((m) => m.userId === userId && m.status === 'active')
      .map((m) => m.clubId);
    return this.store.clubs.filter((c) => memberClubIds.includes(c.id));
  }

  async isCodeUnique(code: string): Promise<boolean> {
    return !this.store.clubs.some((c) => c.code === code);
  }

  // ═══════════════ MEMBERS ═══════════════

  async upsertMember(member: ClubMember): Promise<void> {
    const idx = this.store.members.findIndex(
      (m) => m.clubId === member.clubId && m.userId === member.userId,
    );
    if (idx >= 0) this.store.members[idx] = member;
    else this.store.members.push(member);
    this.scheduleSave();
  }

  async updateMemberStatus(
    clubId: string,
    userId: string,
    status: ClubMemberStatus,
  ): Promise<void> {
    const m = this.store.members.find((m) => m.clubId === clubId && m.userId === userId);
    if (m) {
      m.status = status;
      m.lastSeenAt = new Date().toISOString();
    }
    this.scheduleSave();
  }

  async updateMemberRole(clubId: string, userId: string, role: ClubRole): Promise<void> {
    const m = this.store.members.find((m) => m.clubId === clubId && m.userId === userId);
    if (m) {
      m.role = role;
      m.lastSeenAt = new Date().toISOString();
    }
    this.scheduleSave();
  }

  async deleteMember(clubId: string, userId: string): Promise<void> {
    this.store.members = this.store.members.filter(
      (m) => !(m.clubId === clubId && m.userId === userId),
    );
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

  async updateTable(
    clubTableId: string,
    updates: { name?: string; config?: import('@cardpilot/shared-types').ClubTableConfig },
  ): Promise<void> {
    const t = this.store.tables.find((table) => table.id === clubTableId);
    if (!t) return;
    if (updates.name !== undefined) t.name = updates.name;
    if (updates.config !== undefined) t.config = updates.config;
    this.scheduleSave();
  }

  async fetchTables(clubId: string): Promise<ClubTable[]> {
    return this.store.tables.filter((t) => t.clubId === clubId && t.status !== 'closed');
  }

  // ═══════════════ AUDIT LOG ═══════════════

  async appendAudit(entry: Omit<ClubAuditLogEntry, 'id'>): Promise<void> {
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

  // ═══════════════ WALLET LEDGER ═══════════════

  async appendWalletTx(input: AppendWalletTxInput): Promise<AppendWalletTxResult | null> {
    const now = new Date().toISOString();
    const currency = input.currency ?? 'chips';

    if (input.idempotencyKey) {
      const existing = this.store.walletLedgerEntries.find(
        (tx) =>
          tx.clubId === input.clubId &&
          tx.userId === input.userId &&
          tx.currency === currency &&
          tx.idempotencyKey === input.idempotencyKey,
      );
      if (existing) {
        return {
          tx: existing,
          newBalance: await this.getWalletBalance(input.clubId, input.userId, currency),
          wasDuplicate: true,
        };
      }
    }

    const currentBalance = await this.getWalletBalance(input.clubId, input.userId, currency);
    const newBalance = currentBalance + Math.trunc(input.amount);
    if (newBalance < 0) {
      logWarn({
        event: 'club_repo_json.appendWalletTx.insufficient',
        clubId: input.clubId,
        userId: input.userId,
        currentBalance,
        amount: input.amount,
      });
      throw new Error(
        `Insufficient funds: Balance ${currentBalance}, trying to deduct ${Math.abs(Math.trunc(input.amount))}`,
      );
    }

    const tx: ClubWalletTransaction = {
      id: randomUUID(),
      clubId: input.clubId,
      userId: input.userId,
      type: input.type,
      amount: Math.trunc(input.amount),
      currency,
      refType: input.refType ?? null,
      refId: input.refId ?? null,
      createdAt: now,
      createdBy: input.createdBy ?? null,
      note: input.note ?? null,
      metaJson: input.metaJson ?? {},
      idempotencyKey: input.idempotencyKey ?? null,
    };

    this.store.walletLedgerEntries.push(tx);

    const account = this.store.walletAccounts.find(
      (a) => a.clubId === input.clubId && a.userId === input.userId && a.currency === currency,
    );
    if (account) {
      account.currentBalance = newBalance;
      account.updatedAt = now;
    } else {
      this.store.walletAccounts.push({
        clubId: input.clubId,
        userId: input.userId,
        currency,
        currentBalance: newBalance,
        updatedAt: now,
      });
    }

    const day = now.slice(0, 10);
    const daily = this.getOrCreateDailyStats(input.clubId, input.userId, day);
    if (input.type === 'buy_in') {
      daily.buyIn += Math.abs(Math.trunc(input.amount));
    } else if (input.type === 'cash_out') {
      daily.cashOut += Math.abs(Math.trunc(input.amount));
    } else if ((input.type === 'deposit' || input.type === 'admin_grant') && input.amount > 0) {
      daily.deposits += Math.trunc(input.amount);
    }
    daily.updatedAt = now;

    this.scheduleSave();
    return { tx, newBalance, wasDuplicate: false };
  }

  async getWalletBalance(clubId: string, userId: string, currency = 'chips'): Promise<number> {
    const account = this.store.walletAccounts.find(
      (a) => a.clubId === clubId && a.userId === userId && a.currency === currency,
    );
    if (account) return account.currentBalance;
    return this.store.walletLedgerEntries
      .filter((tx) => tx.clubId === clubId && tx.userId === userId && tx.currency === currency)
      .reduce((sum, tx) => sum + tx.amount, 0);
  }

  async getWalletBalances(
    clubId: string,
    userIds: string[],
    currency = 'chips',
  ): Promise<Map<string, number>> {
    const result = new Map<string, number>();
    for (const userId of [...new Set(userIds)]) {
      result.set(userId, await this.getWalletBalance(clubId, userId, currency));
    }
    return result;
  }

  async listWalletTxs(
    clubId: string,
    userId: string,
    currency = 'chips',
    limit = 50,
    offset = 0,
  ): Promise<ClubWalletTransaction[]> {
    const safeLimit = Math.max(1, Math.min(limit, 200));
    const safeOffset = Math.max(0, offset);
    return this.store.walletLedgerEntries
      .filter((tx) => tx.clubId === clubId && tx.userId === userId && tx.currency === currency)
      .sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt))
      .slice(safeOffset, safeOffset + safeLimit)
      .map((tx) => ({ ...tx }));
  }

  async recordClubHandStats(
    clubId: string,
    userId: string,
    handsDelta: number,
    netDelta: number,
    rakeDelta = 0,
  ): Promise<void> {
    const now = new Date().toISOString();
    const day = now.slice(0, 10);
    const daily = this.getOrCreateDailyStats(clubId, userId, day);
    daily.hands += Math.trunc(handsDelta);
    daily.net += Math.trunc(netDelta);
    daily.rake += Math.trunc(rakeDelta);
    daily.updatedAt = now;
    this.scheduleSave();
  }

  async getClubLeaderboard(
    clubId: string,
    timeRange: ClubLeaderboardRange = 'week',
    metric: ClubLeaderboardMetric = 'net',
    limit = 50,
  ): Promise<ClubLeaderboardEntry[]> {
    const fromDay = this.dayFromRange(timeRange);
    const byUser = new Map<
      string,
      {
        hands: number;
        buyIn: number;
        cashOut: number;
        deposits: number;
        net: number;
      }
    >();

    for (const row of this.store.playerDailyStats) {
      if (row.clubId !== clubId) continue;
      if (row.day < fromDay) continue;
      const current = byUser.get(row.userId) ?? {
        hands: 0,
        buyIn: 0,
        cashOut: 0,
        deposits: 0,
        net: 0,
      };
      current.hands += row.hands;
      current.buyIn += row.buyIn;
      current.cashOut += row.cashOut;
      current.deposits += row.deposits;
      current.net += row.net;
      byUser.set(row.userId, current);
    }

    const rows = [...byUser.entries()].map(([userId, v]) => {
      const metricValue =
        metric === 'hands'
          ? v.hands
          : metric === 'buyin'
            ? v.buyIn
            : metric === 'deposits'
              ? v.deposits
              : v.net;
      return { userId, ...v, metricValue };
    });

    rows.sort((a, b) => b.metricValue - a.metricValue || a.userId.localeCompare(b.userId));

    const walletByUser = new Map<string, number>();
    for (const row of this.store.walletAccounts) {
      if (row.clubId !== clubId || row.currency !== 'chips') continue;
      walletByUser.set(row.userId, row.currentBalance);
    }

    return rows.slice(0, Math.max(1, Math.min(limit, 200))).map((row, idx) => {
      const member = this.store.members.find((m) => m.clubId === clubId && m.userId === row.userId);
      return {
        rank: idx + 1,
        clubId,
        userId: row.userId,
        displayName: member?.displayName,
        metric,
        metricValue: row.metricValue,
        balance: walletByUser.get(row.userId) ?? member?.balance ?? 0,
        hands: row.hands,
        buyIn: row.buyIn,
        cashOut: row.cashOut,
        deposits: row.deposits,
        net: row.net,
      };
    });
  }

  private getOrCreateDailyStats(
    clubId: string,
    userId: string,
    day: string,
  ): {
    clubId: string;
    userId: string;
    day: string;
    hands: number;
    buyIn: number;
    cashOut: number;
    deposits: number;
    net: number;
    rake: number;
    updatedAt: string;
  } {
    let row = this.store.playerDailyStats.find(
      (r) => r.clubId === clubId && r.userId === userId && r.day === day,
    );
    if (!row) {
      row = {
        clubId,
        userId,
        day,
        hands: 0,
        buyIn: 0,
        cashOut: 0,
        deposits: 0,
        net: 0,
        rake: 0,
        updatedAt: new Date().toISOString(),
      };
      this.store.playerDailyStats.push(row);
    }
    return row;
  }

  private dayFromRange(range: ClubLeaderboardRange): string {
    if (range === 'all') {
      return '1970-01-01';
    }
    const now = new Date();
    const dayCount = range === 'day' ? 1 : range === 'month' ? 30 : 7;
    const from = new Date(now.getTime() - (dayCount - 1) * 24 * 60 * 60 * 1000);
    return from.toISOString().slice(0, 10);
  }

  // ═══════════════ BULK HYDRATION ═══════════════

  async hydrateAll(): Promise<{
    clubs: Club[];
    members: ClubMember[];
    invites: ClubInvite[];
    rulesets: ClubRuleset[];
    tables: ClubTable[];
  }> {
    const walletByClubUser = new Map<string, number>();
    for (const row of this.store.walletAccounts) {
      if (row.currency !== 'chips') continue;
      walletByClubUser.set(`${row.clubId}:${row.userId}`, row.currentBalance);
    }

    return {
      clubs: this.store.clubs.filter((c) => !c.isArchived),
      members: this.store.members.map((m) => ({
        ...m,
        balance: walletByClubUser.get(`${m.clubId}:${m.userId}`) ?? m.balance ?? 0,
      })),
      invites: this.store.invites.filter((i) => !i.revoked),
      rulesets: this.store.rulesets,
      tables: this.store.tables.filter((t) => t.status !== 'closed'),
    };
  }
}
