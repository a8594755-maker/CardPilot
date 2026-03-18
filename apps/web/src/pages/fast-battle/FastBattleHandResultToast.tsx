/**
 * FastBattleHandResultToast — Brief notification after each hand showing result.
 */

import type { FastBattleHandResultEntry } from '../../hooks/useFastBattle';

interface Props {
  result: FastBattleHandResultEntry | null;
}

export function FastBattleHandResultToast({ result }: Props) {
  if (!result) return null;

  const isPositive = result.result >= 0;
  const sign = isPositive ? '+' : '';
  const bgColor = isPositive
    ? 'bg-emerald-500/20 border-emerald-500/30'
    : 'bg-red-500/20 border-red-500/30';
  const textColor = isPositive ? 'text-emerald-400' : 'text-red-400';

  return (
    <div className="absolute top-12 left-1/2 -translate-x-1/2 z-50 pointer-events-none animate-fade-in-out">
      <div className={`px-4 py-2 rounded-lg border ${bgColor} backdrop-blur-sm`}>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-slate-400 text-xs">#{result.handNumber}</span>
          <span className={`font-mono font-bold ${textColor}`}>
            {sign}
            {result.result}
          </span>
          <span className="text-slate-500 text-xs">
            {result.heroPosition} {result.holeCards.join('')}
          </span>
        </div>
      </div>
    </div>
  );
}
