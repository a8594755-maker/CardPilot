import { cpus } from "node:os";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { Worker } from "node:worker_threads";
import type { Card, EquityResult } from "@cardpilot/poker-evaluator";

interface EquityTaskInput {
  heroHand: [Card, Card];
  villainHands: Array<[Card, Card]>;
  board: Card[];
  simulations?: number;
}

interface WorkerRequestMessage {
  id: number;
  payload: EquityTaskInput;
}

interface WorkerResultMessage {
  id: number;
  result?: EquityResult;
  error?: string;
}

interface QueuedTask {
  id: number;
  payload: EquityTaskInput;
  resolve: (result: EquityResult) => void;
  reject: (error: Error) => void;
}

interface WorkerState {
  worker: Worker;
  busy: boolean;
  currentTaskId?: number;
}

export interface WorkerPoolConfig {
  size?: number;
  taskTimeoutMs?: number;
}

const DEFAULT_TASK_TIMEOUT_MS = 20_000;

export class WorkerService {
  private readonly workers: WorkerState[] = [];
  private readonly queue: QueuedTask[] = [];
  private readonly inFlight = new Map<number, {
    resolve: (result: EquityResult) => void;
    reject: (error: Error) => void;
    timeout: ReturnType<typeof setTimeout>;
    workerIndex: number;
  }>();

  private readonly taskTimeoutMs: number;
  private readonly workerCount: number;
  private nextTaskId = 1;
  private isShuttingDown = false;

  constructor(config: WorkerPoolConfig = {}) {
    const cpuCount = Math.max(1, cpus().length);
    this.workerCount = Math.max(1, config.size ?? Math.min(4, Math.max(1, cpuCount - 1)));
    this.taskTimeoutMs = Math.max(1_000, config.taskTimeoutMs ?? DEFAULT_TASK_TIMEOUT_MS);

    for (let i = 0; i < this.workerCount; i++) {
      this.workers.push(this.spawnWorker(i));
    }
  }

  calculateEquity(payload: EquityTaskInput): Promise<EquityResult> {
    if (this.isShuttingDown) {
      return Promise.reject(new Error("WorkerService is shutting down"));
    }

    return new Promise<EquityResult>((resolve, reject) => {
      const id = this.nextTaskId++;
      this.queue.push({ id, payload, resolve, reject });
      this.dispatch();
    });
  }

  async destroy(): Promise<void> {
    this.isShuttingDown = true;

    while (this.queue.length > 0) {
      const task = this.queue.shift();
      task?.reject(new Error("WorkerService destroyed before task execution"));
    }

    for (const [, inflight] of this.inFlight) {
      clearTimeout(inflight.timeout);
      inflight.reject(new Error("WorkerService destroyed during task execution"));
    }
    this.inFlight.clear();

    await Promise.all(this.workers.map(({ worker }) => worker.terminate()));
    this.workers.length = 0;
  }

  private dispatch(): void {
    if (this.queue.length === 0) return;

    for (let workerIndex = 0; workerIndex < this.workers.length; workerIndex++) {
      if (this.queue.length === 0) return;
      const state = this.workers[workerIndex];
      if (state.busy) continue;

      const task = this.queue.shift();
      if (!task) return;

      state.busy = true;
      state.currentTaskId = task.id;

      const timeout = setTimeout(() => {
        this.failTask(task.id, new Error(`Equity worker timed out after ${this.taskTimeoutMs}ms`));
      }, this.taskTimeoutMs);

      this.inFlight.set(task.id, {
        resolve: task.resolve,
        reject: task.reject,
        timeout,
        workerIndex,
      });

      const message: WorkerRequestMessage = {
        id: task.id,
        payload: task.payload,
      };

      state.worker.postMessage(message);
    }
  }

  private spawnWorker(index: number): WorkerState {
    const workerUrl = resolveWorkerUrl();
    const worker = new Worker(workerUrl, { execArgv: process.execArgv });

    worker.on("message", (message: WorkerResultMessage) => {
      this.completeTask(message, index);
    });

    worker.on("error", (error) => {
      this.handleWorkerFailure(index, toError(error));
    });

    worker.on("exit", (code) => {
      if (!this.isShuttingDown && code !== 0) {
        this.handleWorkerFailure(index, new Error(`Worker exited with code ${code}`));
      }
    });

    return { worker, busy: false };
  }

  private completeTask(message: WorkerResultMessage, workerIndex: number): void {
    const inflight = this.inFlight.get(message.id);
    if (!inflight) return;

    clearTimeout(inflight.timeout);
    this.inFlight.delete(message.id);

    const state = this.workers[workerIndex];
    if (state) {
      state.busy = false;
      state.currentTaskId = undefined;
    }

    if (message.error) {
      inflight.reject(new Error(message.error));
    } else if (!message.result) {
      inflight.reject(new Error("Worker returned no equity result"));
    } else {
      inflight.resolve(message.result);
    }

    this.dispatch();
  }

  private failTask(taskId: number, error: Error): void {
    const inflight = this.inFlight.get(taskId);
    if (!inflight) return;

    clearTimeout(inflight.timeout);
    this.inFlight.delete(taskId);

    const state = this.workers[inflight.workerIndex];
    if (state && state.currentTaskId === taskId) {
      state.busy = false;
      state.currentTaskId = undefined;
    }

    inflight.reject(error);
    this.dispatch();
  }

  private handleWorkerFailure(workerIndex: number, error: Error): void {
    const state = this.workers[workerIndex];
    if (!state) return;

    const taskId = state.currentTaskId;
    if (typeof taskId === "number") {
      this.failTask(taskId, error);
    }

    if (this.isShuttingDown) return;

    try {
      state.worker.terminate().catch(() => undefined);
    } catch {
      // noop
    }

    this.workers[workerIndex] = this.spawnWorker(workerIndex);
    this.dispatch();
  }
}

function resolveWorkerUrl(): URL {
  const jsUrl = new URL("./equity-worker.js", import.meta.url);
  const tsUrl = new URL("./equity-worker.ts", import.meta.url);

  if (existsSync(fileURLToPath(jsUrl))) {
    return jsUrl;
  }
  return tsUrl;
}

function toError(value: unknown): Error {
  if (value instanceof Error) return value;
  return new Error(typeof value === "string" ? value : "Unknown worker error");
}
