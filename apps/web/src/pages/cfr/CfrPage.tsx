// Unified GTO Strategy page — Preflop + Postflop in one interface.
// Preflop uses full-width grid layout (original PreflopTrainer style).
// Postflop uses sidebar + main content layout.

import { useState } from 'react';
import { useStrategyViewer } from './hooks/useStrategyViewer';
import { useFlopBrowser } from './hooks/useFlopBrowser';
import { usePreflopViewer } from './hooks/usePreflopViewer';
import { FlopSidebar } from './components/sidebar/FlopSidebar';
import { StrategyViewer } from './components/viewer/StrategyViewer';
import { WelcomeScreen } from './components/viewer/WelcomeScreen';
import { TrainingMode } from './components/training/TrainingMode';
import { PreflopContent } from './components/viewer/PreflopContent';
import { SegmentedControl } from './components/shared/SegmentedControl';
import { BoardLoadingSkeleton } from './components/viewer/BoardLoadingSkeleton';

type GtoMode = 'preflop' | 'postflop';

interface CfrPageProps {
  initialMode?: GtoMode;
}

export function CfrPage({ initialMode = 'postflop' }: CfrPageProps) {
  const [gtoMode, setGtoMode] = useState<GtoMode>(initialMode);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Postflop state
  const [postflopState, postflopActions] = useStrategyViewer();
  const [browser, browserActions] = useFlopBrowser(postflopState.flops);

  // Preflop state
  const [preflopState, preflopActions] = usePreflopViewer();

  // ─── PREFLOP MODE: full-width layout (no sidebar) ───
  if (gtoMode === 'preflop') {
    return (
      <main className="flex-1 p-2 sm:p-4 overflow-y-auto">
        <div className="max-w-5xl mx-auto space-y-3">
          {/* Header */}
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <h2 className="text-xl font-bold text-white">GTO Strategy</h2>
              {preflopState.index && (
                <p className="text-[10px] text-slate-500">
                  {preflopState.index.spots.length} spots solved — {preflopState.index.solveDate}
                </p>
              )}
            </div>
            <div className="flex items-center gap-3">
              {/* Mode toggle */}
              <SegmentedControl
                options={[
                  { value: 'preflop' as const, label: 'Preflop' },
                  { value: 'postflop' as const, label: 'Postflop' },
                ]}
                value={gtoMode}
                onChange={setGtoMode}
                size="sm"
              />
            </div>
          </div>

          {/* Preflop content (charts + drill) */}
          {preflopState.loading ? (
            <div className="glass-card p-8 text-center">
              <div className="text-slate-400 text-sm">Loading preflop solutions...</div>
            </div>
          ) : preflopState.error ? (
            <div className="glass-card p-8 text-center">
              <p className="text-red-400 text-sm">{preflopState.error}</p>
            </div>
          ) : preflopState.index ? (
            <PreflopContent state={preflopState} actions={preflopActions} />
          ) : null}
        </div>
      </main>
    );
  }

  // ─── POSTFLOP MODE: sidebar + main content ───
  return (
    <div className="flex h-full max-lg:flex-col relative">
      {/* Collapsible sidebar wrapper */}
      <div className={`transition-all duration-200 max-lg:w-full max-lg:min-w-0 ${sidebarCollapsed ? 'lg:w-0 lg:min-w-0 lg:overflow-hidden' : 'lg:w-[380px] lg:min-w-[380px]'}`}>
        <FlopSidebar
          configs={postflopState.configs}
          selectedConfig={postflopState.selectedConfig}
          onSelectConfig={(name) => { postflopActions.selectConfig(name); browserActions.resetFilters(); }}
          filteredFlops={browser.filteredFlops}
          totalFlops={postflopState.flops.length}
          selectedBoardId={postflopState.selectedBoardId}
          onSelectBoard={postflopActions.selectBoard}
          searchQuery={browser.searchQuery}
          onSearchChange={browserActions.setSearchQuery}
          textureFilter={browser.textureFilter}
          onTextureFilter={browserActions.setTextureFilter}
          pairingFilter={browser.pairingFilter}
          onPairingFilter={browserActions.setPairingFilter}
          highCardFilter={browser.highCardFilter}
          onHighCardFilter={browserActions.setHighCardFilter}
          onResetFilters={browserActions.resetFilters}
          onCollapse={() => setSidebarCollapsed(true)}
        />
      </div>

      {/* Expand sidebar button (desktop only, visible when collapsed) */}
      {sidebarCollapsed && (
        <button
          onClick={() => setSidebarCollapsed(false)}
          className="hidden lg:flex absolute left-0 top-1/2 -translate-y-1/2 z-20 w-6 h-12 items-center justify-center bg-[var(--cp-bg-elevated)] border border-white/10 border-l-0 rounded-r-md text-slate-400 hover:text-white transition-colors"
          title="Expand sidebar"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </button>
      )}

      <main className="flex-1 flex flex-col overflow-y-auto">
        {/* Top bar: mode toggle + sub-mode toggle */}
        <div className="flex items-center justify-center gap-4 flex-wrap px-6 py-3 border-b border-white/10 bg-[var(--cp-bg-surface)]/50 backdrop-blur-sm sticky top-0 z-10">
          <SegmentedControl
            options={[
              { value: 'preflop' as const, label: 'Preflop' },
              { value: 'postflop' as const, label: 'Postflop' },
            ]}
            value={gtoMode}
            onChange={setGtoMode}
            size="sm"
          />
          {postflopState.meta && (
            <SegmentedControl
              options={[
                { value: 'viewer' as const, label: 'Strategy Viewer' },
                { value: 'training' as const, label: 'Training' },
              ]}
              value={postflopState.mode}
              onChange={postflopActions.setMode}
              size="sm"
            />
          )}
        </div>

        {/* Error */}
        {postflopState.error && (
          <div className="mx-6 mt-4 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-2 text-red-300 text-sm">
            {postflopState.error}
            <button onClick={postflopActions.clearError} className="ml-2 text-red-400 hover:text-red-300 underline">dismiss</button>
          </div>
        )}

        {/* Loading skeleton */}
        {postflopState.loadingBoard && (
          <div className="flex-1 px-6 py-2 w-full">
            <BoardLoadingSkeleton />
          </div>
        )}

        {/* Content */}
        {!postflopState.loadingBoard && (
          postflopState.mode === 'training' ? (
            <div className="flex-1 p-6 max-w-[1400px] w-full mx-auto">
              <TrainingMode
                indexed={postflopState.indexed}
                prefixIndex={postflopState.prefixIndex}
                handMap={postflopState.handMap}
                meta={postflopState.meta}
                isV2={postflopState.isV2}
                onBack={() => postflopActions.setMode('viewer')}
              />
            </div>
          ) : postflopState.meta ? (
            <div className="flex-1 px-6 py-3 w-full min-h-0">
              <StrategyViewer state={postflopState} actions={postflopActions} />
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center p-6">
              <WelcomeScreen
                selectedConfig={postflopState.selectedConfig}
                onSelectBoard={postflopActions.selectBoard}
              />
            </div>
          )
        )}
      </main>
    </div>
  );
}
