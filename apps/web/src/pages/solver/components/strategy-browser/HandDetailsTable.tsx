import { useState, useMemo } from 'react';
import type { GtoPlusCombo, GtoPlusSummary } from '../../lib/api-client';
import type { TableDisplayMode } from '../../stores/display-settings';
import type { CategoryKey } from '../../lib/board-aware-categorizer';
import { getCategoriesForHand } from '../../lib/board-aware-categorizer';
import { useStrategyBrowser } from '../../stores/strategy-browser';
import { getActionColor, formatActionLabel } from '../../lib/strategy-utils';

interface HandDetailsTableProps {
  combos: GtoPlusCombo[];
  actions: string[];
  selectedHand: string | null;
  label?: string;
  compact?: boolean;
  summary?: GtoPlusSummary | null;
  highlightCategories?: CategoryKey[];
  boardCards?: string[];
  tableDisplayMode?: TableDisplayMode;
  selectedAction?: string | null;
}

type SortColumn = 'hand' | 'equity' | 'combos' | 'evTotal' | string;
type SortDirection = 'asc' | 'desc';

export function HandDetailsTable({
  combos,
  actions,
  selectedHand,
  label,
  compact,
  summary,
  highlightCategories,
  boardCards,
  tableDisplayMode = 'combos',
  selectedAction,
}: HandDetailsTableProps) {
  const [sortColumn, setSortColumn] = useState<SortColumn>('equity');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const { setHoveredCombo } = useStrategyBrowser();

  const sortedCombos = useMemo(() => {
    const sorted = [...combos];
    sorted.sort((a, b) => {
      let aVal: number, bVal: number;
      switch (sortColumn) {
        case 'hand':
          return sortDirection === 'asc'
            ? a.hand.localeCompare(b.hand)
            : b.hand.localeCompare(a.hand);
        case 'equity':
          aVal = a.equity;
          bVal = b.equity;
          break;
        case 'combos':
          aVal = a.combos;
          bVal = b.combos;
          break;
        case 'evTotal':
          aVal = a.evTotal;
          bVal = b.evTotal;
          break;
        default:
          aVal = a.frequencies[sortColumn] || 0;
          bVal = b.frequencies[sortColumn] || 0;
          break;
      }
      return sortDirection === 'asc' ? aVal - bVal : bVal - aVal;
    });
    return sorted;
  }, [combos, sortColumn, sortDirection]);

  function handleSort(column: SortColumn) {
    if (sortColumn === column) {
      setSortDirection((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortColumn(column);
      setSortDirection('desc');
    }
  }

  function SortHeader({
    column,
    label: headerLabel,
    className,
  }: {
    column: SortColumn;
    label: string;
    className?: string;
  }) {
    const isActive = sortColumn === column;
    return (
      <th
        className={`px-2 py-1.5 font-medium cursor-pointer hover:text-foreground select-none whitespace-nowrap ${className || ''} ${isActive ? 'text-primary' : ''}`}
        onClick={() => handleSort(column)}
      >
        {headerLabel}
        {isActive && (
          <span className="ml-0.5 text-[9px]">{sortDirection === 'asc' ? '▲' : '▼'}</span>
        )}
      </th>
    );
  }

  if (!combos.length) {
    return (
      <div className="p-4 text-center text-muted-foreground text-sm">
        {selectedHand ? `${selectedHand} 無組合` : '點擊手牌查看詳情'}
      </div>
    );
  }

  const cellPx = compact ? 'px-1' : 'px-2';

  // Compute summary from combos if not provided
  const summaryData = useMemo(() => {
    if (!combos.length) return null;
    if (summary) return summary;
    const totalCombos = combos.reduce((s, c) => s + c.combos, 0);
    const overallEquity =
      totalCombos > 0 ? combos.reduce((s, c) => s + c.equity * c.combos, 0) / totalCombos : 0;
    const overallEV =
      totalCombos > 0 ? combos.reduce((s, c) => s + c.evTotal * c.combos, 0) / totalCombos : 0;
    return { totalCombos, overallEquity, overallEV } as {
      totalCombos: number;
      overallEquity: number;
      overallEV: number;
    };
  }, [combos, summary]);

  /** Format action column value based on display mode */
  function formatActionValue(combo: GtoPlusCombo, action: string): string {
    const freq = combo.frequencies[action] || 0;
    switch (tableDisplayMode) {
      case 'percentages':
        return (freq * 100).toFixed(1);
      case 'ev':
        return (combo.evs[action] ?? combo.evTotal).toFixed(3);
      case 'combos':
      default:
        return (freq * combo.combos).toFixed(3);
    }
  }

  const displayActions = selectedAction ? [selectedAction] : actions;

  return (
    <div className="h-full overflow-auto">
      {/* Label header */}
      {label && (
        <div className="sticky top-0 z-20 bg-card px-2 py-1 text-xs font-medium border-b border-border">
          {label}
        </div>
      )}
      <table className="w-full text-xs">
        <thead
          className={`sticky ${label ? 'top-[25px]' : 'top-0'} bg-card border-b border-border z-10`}
        >
          <tr>
            {highlightCategories && highlightCategories.length > 0 && !compact && (
              <th className="w-4" />
            )}
            <SortHeader column="hand" label={compact ? '#' : '手牌'} className="text-left" />
            {!compact && <th className={`${cellPx} py-1.5 font-medium text-left`}>分佈</th>}
            <SortHeader column="equity" label={compact ? 'Eq' : '勝率'} className="text-right" />
            <SortHeader column="combos" label={compact ? '#' : '組合'} className="text-right" />
            {!compact &&
              displayActions.map((a) => (
                <SortHeader
                  key={a}
                  column={a}
                  label={formatActionLabel(a)}
                  className="text-right"
                />
              ))}
            <SortHeader column="evTotal" label="EV" className="text-right" />
          </tr>
        </thead>
        <tbody>
          {sortedCombos.map((c, idx) => {
            const comboCategories =
              boardCards && boardCards.length >= 3 ? getCategoriesForHand(c.hand, boardCards) : [];
            const hasHighlight =
              highlightCategories &&
              highlightCategories.length > 0 &&
              comboCategories.some((cat) => highlightCategories.includes(cat));

            return (
              <tr
                key={c.hand}
                className="border-b border-border/20 hover:bg-secondary/40 transition-colors"
                onMouseEnter={() => setHoveredCombo(c.hand)}
                onMouseLeave={() => setHoveredCombo(null)}
              >
                {highlightCategories && highlightCategories.length > 0 && !compact && (
                  <td className="w-4 text-center">
                    {hasHighlight && <span className="text-blue-500 text-[8px]">&#9654;</span>}
                  </td>
                )}
                <td className={`${cellPx} py-0.5 font-mono`}>
                  <span className="text-muted-foreground text-[9px] mr-0.5">{idx + 1}.</span>
                  <HandDisplay hand={c.hand} />
                </td>
                {!compact && (
                  <td className={`${cellPx} py-0.5`}>
                    <MiniActionBar frequencies={c.frequencies} actions={actions} />
                  </td>
                )}
                <td className={`${cellPx} py-0.5 text-right font-mono`}>
                  {c.equity.toFixed(compact ? 3 : 1)}
                  {compact ? '' : '%'}
                </td>
                <td className={`${cellPx} py-0.5 text-right font-mono text-muted-foreground`}>
                  {c.combos.toFixed(compact ? 2 : 3)}
                </td>
                {!compact &&
                  displayActions.map((a) => {
                    const freq = (c.frequencies[a] || 0) * 100;
                    return (
                      <td key={a} className={`${cellPx} py-0.5 text-right`}>
                        <span
                          className="inline-block px-1 py-0.5 rounded text-[10px] font-mono min-w-[36px] text-center"
                          style={{
                            backgroundColor:
                              freq > 0
                                ? `${getActionColor(a)}${Math.round(Math.min(freq, 100) * 2.55)
                                    .toString(16)
                                    .padStart(2, '0')}`
                                : 'transparent',
                            color: freq > 50 ? 'white' : undefined,
                          }}
                        >
                          {formatActionValue(c, a)}
                        </span>
                      </td>
                    );
                  })}
                <td className={`${cellPx} py-0.5 text-right font-mono font-medium`}>
                  {c.evTotal.toFixed(3)}
                </td>
              </tr>
            );
          })}
        </tbody>
        {/* Summary Row */}
        {summaryData && (
          <tfoot className="sticky bottom-0 bg-card border-t-2 border-border">
            <tr className="font-medium">
              {highlightCategories && highlightCategories.length > 0 && !compact && <td />}
              <td className={`${cellPx} py-1.5 font-mono`}>
                合計 {summaryData.totalCombos.toFixed(0)}
              </td>
              {!compact && <td />}
              <td className={`${cellPx} py-1.5 text-right font-mono`}>
                {summaryData.overallEquity.toFixed(compact ? 3 : 1)}
                {compact ? '' : '%'}
              </td>
              <td className={`${cellPx} py-1.5 text-right font-mono`}>
                {summaryData.totalCombos.toFixed(compact ? 2 : 3)}
              </td>
              {!compact && displayActions.map((a) => <td key={a} />)}
              <td className={`${cellPx} py-1.5 text-right font-mono`}>
                {summaryData.overallEV.toFixed(3)}
              </td>
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}

function HandDisplay({ hand }: { hand: string }) {
  const cards: Array<{ rank: string; suit: string }> = [];
  let i = 0;
  while (i < hand.length) {
    if (i + 1 < hand.length) {
      cards.push({ rank: hand[i], suit: hand[i + 1] });
      i += 2;
    } else {
      break;
    }
  }

  return (
    <span>
      {cards.map((card, idx) => (
        <span key={idx} style={{ color: getSuitColor(card.suit) }}>
          {card.rank}
          {getSuitSymbol(card.suit)}
        </span>
      ))}
    </span>
  );
}

function MiniActionBar({
  frequencies,
  actions,
}: {
  frequencies: Record<string, number>;
  actions: string[];
}) {
  return (
    <div className="flex h-3 w-20 rounded-sm overflow-hidden bg-secondary/20">
      {actions.map((action) => {
        const freq = (frequencies[action] || 0) * 100;
        if (freq < 0.1) return null;
        return (
          <div
            key={action}
            style={{
              width: `${freq}%`,
              backgroundColor: getActionColor(action),
            }}
          />
        );
      })}
    </div>
  );
}

function getSuitColor(suit: string): string {
  switch (suit) {
    case 'h':
      return '#ef4444';
    case 'd':
      return '#3b82f6';
    case 'c':
      return '#22c55e';
    case 's':
      return '#94a3b8';
    default:
      return 'inherit';
  }
}

function getSuitSymbol(suit: string): string {
  switch (suit) {
    case 'h':
      return '\u2665';
    case 'd':
      return '\u2666';
    case 'c':
      return '\u2663';
    case 's':
      return '\u2660';
    default:
      return suit;
  }
}
