import { useSolveSession } from '../../stores/solve-session';
import { ConvergenceChart } from './ConvergenceChart';

interface SolveProgressPanelProps {
  onCancel: () => void;
}

function formatETA(seconds: number): string {
  if (seconds <= 0 || !isFinite(seconds)) return '--:--';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function formatSpeed(speed: number): string {
  if (speed <= 0 || !isFinite(speed)) return '---';
  if (speed >= 1000) return `${(speed / 1000).toFixed(1)}k`;
  return speed.toFixed(1);
}

export function SolveProgressPanel({ onCancel }: SolveProgressPanelProps) {
  const { status, progress, convergenceHistory } = useSolveSession();

  const pctDone =
    progress.totalIterations > 0 ? (progress.currentIteration / progress.totalIterations) * 100 : 0;

  const elapsedSec = progress.elapsed / 1000;
  const elapsedMin = elapsedSec / 60;

  const isSolving = status === 'solving';

  return (
    <div className="space-y-6">
      {/* Status Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {isSolving && (
            <div className="relative flex h-3 w-3">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75" />
              <span className="relative inline-flex h-3 w-3 rounded-full bg-blue-500" />
            </div>
          )}
          <div>
            <h3 className="text-lg font-semibold">
              {status === 'solving'
                ? 'Solving...'
                : status === 'complete'
                  ? 'Complete'
                  : status === 'error'
                    ? 'Error'
                    : status === 'cancelled'
                      ? 'Cancelled'
                      : 'Idle'}
            </h3>
            <p className="text-sm text-muted-foreground">
              {progress.completedFlops} / {progress.totalFlops || '?'} flops
            </p>
          </div>
        </div>
        {isSolving && (
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-md bg-destructive text-destructive-foreground text-sm font-medium hover:opacity-90 transition-opacity"
          >
            Cancel
          </button>
        )}
      </div>

      {/* Progress Bar Section */}
      <div className="space-y-2">
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>
            {progress.currentIteration.toLocaleString()} /{' '}
            {progress.totalIterations.toLocaleString()} iterations
          </span>
          <span className="font-mono">{pctDone.toFixed(1)}%</span>
        </div>
        <div className="h-4 bg-secondary rounded-full overflow-hidden relative">
          <div
            className="h-full rounded-full transition-all duration-500 ease-out bg-gradient-to-r from-blue-600 to-blue-400"
            style={{ width: `${pctDone}%` }}
          />
          {isSolving && pctDone > 0 && pctDone < 100 && (
            <div
              className="absolute top-0 h-full w-8 rounded-full bg-white/20 animate-pulse"
              style={{ left: `calc(${pctDone}% - 2rem)` }}
            />
          )}
        </div>
      </div>

      {/* Speed & ETA Highlight Bar */}
      {(isSolving || status === 'complete') && (
        <div className="flex gap-4">
          <div className="flex-1 bg-card border border-border rounded-lg p-3 flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-blue-500/10 text-blue-500">
              <svg
                className="h-5 w-5"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z"
                />
              </svg>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Speed</div>
              <div className="text-lg font-mono font-semibold">
                {formatSpeed(progress.speed)}{' '}
                <span className="text-xs text-muted-foreground font-normal">it/s</span>
              </div>
            </div>
          </div>
          <div className="flex-1 bg-card border border-border rounded-lg p-3 flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-500">
              <svg
                className="h-5 w-5"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">ETA</div>
              <div className="text-lg font-mono font-semibold">
                {status === 'complete' ? 'Done' : formatETA(progress.eta)}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Iterations" value={progress.currentIteration.toLocaleString()} />
        <StatCard label="Info Sets" value={progress.infoSets.toLocaleString()} />
        <StatCard label="Memory" value={`${progress.memoryMB.toFixed(0)} MB`} />
        <StatCard
          label="Elapsed"
          value={elapsedMin > 1 ? `${elapsedMin.toFixed(1)} min` : `${elapsedSec.toFixed(0)} sec`}
        />
        <StatCard
          label="Exploitability"
          value={progress.exploitability < Infinity ? progress.exploitability.toFixed(4) : '---'}
        />
        <StatCard
          label="Flops Done"
          value={`${progress.completedFlops} / ${progress.totalFlops || '?'}`}
        />
      </div>

      {/* Convergence Chart */}
      {convergenceHistory.length > 1 && (
        <div className="bg-card border border-border rounded-lg p-4">
          <h4 className="text-sm font-medium mb-3">Exploitability Convergence</h4>
          <ConvergenceChart data={convergenceHistory} />
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-card border border-border rounded-lg p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-sm font-mono font-medium mt-1">{value}</div>
    </div>
  );
}
