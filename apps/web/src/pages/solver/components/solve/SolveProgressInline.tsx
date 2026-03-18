import { useSolveSession } from '../../stores/solve-session';
import { getSocket } from '../../lib/solver-ws-client';

function formatETA(seconds: number): string {
  if (seconds <= 0 || !isFinite(seconds)) return '--:--';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

/**
 * Compact inline progress bar for the sidebar solve button area.
 * Shows iteration progress, speed, ETA, and a cancel button.
 */
export function SolveProgressInline() {
  const { status, progress } = useSolveSession();

  if (status !== 'solving') return null;

  const pct =
    progress.totalIterations > 0 ? (progress.currentIteration / progress.totalIterations) * 100 : 0;

  const handleCancel = () => {
    const jobId = useSolveSession.getState().jobId;
    if (!jobId) return;
    getSocket().emit('solve:cancel', { jobId });
    useSolveSession.getState().setStatus('cancelled');
  };

  return (
    <div className="space-y-1.5">
      {/* Progress bar with percentage */}
      <div className="relative h-7 bg-secondary rounded overflow-hidden">
        <div
          className="absolute inset-y-0 left-0 bg-gradient-to-r from-blue-600 to-blue-400 transition-all duration-500 ease-out"
          style={{ width: `${pct}%` }}
        />
        {/* Shimmer effect */}
        {pct > 0 && pct < 100 && (
          <div
            className="absolute inset-y-0 w-12 bg-gradient-to-r from-transparent via-white/15 to-transparent animate-[shimmer_1.5s_infinite]"
            style={{ left: `${Math.max(0, pct - 8)}%` }}
          />
        )}
        {/* Text overlay */}
        <div className="absolute inset-0 flex items-center justify-center text-[11px] font-medium text-white drop-shadow-sm">
          Solving... {pct.toFixed(0)}%
        </div>
      </div>

      {/* Stats row */}
      <div className="flex items-center justify-between text-[10px] text-muted-foreground">
        <span className="font-mono">
          {progress.currentIteration.toLocaleString()} / {progress.totalIterations.toLocaleString()}
        </span>
        <span className="flex items-center gap-2">
          {progress.speed > 0 && (
            <span className="font-mono">
              {progress.speed >= 1000
                ? `${(progress.speed / 1000).toFixed(1)}k`
                : progress.speed.toFixed(0)}{' '}
              it/s
            </span>
          )}
          {progress.eta > 0 && <span className="font-mono">ETA {formatETA(progress.eta)}</span>}
        </span>
      </div>

      {/* Cancel button */}
      <button
        onClick={handleCancel}
        className="w-full py-1 rounded border border-destructive/40 text-destructive text-[11px] hover:bg-destructive/10 transition-colors"
      >
        Cancel
      </button>
    </div>
  );
}
