#!/usr/bin/env tsx
// HTTP Queue Server for distributed CFR solving across multiple machines.
// Runs on the coordinator machine (Machine B).
//
// Endpoints:
//   GET  /pop              — Claim the next pending job (returns JSON or 204)
//   POST /done             — Mark a job as completed { jobId, infoSets, fileSize, elapsedMs, peakMemoryMB }
//   POST /fail             — Mark a job as failed { jobId, error }
//   GET  /status           — Dashboard: pending/running/done/failed counts + per-worker stats
//   POST /generate         — Generate jobs for a config { config, iterations, buckets }
//   GET  /healthz          — Health check

import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import type { TreeConfigName } from '../tree/tree-config.js';

// ---------- Types ----------

export interface PipelineJob {
  jobId: string;                       // e.g. "pipeline_srp__0042"
  flopCards: [number, number, number];
  boardId: number;
  label: string;                       // human-readable board label
  canonical: string;                   // canonical flop string
  iterations: number;
  bucketCount: number;
  configName: TreeConfigName;
  stackLabel: string;
  outputDir: string;
  chartsPath: string;
}

interface RunningJob {
  job: PipelineJob;
  claimedAt: number;
  claimedBy: string; // worker id from header
}

interface CompletedJob {
  jobId: string;
  boardId: number;
  infoSets: number;
  fileSize: number;
  elapsedMs: number;
  peakMemoryMB: number;
  completedAt: number;
  worker: string;
}

interface FailedJob {
  jobId: string;
  boardId: number;
  error: string;
  failedAt: number;
  worker: string;
  retryCount: number;
}

// ---------- Queue State ----------

const pending: PipelineJob[] = [];
const running = new Map<string, RunningJob>();
const completed: CompletedJob[] = [];
const failed: FailedJob[] = [];
const failCounts = new Map<string, number>(); // jobId → retry count

const MAX_RETRIES = 3;
const STALE_TIMEOUT_MS = 30 * 60 * 1000; // 30 min: if a job runs longer, it's reclaimed

// ---------- Queue Operations ----------

function popJob(workerId: string): PipelineJob | null {
  // First, reclaim stale jobs
  reclaimStale();

  if (pending.length === 0) return null;

  const job = pending.shift()!;
  running.set(job.jobId, {
    job,
    claimedAt: Date.now(),
    claimedBy: workerId,
  });
  return job;
}

function markDone(
  jobId: string,
  info: { infoSets: number; fileSize: number; elapsedMs: number; peakMemoryMB: number },
): boolean {
  const entry = running.get(jobId);
  if (!entry) return false;

  running.delete(jobId);
  completed.push({
    jobId,
    boardId: entry.job.boardId,
    infoSets: info.infoSets,
    fileSize: info.fileSize,
    elapsedMs: info.elapsedMs,
    peakMemoryMB: info.peakMemoryMB,
    completedAt: Date.now(),
    worker: entry.claimedBy,
  });
  return true;
}

function markFailed(jobId: string, error: string): boolean {
  const entry = running.get(jobId);
  if (!entry) return false;

  running.delete(jobId);
  const retryCount = (failCounts.get(jobId) ?? 0) + 1;
  failCounts.set(jobId, retryCount);

  if (retryCount < MAX_RETRIES) {
    // Re-queue at the back
    pending.push(entry.job);
  } else {
    failed.push({
      jobId,
      boardId: entry.job.boardId,
      error,
      failedAt: Date.now(),
      worker: entry.claimedBy,
      retryCount,
    });
  }
  return true;
}

function reclaimStale(): void {
  const now = Date.now();
  for (const [jobId, entry] of running) {
    if (now - entry.claimedAt > STALE_TIMEOUT_MS) {
      console.log(`[RECLAIM] Job ${jobId} stale (claimed ${Math.round((now - entry.claimedAt) / 60000)}min ago by ${entry.claimedBy})`);
      running.delete(jobId);
      pending.unshift(entry.job); // re-queue at front (priority)
    }
  }
}

