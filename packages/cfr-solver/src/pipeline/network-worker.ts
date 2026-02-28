#!/usr/bin/env tsx
// Network worker: polls the Queue Server for jobs, solves them locally, reports results.
// Runs on each machine (A, B, C). Spawns multiple solver child processes.
//
// Usage: npx tsx network-worker.ts --server http://192.168.1.100:3500 [--workers 4] [--id machineA]

import { fork, type ChildProcess } from 'node:child_process';
import { cpus, totalmem, hostname } from 'node:os';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { existsSync, mkdirSync } from 'node:fs';
import { request } from 'node:http';
import { getConfigOutputDir, type TreeConfigName } from '../tree/tree-config.js';
import type { PipelineJob } from './queue-server.js';
import type { FlopTask, WorkerResult, WorkerProgress } from '../orchestration/solve-worker.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const SOLVE_WORKER_PATH = resolve(__dirname, '../orchestration/solve-worker.ts');

// Find this machine's project root (may differ from coordinator's)
function findLocalProjectRoot(): string {
  const fromFile = resolve(__dirname, '../../../../');
  if (existsSync(resolve(fromFile, 'data'))) return fromFile;
  if (existsSync(resolve(process.cwd(), 'data'))) return process.cwd();
  const parent = resolve(process.cwd(), '../..');
  if (existsSync(resolve(parent, 'data'))) return parent;
  return process.cwd();
}

const LOCAL_PROJECT_ROOT = findLocalProjectRoot();

/** Resolve outputDir and chartsPath to local paths (coordinator sends its own absolute paths). */
function localizeJob(job: PipelineJob): PipelineJob {
  const localOutputDir = resolve(LOCAL_PROJECT_ROOT, 'data/cfr', getConfigOutputDir(job.configName as TreeConfigName));
  const localChartsPath = resolve(LOCAL_PROJECT_ROOT, 'data/preflop_charts.json');
  return { ...job, outputDir: localOutputDir, chartsPath: localChartsPath };
}

// ---------- HTTP Client ----------

function httpGet(url: string): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const req = request({
      hostname: parsed.hostname,
      port: parsed.port,
      path: parsed.pathname,
      method: 'GET',
      headers: { 'x-worker-id': workerId },
    }, (res) => {
      const chunks: Buffer[] = [];
      res.on('data', (c: Buffer) => chunks.push(c));
      res.on('end', () => resolve({ status: res.statusCode ?? 0, body: Buffer.concat(chunks).toString() }));
    });
    req.on('error', reject);
    req.end();
  });
}

function httpPost(url: string, data: unknown): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const payload = JSON.stringify(data);
    const req = request({
      hostname: parsed.hostname,
      port: parsed.port,
      path: parsed.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload),
        'x-worker-id': workerId,
      },
    }, (res) => {
      const chunks: Buffer[] = [];
      res.on('data', (c: Buffer) => chunks.push(c));
      res.on('end', () => resolve({ status: res.statusCode ?? 0, body: Buffer.concat(chunks).toString() }));
    });
    req.on('error', reject);
    req.write(payload);
    req.end();
  });
}

// ---------- Config ----------

const args = process.argv.slice(2);
function getArg(name: string, defaultVal: string): string {
  const idx = args.indexOf(`--${name}`);
  if (idx !== -1 && args[idx + 1]) return args[idx + 1];
  return defaultVal;
}
function getNumArg(name: string, defaultVal: number): number {
  const idx = args.indexOf(`--${name}`);
  if (idx !== -1 && args[idx + 1]) return parseInt(args[idx + 1], 10);
  return defaultVal;
}

const serverUrl = getArg('server', 'http://localhost:3500');
const workerId = getArg('id', hostname());
const requestedWorkers = getNumArg('workers', 0); // 0 = auto-detect
const heapMB = getNumArg('heap', 0); // 0 = auto-detect

