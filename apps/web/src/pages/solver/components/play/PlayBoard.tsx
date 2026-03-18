import { usePlayMode } from '../../stores/play-mode';

const SUIT_SYMBOLS: Record<string, string> = { h: '\u2665', d: '\u2666', c: '\u2663', s: '\u2660' };
const SUIT_COLORS: Record<string, string> = {
  h: 'text-red-500',
  d: 'text-blue-400',
  c: 'text-green-500',
  s: 'text-foreground',
};

function CardDisplay({ card, faceDown }: { card: string; faceDown?: boolean }) {
  if (faceDown) {
    return (
      <div className="w-14 h-20 rounded-lg border-2 border-border bg-secondary flex items-center justify-center">
        <span className="text-muted-foreground text-lg">?</span>
      </div>
    );
  }

  const rank = card[0];
  const suit = card[1];
  return (
    <div
      className={`w-14 h-20 rounded-lg border-2 border-border bg-card flex flex-col items-center justify-center ${SUIT_COLORS[suit] || ''}`}
    >
      <span className="text-xl font-bold">{rank}</span>
      <span className="text-lg">{SUIT_SYMBOLS[suit] || suit}</span>
    </div>
  );
}

export function PlayBoard() {
  const store = usePlayMode();

  return (
    <div className="flex flex-col items-center gap-6 py-6">
      {/* Villain info */}
      <div className="text-center">
        <div className="text-xs text-muted-foreground mb-1">
          Villain ({store.heroRole === 'oop' ? 'IP' : 'OOP'})
        </div>
        <div className="text-sm font-mono mb-2">Stack: {store.villainStack.toFixed(0)}</div>
        <div className="flex gap-2 justify-center">
          {store.villainCards && store.street === 'showdown' ? (
            store.villainCards.map((c, i) => <CardDisplay key={i} card={c} />)
          ) : (
            <>
              <CardDisplay card="" faceDown />
              <CardDisplay card="" faceDown />
            </>
          )}
        </div>
        {store.lastAction && !store.isHeroTurn && (
          <div className="mt-2 text-xs text-yellow-400">{store.lastAction}</div>
        )}
      </div>

      {/* Board */}
      <div className="bg-secondary/30 rounded-xl px-8 py-6 min-w-[400px]">
        <div className="flex gap-2 justify-center mb-3">
          {store.board.length > 0 ? (
            store.board.map((c, i) => <CardDisplay key={i} card={c} />)
          ) : (
            <div className="text-muted-foreground text-sm py-4">Waiting for flop...</div>
          )}
        </div>
        <div className="text-center">
          <span className="text-xs text-muted-foreground">Pot:</span>
          <span className="ml-1 font-mono font-bold text-lg">{store.pot.toFixed(0)}</span>
        </div>
      </div>

      {/* Street indicator */}
      <div className="flex gap-2">
        {(['flop', 'turn', 'river'] as const).map((s) => (
          <div
            key={s}
            className={`px-3 py-1 rounded text-xs capitalize ${
              store.street === s
                ? 'bg-primary/20 text-primary border border-primary/30'
                : 'text-muted-foreground'
            }`}
          >
            {s}
          </div>
        ))}
      </div>

      {/* Hero cards */}
      <div className="text-center">
        {store.lastAction && store.isHeroTurn && (
          <div className="mb-2 text-xs text-yellow-400">{store.lastAction}</div>
        )}
        <div className="flex gap-2 justify-center">
          {store.heroCards ? (
            store.heroCards.map((c, i) => <CardDisplay key={i} card={c} />)
          ) : (
            <>
              <CardDisplay card="" faceDown />
              <CardDisplay card="" faceDown />
            </>
          )}
        </div>
        <div className="text-sm font-mono mt-2">Stack: {store.heroStack.toFixed(0)}</div>
        <div className="text-xs text-muted-foreground mt-1">
          Hero ({store.heroRole.toUpperCase()})
        </div>
      </div>

      {/* Showdown result */}
      {store.street === 'showdown' && (
        <div className="text-center bg-card border border-border rounded-lg p-4 min-w-[300px]">
          {store.actionHistory.some((a) => a.action === 'fold') ? (
            <div className="text-lg font-semibold">
              {store.actionHistory[store.actionHistory.length - 1]?.player === 'oop'
                ? store.heroRole === 'oop'
                  ? 'You folded'
                  : 'Villain folded'
                : store.heroRole === 'ip'
                  ? 'You folded'
                  : 'Villain folded'}
            </div>
          ) : (
            <div className="text-lg font-semibold">Showdown</div>
          )}
        </div>
      )}

      {/* Action history */}
      {store.actionHistory.length > 0 && (
        <div className="text-xs text-muted-foreground flex flex-wrap gap-1 max-w-md justify-center">
          {store.actionHistory.map((a, i) => (
            <span key={i} className="bg-secondary px-2 py-0.5 rounded">
              {a.player === store.heroRole ? 'Hero' : 'Villain'}: {a.action}
              {a.amount > 0 ? ` ${a.amount}` : ''}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
