import { useState, useRef } from 'react';
import { useStrategyBrowser } from '../../stores/strategy-browser';
import { useWorkspace } from '../../stores/workspace';
import { getActionColor, formatActionLabel } from '../../lib/strategy-utils';
import { CardPicker } from './CardPicker';

const SUIT_SYMBOLS: Record<string, string> = {
  s: '\u2660',
  h: '\u2665',
  d: '\u2666',
  c: '\u2663',
};

const SUIT_COLORS: Record<string, string> = {
  s: '#1a1a2e',
  h: '#e74c3c',
  d: '#3498db',
  c: '#27ae60',
};

export function TreeNavigator() {
  const { currentPath, nodeActions, goBack, goToRoot, navigateTo } = useStrategyBrowser();
  const flopCards = useWorkspace((s) => s.boardCards);

  const [showTurnPicker, setShowTurnPicker] = useState(false);
  const [showRiverPicker, setShowRiverPicker] = useState(false);
  const [turnCard, setTurnCard] = useState<string | null>(null);
  const [riverCard, setRiverCard] = useState<string | null>(null);
  const turnBtnRef = useRef<HTMLButtonElement>(null);
  const riverBtnRef = useRef<HTMLButtonElement>(null);

  // Dead cards: flop + turn + river
  const deadCards = [
    ...flopCards,
    ...(turnCard ? [turnCard] : []),
    ...(riverCard ? [riverCard] : []),
  ];

  return (
    <div className="space-y-2">
      {/* Navigation breadcrumb */}
      <div className="flex items-center gap-1 flex-wrap text-[10px]">
        <button
          onClick={goToRoot}
          className="px-1.5 py-0.5 rounded bg-secondary text-muted-foreground hover:text-foreground"
        >
          Root
        </button>

        {currentPath.map((action, idx) => (
          <div key={idx} className="flex items-center gap-0.5">
            <span className="text-muted-foreground">&gt;</span>
            <button
              onClick={() => {
                // Navigate to this point in the path
                goToRoot();
                for (let i = 0; i <= idx; i++) {
                  navigateTo(currentPath[i]);
                }
              }}
              className="px-1.5 py-0.5 rounded"
              style={{
                backgroundColor: `${getActionColor(action)}20`,
                color: getActionColor(action),
              }}
            >
              {formatActionLabel(action)}
            </button>
          </div>
        ))}

        {/* Back button */}
        {currentPath.length > 0 && (
          <button
            onClick={goBack}
            className="ml-1 px-1.5 py-0.5 rounded bg-secondary text-muted-foreground hover:text-foreground"
            title="Go back"
          >
            &larr;
          </button>
        )}
      </div>

      {/* Flop cards display */}
      {flopCards.length > 0 && (
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-muted-foreground">Flop:</span>
          <div className="flex gap-0.5">
            {flopCards.map((card, idx) => (
              <CardChip key={idx} card={card} />
            ))}
          </div>

          {/* Turn card selector */}
          <div>
            <button
              ref={turnBtnRef}
              onClick={() => setShowTurnPicker(!showTurnPicker)}
              className={`px-1.5 py-0.5 rounded text-[10px] ${turnCard ? 'bg-secondary' : 'bg-primary/20 text-primary hover:bg-primary/30'}`}
            >
              {turnCard ? <CardChip card={turnCard} /> : '+ Turn'}
            </button>
            {showTurnPicker && (
              <CardPicker
                onSelect={(card) => {
                  setTurnCard(card);
                  setRiverCard(null);
                }}
                onClose={() => setShowTurnPicker(false)}
                deadCards={deadCards}
                selectedCard={turnCard}
                anchorRect={turnBtnRef.current?.getBoundingClientRect() ?? null}
              />
            )}
          </div>

          {/* River card selector (only if turn is set) */}
          {turnCard && (
            <div>
              <button
                ref={riverBtnRef}
                onClick={() => setShowRiverPicker(!showRiverPicker)}
                className={`px-1.5 py-0.5 rounded text-[10px] ${riverCard ? 'bg-secondary' : 'bg-primary/20 text-primary hover:bg-primary/30'}`}
              >
                {riverCard ? <CardChip card={riverCard} /> : '+ River'}
              </button>
              {showRiverPicker && (
                <CardPicker
                  onSelect={setRiverCard}
                  onClose={() => setShowRiverPicker(false)}
                  deadCards={deadCards}
                  selectedCard={riverCard}
                  anchorRect={riverBtnRef.current?.getBoundingClientRect() ?? null}
                />
              )}
            </div>
          )}
        </div>
      )}

      {/* Available actions at current node */}
      {nodeActions.length > 0 && (
        <div className="flex items-center gap-1 flex-wrap">
          <span className="text-[10px] text-muted-foreground mr-1">Actions:</span>
          {nodeActions.map((action) => (
            <button
              key={action}
              onClick={() => navigateTo(action)}
              className="px-1.5 py-0.5 rounded text-[10px] hover:opacity-80"
              style={{
                backgroundColor: `${getActionColor(action)}30`,
                color: getActionColor(action),
                borderLeft: `2px solid ${getActionColor(action)}`,
              }}
            >
              {formatActionLabel(action)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function CardChip({ card }: { card: string }) {
  if (card.length < 2) return <span>{card}</span>;
  const rank = card[0];
  const suit = card[1].toLowerCase();

  return (
    <span
      className="inline-flex items-center px-1 py-0.5 rounded bg-secondary font-mono text-[10px] font-medium"
      style={{ color: SUIT_COLORS[suit] || 'inherit' }}
    >
      {rank}
      {SUIT_SYMBOLS[suit] || suit}
    </span>
  );
}
