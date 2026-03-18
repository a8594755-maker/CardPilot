interface NodeStatsBarProps {
  pot: number;
  combos: number;
  stack: number;
  winRate: number;
  callAmount: number;
  ev: number;
  odds: number;
  freq: number;
}

export function NodeStatsBar({
  pot,
  combos,
  stack,
  winRate,
  callAmount,
  ev,
  odds,
  freq,
}: NodeStatsBarProps) {
  return (
    <div className="flex-shrink-0 border-t border-border bg-card px-4 py-2">
      <div className="flex flex-wrap gap-4 text-xs">
        <StatItem label="Pot" value={pot} />
        <StatItem label="Combos" value={combos} />
        <StatItem label="Stack" value={stack} />
        <StatItem label="Win Rate" value={`${winRate.toFixed(1)}%`} />
        <StatItem label="To Call" value={callAmount} />
        <StatItem label="EV" value={ev.toFixed(4)} />
        <StatItem label="Odds" value={odds > 0 ? `${odds.toFixed(1)}:1` : 'NA'} />
        <StatItem label="Freq" value={`${((freq || 1) * 100).toFixed(0)}%`} />
      </div>
    </div>
  );
}

function StatItem({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-secondary/50 border border-border rounded px-2 py-1">
      <span className="text-muted-foreground mr-1">{label}:</span>
      <span className="font-mono font-medium">{value}</span>
    </div>
  );
}
