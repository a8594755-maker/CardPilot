interface StackConfigPanelProps {
  startingPot: number;
  effectiveStack: number;
  numPlayers: number;
  onChange: (
    changes: Partial<{ startingPot: number; effectiveStack: number; numPlayers: number }>,
  ) => void;
}

export function StackConfigPanel({
  startingPot,
  effectiveStack,
  numPlayers,
  onChange,
}: StackConfigPanelProps) {
  return (
    <div className="space-y-4">
      <h4 className="text-sm font-medium">Stack & Pot Configuration</h4>
      <div className="grid grid-cols-3 gap-4">
        <div className="space-y-2">
          <label className="text-xs text-muted-foreground">Starting Pot (bb)</label>
          <input
            type="number"
            value={startingPot}
            onChange={(e) => onChange({ startingPot: Number(e.target.value) })}
            min={1}
            step={0.5}
            className="w-full px-3 py-2 rounded-md bg-secondary border border-border text-sm font-mono"
          />
        </div>
        <div className="space-y-2">
          <label className="text-xs text-muted-foreground">Effective Stack (bb)</label>
          <input
            type="number"
            value={effectiveStack}
            onChange={(e) => onChange({ effectiveStack: Number(e.target.value) })}
            min={1}
            step={0.5}
            className="w-full px-3 py-2 rounded-md bg-secondary border border-border text-sm font-mono"
          />
        </div>
        <div className="space-y-2">
          <label className="text-xs text-muted-foreground">Players</label>
          <select
            value={numPlayers}
            onChange={(e) => onChange({ numPlayers: Number(e.target.value) })}
            className="w-full px-3 py-2 rounded-md bg-secondary border border-border text-sm"
          >
            <option value={2}>2 (Heads-Up)</option>
            <option value={3}>3 (3-Way)</option>
          </select>
        </div>
      </div>
    </div>
  );
}
