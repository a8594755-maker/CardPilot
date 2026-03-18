import type { ReactNode } from 'react';

interface StrategyBrowserLayoutProps {
  leftSidebar: ReactNode;
  centerPanel: ReactNode;
  rightPanel: ReactNode;
}

export function StrategyBrowserLayout({
  leftSidebar,
  centerPanel,
  rightPanel,
}: StrategyBrowserLayoutProps) {
  return (
    <div className="flex h-[calc(100vh-0px)] overflow-hidden -m-6 min-w-[1100px]">
      {/* Left Sidebar */}
      <aside className="w-[220px] flex-shrink-0 border-r border-border bg-card overflow-y-auto">
        {leftSidebar}
      </aside>

      {/* Center Panel */}
      <main className="flex-1 overflow-y-auto bg-background min-w-[500px]">{centerPanel}</main>

      {/* Right Panel */}
      <aside className="w-[340px] flex-shrink-0 border-l border-border bg-card overflow-y-auto">
        {rightPanel}
      </aside>
    </div>
  );
}
