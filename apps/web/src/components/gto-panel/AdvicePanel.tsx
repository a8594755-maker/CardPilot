import { useMemo } from 'react';
import type { AdvicePayload } from '@cardpilot/shared-types';

interface AdvicePanelProps {
  advice: AdvicePayload | null;
  onActionSelect?: (action: 'fold' | 'call' | 'raise') => void;
  actualAction?: string | null;
}

export function AdvicePanel({ advice, onActionSelect, actualAction }: AdvicePanelProps) {
  const deviation = useMemo(() => {
    if (!advice || !actualAction) return null;

    const actionMap: Record<string, keyof typeof advice.mix> = {
      fold: 'fold',
      call: 'call',
      raise: 'raise',
      all_in: 'raise',
    };

    const gtoProb = advice.mix[actionMap[actualAction]] || 0;
    return 1 - gtoProb;
  }, [advice, actualAction]);

  if (!advice) {
    return (
      <div className="bg-slate-900 text-white p-4 rounded-lg w-80">
        <h3 className="text-lg font-bold text-slate-400">GTO Coach</h3>
        <p className="text-sm text-slate-500 mt-2">Waiting for your turn to show advice...</p>
      </div>
    );
  }

  const { mix, explanation, spotKey, heroHand, tags } = advice;

  return (
    <div className="bg-slate-900 text-white p-4 rounded-lg w-80 shadow-xl">
      {/* Header */}
      <div className="mb-4 border-b border-slate-700 pb-3">
        <h3 className="text-lg font-bold text-yellow-400">GTO Coach</h3>
        <div className="text-xs text-slate-400 mt-1">{spotKey}</div>
        <div className="text-sm font-mono text-cyan-400 mt-1">{heroHand}</div>
      </div>

      {/* Strategy Bars */}
      <div className="space-y-3 mb-4">
        <StrategyBar
          action="raise"
          percentage={mix.raise}
          color="bg-red-500"
          onClick={() => onActionSelect?.('raise')}
        />
        <StrategyBar
          action="call"
          percentage={mix.call}
          color="bg-blue-500"
          onClick={() => onActionSelect?.('call')}
        />
        <StrategyBar
          action="fold"
          percentage={mix.fold}
          color="bg-gray-500"
          onClick={() => onActionSelect?.('fold')}
        />
      </div>

      {/* Tags + Explanation */}
      <div className="bg-slate-800 p-3 rounded mb-3">
        {tags && tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-2">
            {tags.map((tag: string) => (
              <span key={tag} className="text-[10px] bg-blue-900 text-blue-200 px-2 py-0.5 rounded">
                {tag}
              </span>
            ))}
          </div>
        )}
        <p className="text-sm leading-relaxed text-slate-200">{explanation}</p>
      </div>

      {/* Deviation Warning */}
      {deviation !== null && deviation > 0.3 && (
        <div className="bg-red-900/50 border border-red-700 p-3 rounded">
          <div className="flex items-center gap-2 text-red-400">
            <span>⚠️</span>
            <span className="text-sm font-medium">
              GTO Deviation: {Math.round(deviation * 100)}%
            </span>
          </div>
          <p className="text-xs text-red-300 mt-1">
            This action differs significantly from GTO strategy. Consider reviewing this spot.
          </p>
        </div>
      )}

      {/* Quick Actions */}
      {onActionSelect && (
        <div className="grid grid-cols-3 gap-2 mt-4">
          <button
            onClick={() => onActionSelect('fold')}
            className="py-2 px-3 bg-gray-600 hover:bg-gray-500 rounded text-sm font-medium transition"
          >
            Fold
          </button>
          <button
            onClick={() => onActionSelect('call')}
            className="py-2 px-3 bg-blue-600 hover:bg-blue-500 rounded text-sm font-medium transition"
          >
            Call
          </button>
          <button
            onClick={() => onActionSelect('raise')}
            className="py-2 px-3 bg-red-600 hover:bg-red-500 rounded text-sm font-medium transition"
          >
            Raise
          </button>
        </div>
      )}
    </div>
  );
}

interface StrategyBarProps {
  action: string;
  percentage: number;
  color: string;
  onClick?: () => void;
}

function StrategyBar({ action, percentage, color, onClick }: StrategyBarProps) {
  const percentageRounded = Math.round(percentage * 100);

  return (
    <div className="flex items-center gap-2 cursor-pointer group" onClick={onClick}>
      <span className="w-14 text-xs uppercase font-medium text-slate-300">{action}</span>
      <div className="flex-1 bg-slate-700 h-6 rounded overflow-hidden relative">
        <div
          className={`h-full ${color} transition-all duration-300 group-hover:opacity-80`}
          style={{ width: `${percentageRounded}%` }}
        />
        {percentageRounded > 0 && (
          <span className="absolute inset-0 flex items-center justify-center text-xs font-bold text-white drop-shadow">
            {percentageRounded}%
          </span>
        )}
      </div>
    </div>
  );
}

export default AdvicePanel;
