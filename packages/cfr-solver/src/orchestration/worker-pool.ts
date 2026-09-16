// Worker pool for parallel CFR solving using child_process.fork().
// Each worker is a separate Node.js process with its own memory space.

import { fork, type ChildProcess } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { totalmem } from 'node:os';
import type { FlopTask, WorkerResult, WorkerProgress } from './solve-worker.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const WORKER_PATH = resolve(__dirname, 'solve-worker.ts');

export interface PoolOptions {
  numWorkers: number;
  maxHeapMB?: number; // per-worker max heap size in MB
  onResult?: (result: WorkerResult) => void;
  onProgress?: (progress: WorkerProgress) => void;
}

interface WorkerEntry {
  process: ChildProcess;
  busy: boolean;
  id: number;
  currentTask: FlopTask | null;
  failed: boolean;
}

export class WorkerPool {
  private workers: WorkerEntry[] = [];
  private taskQueue: FlopTask[] = [];
  private pendingCount = 0;
  private resolveAll: (() => void) | null = null;
  private rejectAll: ((error: Error) => void) | null = null;
  private failure: Error | null = null;
  private shuttingDown = false;
  private onResult: ((result: WorkerResult) => void) | null;
  private onProgress: ((progress: WorkerProgress) => void) | null;

  constructor(private options: PoolOptions) {
    this.onResult = options.onResult || null;
    this.onProgress = options.onProgress || null;

    // Calculate per-worker heap size: use provided value or auto-detect from system RAM
    const heapMB = options.maxHeapMB ?? WorkerPool.autoDetectHeapMB(options.numWorkers);

    for (let i = 0; i < options.numWorkers; i++) {
      // fork() with --import tsx to get TypeScript support in the child process
      const child = fork(WORKER_PATH, [], {
        execArgv: ['--import', 'tsx', `--max-old-space-size=${heapMB}`],
        stdio: ['inherit', 'inherit', 'inherit', 'ipc'],
      });

      const entry: WorkerEntry = {
        process: child,
        busy: false,
        id: i,
        currentTask: null,
        failed: false,
      };

      child.on('message', (msg: WorkerResult | WorkerProgress) => {
        if (msg.type === 'progress') {
          this.onProgress?.(msg);
          return;
        }

        if (msg.type === 'result') {
          this.onResult?.(msg);
          entry.busy = false;
          entry.currentTask = null;
          this.pendingCount--;
          this.dispatchNext(entry);

          // Check if all done
          if (this.pendingCount === 0 && this.taskQueue.length === 0) {
            this.resolveAll?.();
          }
        }
      });

      child.on('error', (err) => {
        this.failWorker(entry, new Error(`Worker ${i} error: ${err.message}`, { cause: err }));
      });

      child.on('exit', (code) => {
        if (!this.shuttingDown && entry.busy) {
          const boardId = entry.currentTask?.boardId;
          this.failWorker(
            entry,
            new Error(
              `Worker ${i} exited with code ${code ?? 'null'} while solving board ${boardId ?? 'unknown'}`,
            ),
          );
        } else if (!this.shuttingDown && code !== 0 && code !== null) {
          console.error(`Worker ${i} exited with code ${code}`);
        }
      });

      this.workers.push(entry);
    }
  }

  /**
   * Submit a flop task to be solved.
   */
  submit(task: FlopTask): void {
    this.taskQueue.push(task);
    this.pendingCount++;

    // Try to dispatch to a free worker
    const free = this.workers.find((w) => !w.busy);
    if (free) {
      this.dispatchNext(free);
    }
  }

  /**
   * Wait for all submitted tasks to complete.
   */
  async waitAll(): Promise<void> {
    if (this.failure) throw this.failure;
    if (this.pendingCount === 0 && this.taskQueue.length === 0) return;
    return new Promise<void>((resolve, reject) => {
      this.resolveAll = resolve;
      this.rejectAll = reject;
    });
  }

  /**
   * Terminate all worker processes.
   */
  async shutdown(): Promise<void> {
    this.shuttingDown = true;
    for (const entry of this.workers) {
      entry.process.kill('SIGTERM');
    }
    // Give processes a moment to clean up
    await new Promise((r) => setTimeout(r, 500));
    for (const entry of this.workers) {
      if (entry.process.exitCode === null) {
        entry.process.kill('SIGKILL');
      }
    }
    this.workers = [];
  }

  /**
   * Auto-detect per-worker heap size based on system total RAM.
   * Reserves ~4GB for OS + main process, splits rest among workers.
   */
  private static autoDetectHeapMB(numWorkers: number): number {
    const totalMB = Math.floor(totalmem() / (1024 * 1024));
    const reservedMB = 4096; // 4GB for OS + main process
    const perWorker = Math.floor((totalMB - reservedMB) / numWorkers);
    // Clamp between 4GB and 64GB per worker.
    return Math.max(4096, Math.min(65536, perWorker));
  }

  private dispatchNext(entry: WorkerEntry): void {
    if (this.taskQueue.length === 0) return;
    const task = this.taskQueue.shift()!;
    entry.busy = true;
    entry.currentTask = task;
    entry.process.send(task);
  }

  private failWorker(entry: WorkerEntry, error: Error): void {
    if (entry.failed || this.shuttingDown) return;
    entry.failed = true;
    entry.busy = false;
    entry.currentTask = null;
    this.failure ??= error;
    console.error(error.message);
    this.rejectAll?.(this.failure);
  }
}
