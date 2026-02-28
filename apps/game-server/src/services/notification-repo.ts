/**
 * Notification persistence adapter — Supabase-backed CRUD for notifications
 * and notification preferences.
 * Uses the service-role client (same pattern as ClubRepo).
 *
 * Every public method is a no-op when Supabase is not configured,
 * allowing the server to run in offline / dev mode.
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { isOverBudget } from "./egress-budget";
import type {
  Notification,
  NotificationType,
  NotificationPreferences,
} from "@cardpilot/shared-types";
import { logInfo, logWarn } from "../logger";

// ── Row ↔ Domain mappers ──────────────────────────────────────────

function rowToNotification(r: Record<string, unknown>): Notification {
  return {
    id: String(r.id),
    userId: String(r.user_id),
    type: String(r.type) as NotificationType,
    clubId: r.club_id ? String(r.club_id) : null,
    refId: r.ref_id ? String(r.ref_id) : null,
    title: String(r.title),
    body: String(r.body),
    metadata: (r.metadata as Record<string, unknown>) ?? {},
    isRead: Boolean(r.is_read),
    readAt: r.read_at ? String(r.read_at) : null,
    createdAt: String(r.created_at),
  };
}

function rowToPreferences(r: Record<string, unknown>): NotificationPreferences {
  return {
    userId: String(r.user_id),
    preferences: (r.preferences as Partial<Record<NotificationType, boolean>>) ?? {},
    updatedAt: String(r.updated_at),
  };
}

// ── NotificationRepo ──────────────────────────────────────────────

export class NotificationRepo {
  private readonly db: SupabaseClient | null;

  constructor() {
    const disabled = process.env.DISABLE_SUPABASE === "1";
    const url = disabled ? undefined : process.env.SUPABASE_URL;
    const serviceKey = disabled ? undefined : process.env.SUPABASE_SERVICE_ROLE_KEY;
    this.db = url && serviceKey
      ? createClient(url, serviceKey, { auth: { persistSession: false } })
      : null;

    logInfo({
      event: "notification_repo.init",
      message: this.db ? "NotificationRepo connected to Supabase" : `NotificationRepo running in offline mode${disabled ? " (DISABLED via env)" : " (no Supabase)"}`,
    });
  }

  enabled(): boolean {
    return this.db !== null;
  }

  // ═══════════════ NOTIFICATIONS ═══════════════

  async create(input: {
    userId: string;
    type: NotificationType;
    clubId?: string;
    refId?: string;
    title: string;
    body: string;
    metadata?: Record<string, unknown>;
  }): Promise<Notification | null> {
    if (!this.db || isOverBudget()) return null;
    const { data, error } = await this.db.from("notifications").insert({
      user_id: input.userId,
      type: input.type,
      club_id: input.clubId ?? null,
      ref_id: input.refId ?? null,
      title: input.title,
      body: input.body,
      metadata: input.metadata ?? {},
    }).select().single();
    if (error) {
      logWarn({ event: "notification_repo.create.failed", message: error.message });
      throw new Error(`Failed to create notification: ${error.message}`);
    }
    return rowToNotification(data as Record<string, unknown>);
  }

  async createMany(inputs: Array<{
    userId: string;
    type: NotificationType;
    clubId?: string;
    refId?: string;
    title: string;
    body: string;
    metadata?: Record<string, unknown>;
  }>): Promise<void> {
    if (!this.db || isOverBudget()) return;
    if (inputs.length === 0) return;
    const rows = inputs.map((input) => ({
      user_id: input.userId,
      type: input.type,
      club_id: input.clubId ?? null,
      ref_id: input.refId ?? null,
      title: input.title,
      body: input.body,
      metadata: input.metadata ?? {},
    }));
    const { error } = await this.db.from("notifications").insert(rows);
    if (error) {
      logWarn({ event: "notification_repo.createMany.failed", message: error.message });
      throw new Error(`Failed to create notifications: ${error.message}`);
    }
  }

  async list(
    userId: string,
    opts?: { limit?: number; before?: string; unreadOnly?: boolean },
  ): Promise<{ notifications: Notification[]; hasMore: boolean }> {
    if (!this.db || isOverBudget()) return { notifications: [], hasMore: false };

    const limit = opts?.limit ?? 50;
    let query = this.db
      .from("notifications")
      .select("id, user_id, type, club_id, ref_id, title, body, metadata, is_read, read_at, created_at")
      .eq("user_id", userId);

    if (opts?.unreadOnly) {
      query = query.eq("is_read", false);
    }

    if (opts?.before) {
      // Sub-query: get created_at for the cursor notification
      const { data: cursorRow, error: cursorError } = await this.db
        .from("notifications")
        .select("created_at")
        .eq("id", opts.before)
        .maybeSingle();

      if (cursorError) {
        logWarn({ event: "notification_repo.list.cursor_failed", message: cursorError.message });
        throw new Error(`Failed to resolve cursor: ${cursorError.message}`);
      }
      if (cursorRow) {
        query = query.lt("created_at", String(cursorRow.created_at));
      }
    }

    query = query
      .order("created_at", { ascending: false })
      .limit(limit + 1);

    const { data, error } = await query;
    if (error) {
      logWarn({ event: "notification_repo.list.failed", message: error.message });
      throw new Error(`Failed to list notifications: ${error.message}`);
    }

    const rows = data ?? [];
    const hasMore = rows.length > limit;
    const slice = hasMore ? rows.slice(0, limit) : rows;
    return {
      notifications: slice.map((row: any) => rowToNotification(row)),
      hasMore,
    };
  }

  async markRead(userId: string, notificationIds: string[]): Promise<void> {
    if (!this.db || isOverBudget()) return;
    if (notificationIds.length === 0) return;
    const { error } = await this.db
      .from("notifications")
      .update({ is_read: true, read_at: new Date().toISOString() })
      .in("id", notificationIds)
      .eq("user_id", userId);
    if (error) {
      logWarn({ event: "notification_repo.markRead.failed", message: error.message });
      throw new Error(`Failed to mark notifications read: ${error.message}`);
    }
  }

  async markAllRead(userId: string, clubId?: string): Promise<void> {
    if (!this.db || isOverBudget()) return;
    let query = this.db
      .from("notifications")
      .update({ is_read: true, read_at: new Date().toISOString() })
      .eq("user_id", userId)
      .eq("is_read", false);

    if (clubId) {
      query = query.eq("club_id", clubId);
    }

    const { error } = await query;
    if (error) {
      logWarn({ event: "notification_repo.markAllRead.failed", message: error.message });
      throw new Error(`Failed to mark all notifications read: ${error.message}`);
    }
  }

  async getUnreadCount(userId: string): Promise<number> {
    if (!this.db || isOverBudget()) return 0;
    const { count, error } = await this.db
      .from("notifications")
      .select("id", { count: "exact", head: true })
      .eq("user_id", userId)
      .eq("is_read", false);
    if (error) {
      logWarn({ event: "notification_repo.getUnreadCount.failed", message: error.message });
      throw new Error(`Failed to get unread count: ${error.message}`);
    }
    return count ?? 0;
  }

  async deleteMany(userId: string, notificationIds: string[]): Promise<void> {
    if (!this.db || isOverBudget()) return;
    if (notificationIds.length === 0) return;
    const { error } = await this.db
      .from("notifications")
      .delete()
      .in("id", notificationIds)
      .eq("user_id", userId);
    if (error) {
      logWarn({ event: "notification_repo.deleteMany.failed", message: error.message });
      throw new Error(`Failed to delete notifications: ${error.message}`);
    }
  }

  // ═══════════════ PREFERENCES ═══════════════

  async getPreferences(userId: string): Promise<NotificationPreferences | null> {
    if (!this.db || isOverBudget()) return null;
    const { data, error } = await this.db
      .from("notification_preferences")
      .select("user_id, preferences, updated_at")
      .eq("user_id", userId)
      .maybeSingle();
    if (error) {
      logWarn({ event: "notification_repo.getPreferences.failed", message: error.message });
      throw new Error(`Failed to fetch notification preferences: ${error.message}`);
    }
    return data ? rowToPreferences(data) : null;
  }

  async updatePreferences(
    userId: string,
    prefs: Partial<Record<NotificationType, boolean>>,
  ): Promise<NotificationPreferences> {
    if (!this.db) {
      return { userId, preferences: prefs, updatedAt: new Date().toISOString() };
    }
    const { data, error } = await this.db
      .from("notification_preferences")
      .upsert({
        user_id: userId,
        preferences: prefs,
        updated_at: new Date().toISOString(),
      }, { onConflict: "user_id" })
      .select()
      .single();
    if (error) {
      logWarn({ event: "notification_repo.updatePreferences.failed", message: error.message });
      throw new Error(`Failed to update notification preferences: ${error.message}`);
    }
    return rowToPreferences(data as Record<string, unknown>);
  }
}
