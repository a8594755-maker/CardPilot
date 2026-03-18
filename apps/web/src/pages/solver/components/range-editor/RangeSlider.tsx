import { useRangeEditor } from '../../stores/range-editor';

/**
 * Dual range slider for selecting/removing top X% of hands.
 * Green slider selects, red slider removes from current selection.
 */

export function RangeSlider() {
  const { topXPercent, selectTopXPercent, removeTopXPercent, selectedHands } = useRangeEditor();

  const totalCombos = countSelectedCombos(selectedHands);
  const maxCombos = 1326;
  const currentPct = ((totalCombos / maxCombos) * 100).toFixed(1);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">Top X% Selection</span>
        <span className="font-mono">
          {currentPct}% ({totalCombos} combos)
        </span>
      </div>

      {/* Select slider (green) */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-green-400 w-12">Select</span>
        <input
          type="range"
          min={0}
          max={100}
          step={1}
          value={topXPercent}
          onChange={(e) => selectTopXPercent(Number(e.target.value))}
          className="flex-1 accent-green-500"
        />
        <span className="text-xs font-mono w-10 text-right">{topXPercent}%</span>
      </div>

      {/* Quick select buttons */}
      <div className="flex gap-1">
        {[10, 20, 30, 40, 50, 100].map((pct) => (
          <button
            key={pct}
            onClick={() => selectTopXPercent(pct)}
            className="px-2 py-0.5 text-[10px] bg-secondary border border-border rounded hover:bg-secondary/80"
          >
            {pct}%
          </button>
        ))}
      </div>

      {/* Remove slider (red) */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-red-400 w-12">Remove</span>
        <input
          type="range"
          min={0}
          max={100}
          step={1}
          defaultValue={0}
          onChange={(e) => {
            const val = Number(e.target.value);
            if (val > 0) removeTopXPercent(val);
          }}
          className="flex-1 accent-red-500"
        />
      </div>
    </div>
  );
}

function countSelectedCombos(hands: Set<string>): number {
  let total = 0;
  for (const h of hands) {
    if (h.length === 2)
      total += 6; // pair
    else if (h.endsWith('s'))
      total += 4; // suited
    else total += 12; // offsuit
  }
  return total;
}
