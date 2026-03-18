import { useState, useEffect, useCallback } from 'react';
import type { Socket } from 'socket.io-client';
import type {
  Notification,
  NotificationType,
  NotificationPreferences,
  NotificationNewPayload,
  NotificationListResponsePayload,
  NotificationUnreadCountPayload,
  NotificationPrefsPayload,
  NotificationErrorPayload,
} from '@cardpilot/shared-types';

export interface NotificationActions {
  loadNotifications: (opts?: { before?: string; unreadOnly?: boolean }) => void;
  markRead: (notificationIds: string[]) => void;
  markAllRead: (clubId?: string) => void;
  refreshUnreadCount: () => void;
  updatePreferences: (prefs: Partial<Record<NotificationType, boolean>>) => void;
  deleteNotifications: (notificationIds: string[]) => void;
}

export interface NotificationState {
  notifications: Notification[];
  hasMore: boolean;
  unreadCount: number;
  preferences: NotificationPreferences | null;
  loading: boolean;
}

export function useNotifications(socket: Socket | null): {
  actions: NotificationActions;
  state: NotificationState;
} {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null);
  const [loading, setLoading] = useState(false);

  // Socket listeners
  useEffect(() => {
    if (!socket) return;

    const onNew = (payload: NotificationNewPayload) => {
      setNotifications((prev) => {
        if (prev.some((n) => n.id === payload.notification.id)) return prev;
        return [payload.notification, ...prev];
      });
    };

    const onList = (payload: NotificationListResponsePayload) => {
      setLoading(false);
      setHasMore(payload.hasMore);
      setNotifications((prev) => {
        const existingIds = new Set(prev.map((n) => n.id));
        const newNotifs = payload.notifications.filter((n) => !existingIds.has(n.id));
        return [...prev, ...newNotifs];
      });
    };

    const onUnreadCount = (payload: NotificationUnreadCountPayload) => {
      setUnreadCount(payload.count);
    };

    const onPrefs = (payload: NotificationPrefsPayload) => {
      setPreferences(payload.preferences);
    };

    const onError = (payload: NotificationErrorPayload) => {
      setLoading(false);
      console.warn('[notifications] error:', payload.code, payload.message);
    };

    socket.on('notification_new', onNew);
    socket.on('notification_list_response', onList);
    socket.on('notification_unread_count', onUnreadCount);
    socket.on('notification_prefs', onPrefs);
    socket.on('notification_error', onError);

    // Fetch initial unread count
    socket.emit('notification_get_unread_count', {});

    return () => {
      socket.off('notification_new', onNew);
      socket.off('notification_list_response', onList);
      socket.off('notification_unread_count', onUnreadCount);
      socket.off('notification_prefs', onPrefs);
      socket.off('notification_error', onError);
    };
  }, [socket]);

  const loadNotifications = useCallback(
    (opts?: { before?: string; unreadOnly?: boolean }) => {
      setLoading(true);
      socket?.emit('notification_list', {
        limit: 30,
        before: opts?.before,
        unreadOnly: opts?.unreadOnly,
      });
    },
    [socket],
  );

  const markRead = useCallback(
    (notificationIds: string[]) => {
      socket?.emit('notification_mark_read', { notificationIds });
      setNotifications((prev) =>
        prev.map((n) =>
          notificationIds.includes(n.id)
            ? { ...n, isRead: true, readAt: new Date().toISOString() }
            : n,
        ),
      );
    },
    [socket],
  );

  const markAllRead = useCallback(
    (clubId?: string) => {
      socket?.emit('notification_mark_all_read', { clubId });
      setNotifications((prev) =>
        prev.map((n) => {
          if (clubId && n.clubId !== clubId) return n;
          return { ...n, isRead: true, readAt: new Date().toISOString() };
        }),
      );
    },
    [socket],
  );

  const refreshUnreadCount = useCallback(() => {
    socket?.emit('notification_get_unread_count', {});
  }, [socket]);

  const updatePreferences = useCallback(
    (prefs: Partial<Record<NotificationType, boolean>>) => {
      socket?.emit('notification_update_prefs', { preferences: prefs });
    },
    [socket],
  );

  const deleteNotifications = useCallback(
    (notificationIds: string[]) => {
      socket?.emit('notification_delete', { notificationIds });
      setNotifications((prev) => prev.filter((n) => !notificationIds.includes(n.id)));
    },
    [socket],
  );

  return {
    actions: {
      loadNotifications,
      markRead,
      markAllRead,
      refreshUnreadCount,
      updatePreferences,
      deleteNotifications,
    },
    state: { notifications, hasMore, unreadCount, preferences, loading },
  };
}
