const RANKS = 'AKQJT98765432';

function getHandLabel(row: number, col: number): string {
  if (row === col) return `${RANKS[row]}${RANKS[col]}`;
  if (row < col) return `${RANKS[row]}${RANKS[col]}s`;
  return `${RANKS[col]}${RANKS[row]}o`;
}

function getHandType(row: number, col: number): 'pair' | 'suited' | 'offsuit' {
  if (row === col) return 'pair';
  if (row < col) return 'suited';
  return 'offsuit';
}

const COLORS = {
  pair: '#ef4444',
  suited: '#3b82f6',
  offsuit: '#22c55e',
  empty: '#1a1a2e',
};

interface MiniRangePreviewProps {
  selectedHands: Set<string>;
  size?: number;
}

export function MiniRangePreview({ selectedHands, size = 80 }: MiniRangePreviewProps) {
  const cellSize = size / 13;

  return (
    <div
      className="rounded border border-border overflow-hidden"
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {Array.from({ length: 13 }, (_, row) =>
          Array.from({ length: 13 }, (_, col) => {
            const hand = getHandLabel(row, col);
            const type = getHandType(row, col);
            const isSelected = selectedHands.has(hand);
            const fill = isSelected ? COLORS[type] : COLORS.empty;
            return (
              <rect
                key={hand}
                x={col * cellSize}
                y={row * cellSize}
                width={cellSize}
                height={cellSize}
                fill={fill}
                stroke="#000"
                strokeWidth={0.3}
              />
            );
          }),
        )}
      </svg>
    </div>
  );
}