// Auto-detect worker count: based on CPU cores and RAM
function autoDetectWorkers(): number {
  const cpuCount = cpus().length;
  const totalMB = Math.floor(totalmem() / (1024 * 1024));
  const peakPerWorkerMB = 300; // conservative estimate based on benchmark (221MB peak)
  const reservedMB = 4096;     // OS + main process
  const maxByRam = Math.floor((totalMB - reservedMB) / peakPerWorkerMB);
  const maxByCpu = Math.max(1, cpuCount - 1); // leave 1 core for OS
  return Math.max(1, Math.min(maxByRam, maxByCpu));
}

function autoDetectHeapMB(numWorkers: number): number {
  const totalMB = Math.floor(totalmem() / (1024 * 1024));
  const reservedMB = 4096;
  const perWorker = Math.floor((totalMB - reservedMB) / numWorkers);
  return Math.max(512, Math.min(16384, perWorker));
}

// ---------- Worker Pool ----------

interface LocalWorker {
  process: ChildProcess;
  busy: boolean;
  id: number;
  currentJob: PipelineJob | null;
}

const localWorkers: LocalWorker[] = [];
let totalSolved = 0;
let totalFailed = 0;
let shuttingDown = false;
const lastProgressSentMs = new Map<string, number>();

function reportProgress(job: PipelineJob, msg: WorkerProgress): void {
  const now = Date.now();
  const prev = lastProgressSentMs.get(job.jobId) ?? 0;
  // Keep coordinator traffic bounded when many workers report at once.
  if (msg.iteration < msg.total && now - prev < 1000) return;
  lastProgressSentMs.set(job.jobId, now);
  void httpPost(`${serverUrl}/progress`, {
    jobId: job.jobId,
    iteration: msg.iteration,
    total: msg.total,
  }).catch(() => {
    // best-effort heartbeat only
  });
}

function spawnWorkers(numWorkers: number, perWorkerHeapMB: number): void {
  for (let i = 0; i < numWorkers; i++) {
    const child = fork(SOLVE_WORKER_PATH, [], {
      execArgv: ['--import', 'tsx', `--max-old-space-size=${perWorkerHeapMB}`],
      stdio: ['inherit', 'inherit', 'inherit', 'ipc'],
    });

    const entry: LocalWorker = { process: child, busy: false, id: i, currentJob: null };

    child.on('message', async (msg: WorkerResult | WorkerProgress) => {
      if (msg.type === 'progress') {
        const job = entry.currentJob;
        if (job && job.boardId === msg.boardId) {
          reportProgress(job, msg);
        }
        return;
      }

      if (msg.type === 'result') {
        const job = entry.currentJob!;
        entry.busy = false;
        entry.currentJob = null;
        lastProgressSentMs.delete(job.jobId);
        totalSolved++;

        // Report completion to server
        try {
          await httpPost(`${serverUrl}/done`, {
            jobId: job.jobId,
            infoSets: msg.infoSets,
            fileSize: msg.fileSize,
            elapsedMs: msg.elapsedMs,
            peakMemoryMB: msg.peakMemoryMB,
          });
        } catch (err) {
          console.error(`[W${i}] Failed to report done for ${job.jobId}:`, err);
        }

        const elapsedStr = (msg.elapsedMs / 1000).toFixed(1);
        const fileSizeStr = (msg.fileSize / 1024).toFixed(0);
        console.log(`[W${i}] Done: ${job.label} | ${elapsedStr}s | ${msg.infoSets} info sets | ${fileSizeStr}KB`);

        // Fetch next job
        if (!shuttingDown) fetchAndDispatch(entry);
      }
    });

    child.on('error', async (err) => {
      console.error(`[W${i}] Process error:`, err);
      const job = entry.currentJob;
      entry.busy = false;
      entry.currentJob = null;
      totalFailed++;

      if (job) {
        lastProgressSentMs.delete(job.jobId);
        try {
          await httpPost(`${serverUrl}/fail`, {
            jobId: job.jobId,
            error: String(err),
          });
        } catch { /* best-effort */ }
      }

      if (!shuttingDown) fetchAndDispatch(entry);
    });

    child.on('exit', async (code) => {
      if (code !== 0 && code !== null && !shuttingDown) {
        console.error(`[W${i}] Exited with code ${code}, respawning...`);
        // Report the current job as failed so it doesn't stay in running map
        const job = entry.currentJob;
        if (job && entry.busy) {
          entry.busy = false;
          entry.currentJob = null;
          lastProgressSentMs.delete(job.jobId);
          totalFailed++;
          try {
            await httpPost(`${serverUrl}/fail`, { jobId: job.jobId, error: `Worker exited with code ${code}` });
          } catch { /* best-effort */ }
        }
        // Respawn after a delay
        setTimeout(() => {
          if (!shuttingDown) {
            localWorkers[i] = spawnSingleWorker(i, perWorkerHeapMB);
            fetchAndDispatch(localWorkers[i]);
          }
        }, 2000);
      }
    });

    localWorkers.push(entry);
  }
}

