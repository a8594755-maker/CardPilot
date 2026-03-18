import { ActionBar } from './ActionBar';

interface NodeDetailProps {
  historyKey: string;
  player: number;
  street: string;
  pot: number;
  stacks: number[];
  actions: string[];
  probs: number[];
  onSelectAction: (action: string) => void;
}

export function NodeDetail({
  historyKey,
  player,
  street,
  pot,
  stacks,
  actions,
  probs,
  onSelectAction,
}: NodeDetailProps) {
  const playerLabel = player === 0 ? 'OOP (BB)' : 'IP (BTN)';
  const spr = stacks[0] ? (stacks[0] / pot).toFixed(1) : '?';

  return (
    <div className="bg-card border border-border rounded-lg p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-medium">{playerLabel} to act</div>
          <div className="text-xs text-muted-foreground font-mono">{street}</div>
        </div>
        <div className="text-right text-xs text-muted-foreground">
          <div>
            Pot: <span className="text-foreground font-mono">{pot.toFixed(1)} bb</span>
          </div>
          <div>
            SPR: <span className="text-foreground font-mono">{spr}</span>
          </div>
        </div>
      </div>

      {/* Strategy Bar */}
      <ActionBar actions={actions} probs={probs} />

      {/* Action Buttons */}
      <div className="flex gap-2 flex-wrap">
        {actions.map((action, i) => {
          const pct = (probs[i] ?? 0) * 100;
          return (
            <button
              key={action}
              onClick={() => onSelectAction(action)}
              className="px-3 py-1.5 rounded-md text-xs font-medium border border-border hover:bg-secondary transition-colors"
            >
              <span className="capitalize">{formatAction(action)}</span>
              <span className="ml-1 text-muted-foreground font-mono">{pct.toFixed(1)}%</span>
            </button>
          );
        })}
      </div>

      {/* Info */}
      <div className="text-[10px] text-muted-foreground font-mono truncate">Key: {historyKey}</div>
    </div>
  );
}

function formatAction(action: string): string {
  if (action.includes('_')) {
    const [type, size] = action.split('_');
    return `${type} ${size}`;
  }
  return action;
}
