import { useSolverConfig } from '../../stores/solver-config';

/**
 * Advanced sizing panel for C-bet/Donk/Probe differentiation
 * and raise multiplier (X-type) input.
 */

export function AdvancedSizingPanel() {
  const store = useSolverConfig();

  return (
    <div className="space-y-4">
      {/* Smooth mode toggle */}
      <div className="flex items-center justify-between">
        <div>
          <label className="text-sm font-medium">Smoothly Mode</label>
          <p className="text-xs text-muted-foreground">
            Interpolate bet sizes for smoother strategy
          </p>
        </div>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={store.smoothMode}
            onChange={(e) => store.setSmoothMode(e.target.checked)}
          />
          <span className="text-xs">{store.smoothMode ? 'On' : 'Off'}</span>
        </label>
      </div>

      {store.smoothMode && (
        <div>
          <label className="text-xs text-muted-foreground">Gradation (bet size count)</label>
          <div className="flex gap-2 mt-1">
            {[5, 10, 15, 20].map((n) => (
              <button
                key={n}
                onClick={() => store.setSmoothGradation(n)}
                className={`px-3 py-1 text-xs rounded border ${
                  store.smoothGradation === n
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border text-muted-foreground'
                }`}
              >
                {n}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* C-bet / Donk / Probe sizing */}
      <div className="border-t border-border pt-4">
        <h3 className="text-sm font-medium mb-2">Context-Specific Sizing</h3>

        <SizingRow
          label="Flop C-bet"
          description="IP bet after preflop raise"
          sizes={store.flopCbet}
          onChange={(sizes) => store.setFlopCbet(sizes)}
        />

        <SizingRow
          label="Flop Donk"
          description="OOP bet into preflop raiser"
          sizes={store.flopDonk}
          onChange={(sizes) => store.setFlopDonk(sizes)}
        />

        <SizingRow
          label="Turn Probe"
          description="Bet after checked-through flop"
          sizes={store.turnProbe}
          onChange={(sizes) => store.setTurnProbe(sizes)}
        />
      </div>

      {/* Raise multipliers */}
      <div className="border-t border-border pt-4">
        <h3 className="text-sm font-medium mb-2">Raise Multipliers (X-type)</h3>
        <p className="text-xs text-muted-foreground mb-2">
          Enter raise sizes as multipliers (e.g. 2x, 3x) instead of pot fractions.
        </p>

        {(['flop', 'turn', 'river'] as const).map((street) => (
          <div key={street} className="flex items-center gap-2 mb-2">
            <span className="w-12 text-xs text-muted-foreground capitalize">{street}</span>
            <MultiplierInput
              values={store.raiseMultipliers[street]}
              onChange={(vals) => store.setRaiseMultipliers({ [street]: vals })}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

function SizingRow({
  label,
  description,
  sizes,
  onChange,
}: {
  label: string;
  description: string;
  sizes: number[];
  onChange: (sizes: number[]) => void;
}) {
  const inputStr = sizes.map((s) => `${Math.round(s * 100)}%`).join(', ');

  function handleChange(value: string) {
    const parsed = value
      .split(',')
      .map((s) => {
        const num = parseFloat(s.trim().replace('%', ''));
        return isNaN(num) ? 0 : num / 100;
      })
      .filter((n) => n > 0);
    onChange(parsed);
  }

  return (
    <div className="flex items-center gap-2 mb-2">
      <div className="w-24">
        <span className="text-xs">{label}</span>
        <p className="text-[10px] text-muted-foreground">{description}</p>
      </div>
      <input
        defaultValue={inputStr}
        onBlur={(e) => handleChange(e.target.value)}
        placeholder="33%, 67%, 100%"
        className="flex-1 px-2 py-1 bg-secondary border border-border rounded text-xs font-mono"
      />
    </div>
  );
}

function MultiplierInput({
  values,
  onChange,
}: {
  values: number[];
  onChange: (vals: number[]) => void;
}) {
  const inputStr = values.map((v) => `${v}x`).join(', ');

  function handleChange(value: string) {
    const parsed = value
      .split(',')
      .map((s) => {
        const num = parseFloat(s.trim().replace('x', ''));
        return isNaN(num) ? 0 : num;
      })
      .filter((n) => n > 0);
    onChange(parsed);
  }

  return (
    <input
      defaultValue={inputStr}
      onBlur={(e) => handleChange(e.target.value)}
      placeholder="2x, 3x"
      className="flex-1 px-2 py-1 bg-secondary border border-border rounded text-xs font-mono"
    />
  );
}
