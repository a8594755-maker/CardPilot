import { useEffect, useCallback } from 'react';
import {
  getSocket,
  type SolveProgress,
  type SolveComplete,
  type SolveError,
} from '../lib/solver-ws-client';
import { useSolveSession } from '../stores/solve-session';
import { useWorkspace } from '../stores/workspace';

export function useSolverSocket(jobId: string | null) {
  const { updateProgress, setStatus, setError, addConvergencePoint } = useSolveSession();

  useEffect(() => {
    if (!jobId) return;

    const socket = getSocket();

    socket.emit('solve:subscribe', { jobId });

    const onProgress = (data: SolveProgress) => {
      if (data.jobId !== jobId) return;
      updateProgress(data);
      if (data.exploitability < Infinity) {
        addConvergencePoint(data.currentIteration, data.exploitability);
      }
    };

    const onComplete = (data: SolveComplete) => {
      if (data.jobId !== jobId) return;
      setStatus('complete');
      // Auto-switch to analyze mode with solver results
      useWorkspace.getState().setDataSource('solver');
      useWorkspace.getState().setMode('analyze');
    };

    const onError = (data: SolveError) => {
      if (data.jobId !== jobId) return;
      setError(data.error || 'Solver failed');
    };

    socket.on('solve:progress', onProgress);
    socket.on('solve:complete', onComplete);
    socket.on('solve:error', onError);

    // Polling fallback: check job status periodically in case socket events are lost
    const pollInterval = setInterval(async () => {
      try {
        const res = await fetch(`/api/gto/solve/${jobId}`);
        if (!res.ok) return;
        const job = await res.json();
        if (job.status === 'complete') {
          setStatus('complete');
          useWorkspace.getState().setDataSource('solver');
          useWorkspace.getState().setMode('analyze');
        } else if (job.status === 'error') {
          setError(job.error || 'Solver failed');
        }
        // Update progress from polling too
        if (job.progress && job.status === 'running') {
          updateProgress(job.progress);
        }
      } catch {
        // Polling failure is non-critical
      }
    }, 3000);

    return () => {
      clearInterval(pollInterval);
      socket.off('solve:progress', onProgress);
      socket.off('solve:complete', onComplete);
      socket.off('solve:error', onError);
      socket.emit('solve:unsubscribe', { jobId });
    };
  }, [jobId, updateProgress, setStatus, setError, addConvergencePoint]);

  const cancel = useCallback(() => {
    if (!jobId) return;
    getSocket().emit('solve:cancel', { jobId });
    setStatus('cancelled');
  }, [jobId, setStatus]);

  return { cancel };
}
