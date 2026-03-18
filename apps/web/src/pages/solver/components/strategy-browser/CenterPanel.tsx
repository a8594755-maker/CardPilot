import { useMemo } from 'react';
import type { GtoPlusCombo, GtoPlusContext, GtoPlusSummary } from '../../lib/api-client';
import { StrategyMatrix } from './StrategyMatrix';
import { HandDetailsTable } from './HandDetailsTable';
import { SummaryBar } from './SummaryBar';
import { BoardDisplay } from '../board/BoardDisplay';
import { useStrategyBrowser } from '../../stores/strategy-browser';
import { useDisplaySettings } from '../../stores/display-settings';
import { getActionColor, formatActionLabel } from '../../lib/strategy-utils';
import {
  categorizeAllCombosWithBoard,
  getCategoriesForHand,
} from '../../lib/board-aware-categorizer';

interface CenterPanelProps {
  grid: Record<string, Record<string, number>>;
  actions: string[];
  combos: GtoPlusCombo[];
  allCombos: GtoPlusCombo[];
  context: GtoPlusContext | null;
  summary: GtoPlusSummary | null;
  selectedHand: string | null;
  onSelectHand: (hand: string) => void;
  boardCards?: string[];
  ipGrid?: Record<string, Record<string, number>>;
  ipActions?: string[];
  ipCombos?: GtoPlusCombo[];
  ipSummary?: GtoPlusSummary | null;
}

