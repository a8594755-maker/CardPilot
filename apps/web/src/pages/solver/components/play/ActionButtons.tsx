import { useState } from 'react';
import { usePlayMode } from '../../stores/play-mode';

interface ActionButtonsProps {
  onAction: (action: string, amount?: number) => void;
}

export function ActionButtons({ onAction }: ActionButtonsProps) {
  const store = usePlayMode();
  const [betAmount, setBetAmount] = useState(store.minBet);

  if (!store.isHeroTurn || store.street === 'showdown' || store.street === 'finished') {
    return null;
  }

  const potSizes = [
    { label: '33%', mult: 0.33 },
    { label: '50%', mult: 0.5 },
    { label: '67%', mult: 0.67 },
    { label: '75%', mult: 0.75 },
    { label: 'Pot', mult: 1.0 },
    { label: '1.5x', mult: 1.5 },
    { label: 'All-in', mult: Infinity },
  ];

  function handlePotSize(mult: number) {
    if (mult === Infinity) {
      setBetAmount(store.maxBet);
    } else {
      const size = Math.round(store.pot * mult);
      setBetAmount(Math.min(Math.max(size, store.minBet), store.maxBet));
    }
  }

  return (
    <div className="bg-card border-t border-border p-4 space-y-3">
      {/* Bet/Raise sizing */}
      {(store.canBet || store.canRaise) && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <input
              type="range"
              min={store.minBet}
              max={store.maxBet}
              value={betAmount}
              onChange={(e) => setBetAmount(Number(e.target.value))}
              className="flex-1"
            />
            <input
              type="number"
              value={betAmount}
              onChange={(e) => setBetAmount(Number(e.target.value))}
              min={store.minBet}
              max={store.maxBet}
              className="w-20 px-2 py-1 bg-secondary border border-border rounded text-sm text-center font-mono"
            />
          </div>
          <div className="flex gap-1 flex-wrap">
            {potSizes.map((ps) => (
              <button
                key={ps.label}
                onClick={() => handlePotSize(ps.mult)}
                className="px-2 py-1 text-xs bg-secondary border border-border rounded hover:bg-secondary/80"
              >
                {ps.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2">
        {store.canFold && (
          <button
            onClick={() => onAction('fold')}
            className="flex-1 py-2.5 rounded text-sm font-medium bg-red-600/20 text-red-400 border border-red-600/30 hover:bg-red-600/30"
          >
            Fold
          </button>
        )}
        {store.canCheck && (
          <button
            onClick={() => onAction('check')}
            className="flex-1 py-2.5 rounded text-sm font-medium bg-green-600/20 text-green-400 border border-green-600/30 hover:bg-green-600/30"
          >
            Check
          </button>
        )}
        {store.canCall && (
          <button
            onClick={() => onAction('call', store.toCall)}
            className="flex-1 py-2.5 rounded text-sm font-medium bg-blue-600/20 text-blue-400 border border-blue-600/30 hover:bg-blue-600/30"
          >
            Call {store.toCall}
          </button>
        )}
        {store.canBet && (
          <button
            onClick={() => onAction('bet', betAmount)}
            className="flex-1 py-2.5 rounded text-sm font-medium bg-yellow-600/20 text-yellow-400 border border-yellow-600/30 hover:bg-yellow-600/30"
          >
            Bet {betAmount}
          </button>
        )}
        {store.canRaise && (
          <button
            onClick={() => onAction('raise', betAmount)}
            className="flex-1 py-2.5 rounded text-sm font-medium bg-yellow-600/20 text-yellow-400 border border-yellow-600/30 hover:bg-yellow-600/30"
          >
            Raise to {betAmount}
          </button>
        )}
      </div>
    </div>
  );
}
