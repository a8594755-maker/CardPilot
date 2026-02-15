import { getCardImagePath, getCardBackPath } from '../../lib/card-images.js';

interface CommunityCardsProps {
  cards: string[]; // e.g., ["As", "Kd", "Qh"]
}

export function CommunityCards({ cards }: CommunityCardsProps) {
  return (
    <div className="flex gap-2">
      {cards.map((card, index) => (
        <img
          key={index}
          src={getCardImagePath(card)}
          alt={card}
          className="w-16 h-auto rounded-lg shadow-xl hover:scale-105 transition-transform"
          onError={(e) => {
            // If image loading fails, show fallback text
            const target = e.target as HTMLImageElement;
            target.style.display = 'none';
            const parent = target.parentElement;
            if (parent) {
              const rank = card[0];
              const suit = card[1];
              const isRed = suit === 'h' || suit === 'd';
              const suitSymbol: Record<string, string> = {
                's': '♠', 'h': '♥', 'd': '♦', 'c': '♣',
              };
              parent.innerHTML = `
                <div class="w-12 h-16 bg-white rounded-lg border-2 border-slate-200 flex flex-col items-center justify-center shadow-lg ${isRed ? 'text-red-600' : 'text-slate-900'}">
                  <span class="text-lg font-bold">${rank}</span>
                  <span class="text-lg">${suitSymbol[suit]}</span>
                </div>
              `;
            }
          }}
        />
      ))}
      
      {/* Placeholder for remaining cards */}
      {Array.from({ length: 5 - cards.length }).map((_, index) => (
        <img
          key={`placeholder-${index}`}
          src={getCardBackPath('blue')}
          alt="Card Placeholder"
          className="w-16 h-auto rounded-lg shadow-xl opacity-30"
          onError={(e) => {
            const target = e.target as HTMLImageElement;
            target.style.display = 'none';
            const parent = target.parentElement;
            if (parent) {
              parent.innerHTML = '<div class="w-12 h-16 bg-slate-700/50 rounded-lg border-2 border-dashed border-slate-600"></div>';
            }
          }}
        />
      ))}
    </div>
  );
}

export default CommunityCards;
