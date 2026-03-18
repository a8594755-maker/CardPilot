import { PokerCard } from '../PokerCard.js';

interface CommunityCardsProps {
  cards: string[]; // e.g., ["As", "Kd", "Qh"]
}

export function CommunityCards({ cards }: CommunityCardsProps) {
  return (
    <div className="flex gap-1.5">
      {cards.map((card, index) => (
        <PokerCard key={index} card={card} variant="table" />
      ))}

      {/* Placeholder for remaining cards */}
      {Array.from({ length: 5 - cards.length }).map((_, index) => (
        <PokerCard key={`placeholder-${index}`} faceDown variant="table" className="opacity-25" />
      ))}
    </div>
  );
}

export default CommunityCards;
