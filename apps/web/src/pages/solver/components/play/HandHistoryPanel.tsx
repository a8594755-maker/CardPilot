import type { PlayHandResult } from '../../stores/play-mode';
import { usePlayMode } from '../../stores/play-mode';

const SEVERITY_COLORS: Record<string, string> = {
  optimal: 'text-green-400',
  minor: 'text-yellow-400',
  moderate: 'text-orange-400',
  major: 'text-red-400',
  blunder: 'text-red-500',
};

export function HandHistoryPanel() {
  const { handResults, totalHeroProfit, handFeedback } = usePlayMode();

  if (handResults.length === 0) {
    return (
      <div className="p-4 text-center text-muted-foreground text-sm">No hands played yet.</div>
    );
  }

  const wins = handResults.filter((h) => h.heroWon > 0).length;
  const losses = handResults.filter((h) => h.heroWon === 0).length;
  const totalEVLost = handFeedback.reduce((sum, f) => sum + Math.abs(Math.min(0, f.deltaEV)), 0);

  return (
    <div className="flex flex-col h-full">
      {/* Summary */}
      <div className="flex-shrink-0 p-3 border-b border-border">
        <div className="grid grid-cols-4 gap-2 text-xs">
          <div>
            <span className="text-muted-foreground">Hands:</span>
            <span className="ml-1 font-mono">{handResults.length}</span>
          </div>
          <div>
            <span className="text-muted-foreground">W/L:</span>
            <span className="ml-1 font-mono text-green-400">{wins}</span>
            <span className="text-muted-foreground">/</span>
            <span className="font-mono text-red-400">{losses}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Profit:</span>
            <span
              className={`ml-1 font-mono ${totalHeroProfit >= 0 ? 'text-green-400' : 'text-red-400'}`}
            >
              {totalHeroProfit >= 0 ? '+' : ''}
              {totalHeroProfit.toFixed(1)}
            </span>
          </div>
          <div>
            <span className="text-muted-foreground">EV Lost:</span>
            <span className="ml-1 font-mono text-orange-400">
              {totalEVLost > 0 ? `-${totalEVLost.toFixed(1)}` : '0.0'}
            </span>
          </div>
        </div>
      </div>

      {/* Hand list */}
      <div className="flex-1 overflow-auto">
        {[...handResults].reverse().map((hand) => (
          <HandResultRow key={hand.id} hand={hand} />
        ))}
      </div>
    </div>
  );
}

function HandResultRow({ hand }: { hand: PlayHandResult }) {
  const won = hand.heroWon > 0;
  const folded = hand.actions.some((a) => a.action === 'fold');

  return (
    <div className="px-3 py-2 border-b border-border/50 hover:bg-secondary/30 text-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">#{hand.id}</span>
          <span className="font-mono font-medium">{hand.heroCards.join(' ')}</span>
          <span className="text-muted-foreground">vs</span>
          <span className="font-mono">{hand.villainCards.join(' ')}</span>
        </div>
        <div className="flex items-center gap-2">
          {hand.handScore != null && (
            <span
              className={`font-mono ${hand.handScore >= 80 ? 'text-green-400' : hand.handScore >= 50 ? 'text-yellow-400' : 'text-red-400'}`}
            >
              {hand.handScore.toFixed(0)}/100
            </span>
          )}
          <span className={`font-mono font-medium ${won ? 'text-green-400' : 'text-red-400'}`}>
            {won ? `+${hand.heroWon.toFixed(0)}` : folded ? 'Fold' : `-${hand.pot.toFixed(0)}`}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-2 mt-1 text-muted-foreground">
        <span>{hand.heroRole.toUpperCase()}</span>
        <span>Board: {hand.board.join(' ')}</span>
      </div>
      {/* Per-decision feedback */}
      {hand.decisionFeedback && hand.decisionFeedback.length > 0 && (
        <div className="mt-1 space-y-0.5">
          {hand.decisionFeedback.map((fb, i) => (
            <div key={i} className="flex items-center gap-1.5">
              <span className="text-muted-foreground w-10">{fb.street}</span>
              <span className="font-mono w-16 truncate">{fb.action}</span>
              <span className={SEVERITY_COLORS[fb.severity] || 'text-gray-400'}>
                {fb.severity === 'optimal'
                  ? 'OK'
                  : `${fb.deltaEV >= 0 ? '+' : ''}${fb.deltaEV.toFixed(2)}`}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
