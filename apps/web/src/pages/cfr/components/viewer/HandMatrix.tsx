import { memo, useCallback, useState } from 'react';
import type { MatrixCellData } from '../../hooks/useHandMatrix';
import { buildStrengthLabels } from '../../lib/cfr-computations';
import { getActionColor } from '../../lib/cfr-colors';

interface HandMatrixProps {
  cells: MatrixCellData[];
  actionLabels: string[];
  selectedHand: string | null;
  onSelectHand: (h: string | null) => void;
  onHoverHand?: (h: string | null) => void;
  bucketCount: number;
}

interface TooltipData {
  cell: MatrixCellData;
  x: number;
  y: number;
}

export const HandMatrix = memo(function HandMatrix({
  cells,
  actionLabels,
  selectedHand,
  onSelectHand,
  onHoverHand,
}: HandMatrixProps) {
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);

  const handleClick = useCallback(
    (hc: string) => {
      onSelectHand(selectedHand === hc ? null : hc);
    },
    [selectedHand, onSelectHand],
  );

  const handleHoverWithPos = useCallback(
    (cell: MatrixCellData | null, x: number, y: number) => {
      if (cell) {
        // Edge clamping: keep tooltip within viewport
        const clampedX = Math.min(x, window.innerWidth - 200);
        const clampedY = Math.max(y, 120);
        setTooltip({ cell, x: clampedX, y: clampedY });
      } else {
        setTooltip(null);
      }
      onHoverHand?.(cell?.handClass ?? null);
    },
    [onHoverHand],
  );

  return (
    <div className="relative">
      <div className="grid gap-0.5" style={{ gridTemplateColumns: 'repeat(13, minmax(0, 1fr))' }}>
        {cells.map((cell) => (
          <HandMatrixCell
            key={cell.handClass}
            cell={cell}
            isSelected={selectedHand === cell.handClass}
            onClick={() => handleClick(cell.handClass)}
            onHoverWithPos={handleHoverWithPos}
          />
        ))}
      </div>

      {/* Hover tooltip — only on devices with hover capability */}
      {tooltip && tooltip.cell.hasData && tooltip.cell.probs && (
        <div
          className="fixed z-50 pointer-events-none bg-[var(--cp-bg-elevated)] border border-white/15 rounded-lg px-3 py-2.5 shadow-xl"
          style={{
            left: tooltip.x + 14,
            top: tooltip.y - 10,
            transform: 'translateY(-100%)',
          }}
        >
          <div className="text-sm font-bold text-white mb-1.5">{tooltip.cell.handClass}</div>
          {/* Mini action bar */}
          <div className="flex rounded overflow-hidden h-2.5 w-36 mb-2">
            {actionLabels.map((label, i) => {
              const pct = tooltip.cell.probs![i] * 100;
              if (pct < 0.5) return null;
              return (
                <div
                  key={label}
                  style={{ width: `${pct}%`, background: getActionColor(label) }}
                  className="h-full"
                />
              );
            })}
          </div>
          {/* Action breakdown */}
          <div className="flex flex-col gap-0.5">
            {actionLabels.map((label, i) => {
              const pct = tooltip.cell.probs![i] * 100;
              if (pct < 0.5) return null;
              return (
                <div key={label} className="flex items-center gap-1.5 text-[10px]">
                  <div
                    className="w-2 h-2 rounded-sm shrink-0"
                    style={{ background: getActionColor(label) }}
                  />
                  <span className="text-slate-400">{label}</span>
                  <span className="ml-auto text-white font-semibold tabular-nums">
                    {pct.toFixed(1)}%
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
});

// Individual cell (memoized for performance)
const HandMatrixCell = memo(function HandMatrixCell({
  cell,
  isSelected,
  onClick,
  onHoverWithPos,
}: {
  cell: MatrixCellData;
  isSelected: boolean;
  onClick: () => void;
  onHoverWithPos: (cell: MatrixCellData | null, x: number, y: number) => void;
}) {
  return (
    <div
      onClick={onClick}
      onMouseMove={(e) => onHoverWithPos(cell, e.clientX, e.clientY)}
      onMouseLeave={() => onHoverWithPos(null, 0, 0)}
      className={`aspect-square rounded-sm flex items-center justify-center cursor-pointer text-[13px] font-bold transition-all border-[1.5px] ${
        isSelected
          ? 'border-blue-500 shadow-[0_0_16px_rgba(59,130,246,0.6)] z-10 scale-110'
          : 'border-black/15 hover:border-white hover:z-10 hover:scale-110 hover:shadow-lg'
      }`}
      style={{ background: cell.bgColor }}
    >
      <span
        className={
          cell.hasData
            ? 'text-white drop-shadow-[0_1px_3px_rgba(0,0,0,0.9)]'
            : 'text-slate-500 font-medium'
        }
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
