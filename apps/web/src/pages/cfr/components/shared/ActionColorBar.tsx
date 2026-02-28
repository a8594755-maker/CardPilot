import { memo } from 'react';
import { getActionColor } from '../../lib/cfr-colors';

interface ActionColorBarProps {
  labels: string[];
  probs: number[];
  height?: number;
}

export const ActionColorBar = memo(function ActionColorBar({ labels, probs, height = 20 }: ActionColorBarProps) {
  const total = probs.reduce((a, b) => a + b, 0);
  if (total < 0.001) return <div className="text-slate-500 text-xs">No data</div>;

  return (
    <div className="flex rounded overflow-hidden gap-px" style={{ height }}>
      {labels.map((label, i) => {
        const pct = (probs[i] / total) * 100;
        if (pct < 1) return null;
        return (
          <div
            key={label}
            className="flex items-center justify-center text-[10px] font-bold text-white"
            style={{
              width: `${pct}%`,
              minWidth: pct > 5 ? '20px' : '4px',
              background: getActionColor(label),
            }}
            title={`${label}: ${pct.toFixed(1)}%`}
          >
            {pct > 12 ? `${Math.round(pct)}%` : ''}
          </div>
        );
      })}
    </div>
  );
});
