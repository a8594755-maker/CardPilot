import { useMemo } from 'react';
import { useRangeVsRange } from '../../stores/range-vs-range';

const HAND_CLASSES = generateHandClasses();

interface RangeMatrixProps {
  selected: Set<string>;
  onToggle: (hand: string) => void;
  label: string;
  color: string;
  otherRange?: Set<string>;
}

function MiniRangeMatrix({ selected, onToggle, label, color, otherRange }: RangeMatrixProps) {
  return (
    <div>
      <h3 className="text-sm font-semibold mb-2">{label}</h3>
      <div className="grid gap-px" style={{ gridTemplateColumns: 'repeat(13, 1fr)' }}>
        {HAND_CLASSES.map((hand) => {
          const isSelected = selected.has(hand);
          const isOverlap = otherRange?.has(hand);
          return (
            <button
              key={hand}
              onClick={() => onToggle(hand)}
              className={`w-full aspect-square text-[8px] font-mono flex items-center justify-center rounded-sm border ${
                isSelected
                  ? isOverlap
                    ? 'border-yellow-400/50 text-white'
                    : 'border-transparent text-white'
                  : 'border-border/30 text-muted-foreground hover:bg-secondary/50'
              }`}
              style={{
                backgroundColor: isSelected ? (isOverlap ? '#854d0e' : color) : 'transparent',
                opacity: isSelected ? 0.9 : 0.4,
              }}
            >
              {hand}
            </button>
          );
        })}
      </div>
      <div className="text-xs text-muted-foreground mt-1">
        {selected.size} hands / {countCombos(selected)} combos
      </div>
    </div>
  );
}

export function RangeVsRangeLayout() {
  const store = useRangeVsRange();

  return (
    <div className="flex gap-6">
      <div className="flex-1">
        <MiniRangeMatrix
          selected={store.range1}
          onToggle={(h) => store.toggleRange1Hand(h)}
          label="Range 1 (OOP)"
          color="#3b82f6"
          otherRange={store.range2}
        />
      </div>
      <div className="flex-1">
        <MiniRangeMatrix
          selected={store.range2}
          onToggle={(h) => store.toggleRange2Hand(h)}
          label="Range 2 (IP)"
          color="#ef4444"
          otherRange={store.range1}
        />
      </div>
    </div>
  );
}

export function StatComparison() {
  const { result } = useRangeVsRange();

  if (!result) return null;

  const allCategories = useMemo(() => {
    const cats = new Set<string>();
    result.categories1.forEach((c) => cats.add(c.category));
    result.categories2.forEach((c) => cats.add(c.category));
    return [...cats];
  }, [result]);

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold">Category Comparison</h3>

      {allCategories.map((cat) => {
        const c1 = result.categories1.find((c) => c.category === cat);
        const c2 = result.categories2.find((c) => c.category === cat);
        const pct1 = c1?.percentage || 0;
        const pct2 = c2?.percentage || 0;

        return (
          <div key={cat} className="space-y-1">
            <div className="flex justify-between text-xs">
              <span>{cat}</span>
              <span className="text-muted-foreground">
                {pct1.toFixed(0)}% vs {pct2.toFixed(0)}%
              </span>
            </div>
            <div className="flex h-3 rounded overflow-hidden bg-secondary/30">
              <div className="h-full bg-blue-500/70" style={{ width: `${pct1}%` }} />
              <div
                className="h-full bg-secondary/50"
                style={{ width: `${Math.abs(pct1 - pct2)}%` }}
              />
              <div className="h-full bg-red-500/70" style={{ width: `${pct2}%` }} />
            </div>
          </div>
        );
      })}

      {result.overlap > 0 && (
        <div className="text-xs text-muted-foreground border-t border-border pt-2">
          Overlap: {result.overlap} hands ({result.overlapHands.slice(0, 10).join(', ')}
          {result.overlapHands.length > 10 ? '...' : ''})
        </div>
      )}
    </div>
  );
}

function generateHandClasses(): string[] {
  const ranks = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2'];
  const hands: string[] = [];
  for (let i = 0; i < 13; i++) {
    for (let j = 0; j < 13; j++) {
      if (i === j) hands.push(`${ranks[i]}${ranks[j]}`);
      else if (i < j) hands.push(`${ranks[i]}${ranks[j]}s`);
      else hands.push(`${ranks[j]}${ranks[i]}o`);
    }
  }
  return hands;
}

function countCombos(hands: Set<string>): number {
  let total = 0;
  for (const h of hands) {
    if (h.length === 2) total += 6;
    else if (h.endsWith('s')) total += 4;
    else total += 12;
  }
  return total;
}
