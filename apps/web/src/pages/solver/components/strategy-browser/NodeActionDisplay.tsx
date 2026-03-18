import type { GtoPlusContext } from '../../lib/api-client';
import { useStrategyBrowser } from '../../stores/strategy-browser';
import { getActionColor, formatActionLabel } from '../../lib/strategy-utils';

export function NodeActionDisplay() {
  const { nodeActions, nodeSummary, nodeContext, currentPath, setPath } = useStrategyBrowser();

  if (!nodeActions.length || !nodeSummary) {
    return (
      <div className="flex items-center justify-center h-20 text-muted-foreground text-xs">
        選擇檔案查看操作
      </div>
    );
  }

  const { actionPercentages, actionCombos } = nodeSummary;

  // Sort actions by descending frequency
  const sortedActions = [...nodeActions].sort(
    (a, b) => (actionPercentages[b] ?? 0) - (actionPercentages[a] ?? 0),
  );

  const maxPct = Math.max(...Object.values(actionPercentages), 1);

  return (
    <div className="space-y-2">
      <PathBreadcrumb path={currentPath} onNavigate={setPath} />
      {nodeContext && <NodeContextCompact context={nodeContext} />}
      <div className="space-y-0.5">
        {sortedActions.map((action) => (
          <ActionFrequencyBar
            key={action}
            action={action}
            percentage={actionPercentages[action] ?? 0}
            combos={actionCombos[action] ?? 0}
            maxPct={maxPct}
          />
        ))}
      </div>
      <OverviewBar actions={sortedActions} percentages={actionPercentages} />
    </div>
  );
}

function PathBreadcrumb({
  path,
  onNavigate,
}: {
  path: string[];
  onNavigate: (path: string[]) => void;
}) {
  return (
    <div className="flex items-center gap-1 text-[10px] font-mono flex-wrap">
      <button onClick={() => onNavigate([])} className="text-primary hover:underline">
        根節點
      </button>
      {path.map((segment, i) => (
        <span key={i} className="flex items-center gap-1">
          <span className="text-muted-foreground">&gt;</span>
          <button
            onClick={() => onNavigate(path.slice(0, i + 1))}
            className={
              i === path.length - 1 ? 'text-foreground font-medium' : 'text-primary hover:underline'
            }
          >
            {formatActionLabel(segment)}
          </button>
        </span>
      ))}
    </div>
  );
}

function NodeContextCompact({ context }: { context: GtoPlusContext }) {
  return (
    <div className="flex items-center gap-2 text-[10px] font-mono text-muted-foreground">
      <span>
        底池: <span className="text-foreground font-medium">{context.pot}</span>
      </span>
      <span className="text-border">|</span>
      <span>
        籌碼: <span className="text-foreground font-medium">{context.stack}</span>
      </span>
      {context.toCall > 0 && (
        <>
          <span className="text-border">|</span>
          <span>
            跟注: <span className="text-foreground font-medium">{context.toCall}</span>
          </span>
        </>
      )}
    </div>
  );
}

function ActionFrequencyBar({
  action,
  percentage,
  combos,
  maxPct,
}: {
  action: string;
  percentage: number;
  combos: number;
  maxPct: number;
}) {
  const color = getActionColor(action);
  const barWidth = maxPct > 0 ? (percentage / maxPct) * 100 : 0;

  return (
    <div className="group">
      <div className="flex items-center gap-1.5">
        {/* Color dot + label */}
        <div className="flex items-center gap-1 w-[60px] flex-shrink-0">
          <div className="w-2 h-2 rounded-sm flex-shrink-0" style={{ backgroundColor: color }} />
          <span className="text-[11px] truncate font-medium">{formatActionLabel(action)}</span>
        </div>

        {/* Bar */}
        <div className="flex-1 h-4 bg-secondary/20 rounded-sm overflow-hidden">
          <div
            className="h-full rounded-sm transition-all"
            style={{
              width: `${barWidth}%`,
              backgroundColor: color,
              opacity: 0.85,
            }}
          />
        </div>

        {/* Percentage */}
        <div className="w-[38px] text-right text-[11px] font-mono flex-shrink-0">
          {percentage.toFixed(1)}%
        </div>
      </div>

      {/* Combo count on hover */}
      <div className="text-[9px] text-muted-foreground/60 pl-[14px] font-mono opacity-0 group-hover:opacity-100 transition-opacity h-0 group-hover:h-3 overflow-hidden">
        {combos.toFixed(1)} 組合
      </div>
    </div>
  );
}

function OverviewBar({
  actions,
  percentages,
}: {
  actions: string[];
  percentages: Record<string, number>;
}) {
  const total = Object.values(percentages).reduce((s, v) => s + v, 0);
  if (total === 0) return null;

  return (
    <div className="flex h-4 rounded-md overflow-hidden">
      {actions.map((action) => {
        const pct = percentages[action] ?? 0;
        if (pct < 0.1) return null;
        const widthPct = (pct / total) * 100;
        return (
          <div
            key={action}
            style={{
              width: `${widthPct}%`,
              backgroundColor: getActionColor(action),
            }}
            className="h-full flex items-center justify-center text-[7px] font-mono text-white font-medium"
            title={`${formatActionLabel(action)}: ${pct.toFixed(1)}%`}
          >
            {widthPct > 10 && `${pct.toFixed(0)}%`}
          </div>
        );
      })}
    </div>
  );
}
