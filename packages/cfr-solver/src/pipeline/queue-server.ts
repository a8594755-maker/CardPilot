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
import { appendFileSync, readFileSync, existsSync } from 'node:fs';
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
  iteration: number; // latest reported iteration
  total: number;     // expected total iterations
  lastProgressAt: number;
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

// Persistent completion logs — survives coordinator restarts
// Supports multiple configs: each config has its own completed.jsonl in its output dir
let completedLogPath: string | null = null;
const completedLogPaths = new Map<string, string>(); // configName → log path

export function setCompletedLogPath(path: string): void {
  completedLogPath = path;
  restoreCompletedLog(path);
}

/** Register a per-config completion log path. */
export function addCompletedLogPath(configName: string, path: string): void {
  completedLogPaths.set(configName, path);
  restoreCompletedLog(path);
}

function restoreCompletedLog(path: string): void {
  if (!existsSync(path)) return;
  try {
    const lines = readFileSync(path, 'utf-8').split('\n').filter(l => l.trim());
    const existingIds = new Set(completed.map(c => c.jobId));
    let restored = 0;
    let corrupt = 0;
    for (const line of lines) {
      try {
        const record = JSON.parse(line);
        const jobId = record.jobId ?? '';
        if (existingIds.has(jobId)) continue;
        completed.push({
          jobId,
          boardId: record.boardId ?? 0,
          infoSets: record.infoSets ?? 0,
          fileSize: record.fileSize ?? 0,
          elapsedMs: record.elapsedMs ?? 0,
          peakMemoryMB: record.peakMemoryMB ?? 0,
          completedAt: record.completedAt ?? 0,
          worker: record.worker ?? 'unknown',
        });
        existingIds.add(jobId);
        restored++;
      } catch {
        corrupt++; // Partial write from crash — skip this line
      }
    }
    if (restored > 0 || corrupt > 0) {
      console.log(`[Queue Server] Restored ${restored} completed records from ${path}${corrupt > 0 ? ` (${corrupt} corrupt lines skipped)` : ''}`);
    }
  } catch (err) {
    console.error(`[Queue Server] Warning: failed to restore completed log:`, err);
  }
}

/** Read completed.jsonl and return set of boardIds already done. */
export function loadCompletedLog(path: string): Set<number> {
  const ids = new Set<number>();
  if (!existsSync(path)) return ids;
  try {
    const lines = readFileSync(path, 'utf-8').split('\n').filter(l => l.trim());
    for (const line of lines) {
      try {
        const record = JSON.parse(line);
        if (typeof record.boardId === 'number') ids.add(record.boardId);
      } catch {
        // Corrupt line from crash — skip
      }
    }
  } catch (err) {
    console.error(`[Queue Server] Warning: failed to read ${path}:`, err);
  }
  return ids;
}

function appendCompletedLog(entry: CompletedJob): void {
  const line = JSON.stringify({
    jobId: entry.jobId,
    boardId: entry.boardId,
    worker: entry.worker,
    infoSets: entry.infoSets,
    fileSize: entry.fileSize,
    peakMemoryMB: entry.peakMemoryMB,
    elapsedMs: entry.elapsedMs,
    completedAt: entry.completedAt,
  }) + '\n';

  // Determine which log to write to: per-config log has priority
  const configName = entry.jobId.split('__')[0]; // e.g. "hu_btn_bb_srp_100bb__0042" → "hu_btn_bb_srp_100bb"
  const logPath = completedLogPaths.get(configName) ?? completedLogPath;
  if (!logPath) return;

  try {
    appendFileSync(logPath, line);
  } catch (err) {
    console.error(`[Queue Server] Warning: failed to append to completion log:`, err);
  }
}

const MAX_RETRIES = 3;
// Heartbeat-based stale detection: network-worker sends parent-level heartbeats every
// 30s (child process IPC is still buffered, but parent event loop is free).
// If no heartbeat arrives within STALE_TIMEOUT_MS, the job is considered stale.
const STALE_TIMEOUT_MS = 5 * 60 * 1000; // 5 min: generous vs 30s heartbeat interval

// ---------- Queue Operations ----------

