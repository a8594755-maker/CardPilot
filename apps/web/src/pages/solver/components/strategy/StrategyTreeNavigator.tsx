import { BoardDisplay } from '../board/BoardDisplay';
import { TreePath } from './TreePath';
import { NodeDetail } from './NodeDetail';
import { useStrategyBrowser } from '../../stores/strategy-browser';

interface StrategyTreeNavigatorProps {
  config: string;
  flopCards: string[];
  strategies: Array<{ key: string; probs: number[] }>;
}

export function StrategyTreeNavigator({
  config,
  flopCards,
  strategies,
}: StrategyTreeNavigatorProps) {
  const { currentPath, navigateTo, goBack, goToRoot, player } = useStrategyBrowser();

  // Build the current history key from path
  const historyStr = currentPath.length > 0 ? currentPath.join('') : '';

  // Find strategies matching current node
  const currentStrategies = strategies.filter((s) => {
    const parts = s.key.split('|');
    const history = parts[3] || '';
    const p = parseInt(parts[2] || '0');
    return history === historyStr && p === player;
  });

  // Determine available actions at this node
  // Parse from strategy keys that extend the current path by one action
  const childHistoryPrefix = historyStr;
  const availableActions = new Set<string>();
  for (const s of strategies) {
    const parts = s.key.split('|');
    const history = parts[3] || '';
    if (history.startsWith(childHistoryPrefix) && history.length > childHistoryPrefix.length) {
      // Extract the next action character(s)
      const remaining = history.slice(childHistoryPrefix.length);
      const nextAction = remaining[0]; // simplified: single char actions
      if (nextAction) availableActions.add(nextAction);
    }
  }

  // Aggregate probabilities across all buckets for current node
  const aggregatedProbs = aggregateStrategies(currentStrategies);

  return (
    <div className="space-y-4">
      {/* Board */}
      <BoardDisplay cards={flopCards} label="Board" size="lg" />

      {/* Tree Path */}
      <TreePath
        path={currentPath}
        onNavigate={(i) => {
          // Navigate to specific depth
          const newPath = currentPath.slice(0, i + 1);
          goToRoot();
          newPath.forEach((a) => navigateTo(a));
        }}
        onRoot={goToRoot}
      />

      {/* Node Detail */}
      {aggregatedProbs && (
        <NodeDetail
          historyKey={historyStr || '(root)'}
          player={player}
          street={getStreetFromPath(currentPath)}
          pot={5} // TODO: calculate from config
          stacks={[47.5, 47.5]} // TODO: calculate from config
          actions={aggregatedProbs.actions}
          probs={aggregatedProbs.probs}
          onSelectAction={navigateTo}
        />
      )}

      {/* Navigation hint */}
      {currentPath.length > 0 && (
        <button
          onClick={goBack}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          ← Go back
        </button>
      )}

      {/* Stats */}
      <div className="text-xs text-muted-foreground">
        {strategies.length} info sets loaded · Config: {config}
      </div>
    </div>
  );
}

function aggregateStrategies(entries: Array<{ key: string; probs: number[] }>): {
  actions: string[];
  probs: number[];
} | null {
  if (entries.length === 0) return null;

  const numActions = entries[0].probs.length;
  const avgProbs = new Array(numActions).fill(0);
  for (const e of entries) {
    for (let i = 0; i < numActions; i++) {
      avgProbs[i] += (e.probs[i] ?? 0) / entries.length;
    }
  }

  // Generate action labels based on count
  const actionLabels = generateActionLabels(numActions);
  return { actions: actionLabels, probs: avgProbs };
}

function generateActionLabels(count: number): string[] {
  if (count === 2) return ['check', 'bet'];
  if (count === 3) return ['fold', 'call', 'raise'];
  if (count === 4) return ['fold', 'call', 'raise_small', 'raise_big'];
  return Array.from({ length: count }, (_, i) => `action_${i}`);
}

function getStreetFromPath(path: string[]): string {
  // Simplified: determine street from path depth
  const actionCount = path.length;
  if (actionCount < 3) return 'FLOP';
  if (actionCount < 6) return 'TURN';
  return 'RIVER';
}
