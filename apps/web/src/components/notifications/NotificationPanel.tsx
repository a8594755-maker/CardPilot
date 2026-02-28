import React, { memo, useEffect } from "react";
import type { Notification } from "@cardpilot/shared-types";
import type { NotificationActions, NotificationState } from "../../pages/clubs/hooks/useNotifications";

interface NotificationPanelProps {
  state: NotificationState;
  actions: NotificationActions;
  onClose: () => void;
  onNavigate?: (clubId: string, refId?: string | null) => void;
}

const NOTIFICATION_ICONS: Record<string, string> = {
  table_opened: "🎯",
  table_started: "🃏",
  join_request_received: "📩",
  join_request_approved: "✅",
  join_request_rejected: "❌",
  role_changed: "👑",
  kicked: "🚫",
  banned: "⛔",
  credit_granted: "💰",
  credit_deducted: "💸",
  chat_mention: "💬",
};

export const NotificationPanel = memo(function NotificationPanel({
  state,
  actions,
  onClose,
  onNavigate,
}: NotificationPanelProps) {
  // Load initial notifications when panel opens
  useEffect(() => {
    if (state.notifications.length === 0) {
      actions.loadNotifications();
    }
  }, [actions, state.notifications.length]);

  const handleMarkAllRead = () => {
    actions.markAllRead();
  };

  const handleNotificationClick = (notification: Notification) => {
    if (!notification.isRead) {
      actions.markRead([notification.id]);
    }
    if (notification.clubId && onNavigate) {
      onNavigate(notification.clubId, notification.refId);
    }
  };

  const handleLoadMore = () => {
    const oldest = state.notifications[state.notifications.length - 1];
    if (oldest) {
      actions.loadNotifications({ before: oldest.id });
    }
  };

  return (
    <div className="absolute right-0 top-full mt-2 w-80 max-h-[480px] rounded-xl border border-slate-700 bg-slate-900 shadow-2xl z-50 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
        <h3 className="text-sm font-semibold text-white">Notifications</h3>
        <div className="flex items-center gap-2">
          {state.unreadCount > 0 && (
            <button
              onClick={handleMarkAllRead}
              className="text-[10px] text-cyan-400 hover:text-cyan-300 transition-colors"
            >
              Mark all read
            </button>
          )}
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-300 transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          </button>
        </div>
      </div>

      {/* Notification list */}
      <div className="flex-1 overflow-y-auto">
        {state.notifications.length === 0 && !state.loading && (
          <div className="px-4 py-8 text-center">
            <div className="text-2xl mb-2">🔔</div>
            <div className="text-xs text-slate-500">No notifications yet</div>
          </div>
        )}

        {state.loading && state.notifications.length === 0 && (
          <div className="px-4 py-8 text-center text-xs text-slate-500">
            Loading...
          </div>
        )}

        {state.notifications.map((notification) => (
          <button
            key={notification.id}
            onClick={() => handleNotificationClick(notification)}
            className={`w-full text-left px-4 py-3 border-b border-slate-800/50 hover:bg-slate-800/40 transition-colors ${
              !notification.isRead ? "bg-slate-800/20" : ""
            }`}
          >
            <div className="flex items-start gap-3">
              <span className="text-lg shrink-0 mt-0.5">
                {NOTIFICATION_ICONS[notification.type] ?? "🔔"}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-slate-200 truncate">
                    {notification.title}
                  </span>
                  {!notification.isRead && (
                    <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 shrink-0" />
                  )}
                </div>
                {notification.body && (
                  <div className="text-[11px] text-slate-400 mt-0.5 line-clamp-2">
                    {notification.body}
                  </div>
                )}
                <div className="text-[10px] text-slate-500 mt-1">
                  {formatRelativeTime(notification.createdAt)}
                </div>
              </div>
            </div>
          </button>
        ))}

        {state.hasMore && (
          <div className="px-4 py-3 text-center">
            <button
              onClick={handleLoadMore}
              disabled={state.loading}
              className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors disabled:opacity-50"
            >
              {state.loading ? "Loading..." : "Load more"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
});

function formatRelativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

export default NotificationPanel;
