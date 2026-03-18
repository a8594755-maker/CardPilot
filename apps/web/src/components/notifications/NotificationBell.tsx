import React, { memo } from 'react';

interface NotificationBellProps {
  unreadCount: number;
  onClick: () => void;
}

export const NotificationBell = memo(function NotificationBell({
  unreadCount,
  onClick,
}: NotificationBellProps) {
  return (
    <button
      onClick={onClick}
      className="relative p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
      aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        className="h-5 w-5"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={2}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
        />
      </svg>
      {unreadCount > 0 && (
        <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-500 px-1 text-[9px] font-bold text-white">
          {unreadCount > 99 ? '99+' : unreadCount}
        </span>
      )}
    </button>
  );
});

export default NotificationBell;
