import { memo, useState, useCallback } from 'react';
import { fetchNearestFlop } from '../../lib/cfr-api';

interface WelcomeScreenProps {
  selectedConfig: string;
  onSelectBoard: (boardId: number) => void;
}

export const WelcomeScreen = memo(function WelcomeScreen({
  selectedConfig,
  onSelectBoard,
}: WelcomeScreenProps) {
  const [searchInput, setSearchInput] = useState('');
  const [searchResult, setSearchResult] = useState('');

  const handleSearch = useCallback(async () => {
    if (!searchInput.trim() || !selectedConfig) {
      setSearchResult('Enter 3 cards, e.g. "As,Kh,7d"');
      return;
    }

    const cards = searchInput.replace(/[\s]+/g, ',').trim();
    setSearchResult('Searching...');

    try {
      const result = await fetchNearestFlop(selectedConfig, cards);
      if (result.distance === 0) {
        setSearchResult(`Exact match: ${result.flopLabel}`);
      } else {
        setSearchResult(`Nearest: ${result.flopLabel} (distance: ${result.distance})`);
      }
      onSelectBoard(result.boardId);
    } catch {
      setSearchResult('Failed to search. Use format: As,Kh,7d');
    }
  }, [searchInput, selectedConfig, onSelectBoard]);

  return (
    <div className="flex flex-col items-center justify-center text-center max-w-[500px]">
      <div className="text-5xl opacity-50 mb-4">♠</div>
      <h2 className="text-xl font-semibold text-white mb-2">Select a Board</h2>
      <p className="text-sm text-slate-500 max-w-[400px] leading-relaxed">
        Pick a flop from the sidebar, or type specific cards below to find the nearest solved board.
      </p>

      {selectedConfig && (
        <div className="mt-5 w-full max-w-[400px] text-left">
          <div className="text-sm font-semibold text-slate-400 mb-1.5">Quick Lookup</div>
          <div className="flex gap-2">
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="e.g. As,Kh,7d"
              className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50"
            />
            <button
              onClick={handleSearch}
              className="px-4 py-2 bg-blue-500 rounded-lg text-sm font-semibold text-white hover:bg-blue-600 transition-colors"
            >
              Find
            </button>
          </div>
          {searchResult && <div className="mt-2 text-sm text-slate-400">{searchResult}</div>}
        </div>
      )}

      <div className="mt-6 bg-[var(--cp-bg-surface)] border border-white/10 rounded-xl p-5 text-left max-w-[460px]">
        <div className="text-sm font-semibold text-white mb-2">Quick Guide</div>
        <ul className="text-[13px] text-slate-400 leading-7 pl-4 list-disc space-y-0.5">
          <li>
            <b className="text-slate-300">Position</b> — OOP = Big Blind (acts first); IP = Button
            (acts last)
          </li>
          <li>
            <b className="text-slate-300">Street</b> — Flop (3 cards), Turn (4th), River (5th)
          </li>
          <li>
            <b className="text-slate-300">Matrix</b> — Each cell shows GTO action mix for that hand
          </li>
          <li>
            <b className="text-slate-300">Colors</b> — Green = check, Yellow = bet, Purple = raise,
            Gray = fold
          </li>
        </ul>
      </div>
    </div>
  );
});
