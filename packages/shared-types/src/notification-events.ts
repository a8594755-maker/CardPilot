// ===== Notification Socket Events =====

import type { Notification, NotificationType, NotificationPreferences } from './notification-types.js';

// ── Client → Server Payloads ──

export interface NotificationListPayload {
  limit?: number;              // default 50
  before?: string;             // cursor: notification id
  unreadOnly?: boolean;
}

export interface NotificationMarkReadPayload {
  notificationIds: string[];
}

export interface NotificationMarkAllReadPayload {
  clubId?: string;             // scope to club, omit for all
}

export interface NotificationGetUnreadCountPayload {}

export interface NotificationUpdatePrefsPayload {
  preferences: Partial<Record<NotificationType, boolean>>;
}

export interface NotificationDeletePayload {
  notificationIds: string[];
}

// ── Server → Client Payloads ──

export interface NotificationNewPayload {
  notification: Notification;
}

export interface NotificationListResponsePayload {
  notifications: Notification[];
  hasMore: boolean;
}

export interface NotificationUnreadCountPayload {
  count: number;
}

export interface NotificationPrefsPayload {
  preferences: NotificationPreferences;
}

export interface NotificationErrorPayload {
  code: string;
  message: string;
}

// ── Event Maps ──

export interface NotificationClientToServerEvents {
  notification_list: (payload: NotificationListPayload) => void;
  notification_mark_read: (payload: NotificationMarkReadPayload) => void;
  notification_mark_all_read: (payload: NotificationMarkAllReadPayload) => void;
  notification_get_unread_count: (payload: NotificationGetUnreadCountPayload) => void;
  notification_update_prefs: (payload: NotificationUpdatePrefsPayload) => void;
  notification_delete: (payload: NotificationDeletePayload) => void;
}

export interface NotificationServerToClientEvents {
  notification_new: (payload: NotificationNewPayload) => void;
  notification_list_response: (payload: NotificationListResponsePayload) => void;
  notification_unread_count: (payload: NotificationUnreadCountPayload) => void;
  notification_prefs: (payload: NotificationPrefsPayload) => void;
  notification_error: (payload: NotificationErrorPayload) => void;
}
