import { useSolverConfig } from '../../stores/solver-config';
import { useRangeEditor } from '../../stores/range-editor';
import { MiniRangePreview } from '../range-editor/MiniRangePreview';
import { CardComponent } from '../board/CardComponent';
import { countCombos } from '../../lib/range-parser';

export function TreeConfigurator({
  onBuildTree,
  onRunSolver,
}: {
  onBuildTree: () => void;
  onRunSolver: () => void;
}) {
  const { openBoardSelector, boardCards } = useSolverConfig();
  const { openEditor: openRangeEditor, playerRanges } = useRangeEditor();

  const range0Combos = countCombos(playerRanges[0]);
  const range1Combos = countCombos(playerRanges[1]);
  const range0Pct = ((range0Combos / 1326) * 100).toFixed(1);
  const range1Pct = ((range1Combos / 1326) * 100).toFixed(1);

  return (
    <div className="space-y-3">
      {/* Range 1 (OOP) */}
      <button
        onClick={() => openRangeEditor(0)}
        className="w-full flex items-center gap-3 p-3 rounded-lg bg-card border border-border hover:border-primary/50 transition-colors cursor-pointer text-left"
      >
        <MiniRangePreview selectedHands={playerRanges[0]} size={72} />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium">Range 1 (OOP)</div>
          <div className="text-xs text-muted-foreground mt-0.5">
            {playerRanges[0].size > 0
              ? `${playerRanges[0].size} hands | ${range0Pct}% | ${range0Combos} combos`
              : 'Click to set range'}
          </div>
        </div>
      </button>

      {/* Range 2 (IP) */}
      <button
        onClick={() => openRangeEditor(1)}
        className="w-full flex items-center gap-3 p-3 rounded-lg bg-card border border-border hover:border-primary/50 transition-colors cursor-pointer text-left"
      >
        <MiniRangePreview selectedHands={playerRanges[1]} size={72} />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium">Range 2 (IP)</div>
          <div className="text-xs text-muted-foreground mt-0.5">
            {playerRanges[1].size > 0
              ? `${playerRanges[1].size} hands | ${range1Pct}% | ${range1Combos} combos`
              : 'Click to set range'}
          </div>
        </div>
      </button>

      {/* Board */}
      <button
        onClick={openBoardSelector}
        className="w-full p-3 rounded-lg bg-card border border-border hover:border-primary/50 transition-colors cursor-pointer text-left"
      >
        <div className="text-sm font-medium mb-2">Board</div>
        <div className="flex gap-1.5 items-center">
          {boardCards.length > 0 ? (
            boardCards.map((card) => <CardComponent key={card} card={card} size="sm" />)
          ) : (
            <span className="text-xs text-muted-foreground">Click to select board cards</span>
          )}
        </div>
      </button>

      {/* Build Tree */}
      <button
        onClick={onBuildTree}
        className="w-full py-2.5 rounded-lg bg-blue-600 text-white font-medium text-sm hover:bg-blue-700 transition-colors cursor-pointer"
      >
        Build Tree
      </button>

      {/* Run Solver */}
      <button
        onClick={onRunSolver}
        className="w-full py-2.5 rounded-lg bg-primary text-primary-foreground font-medium text-sm hover:opacity-90 transition-opacity cursor-pointer"
      >
        Run Solver
      </button>
    </div>
  );
}