function popJob(workerId: string): PipelineJob | null {
  // First, reclaim stale jobs
  reclaimStale();

  if (pending.length === 0) return null;

  const job = pending.shift()!;
  const now = Date.now();
  running.set(job.jobId, {
    job,
    claimedAt: now,
    claimedBy: workerId,
    iteration: 0,
    total: job.iterations,
    lastProgressAt: now,
  });
  return job;
}

function markDone(
  jobId: string,
  info: { infoSets: number; fileSize: number; elapsedMs: number; peakMemoryMB: number },
): boolean {
  const entry = running.get(jobId);
  if (!entry) return false;

  const record: CompletedJob = {
    jobId,
    boardId: entry.job.boardId,
    infoSets: info.infoSets,
    fileSize: info.fileSize,
    elapsedMs: info.elapsedMs,
    peakMemoryMB: info.peakMemoryMB,
    completedAt: Date.now(),
    worker: entry.claimedBy,
  };
  // CRITICAL: Write to persistent log BEFORE removing from running map.
  // If crash happens after write but before delete, on restart the job will
  // be in completed.jsonl (restored) and addJobs() dedup will skip it.
  appendCompletedLog(record);
  completed.push(record);
  running.delete(jobId);
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

function markProgress(jobId: string, info: { iteration: number; total: number; heartbeat?: boolean }): boolean {
  const entry = running.get(jobId);
  if (!entry) return false;

  // Always refresh the heartbeat timestamp (keeps stale detection happy)
  entry.lastProgressAt = Date.now();

  // For heartbeat-only messages (iteration=0 from parent process), don't regress iteration
  if (info.heartbeat && info.iteration === 0) return true;

  const total = Number.isFinite(info.total) && info.total > 0
    ? Math.floor(info.total)
    : entry.total;
  const rawIter = Number.isFinite(info.iteration) ? Math.floor(info.iteration) : entry.iteration;
  const clamped = Math.max(0, Math.min(total, rawIter));

  // Keep progress monotonic in case out-of-order IPC/network delivery.
  entry.total = total;
  entry.iteration = Math.max(entry.iteration, clamped);
  return true;
}

function reclaimStale(): void {
  const now = Date.now();
  for (const [jobId, entry] of running) {
    const timeSinceHeartbeat = now - entry.lastProgressAt;
    if (timeSinceHeartbeat > STALE_TIMEOUT_MS) {
      console.log(`[RECLAIM] Job ${jobId} stale (no heartbeat for ${Math.round(timeSinceHeartbeat / 60000)}min, worker: ${entry.claimedBy})`);
      running.delete(jobId);
      pending.unshift(entry.job); // re-queue at front (priority)
    }
  }
}

/** Force-reclaim all running jobs from a specific worker (used when a worker is known to be dead). */
function reclaimWorker(workerId: string): number {
  let count = 0;
  for (const [jobId, entry] of running) {
    if (entry.claimedBy === workerId) {
      running.delete(jobId);
      pending.unshift(entry.job);
      count++;
    }
  }
  if (count > 0) console.log(`[RECLAIM] Force-reclaimed ${count} jobs from dead worker ${workerId}`);
  return count;
}

function getStatus() {
  const now = Date.now();

  // Per-worker stats (survives restart via completed[] restored from logs)
  const workerStats: Record<string, {
    running: number; completed: number; totalMs: number;
    firstSeen: number; lastSeen: number; avgMemoryMB: number; totalMemoryMB: number;
  }> = {};
  const defaultWs = () => ({
    running: 0, completed: 0, totalMs: 0,
    firstSeen: Infinity, lastSeen: 0, avgMemoryMB: 0, totalMemoryMB: 0,
  });
  for (const entry of running.values()) {
    const w = entry.claimedBy;
    if (!workerStats[w]) workerStats[w] = defaultWs();
    workerStats[w].running++;
  }
  for (const c of completed) {
    if (!workerStats[c.worker]) workerStats[c.worker] = defaultWs();
    const ws = workerStats[c.worker];
    ws.completed++;
    ws.totalMs += c.elapsedMs;
    ws.totalMemoryMB += c.peakMemoryMB;
    if (c.completedAt < ws.firstSeen) ws.firstSeen = c.completedAt;
    if (c.completedAt > ws.lastSeen) ws.lastSeen = c.completedAt;
  }
  for (const ws of Object.values(workerStats)) {
    ws.avgMemoryMB = ws.completed > 0 ? Math.round(ws.totalMemoryMB / ws.completed) : 0;
    if (ws.firstSeen === Infinity) ws.firstSeen = 0;
  }

  const runningDetails = [...running.values()]
    .map((entry) => {
      const elapsedMs = now - entry.claimedAt;
      const progressPct = entry.total > 0 ? (entry.iteration / entry.total) * 100 : 0;
      return {
        jobId: entry.job.jobId,
        boardId: entry.job.boardId,
        label: entry.job.label,
        worker: entry.claimedBy,
        iteration: entry.iteration,
        total: entry.total,
        progressPct: Math.max(0, Math.min(100, progressPct)),
        elapsedMs,
        heartbeatAgeMs: now - entry.lastProgressAt,
      };
    })
    .sort((a, b) => b.progressPct - a.progressPct);

  // ETA calculation
  const avgFromCompleted = completed.length > 0
    ? completed.reduce((s, c) => s + c.elapsedMs, 0) / completed.length
    : 0;
  const avgFromRunning = runningDetails
    .filter(r => r.iteration > 0 && r.total > 0 && r.elapsedMs > 15000)
    .map(r => (r.elapsedMs * r.total) / r.iteration);
  const avgFromRunningMs = avgFromRunning.length > 0
    ? avgFromRunning.reduce((s, v) => s + v, 0) / avgFromRunning.length
    : 0;
  const avgMs = avgFromCompleted > 0 ? avgFromCompleted : avgFromRunningMs;
  const avgSolveSource = avgFromCompleted > 0 ? 'completed' : (avgFromRunningMs > 0 ? 'running_estimate' : 'none');
  const totalWorkers = new Set([...running.values()].map(v => v.claimedBy)).size || 1;
  // Use live heartbeating workers as concurrency estimate (not running.size which can inflate)
  const liveWorkerJobs = runningDetails.filter(r => r.heartbeatAgeMs <= 60000).length;
  const concurrentJobs = liveWorkerJobs > 0 ? liveWorkerJobs : (totalWorkers || 1);
  // Factor in partial progress of running jobs (a 90% done job = 0.1 remaining work)
  const runningRemaining = runningDetails.reduce(
    (sum, r) => sum + (1 - r.progressPct / 100), 0,
  );
  const remainingWork = pending.length + runningRemaining;
  const etaMs = avgMs > 0 ? (remainingWork * avgMs) / concurrentJobs : 0;
  const runningAvgPct = runningDetails.length > 0
    ? runningDetails.reduce((s, r) => s + r.progressPct, 0) / runningDetails.length
    : 0;
  const liveHeartbeats = runningDetails.filter(r => r.heartbeatAgeMs <= 20000).length;

  // Per-config breakdown
  const configStats: Record<string, { pending: number; running: number; completed: number; failed: number }> = {};
  for (const j of pending) {
    const cn = j.configName;
    if (!configStats[cn]) configStats[cn] = { pending: 0, running: 0, completed: 0, failed: 0 };
    configStats[cn].pending++;
  }
  for (const entry of running.values()) {
    const cn = entry.job.configName;
    if (!configStats[cn]) configStats[cn] = { pending: 0, running: 0, completed: 0, failed: 0 };
    configStats[cn].running++;
  }
  for (const c of completed) {
    const cn = c.jobId.split('__')[0];
    if (!configStats[cn]) configStats[cn] = { pending: 0, running: 0, completed: 0, failed: 0 };
    configStats[cn].completed++;
  }
  for (const f of failed) {
    const cn = f.jobId.split('__')[0];
    if (!configStats[cn]) configStats[cn] = { pending: 0, running: 0, completed: 0, failed: 0 };
    configStats[cn].failed++;
  }

  // Throughput: jobs completed in last 1h / 6h / 24h
  const oneHourAgo = now - 3600000;
  const sixHoursAgo = now - 6 * 3600000;
  const oneDayAgo = now - 86400000;
  const last1h = completed.filter(c => (c.completedAt ?? 0) > oneHourAgo).length;
  const last6h = completed.filter(c => (c.completedAt ?? 0) > sixHoursAgo).length;
  const last24h = completed.filter(c => (c.completedAt ?? 0) > oneDayAgo).length;

  return {
    pending: pending.length,
    running: running.size,
    completed: completed.length,
    failed: failed.length,
    total: pending.length + running.size + completed.length + failed.length,
    avgSolveMs: Math.round(avgMs),
    avgSolveSource,
    etaMs: Math.round(etaMs),
    etaHuman: etaMs > 0 ? formatDuration(etaMs) : 'N/A',
    activeWorkers: totalWorkers,
    runningAvgPct: Math.round(runningAvgPct * 10) / 10,
    liveHeartbeats,
    throughput: { last1h, last6h, last24h },
    runningDetails: runningDetails.slice(0, 80),
    workers: workerStats,
    configs: configStats,
    recentCompleted: completed.slice(-10).reverse(),
  };
}

function formatDuration(ms: number): string {
  const d = Math.floor(ms / 86400000);
  const h = Math.floor((ms % 86400000) / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  if (d > 0) return `${d}d ${h}h ${m}m`;
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
    if (method === 'POST' && url === '/progress') {
      const body = JSON.parse(await readBody(req));
      const ok = markProgress(body.jobId, {
        iteration: Number(body.iteration) || 0,
        total: Number(body.total) || 0,
        heartbeat: !!body.heartbeat,
      });
      json(res, ok ? 200 : 404, { ok });
      return;
    }

    if (method === 'GET' && url === '/status') {
      json(res, 200, getStatus());
      return;
    }

    // POST /reclaim-worker — force-reclaim all jobs from a dead worker
    if (method === 'POST' && url === '/reclaim-worker') {
      const body = JSON.parse(await readBody(req));
      const count = reclaimWorker(body.workerId);
      json(res, 200, { ok: true, reclaimed: count });
      return;
    }

    // GET /workers — per-machine breakdown
    if (method === 'GET' && url === '/workers') {
      const s = getStatus();
      json(res, 200, { workers: s.workers, totalWorkers: Object.keys(s.workers).length });
      return;
    }

    // GET /healthz — health check
    if (method === 'GET' && url === '/healthz') {
      json(res, 200, { ok: true, uptime: process.uptime() });
      return;
    }

    // GET / — HTML dashboard
    if (method === 'GET' && (url === '/' || url === '/dashboard')) {
      const html = getDashboardHTML();
      res.writeHead(200, {
        'Content-Type': 'text/html; charset=utf-8',
        'Content-Length': Buffer.byteLength(html),
      });
      res.end(html);
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

  // Periodic stale job cleanup (don't rely solely on /pop triggering reclaimStale)
  setInterval(() => {
    reclaimStale();
  }, 60_000);

  return server;
}

// ---------- Dashboard HTML ----------

function getDashboardHTML(): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CFR Pipeline Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0f1117; color: #e1e4e8; min-height: 100vh; }
  .header { background: linear-gradient(135deg, #1a1e2e 0%, #0d1117 100%); padding: 24px 32px; border-bottom: 1px solid #21262d; }
  .header h1 { font-size: 22px; font-weight: 600; color: #f0f6fc; }
  .header .subtitle { font-size: 13px; color: #8b949e; margin-top: 4px; }
  .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .card { background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 20px; }
  .card .label { font-size: 12px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; }
  .card .value { font-size: 32px; font-weight: 700; margin-top: 6px; color: #f0f6fc; }
  .card .value.green { color: #3fb950; }
  .card .value.blue { color: #58a6ff; }
  .card .value.orange { color: #d29922; }
  .card .value.red { color: #f85149; }
  .progress-container { margin-bottom: 24px; }
  .progress-bar { width: 100%; height: 32px; background: #21262d; border-radius: 8px; overflow: hidden; position: relative; }
  .progress-fill { height: 100%; background: linear-gradient(90deg, #238636 0%, #3fb950 100%); transition: width 0.8s ease; border-radius: 8px; }
  .progress-text { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 14px; font-weight: 600; color: #f0f6fc; text-shadow: 0 1px 2px rgba(0,0,0,0.5); }
  .section { background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 20px; margin-bottom: 24px; }
  .section h2 { font-size: 16px; font-weight: 600; margin-bottom: 16px; color: #f0f6fc; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; font-size: 12px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; padding: 8px 12px; border-bottom: 1px solid #21262d; }
  td { padding: 10px 12px; border-bottom: 1px solid #21262d; font-size: 14px; }
  tr:last-child td { border-bottom: none; }
  .status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
  .dot-green { background: #3fb950; }
  .dot-yellow { background: #d29922; }
  .dot-red { background: #f85149; }
  .rate { font-size: 13px; color: #8b949e; margin-top: 4px; }
  .update-time { font-size: 12px; color: #484f58; text-align: right; margin-top: 8px; }
  .chart-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }
  @media (max-width: 768px) { .chart-row { grid-template-columns: 1fr; } .grid { grid-template-columns: repeat(2, 1fr); } }
  .speed-chart { height: 200px; position: relative; }
  .speed-chart canvas { width: 100% !important; height: 100% !important; }
</style>
</head>
<body>
<div class="header">
  <h1>CFR Pipeline Dashboard</h1>
  <div class="subtitle">Distributed Solver — <span id="configCount"></span> configs</div>
</div>
<div class="container">
  <div class="progress-container">
    <div class="progress-bar">
      <div class="progress-fill" id="progressFill" style="width: 0%"></div>
      <div class="progress-text" id="progressText">0%</div>
    </div>
  </div>
  <div class="grid">
    <div class="card">
      <div class="label">Completed</div>
      <div class="value green" id="completed">0</div>
    </div>
    <div class="card">
      <div class="label">Running</div>
      <div class="value blue" id="running">0</div>
    </div>
    <div class="card">
      <div class="label">Pending</div>
      <div class="value orange" id="pending">0</div>
    </div>
    <div class="card">
      <div class="label">Failed</div>
      <div class="value red" id="failed">0</div>
    </div>
    <div class="card">
      <div class="label">ETA</div>
      <div class="value" id="eta">N/A</div>
    </div>
    <div class="card">
      <div class="label">Throughput</div>
      <div class="value" id="throughput">—</div>
      <div class="rate" id="throughputDetail"></div>
    </div>
    <div class="card">
      <div class="label">Avg Solve Time</div>
      <div class="value" id="avgTime">—</div>
      <div class="rate" id="rate"></div>
      <div class="rate" id="avgSource"></div>
    </div>
    <div class="card">
      <div class="label">Running Avg Progress</div>
      <div class="value blue" id="runningAvgPct">0%</div>
      <div class="rate">Across currently running boards</div>
    </div>
    <div class="card">
      <div class="label">Live Heartbeats</div>
      <div class="value green" id="liveHeartbeats">0/0</div>
      <div class="rate">Workers reporting recent iteration updates</div>
    </div>
  </div>

  <div class="chart-row">
    <div class="section">
      <h2>Solve Speed (flops/min)</h2>
      <div class="speed-chart"><canvas id="speedCanvas"></canvas></div>
    </div>
    <div class="section">
      <h2>Completion Over Time</h2>
      <div class="speed-chart"><canvas id="completionCanvas"></canvas></div>
    </div>
  </div>

  <div class="section">
    <h2>Configs</h2>
    <table>
      <thead><tr><th>Config</th><th>Completed</th><th>Running</th><th>Pending</th><th>Failed</th><th>Progress</th></tr></thead>
      <tbody id="configTable"></tbody>
    </table>
  </div>

  <div class="section">
    <h2>Workers</h2>
    <table>
      <thead><tr><th>Worker</th><th>Status</th><th>Completed</th><th>Running</th><th>Avg Time</th><th>Avg Mem</th><th>Last Active</th></tr></thead>
      <tbody id="workerTable"></tbody>
    </table>
  </div>

  <div class="section">
    <h2>Running Jobs (Live Iteration Progress)</h2>
    <table>
      <thead><tr><th>Worker</th><th>Board</th><th>Iteration</th><th>Progress</th><th>Elapsed</th><th>Heartbeat</th></tr></thead>
      <tbody id="runningTable"></tbody>
    </table>
  </div>

  <div class="section">
    <h2>Recent Completions</h2>
    <table>
      <thead><tr><th>Board</th><th>Info Sets</th><th>Time</th><th>Memory</th><th>Worker</th></tr></thead>
      <tbody id="recentTable"></tbody>
    </table>
  </div>

  <div class="update-time">Last update: <span id="lastUpdate">—</span></div>
</div>

<script>
const speedHistory = [];
const completionHistory = [];
let lastCompleted = -1;
let lastTime = Date.now();

function drawChart(canvasId, data, color, label) {
  const canvas = document.getElementById(canvasId);
  const ctx = canvas.getContext('2d');
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = rect.width * devicePixelRatio;
  canvas.height = rect.height * devicePixelRatio;
  ctx.scale(devicePixelRatio, devicePixelRatio);
  const w = rect.width, h = rect.height;
  ctx.clearRect(0, 0, w, h);
  if (data.length < 2) { ctx.fillStyle = '#484f58'; ctx.font = '13px system-ui'; ctx.fillText('Collecting data...', w/2 - 50, h/2); return; }
  const max = Math.max(...data) * 1.2 || 1;
  const step = w / (data.length - 1);
  // Grid
  ctx.strokeStyle = '#21262d'; ctx.lineWidth = 1;
  for (let i = 0; i < 4; i++) { const y = h * i / 4; ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); }
  // Line
  ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = 2;
  data.forEach((v, i) => { const x = i * step; const y = h - (v / max) * (h - 20); i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y); });
  ctx.stroke();
  // Fill
  ctx.lineTo((data.length - 1) * step, h); ctx.lineTo(0, h); ctx.closePath();
  ctx.fillStyle = color.replace(')', ', 0.1)').replace('rgb', 'rgba'); ctx.fill();
  // Labels
  ctx.fillStyle = '#8b949e'; ctx.font = '11px system-ui';
  ctx.fillText(max.toFixed(1), 4, 14);
  ctx.fillText('0', 4, h - 4);
  ctx.fillText(label, w - ctx.measureText(label).width - 4, 14);
}

async function refresh() {
  try {
    const r = await fetch('/status');
    const s = await r.json();
    const pct = s.total > 0 ? (s.completed / s.total * 100) : 0;
    document.getElementById('progressFill').style.width = pct.toFixed(1) + '%';
    document.getElementById('progressText').textContent = pct.toFixed(1) + '% (' + s.completed + '/' + s.total + ')';
    document.getElementById('completed').textContent = s.completed;
    document.getElementById('running').textContent = s.running;
    document.getElementById('pending').textContent = s.pending;
    document.getElementById('failed').textContent = s.failed;
    document.getElementById('eta').textContent = s.etaHuman || 'N/A';
    if (s.throughput) {
      document.getElementById('throughput').textContent = s.throughput.last1h + ' jobs/hr';
      document.getElementById('throughputDetail').textContent = 'Last 6h: ' + s.throughput.last6h + ' | Last 24h: ' + s.throughput.last24h;
    }
    if (s.avgSolveMs > 0) {
      const mins = (s.avgSolveMs / 60000).toFixed(1);
      document.getElementById('avgTime').textContent = mins + 'm';
      const fpm = s.activeWorkers > 0 ? (60000 / s.avgSolveMs * s.activeWorkers).toFixed(1) : '—';
      document.getElementById('rate').textContent = fpm + ' flops/min across ' + s.activeWorkers + ' workers';
      document.getElementById('avgSource').textContent = 'Source: ' + (s.avgSolveSource || 'none');
    }
    document.getElementById('runningAvgPct').textContent = (s.runningAvgPct || 0).toFixed(1) + '%';
    document.getElementById('configCount').textContent = s.configs ? Object.keys(s.configs).length : '?';
    document.getElementById('liveHeartbeats').textContent = (s.liveHeartbeats || 0) + '/' + s.running;
    // Speed chart
    const now = Date.now();
    if (lastCompleted >= 0 && s.completed > lastCompleted) {
      const elapsed = (now - lastTime) / 60000;
      const speed = elapsed > 0 ? (s.completed - lastCompleted) / elapsed : 0;
      speedHistory.push(speed);
      if (speedHistory.length > 60) speedHistory.shift();
    }
    completionHistory.push(s.completed);
    if (completionHistory.length > 120) completionHistory.shift();
    lastCompleted = s.completed;
    lastTime = now;
    drawChart('speedCanvas', speedHistory, 'rgb(88, 166, 255)', 'flops/min');
    drawChart('completionCanvas', completionHistory, 'rgb(63, 185, 80)', 'completed');
    // Configs
    const ct = document.getElementById('configTable');
    ct.innerHTML = '';
    if (s.configs) {
      for (const [cn, cs] of Object.entries(s.configs)) {
        const t = cs.pending + cs.running + cs.completed + cs.failed;
        const pctC = t > 0 ? (cs.completed / t * 100).toFixed(1) : '0.0';
        const bar = '<div style="background:#21262d;border-radius:4px;height:16px;width:120px;display:inline-block;overflow:hidden"><div style="background:#238636;height:100%;width:' + pctC + '%;border-radius:4px"></div></div>';
        ct.innerHTML += '<tr><td>' + cn + '</td><td class="green">' + cs.completed + '</td><td class="blue">' + cs.running + '</td><td class="orange">' + cs.pending + '</td><td class="red">' + cs.failed + '</td><td>' + bar + ' ' + pctC + '%</td></tr>';
      }
    }
    // Workers
    const wt = document.getElementById('workerTable');
    wt.innerHTML = '';
    if (s.workers) {
      for (const [wid, ws] of Object.entries(s.workers)) {
        const avg = ws.completed > 0 ? (ws.totalMs / ws.completed / 1000).toFixed(0) + 's' : '—';
        const dot = ws.running > 0 ? '<span class="status-dot dot-green"></span>Active' : '<span class="status-dot dot-yellow"></span>Idle';
        const avgMem = ws.avgMemoryMB ? ws.avgMemoryMB + 'MB' : '—';
        const lastActive = ws.lastSeen ? new Date(ws.lastSeen).toLocaleTimeString() : '—';
        wt.innerHTML += '<tr><td>' + wid + '</td><td>' + dot + '</td><td>' + ws.completed + '</td><td>' + ws.running + '</td><td>' + avg + '</td><td>' + avgMem + '</td><td>' + lastActive + '</td></tr>';
      }
    }
    // Running jobs
    const rjt = document.getElementById('runningTable');
    rjt.innerHTML = '';
    if (s.runningDetails) {
      for (const r of s.runningDetails) {
        const elapsed = r.elapsedMs >= 60000 ? (r.elapsedMs / 60000).toFixed(1) + 'm' : (r.elapsedMs / 1000).toFixed(0) + 's';
        const hbAge = r.heartbeatAgeMs < 60000 ? (r.heartbeatAgeMs / 1000).toFixed(0) + 's ago' : (r.heartbeatAgeMs / 60000).toFixed(1) + 'm ago';
        const hbDot = r.heartbeatAgeMs <= 60000 ? 'dot-green' : (r.heartbeatAgeMs <= 300000 ? 'dot-yellow' : 'dot-red');
        const pct = r.progressPct.toFixed(1) + '%';
        const iterStr = r.iteration.toLocaleString() + '/' + r.total.toLocaleString();
        rjt.innerHTML += '<tr><td>' + r.worker + '</td><td>' + r.label + '</td><td>' + iterStr + '</td><td>' + pct + '</td><td>' + elapsed + '</td><td><span class="status-dot ' + hbDot + '"></span>' + hbAge + '</td></tr>';
      }
    }
    // Recent
    const rt = document.getElementById('recentTable');
    rt.innerHTML = '';
    if (s.recentCompleted) {
      for (const c of s.recentCompleted) {
        rt.innerHTML += '<tr><td>flop_' + String(c.boardId).padStart(4,'0') + '</td><td>' + (c.infoSets||0).toLocaleString() + '</td><td>' + (c.elapsedMs/1000).toFixed(0) + 's</td><td>' + (c.peakMemoryMB||0).toFixed(0) + 'MB</td><td>' + c.worker + '</td></tr>';
      }
    }
    document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
  } catch (e) { console.error('Fetch error:', e); }
}

refresh();
setInterval(refresh, 5000);
window.addEventListener('resize', () => {
  drawChart('speedCanvas', speedHistory, 'rgb(88, 166, 255)', 'flops/min');
  drawChart('completionCanvas', completionHistory, 'rgb(63, 185, 80)', 'completed');
});
</script>
</body>
</html>`;
}

// Export queue state for the CLI to use
export { pending, running, completed, failed, getStatus };
