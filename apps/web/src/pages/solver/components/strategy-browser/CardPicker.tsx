import { useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';

const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2'] as const;
const SUITS = ['s', 'h', 'd', 'c'] as const;

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

interface CardPickerProps {
  onSelect: (card: string) => void;
  onClose: () => void;
  deadCards?: string[];
  selectedCard?: string | null;
  anchorRect: DOMRect | null;
}

export function CardPicker({
  onSelect,
  onClose,
  deadCards = [],
  selectedCard,
  anchorRect,
}: CardPickerProps) {
  const deadSet = new Set(deadCards.map((c) => c.toLowerCase()));
  const ref = useRef<HTMLDivElement>(null);

  const handleClickOutside = useCallback(
    (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    },
    [onClose],
  );

  useEffect(() => {
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [handleClickOutside]);

  if (!anchorRect) return null;

  const content = (
    <div
      ref={ref}
      className="fixed z-[9999] bg-card border border-border rounded-lg shadow-xl p-2"
      style={{ top: anchorRect.bottom + 4, left: anchorRect.left }}
    >
      <div className="inline-grid gap-[2px]" style={{ gridTemplateColumns: `repeat(4, 1fr)` }}>
        {RANKS.map((rank) =>
          SUITS.map((suit) => {
            const card = `${rank}${suit}`;
            const isDead = deadSet.has(card.toLowerCase());
            const isSelected = selectedCard === card;

            return (
              <button
                key={card}
                disabled={isDead}
                onClick={() => {
                  onSelect(card);
                  onClose();
                }}
                className={`w-9 h-7 rounded text-[10px] font-mono font-medium flex items-center justify-center transition-colors ${
                  isDead
                    ? 'bg-secondary/30 text-muted-foreground/30 cursor-not-allowed'
                    : isSelected
                      ? 'ring-2 ring-primary bg-primary/20'
                      : 'bg-secondary hover:bg-secondary/80 cursor-pointer'
                }`}
                style={!isDead ? { color: SUIT_COLORS[suit] } : undefined}
                title={`${rank}${SUIT_SYMBOLS[suit]}`}
              >
                {rank}
                {SUIT_SYMBOLS[suit]}
              </button>
            );
          }),
        )}
      </div>
    </div>
  );

  return createPortal(content, document.body);
}