function spawnSingleWorker(id: number, heapMBVal: number): LocalWorker {
  const child = fork(SOLVE_WORKER_PATH, [], {
    execArgv: ['--import', 'tsx', `--max-old-space-size=${heapMBVal}`],
    stdio: ['inherit', 'inherit', 'inherit', 'ipc'],
  });

  const entry: LocalWorker = { process: child, busy: false, id, currentJob: null };

  child.on('message', async (msg: WorkerResult | WorkerProgress) => {
    if (msg.type === 'progress') {
      const job = entry.currentJob;
      if (job && job.boardId === msg.boardId) {
        reportProgress(job, msg);
      }
      return;
    }

    if (msg.type === 'result') {
      const job = entry.currentJob!;
      entry.busy = false;
      entry.currentJob = null;
      lastProgressSentMs.delete(job.jobId);
      totalSolved++;

      try {
        await httpPost(`${serverUrl}/done`, {
          jobId: job.jobId,
          infoSets: msg.infoSets,
          fileSize: msg.fileSize,
          elapsedMs: msg.elapsedMs,
          peakMemoryMB: msg.peakMemoryMB,
        });
      } catch { /* best-effort */ }

      console.log(`[W${id}] Done: ${job.label} | ${(msg.elapsedMs / 1000).toFixed(1)}s`);
      if (!shuttingDown) fetchAndDispatch(entry);
    }
  });

  child.on('error', async (err) => {
    const job = entry.currentJob;
    entry.busy = false;
    entry.currentJob = null;
    totalFailed++;
    if (job) {
      lastProgressSentMs.delete(job.jobId);
      try { await httpPost(`${serverUrl}/fail`, { jobId: job.jobId, error: String(err) }); } catch { }
    }
    if (!shuttingDown) fetchAndDispatch(entry);
  });

  return entry;
}

async function fetchAndDispatch(worker: LocalWorker): Promise<void> {
  if (worker.busy || shuttingDown) return;

  try {
    const res = await httpGet(`${serverUrl}/pop`);
    if (res.status === 204) {
      // No jobs available, wait and retry
      setTimeout(() => {
        if (!shuttingDown) fetchAndDispatch(worker);
      }, 5000);
      return;
    }
    if (res.status !== 200) {
      console.error(`[W${worker.id}] Unexpected status from /pop: ${res.status}`);
      setTimeout(() => fetchAndDispatch(worker), 10000);
      return;
    }

    const rawJob: PipelineJob = JSON.parse(res.body);
    const job = localizeJob(rawJob);

    // Ensure output dir exists (local path)
    mkdirSync(job.outputDir, { recursive: true });

    // Convert PipelineJob to FlopTask for the solve worker
    const task: FlopTask = {
      type: 'solve',
      flopCards: job.flopCards,
      boardId: job.boardId,
      label: job.label,
      iterations: job.iterations,
      bucketCount: job.bucketCount,
      outputDir: job.outputDir,
      chartsPath: job.chartsPath,
      configName: job.configName,
      stackLabel: job.stackLabel,
    };

    worker.busy = true;
    worker.currentJob = job;
    reportProgress(job, { type: 'progress', boardId: job.boardId, iteration: 0, total: job.iterations });
    worker.process.send(task);
  } catch (err) {
    console.error(`[W${worker.id}] Error fetching job:`, err);
    setTimeout(() => {
      if (!shuttingDown) fetchAndDispatch(worker);
    }, 10000);
  }
}

// ---------- Heartbeat ----------

