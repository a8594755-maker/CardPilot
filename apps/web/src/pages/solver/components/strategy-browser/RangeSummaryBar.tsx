import { useRangeEditor } from '../../stores/range-editor';

interface RangeSummaryBarProps {
  label: string;
  player: 0 | 1;
}

export function RangeSummaryBar({ label, player }: RangeSummaryBarProps) {
  const { openEditor } = useRangeEditor();

  return (
    <div
      className="cursor-pointer hover:bg-secondary/50 rounded p-1 -m-1 transition-colors"
      onClick={() => openEditor(player)}
    >
      <div className="text-xs text-muted-foreground mb-1">{label}</div>
      {/* Mini range visualization - simplified colored bars */}
      <div className="h-16 bg-secondary/30 rounded border border-border overflow-hidden relative">
        {/* 13x13 mini grid representation */}
        <div className="absolute inset-0 grid grid-cols-13 grid-rows-13 gap-0">
          {Array.from({ length: 169 }, (_, i) => {
            const row = Math.floor(i / 13);
            const col = i % 13;
            const isPair = row === col;
            const isSuited = row < col;
            // Color based on rough hand strength
            const strength = getHandStrengthColor(row, col, isPair, isSuited);
            return <div key={i} style={{ backgroundColor: strength }} />;
          })}
        </div>
      </div>
    </div>
  );
}

function getHandStrengthColor(
  row: number,
  col: number,
  isPair: boolean,
  isSuited: boolean,
): string {
  // Simple heuristic: closer to top-left = stronger
  const strength = (26 - row - col) / 26;

  if (isPair) {
    if (row <= 4) return '#ef4444'; // Premium pairs
    if (row <= 8) return '#22c55e'; // Medium pairs
    return '#3b82f6'; // Small pairs
  }

  if (isSuited) {
    if (strength > 0.75) return '#ef4444';
    if (strength > 0.5) return '#22c55e';
    return '#3b82f6';
  }

  // Offsuit
  if (strength > 0.8) return '#ef4444';
  if (strength > 0.6) return '#22c55e';
  if (strength > 0.4) return '#3b82f6';
  return 'transparent';
}
