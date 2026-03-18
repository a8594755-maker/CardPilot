import { useState } from 'react';
import { useRangeEditor } from '../../stores/range-editor';
import { useSolverConfig } from '../../stores/solver-config';
import { useWorkspace } from '../../stores/workspace';
import { useSolveSession } from '../../stores/solve-session';
import { MiniRangePreview } from '../range-editor/MiniRangePreview';
import { NodeActionDisplay } from '../strategy-browser/NodeActionDisplay';
import { TreeNavigator } from '../strategy-browser/TreeNavigator';
import { CardComponent } from '../board/CardComponent';
import { SolveProgressInline } from '../solve/SolveProgressInline';
import { startSolve } from '../../lib/api-client';
import { countCombos } from '../../lib/range-parser';

export function AnalyzeSidebar() {
  const { openEditor: openRangeEditor, playerRanges } = useRangeEditor();
  const { configName, iterations, treeConfig, syncTreeConfig } = useSolverConfig();
  const { boardCards, openBoardSelector } = useWorkspace();
  const { setJobId } = useSolveSession();
  const solveStatus = useSolveSession((s) => s.status);
  const setActiveJobId = useWorkspace((s) => s.setActiveJobId);

  const isSolving = solveStatus === 'solving';
  const [error, setError] = useState<string | null>(null);
  const [solving, setSolving] = useState(false);

  const range0Combos = countCombos(playerRanges[0]);
  const range1Combos = countCombos(playerRanges[1]);

  const handleSolve = async () => {
    setError(null);
    if (boardCards.length < 3) {
      setError('Select at least 3 board cards');
      return;
    }
    if (playerRanges[0].size === 0 || playerRanges[1].size === 0) {
      setError('Set both OOP and IP ranges');
      return;
    }
    syncTreeConfig();
    setSolving(true);
    try {
      const result = await startSolve({
        configName,
        iterations,
        buckets: 100,
        board: boardCards,
        oopRange: [...playerRanges[0]],
        ipRange: [...playerRanges[1]],
        treeConfig: { ...treeConfig },
      });
      setJobId(result.jobId);
      setActiveJobId(result.jobId);
    } catch (err) {
      setError(String(err));
    } finally {
      setSolving(false);
    }
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Range 1 (OOP) */}
      <button
        onClick={() => openRangeEditor(0)}
        className="flex-shrink-0 flex items-center gap-2 p-2 border-b border-border hover:bg-secondary/50 transition-colors cursor-pointer text-left"
      >
        <MiniRangePreview selectedHands={playerRanges[0]} size={64} />
        <div className="flex-1 min-w-0">
          <div className="text-[11px] font-medium text-primary">Range 1 (OOP)</div>
          <div className="text-[10px] text-muted-foreground">
            {playerRanges[0].size > 0
              ? `${playerRanges[0].size} hands | ${range0Combos.toFixed(0)} combos`
              : 'Click to set'}
          </div>
        </div>
      </button>

      {/* Range 2 (IP) */}
      <button
        onClick={() => openRangeEditor(1)}
        className="flex-shrink-0 flex items-center gap-2 p-2 border-b border-border hover:bg-secondary/50 transition-colors cursor-pointer text-left"
      >
        <MiniRangePreview selectedHands={playerRanges[1]} size={64} />
        <div className="flex-1 min-w-0">
          <div className="text-[11px] font-medium text-primary">Range 2 (IP)</div>
          <div className="text-[10px] text-muted-foreground">
            {playerRanges[1].size > 0
              ? `${playerRanges[1].size} hands | ${range1Combos.toFixed(0)} combos`
              : 'Click to set'}
          </div>
        </div>
      </button>

      {/* Board display */}
      <button
        onClick={openBoardSelector}
        className="flex-shrink-0 p-2 border-b border-border hover:bg-secondary/50 transition-colors cursor-pointer text-left"
      >
        <div className="text-[11px] font-medium text-primary mb-1.5">Board</div>
        <div className="flex gap-1 items-center">
          {boardCards.length > 0 ? (
            boardCards.map((card) => <CardComponent key={card} card={card} size="sm" />)
          ) : (
            <span className="text-[10px] text-muted-foreground">Click to select board</span>
          )}
        </div>
      </button>

      {/* Solve controls */}
      <div className="flex-shrink-0 p-2 border-b border-border space-y-2">
        {error && (
          <div className="p-1.5 bg-destructive/10 border border-destructive/30 rounded text-destructive text-[10px]">
            {error}
          </div>
        )}

        {isSolving ? (
          <SolveProgressInline />
        ) : (
          <div className="flex gap-2">
            <button
              onClick={() => useWorkspace.getState().setMode('configure')}
              className="flex-1 py-1.5 rounded bg-secondary text-secondary-foreground text-xs hover:bg-secondary/80 transition-colors"
            >
              Build Tree
            </button>
            <button
              onClick={handleSolve}
              disabled={solving || boardCards.length < 3}
              className="flex-1 py-1.5 rounded bg-primary text-primary-foreground text-xs hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {solving ? 'Starting...' : 'Run Solver'}
            </button>
          </div>
        )}

        {/* Context info */}
        <div className="text-[10px] text-muted-foreground space-y-0.5">
          <div>
            Pot: {treeConfig.startingPot} | Stack: {treeConfig.effectiveStack}
          </div>
          <div>Iterations: {iterations.toLocaleString()}</div>
        </div>
      </div>

      {/* Tree Navigator */}
      <div className="flex-shrink-0 border-b border-border p-2">
        <TreeNavigator />
      </div>

      {/* Node Action Display */}
      <div className="flex-shrink-0 border-b border-border p-2">
        <NodeActionDisplay />
      </div>
    </div>
  );
}
