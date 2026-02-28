import { memo } from "react";

type AppView = "lobby" | "table" | "profile" | "history" | "clubs" | "training" | "preflop";

interface TabDef {
  id: AppView | "__more__";
  label: string;
  icon: string;
}

const PRIMARY_TABS: TabDef[] = [
  { id: "lobby",   label: "Lobby",   icon: "🏠" },
  { id: "table",   label: "Table",   icon: "🃏" },
  { id: "clubs", label: "Clubs", icon: "🏆" },
  { id: "profile", label: "Profile", icon: "👤" },
  { id: "__more__", label: "More",   icon: "⋯" },
];

const SECONDARY_VIEWS: AppView[] = ["history", "training", "preflop"];

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
          const isMore = tab.id === "__more__";
          const isActive = isMore
            ? (moreOpen || isSecondaryActive)
            : activeView === tab.id;

          return (
            <button
              key={tab.id}
              role="tab"
              aria-selected={isActive}
              data-active={isActive ? "true" : undefined}
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
