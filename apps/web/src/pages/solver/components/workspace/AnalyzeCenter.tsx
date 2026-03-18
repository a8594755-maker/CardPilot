import type { GtoPlusCombo } from '../../lib/api-client';
import { CenterPanel } from '../strategy-browser/CenterPanel';
import { TreeMinimap } from '../strategy-browser/TreeMinimap';
import { useStrategyBrowser } from '../../stores/strategy-browser';
import { useWorkspace } from '../../stores/workspace';
import { useSolveSession } from '../../stores/solve-session';

interface AnalyzeCenterProps {
  displayCombos: GtoPlusCombo[];
  allCombos: GtoPlusCombo[];
  ipCombos?: GtoPlusCombo[];
}

export function AnalyzeCenter({ displayCombos, allCombos, ipCombos }: AnalyzeCenterProps) {
  const store = useStrategyBrowser();
  const boardCards = useWorkspace((s) => s.boardCards);
  const solveStatus = useSolveSession((s) => s.status);
  const board = boardCards.length > 0 ? boardCards : undefined;

  if (!store.nodeActions.length) {
    let message = 'Run the solver to view strategy';
    if (solveStatus === 'solving') message = 'Solver running...';
    else if (boardCards.length < 3) message = 'Select board cards to begin';
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        {message}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Top-left: Navigation tree minimap */}
      <div className="flex-shrink-0 p-2 border-b border-border">
        <TreeMinimap />
      </div>

      {/* Main: Strategy center panel */}
      <div className="flex-1 min-h-0">
        <CenterPanel
          grid={store.nodeGrid}
          actions={store.nodeActions}
          combos={displayCombos}
          allCombos={allCombos}
          context={store.nodeContext}
          summary={store.nodeSummary}
          selectedHand={store.selectedHandClass}
          onSelectHand={(hand) => store.selectHand(hand === store.selectedHandClass ? null : hand)}
          boardCards={board}
          ipGrid={store.ipGrid}
          ipActions={store.ipActions}
          ipCombos={ipCombos}
          ipSummary={store.ipSummary}
        />
      </div>
    </div>
  );
}