/** Send periodic heartbeats for all busy workers so the coordinator knows we're alive.
 *  Child process IPC progress messages are buffered during synchronous solveCFR and
 *  never arrive until the solve finishes.  This parent-level heartbeat runs on the
 *  (idle) main event loop and keeps lastProgressAt fresh on the coordinator. */
function startHeartbeatLoop(): void {
  setInterval(async () => {
    for (const w of localWorkers) {
      if (!w.busy || !w.currentJob) continue;
      try {
        await httpPost(`${serverUrl}/progress`, {
          jobId: w.currentJob.jobId,
          iteration: 0,   // we don't know real iteration; 0 is fine — it just refreshes lastProgressAt
          total: w.currentJob.iterations,
          heartbeat: true, // flag so coordinator can distinguish real progress from keep-alive
        });
      } catch { /* best-effort */ }
    }
  }, 30_000);
}

// ---------- Status Printer ----------

function printStatusLoop(): void {
  setInterval(async () => {
    try {
      const res = await httpGet(`${serverUrl}/status`);
      if (res.status === 200) {
        const s = JSON.parse(res.body);
        const busy = localWorkers.filter(w => w.busy).length;
        process.stdout.write(
          `\r[${workerId}] local: ${busy}/${localWorkers.length} busy | ` +
          `queue: ${s.pending} pending, ${s.running} running, ${s.completed} done | ` +
          `ETA: ${s.etaHuman}   `
        );
      }
    } catch { /* server might be temporarily unreachable */ }
  }, 15000);
}

// ---------- Main ----------

async function main(): Promise<void> {
  console.log('╔═══════════════════════════════════════════════╗');
  console.log('║   CFR Pipeline — Network Worker               ║');
  console.log('╚═══════════════════════════════════════════════╝');
  console.log();

  const numWorkers = requestedWorkers > 0 ? requestedWorkers : autoDetectWorkers();
  const perWorkerHeapMB = heapMB > 0 ? heapMB : autoDetectHeapMB(numWorkers);

  console.log(`Worker ID:     ${workerId}`);
  console.log(`Server:        ${serverUrl}`);
  console.log(`Project root:  ${LOCAL_PROJECT_ROOT}`);
  console.log(`Local workers: ${numWorkers}`);
  console.log(`Heap/worker:   ${perWorkerHeapMB}MB`);
  console.log(`Total RAM:     ${Math.floor(totalmem() / (1024 * 1024))}MB`);
  console.log(`CPU cores:     ${cpus().length}`);
  console.log();

  // Health check
  console.log('Checking server connectivity...');
  try {
    const res = await httpGet(`${serverUrl}/healthz`);
    if (res.status !== 200) throw new Error(`Status ${res.status}`);
    console.log('Server OK');
  } catch (err) {
    console.error(`Cannot reach server at ${serverUrl}:`, err);
    console.error('Make sure the queue server is running first.');
    process.exit(1);
  }
  console.log();

  // Spawn workers
  console.log(`Spawning ${numWorkers} solver workers...`);
  spawnWorkers(numWorkers, perWorkerHeapMB);
  console.log('Workers ready. Starting job polling...');
  console.log();

  // Start fetching jobs for all workers
  for (const worker of localWorkers) {
    fetchAndDispatch(worker);
  }

  // Heartbeat & status printer
  startHeartbeatLoop();
  printStatusLoop();

  // Graceful shutdown
  const shutdown = () => {
    if (shuttingDown) return;
    shuttingDown = true;
    console.log('\n[Shutdown] Waiting for active solves to finish...');

    const active = localWorkers.filter(w => w.busy);
    if (active.length === 0) {
      process.exit(0);
    }

    // Wait up to 60s for active workers
    const deadline = Date.now() + 60000;
    const check = setInterval(() => {
      const stillBusy = localWorkers.filter(w => w.busy);
      if (stillBusy.length === 0 || Date.now() > deadline) {
        clearInterval(check);
        for (const w of localWorkers) {
          w.process.kill('SIGTERM');
        }
        setTimeout(() => process.exit(0), 1000);
      }
    }, 1000);
  };

  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

main().catch(err => {
  console.error('[FATAL]', err);
  process.exit(1);
});