export function CenterPanel({
  grid,
  actions,
  combos,
  allCombos,
  context,
  summary,
  selectedHand,
  onSelectHand,
  boardCards,
  ipGrid,
  ipActions,
  ipCombos,
  ipSummary,
}: CenterPanelProps) {
  const { hoveredCategory, fixedCategory, selectedAction, setSelectedAction, hoveredCombo } =
    useStrategyBrowser();
  const { tableDisplayMode, setTableDisplayMode, cardRemoval, toggleCardRemoval } =
    useDisplaySettings();

  // Get active category for filtering
  const activeCategory = fixedCategory || hoveredCategory;

  // Build category data for filtering combos by category
  const categoryData = useMemo(() => {
    if (!allCombos.length || !activeCategory) return null;
    const cats = categorizeAllCombosWithBoard(allCombos, boardCards || [], actions);
    return cats.find((c) => c.key === activeCategory) || null;
  }, [allCombos, boardCards, actions, activeCategory]);

  // Filter combos based on active category
  const filteredCombos = useMemo(() => {
    if (!activeCategory || !categoryData) return combos;
    const handSet = new Set(categoryData.comboHands);
    return combos.filter((c) => handSet.has(c.hand));
  }, [combos, activeCategory, categoryData]);

  // Filter combos by selected action
  const actionFilteredCombos = useMemo(() => {
    if (!selectedAction) return filteredCombos;
    return filteredCombos.filter((c) => (c.frequencies[selectedAction] || 0) > 0.001);
  }, [filteredCombos, selectedAction]);

  // Get categories for hovered combo (for blue triangle indicators)
  const hoveredComboCategories = useMemo(() => {
    if (!hoveredCombo || !boardCards?.length) return [];
    return getCategoriesForHand(hoveredCombo, boardCards);
  }, [hoveredCombo, boardCards]);

  if (!actions.length) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        選擇一個檔案來查看策略
      </div>
    );
  }

  const hasIpData = ipCombos && ipCombos.length > 0;

  return (
    <div className="flex flex-col h-full">
      {/* Board Cards Display */}
      {boardCards && boardCards.length > 0 && (
        <div className="flex-shrink-0 px-4 pt-3 pb-1 flex items-center gap-3">
          <BoardDisplay cards={boardCards} size="sm" />
          {context && (
            <div className="flex items-center gap-3 text-xs text-muted-foreground font-mono">
              <span>
                底池: <span className="text-foreground font-medium">{context.pot}</span>
              </span>
              <span>
                籌碼: <span className="text-foreground font-medium">{context.stack}</span>
              </span>
              {context.toCall > 0 && (
                <span>
                  跟注: <span className="text-foreground font-medium">{context.toCall}</span>
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Top: Strategy Grids (OOP vs IP when both available) */}
      <div className="flex-shrink-0 p-4 pt-2">
        <StrategyMatrix
          grid={grid}
          actions={actions}
          selectedHand={selectedHand}
          onCellClick={onSelectHand}
          highlightHands={categoryData?.comboHands}
          selectedAction={selectedAction}
          ipGrid={ipGrid}
          ipActions={ipActions}
        />
      </div>

      {/* Action Tabs + Table Display Mode */}
      <div className="flex-shrink-0 px-4 pb-1 flex items-center justify-between">
        {/* Action filter tabs */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => setSelectedAction(null)}
            className={`px-2 py-0.5 rounded text-[10px] ${!selectedAction ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground hover:text-foreground'}`}
          >
            全部
          </button>
          {actions.map((action) => (
            <button
              key={action}
              onClick={() => setSelectedAction(selectedAction === action ? null : action)}
              className={`px-2 py-0.5 rounded text-[10px] flex items-center gap-1 ${selectedAction === action ? 'ring-1 ring-offset-1' : 'bg-secondary text-muted-foreground hover:text-foreground'}`}
              style={
                selectedAction === action
                  ? { backgroundColor: getActionColor(action), color: 'white' }
                  : undefined
              }
            >
              <div
                className="w-1.5 h-1.5 rounded-sm"
                style={{ backgroundColor: getActionColor(action) }}
              />
              {formatActionLabel(action)}
            </button>
          ))}
        </div>

        {/* Table display mode + card removal toggle */}
        <div className="flex items-center gap-1">
          {(['combos', 'percentages', 'ev'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => setTableDisplayMode(mode)}
              className={`px-1.5 py-0.5 rounded text-[10px] ${tableDisplayMode === mode ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground hover:text-foreground'}`}
            >
              {mode === 'combos' ? '#' : mode === 'percentages' ? '%' : 'EV'}
            </button>
          ))}
          <button
            onClick={toggleCardRemoval}
            className={`px-1.5 py-0.5 rounded text-[10px] ml-1 ${cardRemoval ? 'bg-orange-500 text-white' : 'bg-secondary text-muted-foreground hover:text-foreground'}`}
            title="移除效應"
          >
            CR
          </button>
        </div>
      </div>

      {/* Middle: Hand Details Table(s) */}
      <div className="flex-1 min-h-0 border-t border-border">
        {hasIpData ? (
          <div className="flex h-full">
            <div className="flex-1 min-w-0 border-r border-border">
              <HandDetailsTable
                combos={actionFilteredCombos}
                actions={actions}
                selectedHand={selectedHand}
                label="OOP"
                compact
                summary={summary}
                highlightCategories={hoveredComboCategories}
                boardCards={boardCards}
                tableDisplayMode={tableDisplayMode}
                selectedAction={selectedAction}
              />
            </div>
            <div className="flex-1 min-w-0">
              <HandDetailsTable
                combos={ipCombos}
                actions={actions}
                selectedHand={selectedHand}
                label="IP"
                compact
                summary={ipSummary ?? null}
                boardCards={boardCards}
                tableDisplayMode={tableDisplayMode}
                selectedAction={selectedAction}
              />
            </div>
          </div>
        ) : (
          <HandDetailsTable
            combos={actionFilteredCombos}
            actions={actions}
            selectedHand={selectedHand}
            summary={summary}
            highlightCategories={hoveredComboCategories}
            boardCards={boardCards}
            tableDisplayMode={tableDisplayMode}
            selectedAction={selectedAction}
          />
        )}
      </div>

      {/* Bottom: Summary Bar */}
      <SummaryBar combos={allCombos} actions={actions} context={context} summary={summary} />
    </div>
  );
}
