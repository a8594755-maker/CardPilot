import { useParams } from 'react-router-dom';
import { SolveProgressPanel } from './components/solve/SolveProgressPanel';
import { useSolverSocket } from './hooks/useSolverSocket';
import { useSolveSession } from './stores/solve-session';

import '../../solver-tokens.css';

export default function SolverSolveProgress() {
  const { jobId } = useParams<{ jobId: string }>();
  const { status } = useSolveSession();
  const { cancel } = useSolverSocket(jobId || null);

  if (!jobId) {
    return (
      <div className="solver-page flex items-center justify-center h-screen">
        <p className="text-[hsl(var(--solver-muted-foreground))]">No job ID specified</p>
      </div>
    );
  }

  return (
    <div className="solver-page min-h-screen p-8">
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-[hsl(var(--solver-foreground))]">
            Solve Progress
          </h1>
          <p className="text-sm text-[hsl(var(--solver-muted-foreground))] mt-1 font-mono">
            {jobId}
          </p>
        </div>
        <SolveProgressPanel onCancel={cancel} />
        {status === 'complete' && (
          <a
            href={`/solver?job=${jobId}`}
            className="block text-center py-3 rounded-lg bg-[hsl(var(--solver-primary))] text-white font-semibold hover:opacity-90 transition-opacity text-sm"
          >
            View Results
          </a>
        )}
      </div>
    </div>
  );
}
