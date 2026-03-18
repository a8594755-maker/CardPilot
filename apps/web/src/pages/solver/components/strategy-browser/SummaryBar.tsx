import { useMemo } from 'react';
import type { GtoPlusCombo, GtoPlusContext, GtoPlusSummary } from '../../lib/api-client';
import { getActionColor, formatActionLabel } from '../../lib/strategy-utils';

interface SummaryBarProps {
  combos: GtoPlusCombo[];
  actions: string[];
  context: GtoPlusContext | null;
  summary: GtoPlusSummary | null;
}

interface ActionSummary {
  action: string;
  combos: number;
  percentage: number;
  equity: number;
  ev: number;
}

export function SummaryBar({ combos, actions, context, summary }: SummaryBarProps) {
  const actionSummaries = useMemo(() => {
    if (!combos.length || !actions.length) return [];

    const results: ActionSummary[] = [];
    const totalCombos = combos.reduce((s, c) => s + c.combos, 0);

    for (const action of actions) {
      let actionCombos = 0;
      let weightedEquity = 0;
      let weightedEv = 0;

      for (const c of combos) {
        const freq = c.frequencies[action] || 0;
        const contribution = freq * c.combos;
        actionCombos += contribution;
        weightedEquity += c.equity * contribution;
        weightedEv += (c.evs[action] ?? c.evTotal) * contribution;
      }

      results.push({
        action,
        combos: actionCombos,
        percentage: totalCombos > 0 ? (actionCombos / totalCombos) * 100 : 0,
        equity: actionCombos > 0 ? weightedEquity / actionCombos : 0,
        ev: actionCombos > 0 ? weightedEv / actionCombos : 0,
      });
    }

    return results;
  }, [combos, actions]);

  if (!summary || !context) return null;

  return (
    <div className="flex-shrink-0 border-t border-border bg-card">
      {/* Action frequency bar */}
      <div className="flex h-4 mx-4 mt-2 rounded-md overflow-hidden bg-secondary/20">
        {actionSummaries.map((as) => {
          if (as.percentage < 0.1) return null;
          return (
            <div
              key={as.action}
              className="h-full flex items-center justify-center text-[7px] font-mono font-medium"
              style={{
                width: `${as.percentage}%`,
                backgroundColor: getActionColor(as.action),
                color: 'white',
              }}
              title={`${formatActionLabel(as.action)}: ${as.percentage.toFixed(1)}%`}
            >
              {as.percentage > 10 && `${as.percentage.toFixed(0)}%`}
            </div>
          );
        })}
      </div>

      {/* Stats row */}
      <div className="px-4 py-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs">
        <StatItem label="組合" value={summary.totalCombos.toFixed(0)} />
        <StatItem label="勝率" value={`${summary.overallEquity.toFixed(1)}%`} />
        <StatItem label="EV" value={summary.overallEV.toFixed(3)} />
        {context.pot > 0 && <StatItem label="底池" value={context.pot.toFixed(0)} />}
        {context.stack > 0 && <StatItem label="籌碼" value={context.stack.toFixed(0)} />}
        {context.toCall > 0 && <StatItem label="跟注" value={context.toCall.toFixed(0)} />}
      </div>

      {/* Per-action summary row */}
      <div className="px-4 pb-2 flex flex-wrap gap-x-2 gap-y-1">
        {actionSummaries.map((as) => (
          <div
            key={as.action}
            className="flex items-center gap-1 text-[10px] bg-secondary/40 border border-border/50 rounded-md px-1.5 py-0.5"
          >
            <div
              className="w-2 h-2 rounded-sm"
              style={{ backgroundColor: getActionColor(as.action) }}
            />
            <span className="font-medium">{formatActionLabel(as.action)}:</span>
            <span className="font-mono">{as.percentage.toFixed(1)}%</span>
            <span className="text-muted-foreground/50">|</span>
            <span className="font-mono text-muted-foreground">{as.equity.toFixed(1)}%</span>
            <span className="text-muted-foreground/50">|</span>
            <span className="font-mono">{as.ev.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-muted-foreground mr-1">{label}:</span>
      <span className="font-mono font-medium">{value}</span>
    </div>
  );
}
