import { useRangeEditor } from '../../stores/range-editor';
import type { SuitFilter } from '../../stores/range-editor';

/**
 * Suit selector - 4 suit buttons to filter combos by suit.
 */

const SUITS: Array<{ key: SuitFilter; symbol: string; color: string }> = [
  { key: 'spade', symbol: '\u2660', color: 'text-foreground' },
  { key: 'heart', symbol: '\u2665', color: 'text-red-500' },
  { key: 'diamond', symbol: '\u2666', color: 'text-blue-400' },
  { key: 'club', symbol: '\u2663', color: 'text-green-500' },
];

export function SuitSelector() {
  const { selectedSuits, toggleSuitFilter } = useRangeEditor();

  return (
    <div className="space-y-1">
      <label className="text-xs text-muted-foreground">Suit Filter</label>
      <div className="flex gap-1">
        {SUITS.map((s) => {
          const active = selectedSuits.includes(s.key);
          return (
            <button
              key={s.key}
              onClick={() => toggleSuitFilter(s.key)}
              className={`w-8 h-8 flex items-center justify-center rounded border text-lg ${
                active
                  ? `border-primary bg-primary/10 ${s.color}`
                  : 'border-border text-muted-foreground hover:border-muted-foreground'
              }`}
            >
              {s.symbol}
            </button>
          );
        })}
        <button
          onClick={() => {
            // Toggle all suits
            if (selectedSuits.length === 4) {
              for (const s of SUITS) toggleSuitFilter(s.key);
            } else {
              for (const s of SUITS) {
                if (!selectedSuits.includes(s.key)) toggleSuitFilter(s.key);
              }
            }
          }}
          className="px-2 h-8 flex items-center justify-center rounded border border-border text-xs text-muted-foreground hover:text-foreground"
        >
          {selectedSuits.length === 4 ? 'None' : 'All'}
        </button>
      </div>
    </div>
  );
}
