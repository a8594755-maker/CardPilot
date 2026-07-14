import { memo, useEffect } from 'react';
import type { AppView } from './MobileBottomTabs';
import { useI18n, LanguageToggle } from '../../i18n';

interface MoreMenuItem {
  id: AppView;
  label: string;
  icon: string;
}

const MORE_ITEMS: MoreMenuItem[] = [
  { id: 'clubs', label: 'Clubs', icon: '🏆' },
  { id: 'fast-battle', label: 'Fast Battle', icon: '⚡' },
  { id: 'cfr', label: 'GTO Strategy', icon: '📊' },
  { id: 'preflop', label: 'Preflop GTO', icon: '🎴' },
  { id: 'solver', label: 'GTO Solver', icon: '🧮' },
  { id: 'profile', label: 'Profile', icon: '👤' },
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
  const { t } = useI18n();
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
            <span>{t(item.label)}</span>
          </button>
        ))}
        <div className="flex justify-center py-2">
          <LanguageToggle />
        </div>
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
              <span className="cp-mob-more-item-icon">🚪</span>
              <span className="text-red-400">{t('Sign Out')}</span>
            </button>
          </>
        )}
      </div>
    </>
  );
});
