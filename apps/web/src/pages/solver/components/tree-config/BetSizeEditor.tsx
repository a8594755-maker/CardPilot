interface BetSizeEditorProps {
  betSizes: { flop: number[]; turn: number[]; river: number[] };
  onChange: (sizes: { flop: number[]; turn: number[]; river: number[] }) => void;
}

const COMMON_SIZES = [0.25, 0.33, 0.5, 0.66, 0.75, 1.0, 1.5, 2.0];

export function BetSizeEditor({ betSizes, onChange }: BetSizeEditorProps) {
  const streets: Array<'flop' | 'turn' | 'river'> = ['flop', 'turn', 'river'];

  const toggleSize = (street: 'flop' | 'turn' | 'river', size: number) => {
    const current = betSizes[street];
    const newSizes = current.includes(size)
      ? current.filter((s) => s !== size)
      : [...current, size].sort((a, b) => a - b);
    onChange({ ...betSizes, [street]: newSizes });
  };

  return (
    <div className="space-y-4">
      <h4 className="text-sm font-medium">Bet Sizes (% of pot)</h4>
      {streets.map((street) => (
        <div key={street} className="space-y-2">
          <div className="text-xs text-muted-foreground capitalize">{street}</div>
          <div className="flex gap-1.5 flex-wrap">
            {COMMON_SIZES.map((size) => {
              const active = betSizes[street].includes(size);
              return (
                <button
                  key={size}
                  onClick={() => toggleSize(street, size)}
                  className={`px-2 py-1 rounded text-xs font-mono transition-colors ${
                    active
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-secondary text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {(size * 100).toFixed(0)}%
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
