import { useEffect, memo } from "react";

/* ═══════════════════════════════════════════════════════════════
   LeftOptionsRail + OptionsDrawer
   Compact left-side vertical rail with icons + labels.
   Clicking "Options" opens a collapsible side drawer.
   ═══════════════════════════════════════════════════════════════ */

export interface RailAction {
  id: string;
  icon: string;
  label: string;
  onClick?: () => void;
  active?: boolean;
  danger?: boolean;
  hidden?: boolean;
}

interface LeftOptionsRailProps {
  actions: RailAction[];
  onOpenDrawer: () => void;
  drawerOpen: boolean;
}

export function LeftOptionsRail({ actions, onOpenDrawer, drawerOpen }: LeftOptionsRailProps) {
  const visibleActions = actions.filter(a => !a.hidden);

  return (
    <nav className="cp-rail" aria-label="Table options">
      {/* Options button (always first) */}
      <button
        className="cp-rail-btn"
        data-active={drawerOpen ? "true" : undefined}
        onClick={onOpenDrawer}
        aria-label="Open options"
      >
        <span className="cp-rail-icon">☰</span>
        <span>Options</span>
      </button>

      {/* Divider */}
      <div className="w-8 h-px bg-white/8 mx-auto my-0.5" />

      {/* Dynamic actions */}
      {visibleActions.map((action) => (
        <button
          key={action.id}
          className="cp-rail-btn"
          data-active={action.active ? "true" : undefined}
          onClick={action.onClick}
          aria-label={action.label}
          style={action.danger ? { color: 'var(--cp-danger)' } : undefined}
        >
          <span className="cp-rail-icon">{action.icon}</span>
          <span>{action.label}</span>
        </button>
      ))}
    </nav>
  );
}

/* ═══════════════════════════════════════════════════════════════
   OptionsDrawer
   Side panel with quick settings & navigation sections.
   Closes on Esc, click outside, or explicit close.
   ═══════════════════════════════════════════════════════════════ */

export interface DrawerSection {
  id: string;
  icon: string;
  label: string;
  onClick: () => void;
  badge?: string;
  disabled?: boolean;
  disabledLabel?: string;
}

interface OptionsDrawerProps {
  open: boolean;
  onClose: () => void;
  sections: DrawerSection[];
  roomName?: string;
  roomCode?: string;
  blinds?: string;
  isHost?: boolean;
  onCopyCode?: () => void;
}

export const OptionsDrawer = memo(function OptionsDrawer({
  open,
  onClose,
  sections,
  roomName,
  roomCode,
  blinds,
  isHost,
  onCopyCode,
}: OptionsDrawerProps) {
  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="cp-drawer-backdrop"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer */}
      <aside className="cp-drawer" role="dialog" aria-label="Options panel">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/8">
          <div>
            <h2 className="text-base font-bold text-white">Options</h2>
            {roomName && (
              <p className="text-xs text-slate-400 mt-0.5">{roomName}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="cp-btn cp-btn-ghost !min-h-[36px] !min-w-[36px] !px-0 text-slate-400 hover:text-white"
            aria-label="Close options"
          >
            ✕
          </button>
        </div>

        {/* Room info strip */}
        {(roomCode || blinds) && (
          <div className="px-4 py-3 border-b border-white/5 flex items-center gap-3">
            {roomCode && (
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-slate-500 uppercase tracking-wider">Code</span>
                <span className="text-sm font-mono font-bold text-amber-400 tracking-wider">{roomCode}</span>
                {onCopyCode && (
                  <button
                    onClick={onCopyCode}
                    className="text-slate-500 hover:text-white transition-colors text-xs"
                    title="Copy room code"
                  >
                    📋
                  </button>
                )}
              </div>
            )}
            {blinds && (
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-slate-500 uppercase tracking-wider">Blinds</span>
                <span className="text-sm font-semibold text-slate-300">{blinds}</span>
              </div>
            )}
            {isHost && (
              <span className="text-[10px] px-2 py-1 rounded-full bg-amber-500/15 text-amber-400 font-bold uppercase">Host</span>
            )}
          </div>
        )}

        {/* Navigation sections */}
        <div className="p-3 space-y-1" data-testid="options-drawer-sections">
          {sections.map((section) => (
            <button
              key={section.id}
              data-testid={`drawer-item-${section.id}`}
              onClick={section.disabled ? undefined : section.onClick}
              disabled={section.disabled}
              aria-disabled={section.disabled}
              className={`w-full flex items-center gap-3 px-3 py-3 rounded-lg text-left transition-colors group ${
                section.disabled
                  ? "opacity-50 cursor-not-allowed"
                  : "hover:bg-white/5"
              }`}
            >
              <span className={`text-lg transition-opacity ${
                section.disabled ? "opacity-40" : "opacity-70 group-hover:opacity-100"
              }`}>
                {section.icon}
              </span>
              <div className="flex-1 min-w-0">
                <span className={`text-sm font-medium block transition-colors ${
                  section.disabled
                    ? "text-slate-500"
                    : "text-slate-300 group-hover:text-white"
                }`}>
                  {section.label}
                </span>
                {section.disabledLabel && (
                  <span className="text-[10px] text-slate-600 block mt-0.5">
                    {section.disabledLabel}
                  </span>
                )}
              </div>
              {section.badge && (
                <span className="cp-badge bg-amber-500/15 text-amber-400 border border-amber-500/25">
                  {section.badge}
                </span>
              )}
              {!section.disabled && (
                <span className="text-slate-600 text-xs group-hover:text-slate-400 transition-colors">›</span>
              )}
            </button>
          ))}
        </div>
      </aside>
    </>
  );
});

export default LeftOptionsRail;
