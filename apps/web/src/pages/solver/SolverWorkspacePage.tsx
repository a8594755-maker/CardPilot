import { useEffect } from 'react';
import { useWorkspace } from './stores/workspace';
import { useSolveSession } from './stores/solve-session';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import { useStrategyData } from './hooks/useStrategyData';
import { useSolverSocket } from './hooks/useSolverSocket';
import { WorkspaceHeader } from './components/workspace/WorkspaceHeader';
import { BoardSelectorModal } from './components/board/BoardSelectorModal';
import { RangeEditorModal } from './components/range-editor/RangeEditorModal';
import { StacksDialog } from './components/workspace/StacksDialog';
import { TreeBuilderDialog } from './components/workspace/TreeBuilderDialog';

// Analyze mode
import { AnalyzeSidebar } from './components/workspace/AnalyzeSidebar';
import { AnalyzeCenter } from './components/workspace/AnalyzeCenter';
import { AnalyzeRight } from './components/workspace/AnalyzeRight';

// Configure mode
import { ConfigureSidebar } from './components/workspace/ConfigureSidebar';
import { ConfigureCenter } from './components/workspace/ConfigureCenter';
import { ConfigureRight } from './components/workspace/ConfigureRight';

// Play mode
import { PlaySidebar } from './components/workspace/PlaySidebar';
import { PlayCenter } from './components/workspace/PlayCenter';
import { PlayRight } from './components/workspace/PlayRight';

import '../../solver-tokens.css';

export default function SolverWorkspacePage() {
  const mode = useWorkspace((s) => s.mode);
  const leftPanelOpen = useWorkspace((s) => s.leftPanelOpen);
  const rightPanelOpen = useWorkspace((s) => s.rightPanelOpen);
  const setMode = useWorkspace((s) => s.setMode);

  useKeyboardShortcuts();

  // Subscribe to solver progress via socket.io
  const activeJobId = useWorkspace((s) => s.activeJobId);
  const solveJobId = useSolveSession((s) => s.jobId);
  useSolverSocket(solveJobId ?? activeJobId);

  // Mode keyboard shortcuts: Ctrl+1/2/3
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if (!e.ctrlKey) return;
      if (e.key === '1') {
        e.preventDefault();
        setMode('configure');
      }
      if (e.key === '2') {
        e.preventDefault();
        setMode('analyze');
      }
      if (e.key === '3') {
        e.preventDefault();
        setMode('play');
      }
    }
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [setMode]);

  // Auto-load strategy data
  const strategyData = useStrategyData();

  return (
    <div className="solver-page flex flex-col h-screen overflow-hidden">
      {/* Header with Board Bar + Mode Selector */}
      <WorkspaceHeader />

      {/* Body: 3-panel layout */}
      <div className="flex-1 flex overflow-hidden min-w-[900px]">
        {/* Left Panel */}
        {leftPanelOpen && (
          <aside className="w-[240px] flex-shrink-0 border-r border-[hsl(var(--solver-border))] bg-[hsl(var(--solver-card))] overflow-hidden">
            {mode === 'configure' && <ConfigureSidebar />}
            {mode === 'analyze' && <AnalyzeSidebar />}
            {mode === 'play' && <PlaySidebar />}
          </aside>
        )}

        {/* Center Panel */}
        <main className="flex-1 overflow-hidden min-w-[400px]">
          {mode === 'configure' && <ConfigureCenter />}
          {mode === 'analyze' && (
            <AnalyzeCenter
              displayCombos={strategyData.displayCombos}
              allCombos={strategyData.allCombosData?.combos || []}
              ipCombos={strategyData.ipAllCombosData?.combos}
            />
          )}
          {mode === 'play' && <PlayCenter />}
        </main>

        {/* Right Panel */}
        {rightPanelOpen && (
          <aside className="w-[340px] flex-shrink-0 border-l border-[hsl(var(--solver-border))] bg-[hsl(var(--solver-card))] overflow-hidden">
            {mode === 'configure' && <ConfigureRight />}
            {mode === 'analyze' && (
              <AnalyzeRight
                allCombos={strategyData.allCombosData?.combos || []}
                ipCombos={strategyData.ipAllCombosData?.combos}
              />
            )}
            {mode === 'play' && <PlayRight />}
          </aside>
        )}
      </div>

      {/* Modals */}
      <BoardSelectorModal />
      <RangeEditorModal />
      <StacksDialog />
      <TreeBuilderDialog />
    </div>
  );
}
