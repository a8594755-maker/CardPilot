import { memo, useCallback } from 'react';
import type { MatrixCellData } from '../../hooks/useHandMatrix';
import { buildStrengthLabels } from '../../lib/cfr-computations';

interface HandMatrixProps {
  cells: MatrixCellData[];
  actionLabels: string[];
  selectedHand: string | null;
  onSelectHand: (h: string | null) => void;
  onHoverHand?: (h: string | null) => void;
  bucketCount: number;
}

export const HandMatrix = memo(function HandMatrix({ cells, selectedHand, onSelectHand, onHoverHand }: HandMatrixProps) {
  const handleClick = useCallback((hc: string) => {
    onSelectHand(selectedHand === hc ? null : hc);
  }, [selectedHand, onSelectHand]);

  return (
    <div className="max-w-[900px]">
      <div className="grid gap-0.5" style={{ gridTemplateColumns: 'repeat(13, minmax(0, 1fr))' }}>
        {cells.map(cell => (
          <HandMatrixCell
            key={cell.handClass}
            cell={cell}
            isSelected={selectedHand === cell.handClass}
            onClick={() => handleClick(cell.handClass)}
            onHover={onHoverHand ?? (() => {})}
          />
        ))}
      </div>
    </div>
  );
});

// Individual cell (memoized for performance)
const HandMatrixCell = memo(function HandMatrixCell({
  cell, isSelected, onClick, onHover,
}: {
  cell: MatrixCellData;
  isSelected: boolean;
  onClick: () => void;
  onHover: (h: string | null) => void;
}) {
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => onHover(cell.handClass)}
      onMouseLeave={() => onHover(null)}
      className={`aspect-square rounded-sm flex items-center justify-center cursor-pointer text-[13px] font-bold transition-all border-[1.5px] ${
        isSelected
          ? 'border-blue-500 shadow-[0_0_16px_rgba(59,130,246,0.6)] z-10 scale-110'
          : 'border-black/15 hover:border-white hover:z-10 hover:scale-110 hover:shadow-lg'
      }`}
      style={{ background: cell.bgColor }}
    >
      <span
        className={cell.hasData ? 'text-white drop-shadow-[0_1px_3px_rgba(0,0,0,0.9)]' : 'text-slate-500 font-medium'}
        style={{ fontSize: '0.8125rem', letterSpacing: '0.02em' }}
      >
        {cell.handClass}
      </span>
    </div>
  );
});

export function getStrengthLabel(bucket: number, bc: number): string {
  const labels = buildStrengthLabels(bc);
  for (const s of labels) {
    if (bucket >= s.from && bucket < s.to) return s.label;
  }
  return labels[labels.length - 1].label;
}
