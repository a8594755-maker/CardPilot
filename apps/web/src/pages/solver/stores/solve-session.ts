import { create } from 'zustand';

interface SolveProgress {
  completedFlops: number;
  totalFlops: number;
  currentIteration: number;
  totalIterations: number;
  infoSets: number;
  memoryMB: number;
  elapsed: number;
  exploitability: number;
  speed: number; // iterations per second
  eta: number; // estimated remaining seconds
}

interface SolveSessionStore {
  jobId: string | null;
  status: 'idle' | 'solving' | 'complete' | 'error' | 'cancelled';
  progress: SolveProgress;
  error: string | null;
  convergenceHistory: Array<{ iteration: number; exploitability: number }>;
  setJobId: (id: string) => void;
  setStatus: (status: SolveSessionStore['status']) => void;
  setError: (error: string) => void;
  updateProgress: (p: Partial<SolveProgress>) => void;
  addConvergencePoint: (iteration: number, exploitability: number) => void;
  reset: () => void;
}

const initialProgress: SolveProgress = {
  completedFlops: 0,
  totalFlops: 0,
  currentIteration: 0,
  totalIterations: 0,
  infoSets: 0,
  memoryMB: 0,
  elapsed: 0,
  exploitability: Infinity,
  speed: 0,
  eta: 0,
};

export const useSolveSession = create<SolveSessionStore>((set) => ({
  jobId: null,
  status: 'idle',
  progress: initialProgress,
  error: null,
  convergenceHistory: [],
  setJobId: (jobId) => set({ jobId, status: 'solving', error: null, convergenceHistory: [] }),
  setStatus: (status) => set({ status }),
  setError: (error) => set({ status: 'error', error }),
  updateProgress: (p) => set((s) => ({ progress: { ...s.progress, ...p } })),
  addConvergencePoint: (iteration, exploitability) =>
    set((s) => ({
      convergenceHistory: [...s.convergenceHistory, { iteration, exploitability }],
    })),
  reset: () =>
    set({
      jobId: null,
      status: 'idle',
      progress: initialProgress,
      error: null,
      convergenceHistory: [],
    }),
}));
