// Action color legend for the hand grid.

import { memo } from 'react';
import { getActionColor, getActionLabel } from '../../data/preflop-loader';

interface ActionLegendProps {
  actions: string[];
}

export const ActionLegend = memo(function ActionLegend({ actions }: ActionLegendProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {actions.map(action => (
        <div key={action} className="flex items-center gap-1">
          <div
            className="w-3 h-3 rounded-sm"
            style={{ backgroundColor: getActionColor(action) }}
          />
          <span className="text-[10px] text-slate-400">{getActionLabel(action)}</span>
        </div>
      ))}
    </div>
  );
});
