// 13×13 hand class grid — GTO Wizard style.
// Color blended by action frequencies. Click/hover for details.

import { memo, useCallback } from 'react';
import {
  RANKS,
  handClassAt,
  blendActionColors,
  dominantAction,
  type SpotSolution,
} from '../../data/preflop-loader';

interface HandGridProps {
  solution: SpotSolution;
  selectedHand: string | null;
  onSelectHand: (handClass: string | null) => void;
}

export const HandGrid = memo(function HandGrid({
  solution,
  selectedHand,
  onSelectHand,
}: HandGridProps) {
  const { grid } = solution;

  return (
    <div className="select-none">
      <div className="grid gap-[1px]" style={{ gridTemplateColumns: `repeat(13, 1fr)` }}>
        {RANKS.map((_, row) =>
          RANKS.map((_, col) => {
            const hc = handClassAt(row, col);
            const freqs = grid[hc];
            return (
              <HandCell
                key={hc}
                handClass={hc}
                freqs={freqs}
                isSelected={selectedHand === hc}
                onClick={onSelectHand}
              />
            );
          }),
        )}
      </div>
    </div>
  );
});

interface HandCellProps {
  handClass: string;
  freqs: Record<string, number> | undefined;
  isSelected: boolean;
  onClick: (hc: string | null) => void;
}

const HandCell = memo(function HandCell({ handClass, freqs, isSelected, onClick }: HandCellProps) {
  const handleClick = useCallback(() => {
    onClick(isSelected ? null : handClass);
  }, [handClass, isSelected, onClick]);

  if (!freqs) {
    return (
      <div className="aspect-square bg-slate-800/50 rounded-[2px] flex items-center justify-center">
        <span className="text-[9px] text-slate-600">{handClass}</span>
      </div>
    );
  }

  const bg = blendActionColors(freqs);
  const { freq: domFreq } = dominantAction(freqs);
  const foldFreq = freqs['fold'] ?? 0;
  const opacity =
    foldFreq >= 0.99
      ? 0.15
      : foldFreq > 0.5
        ? 0.3 + (1 - foldFreq) * 0.7
        : 0.6 + (1 - foldFreq) * 0.4;

  return (
    <div
      className={`aspect-square rounded-[2px] flex items-center justify-center cursor-pointer transition-all duration-150 relative ${
        isSelected
          ? 'ring-2 ring-white ring-offset-1 ring-offset-slate-900 z-10 scale-110'
          : 'hover:brightness-125 hover:z-10'
      }`}
      style={{ backgroundColor: bg, opacity }}
      onClick={handleClick}
      title={formatTooltip(handClass, freqs)}
    >
      <span
        className={`text-[10px] sm:text-[11px] font-semibold leading-none ${
          foldFreq > 0.7 ? 'text-white/50' : 'text-white'
        }`}
        style={{ textShadow: '0 1px 2px rgba(0,0,0,0.5)' }}
      >
        {handClass}
      </span>
      {/* Mixed indicator: small dot if not pure (>90%) */}
      {domFreq < 0.9 && domFreq > 0.01 && (
        <div
          className="absolute bottom-[1px] right-[1px] w-[4px] h-[4px] rounded-full"
          style={{ backgroundColor: 'rgba(255,255,255,0.6)' }}
        />
      )}
    </div>
  );
});

function formatTooltip(hc: string, freqs: Record<string, number>): string {
  const lines = [hc];
  for (const [action, freq] of Object.entries(freqs)) {
    if (freq > 0.001) {
      lines.push(`${action}: ${(freq * 100).toFixed(1)}%`);
    }
  }
  return lines.join('\n');
}
