import { memo, useEffect } from 'react';
import type { AppView } from './MobileBottomTabs';

interface MoreMenuItem {
  id: AppView;
  label: string;
  icon: React.ReactNode;
}

/* SVG icons — Lucide-style (no-emoji-icons per UX guidelines) */
const IconHistory = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
);
const IconTraining = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <circle cx="12" cy="12" r="10" />
    <circle cx="12" cy="12" r="6" />
    <circle cx="12" cy="12" r="2" />
  </svg>
);
const IconBattle = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
  </svg>
);
const IconPreflop = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <line x1="18" y1="20" x2="18" y2="10" />
    <line x1="12" y1="20" x2="12" y2="4" />
    <line x1="6" y1="20" x2="6" y2="14" />
  </svg>
);
const IconSolver = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <rect x="4" y="4" width="16" height="16" rx="2" />
    <line x1="4" y1="10" x2="20" y2="10" />
    <line x1="10" y1="4" x2="10" y2="20" />
  </svg>
);
const IconSignOut = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <polyline points="16 17 21 12 16 7" />
    <line x1="21" y1="12" x2="9" y2="12" />
  </svg>
);

const MORE_ITEMS: MoreMenuItem[] = [
  { id: 'history', label: 'History', icon: <IconHistory /> },
  { id: 'training', label: 'Training', icon: <IconTraining /> },
  { id: 'fast-battle', label: 'Fast Battle', icon: <IconBattle /> },
  { id: 'preflop', label: 'Preflop GTO', icon: <IconPreflop /> },
  { id: 'solver', label: 'GTO Solver', icon: <IconSolver /> },
];

interface MobileMoreMenuProps {
  open: boolean;
  onClose: () => void;
  activeView: string;
  onNavigate: (view: AppView) => void;
  onSignOut?: () => void;
}

export const MobileMoreMenu = memo(function MobileMoreMenu({
  open,
  onClose,
  activeView,
  onNavigate,
  onSignOut,
}: MobileMoreMenuProps) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      <div className="cp-mob-more-backdrop" onClick={onClose} aria-hidden="true" />
      <div className="cp-mob-more-sheet" role="dialog" aria-label="More options">
        <div className="cp-mob-more-handle" />
        {MORE_ITEMS.map((item) => (
          <button
            key={item.id}
            className="cp-mob-more-item"
            data-active={activeView === item.id ? 'true' : undefined}
            onClick={() => {
              onNavigate(item.id);
              onClose();
            }}
          >
            <span className="cp-mob-more-item-icon">{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
        {onSignOut && (
          <>
            <div className="mx-5 my-1 border-t border-white/5" />
            <button
              className="cp-mob-more-item"
              onClick={() => {
                onSignOut();
                onClose();
              }}
            >
              <span className="cp-mob-more-item-icon text-red-400">
                <IconSignOut />
              </span>
              <span className="text-red-400">Sign Out</span>
            </button>
          </>
        )}
      </div>
    </>
  );
});
