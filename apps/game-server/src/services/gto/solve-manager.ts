// Manages solver jobs: start, monitor progress, cancel.
// Wraps cfr-solver's orchestration for the API.

import { randomUUID } from 'node:crypto';
import type { Namespace } from 'socket.io';

export interface SolveJobConfig {
  configName: string;
  iterations: number;
  buckets: number;
  board: string[]; // Card strings, e.g. ["Ah", "Kd", "7c"]
  oopRange: string[]; // Hand classes, e.g. ["AA", "AKs", "KQo"]
  ipRange: string[]; // Hand classes
  flops?: number[];
  allFlops?: boolean;
  treeConfig?: {
    startingPot: number;
    effectiveStack: number;
    betSizes: {
      flop: number[];
      turn: number[];
      river: number[];
      flopCbet?: number[];
      flopDonk?: number[];
      turnProbe?: number[];
      raiseMultipliers?: { flop?: number[]; turn?: number[]; river?: number[] };
    };
    raiseCapPerStreet: number;
    numPlayers?: number;
    rake?: { percentage: number; cap: number };
    smoothMode?: boolean;
    smoothGradation?: number;
    advancedConfig?: {
      oop: {
        noDonkBet: boolean;
        allInThresholdEnabled: boolean;
        allInThresholdPct: number;
        remainingBetAllIn: boolean;
        remainingBetPct: number;
      };
      ip: {
        noDonkBet: boolean;
        allInThresholdEnabled: boolean;
        allInThresholdPct: number;
        remainingBetAllIn: boolean;
        remainingBetPct: number;
      };
    };
    limitMode?: boolean;
    limitConfig?: {
      flopBet: number;
      flopCap: number;
      turnBet: number;
      turnCap: number;
      riverBet: number;
      riverCap: number;
    };
  };
}

export interface SolveJob {
  id: string;
  status: 'queued' | 'running' | 'complete' | 'cancelled' | 'error';
  config: SolveJobConfig;
  progress: {
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
  };
  error?: string;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
}

// In-memory job store
const jobs = new Map<string, SolveJob>();
let gtoNs: Namespace | null = null;

// Throttle state per job — prevents flooding WebSocket at 230+ it/s
const throttleState = new Map<string, number>();
const THROTTLE_MS = 500;

export function setGtoNamespace(ns: Namespace) {
  gtoNs = ns;
}

export function createJob(config: SolveJobConfig): SolveJob {
  const job: SolveJob = {
    id: randomUUID(),
    status: 'queued',
    config,
    progress: {
      completedFlops: 0,
      totalFlops: 0,
      currentIteration: 0,
      totalIterations: config.iterations,
      infoSets: 0,
      memoryMB: 0,
      elapsed: 0,
      exploitability: Infinity,
      speed: 0,
      eta: 0,
    },
    createdAt: new Date().toISOString(),
  };
  jobs.set(job.id, job);
  return job;
}

export function getJob(id: string): SolveJob | undefined {
  return jobs.get(id);
}

export function getJobs(): SolveJob[] {
  return [...jobs.values()].sort(
    (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
  );
}

export function cancelJob(id: string): boolean {
  const job = jobs.get(id);
  if (!job || job.status === 'complete' || job.status === 'cancelled') return false;
  job.status = 'cancelled';
  throttleState.delete(id);
  gtoNs?.emit('solve:cancelled', { jobId: id });
  return true;
}

/**
 * Create a throttled onProgress callback for a given job.
 * Emits at most once per THROTTLE_MS, plus always emits the final iteration.
 */
export function createProgressCallback(jobId: string): (iter: number, elapsed: number) => void {
  const job = jobs.get(jobId);
  if (!job) return () => {};

  throttleState.set(jobId, 0);

  return (iter: number, elapsed: number) => {
    const now = Date.now();
    const lastEmit = throttleState.get(jobId) ?? 0;
    const isFinal = iter >= job.progress.totalIterations;

    if (now - lastEmit < THROTTLE_MS && !isFinal) return;

    // Calculate speed and ETA
    const elapsedSec = elapsed / 1000;
    const speed = elapsedSec > 0 ? iter / elapsedSec : 0;
    const remaining = job.progress.totalIterations - iter;
    const eta = speed > 0 ? remaining / speed : 0;

    job.progress.currentIteration = iter;
    job.progress.elapsed = elapsed;
    job.progress.speed = speed;
    job.progress.eta = eta;

    throttleState.set(jobId, now);

    if (gtoNs) {
      gtoNs.emit('solve:progress', {
        jobId,
        ...job.progress,
      });
    }
  };
}

export function updateJobProgress(id: string, progress: Partial<SolveJob['progress']>) {
  const job = jobs.get(id);
  if (!job) return;
  Object.assign(job.progress, progress);

  if (gtoNs) {
    gtoNs.emit('solve:progress', {
      jobId: id,
      ...job.progress,
    });
  }
}

export function completeJob(id: string) {
  const job = jobs.get(id);
  if (!job) return;
  job.status = 'complete';
  job.completedAt = new Date().toISOString();
  throttleState.delete(id);

  if (gtoNs) {
    gtoNs.emit('solve:complete', {
      jobId: id,
      totalFlops: job.progress.completedFlops,
      totalInfoSets: job.progress.infoSets,
      elapsed: job.progress.elapsed,
    });
  }
}

export function failJob(id: string, error: string) {
  const job = jobs.get(id);
  if (!job) return;
  job.status = 'error';
  job.error = error;
  throttleState.delete(id);

  if (gtoNs) {
    gtoNs.emit('solve:error', { jobId: id, error });
  }
}
