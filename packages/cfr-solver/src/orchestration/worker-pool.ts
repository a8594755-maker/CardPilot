// Worker pool for parallel CFR solving using child_process.fork().
// Each worker is a separate Node.js process with its own memory space.

import { fork, type ChildProcess } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import type { FlopTask, WorkerResult, WorkerProgress } from './solve-worker.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const WORKER_PATH = resolve(__dirname, 'solve-worker.ts');

export interface PoolOptions {
  numWorkers: number;
  onResult?: (result: WorkerResult) => void;
  onProgress?: (progress: WorkerProgress) => void;
}

interface WorkerEntry {
  process: ChildProcess;
  busy: boolean;
  id: number;
}

export class WorkerPool {
  private workers: WorkerEntry[] = [];
  private taskQueue: FlopTask[] = [];
  private pendingCount = 0;
  private resolveAll: (() => void) | null = null;
  private onResult: ((result: WorkerResult) => void) | null;
  private onProgress: ((progress: WorkerProgress) => void) | null;

  constructor(private options: PoolOptions) {
    this.onResult = options.onResult || null;
    this.onProgress = options.onProgress || null;

    for (let i = 0; i < options.numWorkers; i++) {
      // fork() with --import tsx to get TypeScript support in the child process
      const child = fork(WORKER_PATH, [], {
        execArgv: ['--import', 'tsx'],
        stdio: ['inherit', 'inherit', 'inherit', 'ipc'],
      });

      const entry: WorkerEntry = { process: child, busy: false, id: i };

      child.on('message', (msg: WorkerResult | WorkerProgress) => {
        if (msg.type === 'progress') {
          this.onProgress?.(msg);
          return;
        }

        if (msg.type === 'result') {
          this.onResult?.(msg);
          entry.busy = false;
          this.pendingCount--;
          this.dispatchNext(entry);

          // Check if all done
          if (this.pendingCount === 0 && this.taskQueue.length === 0) {
            this.resolveAll?.();
          }
        }
      });

      child.on('error', (err) => {
        console.error(`Worker ${i} error:`, err);
        entry.busy = false;
        this.pendingCount--;

        if (this.pendingCount === 0 && this.taskQueue.length === 0) {
          this.resolveAll?.();
        }
      });

      child.on('exit', (code) => {
        if (code !== 0 && code !== null) {
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
    const free = this.workers.find(w => !w.busy);
    if (free) {
      this.dispatchNext(free);
    }
  }

  /**
   * Wait for all submitted tasks to complete.
   */
  async waitAll(): Promise<void> {
    if (this.pendingCount === 0 && this.taskQueue.length === 0) return;
    return new Promise<void>(resolve => {
      this.resolveAll = resolve;
    });
  }

  /**
   * Terminate all worker processes.
   */
  async shutdown(): Promise<void> {
    for (const entry of this.workers) {
      entry.process.kill('SIGTERM');
    }
    // Give processes a moment to clean up
    await new Promise(r => setTimeout(r, 500));
    for (const entry of this.workers) {
      if (entry.process.exitCode === null) {
        entry.process.kill('SIGKILL');
      }
    }
    this.workers = [];
  }

  private dispatchNext(entry: WorkerEntry): void {
    if (this.taskQueue.length === 0) return;
    const task = this.taskQueue.shift()!;
    entry.busy = true;
    entry.process.send(task);
  }
}
