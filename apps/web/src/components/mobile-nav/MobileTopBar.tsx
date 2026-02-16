import { memo } from "react";

interface MobileTopBarProps {
  title: string;
  isConnected: boolean;
  onMenuOpen: () => void;
  displayName: string;
}

export const MobileTopBar = memo(function MobileTopBar({
  title,
  isConnected,
  onMenuOpen,
  displayName,
}: MobileTopBarProps) {
  return (
    <>
      <div className="cp-mob-topbar" role="banner">
        {/* Left: menu button */}
        <button
          onClick={onMenuOpen}
          className="flex items-center justify-center w-10 h-10 rounded-lg active:bg-white/10 transition-colors"
          aria-label="Open menu"
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" className="text-slate-300">
            <line x1="3" y1="5" x2="17" y2="5" />
            <line x1="3" y1="10" x2="17" y2="10" />
            <line x1="3" y1="15" x2="17" y2="15" />
          </svg>
        </button>

        {/* Center: page title */}
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-md bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-[9px] font-extrabold text-slate-900">C</div>
          <span className="text-sm font-bold text-white tracking-tight">{title}</span>
        </div>

        {/* Right: connection + avatar */}
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${isConnected ? "bg-emerald-400" : "bg-red-400 animate-pulse"}`} />
          <div
            className="w-7 h-7 rounded-full bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-[10px] font-bold text-white uppercase"
            title={displayName}
          >
            {displayName[0]}
          </div>
        </div>
      </div>
    </>
  );
});
