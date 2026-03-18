import { useMemo } from 'react';
import type { GtoPlusCombo, GtoPlusContext } from '../../lib/api-client';
import { StatisticsPanel } from './StatisticsPanel';
import { EquityDistributionBar } from './EquityDistributionBar';
import { EquityCurveChart } from './EquityCurveChart';
import { EvEquityScatter } from './EvEquityScatter';
import { categorizeAllCombosWithBoard } from '../../lib/board-aware-categorizer';
import { computeEquityBuckets } from '../../lib/hand-categorizer';

interface RightPanelProps {
  combos: GtoPlusCombo[];
  actions: string[];
  context: GtoPlusContext | null;
  ipCombos?: GtoPlusCombo[];
  boardCards?: string[];
}

export function RightPanel({
  combos,
  actions,
  context: _context,
  ipCombos,
  boardCards,
}: RightPanelProps) {
  const board = boardCards || [];

  const oopCategories = useMemo(() => {
    if (!combos.length) return [];
    return categorizeAllCombosWithBoard(combos, board, actions);
  }, [combos, board, actions]);

  const ipCategories = useMemo(() => {
    if (!ipCombos?.length) return [];
    return categorizeAllCombosWithBoard(ipCombos, board, actions);
  }, [ipCombos, board, actions]);

  const equityBuckets = useMemo(() => {
    if (!combos.length) return [];
    return computeEquityBuckets(combos);
  }, [combos]);

  if (!combos.length) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        尚未載入資料
      </div>
    );
  }

  const oopTotalCombos = combos.reduce((sum, c) => sum + c.combos, 0);
  const ipTotalCombos = ipCombos ? ipCombos.reduce((sum, c) => sum + c.combos, 0) : 0;

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Equity Curve */}
      <div className="flex-shrink-0 p-3 border-b border-border">
        <div className="text-xs font-medium mb-1">勝率曲線</div>
        <EquityCurveChart combos={combos} ipCombos={ipCombos} />
      </div>

      {/* EV vs Equity Scatter */}
      <div className="flex-shrink-0 p-3 border-b border-border">
        <div className="text-xs font-medium mb-1">EV vs 勝率</div>
        <EvEquityScatter combos={combos} ipCombos={ipCombos} />
      </div>

      {/* Category Breakdown with Action-Segmented Bars */}
      <div className="flex-1 p-3 border-b border-border">
        <StatisticsPanel
          oopCategories={oopCategories}
          oopTotalCombos={oopTotalCombos}
          actions={actions}
          ipCategories={ipCategories.length > 0 ? ipCategories : undefined}
          ipTotalCombos={ipTotalCombos || undefined}
        />
      </div>

      {/* Equity Distribution */}
      <div className="flex-shrink-0 p-3">
        <div className="text-xs font-medium mb-2">勝率分佈</div>
        <EquityDistributionBar buckets={equityBuckets} />
      </div>
    </div>
  );
}
