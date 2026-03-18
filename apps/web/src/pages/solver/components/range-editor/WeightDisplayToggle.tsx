import { useRangeEditor } from '../../stores/range-editor';
import type { WeightDisplayMode } from '../../stores/range-editor';

/**
 * Toggle between weight display methods:
 * - Intensity: darker = higher weight (default)
 * - Bar: small bar chart inside each cell
 */

export function WeightDisplayToggle() {
  const { weightDisplayMode, setWeightDisplayMode } = useRangeEditor();

  return (
    <div className="flex items-center gap-2">
      <label className="text-xs text-muted-foreground">Display:</label>
      <div className="flex rounded overflow-hidden border border-border">
        {(['intensity', 'bar'] as WeightDisplayMode[]).map((mode) => (
          <button
            key={mode}
            onClick={() => setWeightDisplayMode(mode)}
            className={`px-3 py-1 text-xs capitalize ${
              weightDisplayMode === mode
                ? 'bg-primary/20 text-primary'
                : 'bg-secondary text-muted-foreground hover:text-foreground'
            }`}
          >
            {mode}
          </button>
        ))}
      </div>
    </div>
  );
}
