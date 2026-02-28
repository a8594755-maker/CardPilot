/**
 * Chat persistence adapter — Supabase-backed CRUD for chat entities.
 * Uses the service-role client (same pattern as ClubRepo).
 *
 * Every public method is a no-op when Supabase is not configured,
 * allowing the server to run in offline / dev mode.
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { isOverBudget } from "./egress-budget";
import type {
  ChatMessage,
  ChatMute,
  ChatReadCursor,
  ChatUnreadCount,
} from "@cardpilot/shared-types";
import { logInfo, logWarn } from "../logger";

// ── Row ↔ Domain mappers ──────────────────────────────────────────

function rowToMessage(r: Record<string, unknown>): ChatMessage {
  return {
    id: String(r.id),
    clubId: String(r.club_id),
    tableId: r.table_id ? String(r.table_id) : null,
    senderUserId: String(r.sender_user_id),
    senderDisplayName: String(r.sender_display_name ?? ""),
    messageType: (r.message_type as ChatMessage["messageType"]) ?? "text",
    content: String(r.content ?? ""),
    mentions: Array.isArray(r.mentions) ? (r.mentions as string[]) : [],
    deletedAt: r.deleted_at ? String(r.deleted_at) : null,
    deletedBy: r.deleted_by ? String(r.deleted_by) : null,
    createdAt: String(r.created_at),
  };
}

function rowToMute(r: Record<string, unknown>): ChatMute {
  return {
    id: String(r.id),
    clubId: String(r.club_id),
    userId: String(r.user_id),
    mutedBy: String(r.muted_by),
    reason: String(r.reason ?? ""),
    expiresAt: r.expires_at ? String(r.expires_at) : null,
    createdAt: String(r.created_at),
  };
}

function rowToReadCursor(r: Record<string, unknown>): ChatReadCursor {
  return {
    clubId: String(r.club_id),
    userId: String(r.user_id),
    scopeKey: String(r.scope_key),
    lastReadMessageId: r.last_read_message_id ? String(r.last_read_message_id) : null,
    lastReadAt: String(r.last_read_at),
  };
}

// ── ChatRepo ──────────────────────────────────────────────────────

export class ChatRepo {
  private readonly db: SupabaseClient | null;

  constructor() {
    const disabled = process.env.DISABLE_SUPABASE === "1";
    const url = disabled ? undefined : process.env.SUPABASE_URL;
    const serviceKey = disabled ? undefined : process.env.SUPABASE_SERVICE_ROLE_KEY;
    this.db = url && serviceKey
      ? createClient(url, serviceKey, { auth: { persistSession: false } })
      : null;

    logInfo({
      event: "chat_repo.init",
      message: this.db ? "ChatRepo connected to Supabase" : `ChatRepo running in offline mode${disabled ? " (DISABLED via env)" : " (no Supabase)"}`,
    });
  }

  enabled(): boolean {
    return this.db !== null;
  }

  // ═══════════════ MESSAGES ═══════════════

  async sendMessage(msg: {
    clubId: string;
    tableId?: string | null;
    senderUserId: string;
    senderDisplayName: string;
    messageType: ChatMessage["messageType"];
    content: string;
    mentions?: string[];
  }): Promise<ChatMessage | null> {
    if (!this.db || isOverBudget()) return null;
    const { data, error } = await this.db.from("chat_messages").insert({
      club_id: msg.clubId,
      table_id: msg.tableId ?? null,
      sender_user_id: msg.senderUserId,
      sender_display_name: msg.senderDisplayName,
      message_type: msg.messageType,
      content: msg.content,
      mentions: msg.mentions ?? [],
    }).select().single();
    if (error) {
      logWarn({ event: "chat_repo.sendMessage.failed", message: error.message });
      throw new Error(`Failed to send message: ${error.message}`);
    }
    return rowToMessage(data as Record<string, unknown>);
  }

  async getHistory(
    clubId: string,
    tableId?: string | null,
    before?: string | null,
    limit = 50,
  ): Promise<{ messages: ChatMessage[]; hasMore: boolean }> {
    if (!this.db || isOverBudget()) return { messages: [], hasMore: false };

    const safeLimit = Math.max(1, Math.min(limit, 200));

    let query = this.db
      .from("chat_messages")
      .select("id, club_id, table_id, sender_user_id, sender_display_name, message_type, content, mentions, deleted_at, deleted_by, created_at")
      .eq("club_id", clubId)
      .is("deleted_at", null)
      .order("created_at", { ascending: false })
      .limit(safeLimit + 1);

    if (tableId) {
      query = query.eq("table_id", tableId);
    } else {
      query = query.is("table_id", null);
    }

    if (before) {
      // Sub-query: get created_at of the cursor message
      const { data: cursorRow, error: cursorError } = await this.db
        .from("chat_messages")
        .select("created_at")
        .eq("id", before)
        .maybeSingle();
      if (cursorError) {
        logWarn({ event: "chat_repo.getHistory.cursor_failed", message: cursorError.message });
        throw new Error(`Failed to resolve cursor: ${cursorError.message}`);
      }
      if (cursorRow) {
        query = query.lt("created_at", String(cursorRow.created_at));
      }
    }

    const { data, error } = await query;
    if (error) {
      logWarn({ event: "chat_repo.getHistory.failed", message: error.message });
      throw new Error(`Failed to fetch chat history: ${error.message}`);
    }

    const rows = data ?? [];
    const hasMore = rows.length > safeLimit;
    const slice = hasMore ? rows.slice(0, safeLimit) : rows;

    return {
      messages: slice.map((row: any) => rowToMessage(row as Record<string, unknown>)),
      hasMore,
    };
  }

  async deleteMessage(messageId: string, deletedBy: string): Promise<void> {
    if (!this.db || isOverBudget()) return;
    const { error } = await this.db.from("chat_messages").update({
      deleted_at: new Date().toISOString(),
      deleted_by: deletedBy,
    }).eq("id", messageId);
    if (error) {
      logWarn({ event: "chat_repo.deleteMessage.failed", message: error.message });
      throw new Error(`Failed to delete message: ${error.message}`);
    }
  }

  // ═══════════════ MUTES ═══════════════

  async muteUser(
    clubId: string,
    userId: string,
    mutedBy: string,
    reason?: string,
    durationMinutes?: number,
  ): Promise<ChatMute | null> {
    if (!this.db || isOverBudget()) return null;

    const expiresAt = durationMinutes
      ? new Date(Date.now() + durationMinutes * 60 * 1000).toISOString()
      : null;

    const { data, error } = await this.db.from("chat_mutes").upsert({
      club_id: clubId,
      user_id: userId,
      muted_by: mutedBy,
      reason: reason ?? "",
      expires_at: expiresAt,
    }, { onConflict: "club_id,user_id" }).select().single();
    if (error) {
      logWarn({ event: "chat_repo.muteUser.failed", message: error.message });
      throw new Error(`Failed to mute user: ${error.message}`);
    }
    return rowToMute(data as Record<string, unknown>);
  }

  async unmuteUser(clubId: string, userId: string): Promise<void> {
    if (!this.db || isOverBudget()) return;
    const { error } = await this.db.from("chat_mutes").delete().eq("club_id", clubId).eq("user_id", userId);
    if (error) {
      logWarn({ event: "chat_repo.unmuteUser.failed", message: error.message });
      throw new Error(`Failed to unmute user: ${error.message}`);
    }
  }

  async isMuted(clubId: string, userId: string): Promise<ChatMute | null> {
    if (!this.db || isOverBudget()) return null;
    const { data, error } = await this.db
      .from("chat_mutes")
      .select("id, club_id, user_id, muted_by, reason, expires_at, created_at")
      .eq("club_id", clubId)
      .eq("user_id", userId)
      .or("expires_at.is.null,expires_at.gt." + new Date().toISOString())
      .maybeSingle();
    if (error) {
      logWarn({ event: "chat_repo.isMuted.failed", message: error.message });
      throw new Error(`Failed to check mute status: ${error.message}`);
    }
    return data ? rowToMute(data as Record<string, unknown>) : null;
  }

  // ═══════════════ READ CURSORS ═══════════════

  async markRead(
    clubId: string,
    userId: string,
    scopeKey: string,
    lastReadMessageId: string,
  ): Promise<void> {
    if (!this.db || isOverBudget()) return;
    const { error } = await this.db.from("chat_read_cursors").upsert({
      club_id: clubId,
      user_id: userId,
      scope_key: scopeKey,
      last_read_message_id: lastReadMessageId,
      last_read_at: new Date().toISOString(),
    }, { onConflict: "club_id,user_id,scope_key" });
    if (error) {
      logWarn({ event: "chat_repo.markRead.failed", message: error.message });
      throw new Error(`Failed to mark read: ${error.message}`);
    }
  }

  async getUnreads(clubId: string, userId: string): Promise<ChatUnreadCount[]> {
    if (!this.db || isOverBudget()) return [];

    // Fetch all existing cursors for this user in this club
    const { data: cursors, error: cursorError } = await this.db
      .from("chat_read_cursors")
      .select("club_id, user_id, scope_key, last_read_message_id, last_read_at")
      .eq("club_id", clubId)
      .eq("user_id", userId);
    if (cursorError) {
      logWarn({ event: "chat_repo.getUnreads.cursors_failed", message: cursorError.message });
      throw new Error(`Failed to fetch read cursors: ${cursorError.message}`);
    }

    const results: ChatUnreadCount[] = [];
    const cursorMap = new Map<string, ChatReadCursor>();
    for (const row of cursors ?? []) {
      const cursor = rowToReadCursor(row as Record<string, unknown>);
      cursorMap.set(cursor.scopeKey, cursor);
    }

    // Build all count queries and run them in parallel (instead of sequentially)
    const countTasks: Array<{ scopeKey: string; promise: PromiseLike<{ count: number | null; error: any }> }> = [];

    for (const cursor of cursorMap.values()) {
      let query = this.db
        .from("chat_messages")
        .select("id", { count: "exact", head: true })
        .eq("club_id", clubId)
        .is("deleted_at", null)
        .gt("created_at", cursor.lastReadAt);

      if (cursor.scopeKey === "club") {
        query = query.is("table_id", null);
      } else if (cursor.scopeKey.startsWith("table:")) {
        const tableId = cursor.scopeKey.slice("table:".length);
        query = query.eq("table_id", tableId);
      }

      countTasks.push({ scopeKey: cursor.scopeKey, promise: query });
    }

    // If no 'club' cursor exists, all club-level messages are unread
    if (!cursorMap.has("club")) {
      countTasks.push({
        scopeKey: "club",
        promise: this.db
          .from("chat_messages")
          .select("id", { count: "exact", head: true })
          .eq("club_id", clubId)
          .is("table_id", null)
          .is("deleted_at", null),
      });
    }

    const settled = await Promise.all(countTasks.map(async (task) => {
      const { count, error } = await task.promise;
      if (error) {
        logWarn({ event: "chat_repo.getUnreads.count_failed", scopeKey: task.scopeKey, message: error.message });
        return null;
      }
      return { clubId, scopeKey: task.scopeKey, count: count ?? 0 } as ChatUnreadCount;
    }));

    return settled.filter((r): r is ChatUnreadCount => r !== null);
  }
}