function getStatus() {
  // Per-worker stats
  const workerStats: Record<string, { running: number; completed: number; totalMs: number }> = {};
  for (const entry of running.values()) {
    const w = entry.claimedBy;
    if (!workerStats[w]) workerStats[w] = { running: 0, completed: 0, totalMs: 0 };
    workerStats[w].running++;
  }
  for (const c of completed) {
    if (!workerStats[c.worker]) workerStats[c.worker] = { running: 0, completed: 0, totalMs: 0 };
    workerStats[c.worker].completed++;
    workerStats[c.worker].totalMs += c.elapsedMs;
  }

  // ETA calculation
  const avgMs = completed.length > 0
    ? completed.reduce((s, c) => s + c.elapsedMs, 0) / completed.length
    : 0;
  const totalWorkers = new Set([...running.values()].map(v => v.claimedBy)).size || 1;
  const remainingJobs = pending.length + running.size;
  const etaMs = avgMs > 0 ? (remainingJobs * avgMs) / totalWorkers : 0;

  return {
    pending: pending.length,
    running: running.size,
    completed: completed.length,
    failed: failed.length,
    total: pending.length + running.size + completed.length + failed.length,
    avgSolveMs: Math.round(avgMs),
    etaMs: Math.round(etaMs),
    etaHuman: etaMs > 0 ? formatDuration(etaMs) : 'N/A',
    activeWorkers: totalWorkers,
    workers: workerStats,
    recentCompleted: completed.slice(-10).reverse(),
  };
}

function formatDuration(ms: number): string {
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

// ---------- Job Generation ----------

export function addJobs(jobs: PipelineJob[]): number {
  // Dedup: don't add jobs that are already pending, running, or completed
  const existingIds = new Set([
    ...pending.map(j => j.jobId),
    ...running.keys(),
    ...completed.map(c => c.jobId),
  ]);

  let added = 0;
  for (const job of jobs) {
    if (!existingIds.has(job.jobId)) {
      pending.push(job);
      existingIds.add(job.jobId);
      added++;
    }
  }
  return added;
}

// ---------- HTTP Server ----------

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on('data', (chunk: Buffer) => chunks.push(chunk));
    req.on('end', () => resolve(Buffer.concat(chunks).toString()));
    req.on('error', reject);
  });
}

function json(res: ServerResponse, status: number, data: unknown): void {
  const body = JSON.stringify(data);
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(body),
  });
  res.end(body);
}

async function handleRequest(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const url = req.url ?? '/';
  const method = req.method ?? 'GET';

  try {
    // GET /pop — claim next job
    if (method === 'GET' && url === '/pop') {
      const workerId = (req.headers['x-worker-id'] as string) || 'unknown';
      const job = popJob(workerId);
      if (job) {
        json(res, 200, job);
      } else {
        res.writeHead(204);
        res.end();
      }
      return;
    }

    // POST /done — mark job complete
    if (method === 'POST' && url === '/done') {
      const body = JSON.parse(await readBody(req));
      const ok = markDone(body.jobId, body);
      json(res, ok ? 200 : 404, { ok });
      return;
    }

    // POST /fail — mark job failed
    if (method === 'POST' && url === '/fail') {
      const body = JSON.parse(await readBody(req));
      const ok = markFailed(body.jobId, body.error || 'unknown');
      json(res, ok ? 200 : 404, { ok });
      return;
    }

    // GET /status — dashboard
    if (method === 'GET' && url === '/status') {
      json(res, 200, getStatus());
      return;
    }

    // GET /healthz — health check
    if (method === 'GET' && url === '/healthz') {
      json(res, 200, { ok: true, uptime: process.uptime() });
      return;
    }

    // 404
    json(res, 404, { error: 'Not found' });
  } catch (err) {
    console.error('[ERROR]', err);
    json(res, 500, { error: String(err) });
  }
}

// ---------- Start Server ----------

export function startQueueServer(port = 3500): ReturnType<typeof createServer> {
  const server = createServer((req, res) => {
    handleRequest(req, res).catch(err => {
      console.error('[FATAL]', err);
      res.writeHead(500);
      res.end();
    });
  });

  server.listen(port, '0.0.0.0', () => {
    console.log(`[Queue Server] Listening on http://0.0.0.0:${port}`);
    console.log(`[Queue Server] Workers should connect to http://<this-ip>:${port}`);
    console.log();
  });

  return server;
}

// Export queue state for the CLI to use
export { pending, running, completed, failed, getStatus };
