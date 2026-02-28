/**
 * Notification Manager — Business logic layer for the notification system.
 *
 * Provides:
 * - notify()              — send a single notification (with preference check)
 * - notifyMany()          — batch-send notifications grouped by user
 * - notifyClubMembers()   — fan-out to all club members (with optional exclude)
 * - list / markRead / markAllRead / getUnreadCount
 * - getPreferences / updatePreferences
 * - deleteNotifications
 *
 * Real-time delivery is handled via a `deliverToUser` callback that the
 * caller (server.ts) wires to Socket.IO.
 */

import type { NotificationRepo } from './notification-repo';
import type {
  Notification,
  NotificationType,
  NotificationPreferences,
} from '@cardpilot/shared-types';
import { logInfo, logWarn } from '../logger';

// ── Input shape shared by notify / notifyMany ──

export interface NotifyInput {
  userId: string;
  type: NotificationType;
  clubId?: string;
  refId?: string;
  title: string;
  body: string;
  metadata?: Record<string, unknown>;
}

export class NotificationManager {
  constructor(
    private readonly repo: NotificationRepo,
    private readonly deliverToUser: (userId: string, event: string, payload: unknown) => void,
  ) {}

  // ── Single notification ──

  async notify(input: NotifyInput): Promise<Notification | null> {
    // Check user preferences — skip if this type is disabled
    const prefs = await this.repo.getPreferences(input.userId);
    if (prefs && prefs.preferences[input.type] === false) {
      logInfo({
        event: 'notification.skipped',
        userId: input.userId,
        message: `User disabled notification type "${input.type}"`,
      });
      return null;
    }

    const notification = await this.repo.create(input);

    // Push the new notification to the user in real time
    this.deliverToUser(input.userId, 'notification_new', { notification });

    // Push updated unread count
    const count = await this.repo.getUnreadCount(input.userId);
    this.deliverToUser(input.userId, 'notification_unread_count', { count });

    logInfo({
      event: 'notification.sent',
      userId: input.userId,
      message: `Notification "${input.type}" delivered: ${input.title}`,
    });

    return notification;
  }

  // ── Batch notifications ──

  async notifyMany(inputs: NotifyInput[]): Promise<void> {
    if (inputs.length === 0) return;

    // Group inputs by userId so we fetch preferences once per user
    const byUser = new Map<string, NotifyInput[]>();
    for (const input of inputs) {
      const list = byUser.get(input.userId) ?? [];
      list.push(input);
      byUser.set(input.userId, list);
    }

    // Filter out disabled notification types per user
    const validInputs: NotifyInput[] = [];
    for (const [userId, userInputs] of byUser) {
      const prefs = await this.repo.getPreferences(userId);
      for (const input of userInputs) {
        if (prefs && prefs.preferences[input.type] === false) {
          logInfo({
            event: 'notification.skipped',
            userId,
            message: `User disabled notification type "${input.type}"`,
          });
          continue;
        }
        validInputs.push(input);
      }
    }

    if (validInputs.length === 0) return;

    // Persist all valid notifications in a single batch
    await this.repo.createMany(validInputs);

    // Group valid inputs by userId for delivery
    const inputsByUser = new Map<string, NotifyInput[]>();
    for (const input of validInputs) {
      const list = inputsByUser.get(input.userId) ?? [];
      list.push(input);
      inputsByUser.set(input.userId, list);
    }

    // Deliver updated unread count per user
    for (const [userId] of inputsByUser) {
      const count = await this.repo.getUnreadCount(userId);
      this.deliverToUser(userId, 'notification_unread_count', { count });
    }

    logInfo({
      event: 'notification.batch_sent',
      message: `Batch delivered ${validInputs.length} notifications to ${inputsByUser.size} users`,
    });
  }

  // ── Club-wide fan-out ──

  async notifyClubMembers(
    memberUserIds: string[],
    input: Omit<NotifyInput, 'userId'> & { clubId: string },
    excludeUserId?: string,
  ): Promise<void> {
    const targets = excludeUserId
      ? memberUserIds.filter((id) => id !== excludeUserId)
      : memberUserIds;

    if (targets.length === 0) return;

    const inputs: NotifyInput[] = targets.map((userId) => ({
      ...input,
      userId,
    }));

    await this.notifyMany(inputs);
  }

  // ── List / pagination ──

  async list(
    userId: string,
    opts?: { limit?: number; before?: string; unreadOnly?: boolean },
  ): Promise<{ notifications: Notification[]; hasMore: boolean }> {
    return this.repo.list(userId, opts);
  }

  // ── Mark as read ──

  async markRead(userId: string, notificationIds: string[]): Promise<void> {
    if (notificationIds.length === 0) return;

    await this.repo.markRead(userId, notificationIds);

    const count = await this.repo.getUnreadCount(userId);
    this.deliverToUser(userId, 'notification_unread_count', { count });

    logInfo({
      event: 'notification.mark_read',
      userId,
      message: `Marked ${notificationIds.length} notification(s) as read`,
    });
  }

  async markAllRead(userId: string, clubId?: string): Promise<void> {
    await this.repo.markAllRead(userId, clubId);

    // Recalculate — if clubId was scoped, other clubs may still have unread
    const count = await this.repo.getUnreadCount(userId);
    this.deliverToUser(userId, 'notification_unread_count', { count });

    logInfo({
      event: 'notification.mark_all_read',
      userId,
      message: clubId
        ? `Marked all notifications read for club ${clubId}`
        : 'Marked all notifications read',
    });
  }

  // ── Unread count ──

  async getUnreadCount(userId: string): Promise<number> {
    return this.repo.getUnreadCount(userId);
  }

  // ── Preferences ──

  async getPreferences(userId: string): Promise<NotificationPreferences | null> {
    return this.repo.getPreferences(userId);
  }

  async updatePreferences(
    userId: string,
    prefs: Partial<Record<NotificationType, boolean>>,
  ): Promise<void> {
    await this.repo.updatePreferences(userId, prefs);

    const updated = await this.repo.getPreferences(userId);
    if (updated) {
      this.deliverToUser(userId, 'notification_prefs', { preferences: updated });
    }

    logInfo({
      event: 'notification.prefs_updated',
      userId,
      message: `Notification preferences updated`,
    });
  }

  // ── Delete ──

  async deleteNotifications(userId: string, notificationIds: string[]): Promise<void> {
    if (notificationIds.length === 0) return;

    await this.repo.deleteMany(userId, notificationIds);

    const count = await this.repo.getUnreadCount(userId);
    this.deliverToUser(userId, 'notification_unread_count', { count });

    logInfo({
      event: 'notification.deleted',
      userId,
      message: `Deleted ${notificationIds.length} notification(s)`,
    });
  }
}
