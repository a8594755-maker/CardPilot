import { memo } from 'react';
import { cardRankSuit, SUIT_SYMBOLS } from '../../lib/cfr-constants';

const SUIT_CARD_COLORS: Record<string, string> = {
  h: 'text-red-500 border-red-500/30',
  d: 'text-blue-500 border-blue-500/30',
  c: 'text-green-500 border-green-500/30',
  s: 'text-slate-800 border-slate-400',
};

interface PokerCardDisplayProps {
  cardIndex: number;
  size?: 'sm' | 'lg';
}

export const PokerCardDisplay = memo(function PokerCardDisplay({ cardIndex, size = 'lg' }: PokerCardDisplayProps) {
  const { rank, suit } = cardRankSuit(cardIndex);
  const colorClass = SUIT_CARD_COLORS[suit] || 'text-slate-800 border-slate-400';

  if (size === 'sm') {
    return (
      <div className={`inline-flex items-center justify-center w-8 h-10 rounded bg-white shadow-sm text-[13px] font-bold border ${colorClass}`}>
        {rank}{SUIT_SYMBOLS[suit]}
      </div>
    );
  }

  return (
    <div className={`inline-flex flex-col items-center justify-center w-[54px] h-[74px] rounded-lg bg-white border-2 shadow-md font-bold ${colorClass}`}>
      <span className="text-xl leading-none">{rank}</span>
      <span className="text-base leading-none">{SUIT_SYMBOLS[suit]}</span>
    </div>
  );
});
