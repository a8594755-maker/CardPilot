import { memo } from 'react';

type AppView =
  | 'lobby'
  | 'table'
  | 'profile'
  | 'history'
  | 'clubs'
  | 'training'
  | 'preflop'
  | 'fast-battle'
  | 'cfr'
  | 'solver';

interface TabDef {
  id: AppView | '__more__';
  label: string;
  icon: React.ReactNode;
}

/* SVG icons — Lucide-style, 20x20, stroke-based (no-emoji-icons per UX guidelines) */
const IconLobby = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    <polyline points="9 22 9 12 15 12 15 22" />
  </svg>
);
const IconTable = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <rect x="2" y="4" width="20" height="16" rx="3" />
    <ellipse cx="12" cy="12" rx="6" ry="4" />
  </svg>
);
const IconClubs = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M6 9H4.5a2.5 2.5 0 0 1 0-5C7 4 9 7 12 7s5-3 7.5-3a2.5 2.5 0 0 1 0 5H18" />
    <path d="M12 7v10" />
    <path d="M8 21h8" />
    <path d="M12 17l-4 4" />
    <path d="M12 17l4 4" />
  </svg>
);
const IconProfile = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
    <circle cx="12" cy="7" r="4" />
  </svg>
);
const IconMore = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <circle cx="12" cy="12" r="1" />
    <circle cx="19" cy="12" r="1" />
    <circle cx="5" cy="12" r="1" />
  </svg>
);

const PRIMARY_TABS: TabDef[] = [
  { id: 'lobby', label: 'Lobby', icon: <IconLobby /> },
  { id: 'table', label: 'Table', icon: <IconTable /> },
  { id: 'clubs', label: 'Clubs', icon: <IconClubs /> },
  { id: 'profile', label: 'Profile', icon: <IconProfile /> },
  { id: '__more__', label: 'More', icon: <IconMore /> },
];

const SECONDARY_VIEWS: AppView[] = ['history', 'training', 'preflop', 'fast-battle', 'solver'];

interface MobileBottomTabsProps {
  activeView: string;
  onNavigate: (view: AppView) => void;
  onMoreOpen: () => void;
  moreOpen: boolean;
}

export const MobileBottomTabs = memo(function MobileBottomTabs({
  activeView,
  onNavigate,
  onMoreOpen,
  moreOpen,
}: MobileBottomTabsProps) {
  const isSecondaryActive = SECONDARY_VIEWS.includes(activeView as AppView);

  return (
    <>
      <nav className="cp-mob-bottomtabs" role="tablist" aria-label="Main navigation">
        {PRIMARY_TABS.map((tab) => {
          const isMore = tab.id === '__more__';
          const isActive = isMore ? moreOpen || isSecondaryActive : activeView === tab.id;

          return (
            <button
              key={tab.id}
              role="tab"
              aria-selected={isActive}
              data-active={isActive ? 'true' : undefined}
              className="cp-mob-tab"
              onClick={() => {
                if (isMore) {
                  onMoreOpen();
                } else {
                  onNavigate(tab.id as AppView);
                }
              }}
            >
              <span className="cp-mob-tab-icon">{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          );
        })}
      </nav>
    </>
  );
});

export { SECONDARY_VIEWS };
export type { AppView };
