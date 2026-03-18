import { useState } from 'react';
import { MatrixCell } from './MatrixCell';

const RANKS = 'AKQJT98765432';

function getHandLabel(row: number, col: number): string {
  if (row === col) return `${RANKS[row]}${RANKS[col]}`;
  if (row < col) return `${RANKS[row]}${RANKS[col]}s`;
  return `${RANKS[col]}${RANKS[row]}o`;
}

interface RangeMatrix13x13Props {
  grid: Record<string, Record<string, number>>;
  actions: string[];
  onCellClick?: (hand: string) => void;
  onCellHover?: (hand: string | null) => void;
  selectedHand?: string | null;
  compact?: boolean;
  hideLegend?: boolean;
  dimmedHands?: Set<string>;
}

export function RangeMatrix13x13({
  grid,
  actions,
  onCellClick,
  onCellHover,
  selectedHand,
  compact,
  hideLegend,
  dimmedHands,
}: RangeMatrix13x13Props) {
  const [hoveredHand, setHoveredHand] = useState<string | null>(null);

  function handleMouseEnter(hand: string) {
    setHoveredHand(hand);
    onCellHover?.(hand);
  }

  function handleMouseLeave() {
    setHoveredHand(null);
    onCellHover?.(null);
  }

  return (
    <div className={compact ? 'space-y-1' : 'space-y-3'}>
      {/* Action Legend */}
      {!hideLegend && (
        <div className="flex items-center gap-4 text-xs">
          {actions.map((action) => (
            <div key={action} className="flex items-center gap-1.5">
              <div
                className="w-3 h-3 rounded-sm"
                style={{ backgroundColor: getActionColor(action) }}
              />
              <span className="text-muted-foreground capitalize">{formatAction(action)}</span>
            </div>
          ))}
        </div>
      )}

      {/* Matrix Grid */}
      <div
        className="inline-grid gap-[1px] bg-border/50 p-[1px] rounded-md"
        style={{ gridTemplateColumns: 'repeat(13, 1fr)' }}
      >
        {Array.from({ length: 13 }, (_, row) =>
          Array.from({ length: 13 }, (_, col) => {
            const hand = getHandLabel(row, col);
            const freqs = grid[hand] || {};
            const isSelected = selectedHand === hand;
            const isHovered = hoveredHand === hand;
            const isDimmed = dimmedHands ? dimmedHands.has(hand) : false;

            return (
              <MatrixCell
                key={hand}
                hand={hand}
                frequencies={freqs}
                actions={actions}
                isPair={row === col}
                isSuited={row < col}
                isSelected={isSelected}
                isHovered={isHovered}
                isDimmed={isDimmed}
                compact={compact}
                onClick={() => onCellClick?.(hand)}
                onMouseEnter={() => handleMouseEnter(hand)}
                onMouseLeave={handleMouseLeave}
              />
            );
          }),
        )}
      </div>

      {/* Hovered/Selected Hand Detail (hidden in compact mode) */}
      {!compact && (hoveredHand || selectedHand) && (
        <HandDetail
          hand={hoveredHand || selectedHand!}
          frequencies={grid[hoveredHand || selectedHand!] || {}}
          actions={actions}
        />
      )}
    </div>
  );
}

function HandDetail({
  hand,
  frequencies,
  actions,
}: {
  hand: string;
  frequencies: Record<string, number>;
  actions: string[];
}) {
  return (
    <div className="bg-card border border-border rounded-lg p-3 text-sm">
      <div className="font-mono font-bold text-lg mb-2">{hand}</div>
      <div className="space-y-1.5">
        {actions.map((action) => {
          const freq = frequencies[action] ?? 0;
          return (
            <div key={action} className="flex items-center gap-2">
              <div className="w-16 text-muted-foreground capitalize text-xs">
                {formatAction(action)}
              </div>
              <div className="flex-1 h-4 bg-secondary rounded-sm overflow-hidden">
                <div
                  className="h-full rounded-sm transition-all"
                  style={{
                    width: `${freq * 100}%`,
                    backgroundColor: getActionColor(action),
                  }}
                />
              </div>
              <div className="w-12 text-right font-mono text-xs">{(freq * 100).toFixed(1)}%</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function getActionColor(action: string): string {
  if (action === 'fold') return '#ef4444';
  if (action === 'call') return '#22c55e';
  if (action === 'check') return '#a3a3a3';
  if (action.startsWith('raise') || action.startsWith('3bet') || action.startsWith('4bet'))
    return '#3b82f6';
  if (action.startsWith('bet')) return '#f59e0b';
  if (action === 'allin') return '#8b5cf6';
  return '#3b82f6'; // default for unknown raise/bet actions
}

function formatAction(action: string): string {
  if (action.includes('_')) {
    const [type, size] = action.split('_');
    return `${type} ${size}`;
  }
  return action;
}
