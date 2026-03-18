interface ActionBarProps {
  actions: string[];
  probs: number[];
  showLabels?: boolean;
  height?: number;
}

const ACTION_COLORS: Record<string, string> = {
  fold: '#ef4444',
  call: '#22c55e',
  check: '#a3a3a3',
  allin: '#8b5cf6',
};

function getColor(action: string): string {
  if (ACTION_COLORS[action]) return ACTION_COLORS[action];
  if (action.startsWith('raise') || action.startsWith('3bet') || action.startsWith('4bet'))
    return '#3b82f6';
  if (action.startsWith('bet')) return '#f59e0b';
  return '#3b82f6';
}

function formatAction(action: string): string {
  if (action.includes('_')) {
    const [type, size] = action.split('_');
    return `${type} ${size}`;
  }
  return action;
}

export function ActionBar({ actions, probs, showLabels = true, height = 28 }: ActionBarProps) {
  return (
    <div className="space-y-1">
      <div className="flex rounded-md overflow-hidden" style={{ height }}>
        {actions.map((action, i) => {
          const pct = (probs[i] ?? 0) * 100;
          if (pct < 0.5) return null;
          return (
            <div
              key={action}
              className="flex items-center justify-center text-[10px] font-mono font-medium transition-all"
              style={{
                width: `${pct}%`,
                backgroundColor: getColor(action),
                color: 'white',
                minWidth: pct > 5 ? undefined : 0,
              }}
              title={`${formatAction(action)}: ${pct.toFixed(1)}%`}
            >
              {pct > 8 && `${pct.toFixed(0)}%`}
            </div>
          );
        })}
      </div>
      {showLabels && (
        <div className="flex gap-3 text-[10px] text-muted-foreground">
          {actions.map((action, i) => {
            const pct = (probs[i] ?? 0) * 100;
            if (pct < 0.5) return null;
            return (
              <div key={action} className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-sm" style={{ backgroundColor: getColor(action) }} />
                <span className="capitalize">{formatAction(action)}</span>
                <span className="font-mono">{pct.toFixed(1)}%</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
