import { memo } from "react";
import { NotificationBell } from "../notifications/NotificationBell";

interface MobileTopBarProps {
  title: string;
  isConnected: boolean;
  onMenuOpen: () => void;
  displayName: string;
  notificationCount?: number;
  onNotificationsClick?: () => void;
}

export const MobileTopBar = memo(function MobileTopBar({
  title,
  isConnected,
  onMenuOpen,
  displayName,
  notificationCount = 0,
  onNotificationsClick,
}: MobileTopBarProps) {
  return (
    <>
      <div className="cp-mob-topbar" role="banner">
        {/* Left: menu button */}
        <button
          onClick={onMenuOpen}
          className="flex items-center justify-center w-8.5 h-8.5 rounded-lg active:bg-white/10 transition-colors"
          aria-label="Open menu"
        >
          <svg width="17" height="17" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" className="text-slate-300">
            <line x1="3" y1="5" x2="17" y2="5" />
            <line x1="3" y1="10" x2="17" y2="10" />
            <line x1="3" y1="15" x2="17" y2="15" />
          </svg>
        </button>

        {/* Center: page title */}
        <div className="flex items-center gap-1.5">
          <div className="w-4.5 h-4.5 rounded-md bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-[8px] font-extrabold text-slate-900">C</div>
          <span className="text-[13px] font-bold text-white tracking-tight">{title}</span>
        </div>

        {/* Right: connection + notifications + avatar */}
        <div className="flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? "bg-emerald-400" : "bg-red-400 animate-pulse"}`} />
          {onNotificationsClick && (
            <NotificationBell unreadCount={notificationCount} onClick={onNotificationsClick} />
          )}
          <div
            className="w-6 h-6 rounded-full bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-[9px] font-bold text-white uppercase"
            title={displayName}
          >
            {displayName[0]}
          </div>
        </div>
      </div>
    </>
  );
});
