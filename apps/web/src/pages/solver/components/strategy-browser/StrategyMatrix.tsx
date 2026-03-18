import { useMemo } from 'react';
import { RangeMatrix13x13 } from '../range/RangeMatrix13x13';
import { useDisplaySettings } from '../../stores/display-settings';
import { useStrategyBrowser } from '../../stores/strategy-browser';
import { getActionColor, formatActionLabel } from '../../lib/strategy-utils';

interface StrategyMatrixProps {
  grid: Record<string, Record<string, number>>;
  actions: string[];
  selectedHand: string | null;
  onCellClick: (hand: string) => void;
  highlightHands?: string[];
  selectedAction?: string | null;
  ipGrid?: Record<string, Record<string, number>>;
  ipActions?: string[];
}

export function StrategyMatrix({
  grid,
  actions,
  selectedHand,
  onCellClick,
  highlightHands,
  selectedAction,
  ipGrid,
  ipActions,
}: StrategyMatrixProps) {
  const { matrixMode, setMatrixMode } = useDisplaySettings();
  const { setHoveredHandClass } = useStrategyBrowser();

  const hasIp = ipGrid && Object.keys(ipGrid).length > 0;

  const normalizedGrid = useMemo(() => normalizeGrid(grid), [grid]);
  const normalizedActions = useMemo(() => actions.filter((a) => a !== 'fold'), [actions]);

  // When a specific action is selected, build a single-action grid
  const actionGrid = useMemo(() => {
    if (!selectedAction) return null;
    const result: Record<string, Record<string, number>> = {};
    for (const [hand, freqs] of Object.entries(grid)) {
      result[hand] = { [selectedAction]: freqs[selectedAction] || 0 };
    }
    return result;
  }, [grid, selectedAction]);

  const ipActionGrid = useMemo(() => {
    if (!selectedAction || !ipGrid) return null;
    const result: Record<string, Record<string, number>> = {};
    for (const [hand, freqs] of Object.entries(ipGrid)) {
      result[hand] = { [selectedAction]: freqs[selectedAction] || 0 };
    }
    return result;
  }, [ipGrid, selectedAction]);

  // Build dimmed grid when highlighting specific hands (from category hover)
  const highlightSet = useMemo(() => {
    if (!highlightHands?.length) return null;
    const classes = new Set<string>();
    for (const hand of highlightHands) {
      classes.add(comboToHandClass(hand));
    }
    return classes;
  }, [highlightHands]);

  const displayGrid = actionGrid || grid;
  const displayActions = selectedAction ? [selectedAction] : actions;
  const ipDisplayGrid = ipActionGrid || ipGrid;
  const ipDisplayActions = selectedAction ? [selectedAction] : ipActions || actions;

  return (
    <div className="space-y-2">
      {/* Toolbar */}
      <div className="flex items-center gap-3 text-xs">
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setMatrixMode('strategy')}
            className={`px-2 py-1 rounded text-xs ${matrixMode === 'strategy' ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground hover:text-foreground'}`}
          >
            組合 (F1)
          </button>
          <button
            onClick={() => setMatrixMode('equity')}
            className={`px-2 py-1 rounded text-xs ${matrixMode === 'equity' ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground hover:text-foreground'}`}
          >
            頻率 (F2)
          </button>
          <button
            onClick={() => setMatrixMode('ev')}
            className={`px-2 py-1 rounded text-xs ${matrixMode === 'ev' ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground hover:text-foreground'}`}
          >
            EV (F3)
          </button>
        </div>
      </div>

      {/* Dual Grids */}
      <div className="flex gap-4">
        {hasIp ? (
          <>
            {/* OOP Grid */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <div className="w-2.5 h-2.5 rounded-full bg-blue-500" />
                <span className="text-xs font-medium">OOP</span>
              </div>
              <RangeMatrix13x13
                grid={displayGrid}
                actions={displayActions}
                onCellClick={onCellClick}
                onCellHover={setHoveredHandClass}
                selectedHand={selectedHand}
                compact
                hideLegend
                dimmedHands={highlightSet ? getDimmedHands(grid, highlightSet) : undefined}
              />
            </div>

            {/* IP Grid */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <div className="w-2.5 h-2.5 rounded-full bg-green-500" />
                <span className="text-xs font-medium">IP</span>
              </div>
              <RangeMatrix13x13
                grid={ipDisplayGrid!}
                actions={ipDisplayActions}
                onCellClick={onCellClick}
                onCellHover={setHoveredHandClass}
                selectedHand={selectedHand}
                compact
                hideLegend
                dimmedHands={highlightSet ? getDimmedHands(ipGrid!, highlightSet) : undefined}
              />
            </div>
          </>
        ) : (
          <>
            {/* Strategy Grid (raw frequencies) */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <div className="w-2.5 h-2.5 rounded-full bg-primary" />
                <span className="text-xs text-muted-foreground">策略</span>
              </div>
              <RangeMatrix13x13
                grid={displayGrid}
                actions={displayActions}
                onCellClick={onCellClick}
                onCellHover={setHoveredHandClass}
                selectedHand={selectedHand}
                compact
                hideLegend
                dimmedHands={highlightSet ? getDimmedHands(grid, highlightSet) : undefined}
              />
            </div>

            {/* Normalized Grid (fold excluded) */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <div className="w-2.5 h-2.5 rounded-full bg-primary/50" />
                <span className="text-xs text-muted-foreground">標準化</span>
              </div>
              <RangeMatrix13x13
                grid={normalizedGrid}
                actions={normalizedActions}
                onCellClick={onCellClick}
                onCellHover={setHoveredHandClass}
                selectedHand={selectedHand}
                compact
                hideLegend
                dimmedHands={
                  highlightSet ? getDimmedHands(normalizedGrid, highlightSet) : undefined
                }
              />
            </div>
          </>
        )}
      </div>

      {/* Shared Action Legend */}
      <div className="flex items-center gap-3 text-xs flex-wrap">
        {displayActions.map((action) => (
          <div key={action} className="flex items-center gap-1">
            <div
              className="w-2.5 h-2.5 rounded-sm"
              style={{ backgroundColor: getActionColor(action) }}
            />
            <span className="text-muted-foreground">{formatActionLabel(action)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function normalizeGrid(
  grid: Record<string, Record<string, number>>,
): Record<string, Record<string, number>> {
  const result: Record<string, Record<string, number>> = {};
  for (const [hand, freqs] of Object.entries(grid)) {
    const nonFoldTotal = Object.entries(freqs)
      .filter(([action]) => action !== 'fold')
      .reduce((sum, [, v]) => sum + v, 0);

    if (nonFoldTotal <= 0) {
      result[hand] = freqs;
      continue;
    }

    const normalized: Record<string, number> = {};
    for (const [action, freq] of Object.entries(freqs)) {
      if (action === 'fold') continue;
      normalized[action] = freq / nonFoldTotal;
    }
    result[hand] = normalized;
  }
  return result;
}

/** Convert a combo hand like "AhKh" to a hand class like "AKs" */
function comboToHandClass(hand: string): string {
  if (hand.length < 4) return hand;
  const r1 = hand[0];
  const s1 = hand[1];
  const r2 = hand[2];
  const s2 = hand[3];

  if (r1 === r2) return `${r1}${r2}`;
  const RANK_ORDER = 'AKQJT98765432';
  const i1 = RANK_ORDER.indexOf(r1);
  const i2 = RANK_ORDER.indexOf(r2);
  const high = i1 < i2 ? r1 : r2;
  const low = i1 < i2 ? r2 : r1;
  const suffix = s1 === s2 ? 's' : 'o';
  return `${high}${low}${suffix}`;
}

/** Get set of hands that should be dimmed (not in highlight set) */
function getDimmedHands(
  grid: Record<string, Record<string, number>>,
  highlightSet: Set<string>,
): Set<string> {
  const dimmed = new Set<string>();
  for (const hand of Object.keys(grid)) {
    if (!highlightSet.has(hand)) {
      dimmed.add(hand);
    }
  }
  return dimmed;
}
