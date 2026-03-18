/**
 * Parallel WASM CFR solver.
 *
 * Distributes iterations across multiple child_process.fork() workers,
 * each loading its own WASM module. Aggregates strategySums via linear
 * CFR weighting after all workers complete.
 */

import { fork } from 'child_process';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
import { cpus } from 'os';
import type { WasmSolveParams, WasmSolveResult } from './wasm-cfr-bridge.js';
import { serializeWasmParams } from './wasm-cfr-bridge.js';

const __dirname = dirname(fileURLToPath(import.meta.url));

export interface WasmParallelParams extends WasmSolveParams {
  numWorkers?: number;
}

/**
 * Solve with multiple WASM workers in parallel.
 * Each worker independently builds subtrees and solves its iteration range.
 * Returns aggregated strategySums (sum across all workers).
 */
export async function solveWithWasmParallel(
  params: WasmParallelParams,
): Promise<WasmSolveResult | null> {
  const numWorkers = Math.min(params.numWorkers ?? cpus().length, params.iterations);

  if (numWorkers <= 1) {
    // Fall back to single-threaded
    const { solveWithWasm } = await import('./wasm-cfr-bridge.js');
    return solveWithWasm(params);
  }

  // Worker script -- use compiled JS from dist/ if available, else tsx source
  const srcWorkerPath = join(__dirname, 'wasm-cfr-worker.ts');

  // Since we run via `node --import tsx`, the source .ts file works with fork()
  const workerPath = srcWorkerPath;

  console.log(`  Launching ${numWorkers} parallel WASM workers...`);

  const baseIters = Math.floor(params.iterations / numWorkers);
  const extraIters = params.iterations % numWorkers;

  interface WorkerResult {
    strategySums: number[];
    flopNC: number;
  }

  const workerPromises: Promise<WorkerResult>[] = [];

  for (let w = 0; w < numWorkers; w++) {
    const workerIters = baseIters + (w < extraIters ? 1 : 0);
    if (workerIters <= 0) continue;

    // Each worker covers a distinct iteration range with correct linear CFR
    // weights: globalIterOffset = cumulative iters before this worker, so
    // later workers get higher weights (more converged strategies dominant).
    // This matches the TypeScript parallel approach and maximizes convergence.
    const globalIterOffset = w * baseIters;
    const workerParams: WasmSolveParams = {
      ...params,
      iterations: workerIters,
      globalIterOffset,
      rngSeed: 42 + w * 1000, // unique seed per worker for diverse sampling
    };

    workerPromises.push(
      new Promise<WorkerResult>((resolve, reject) => {
        const child = fork(workerPath, [], {
          execArgv: [...process.execArgv],
          serialization: 'advanced',
          stdio: ['pipe', 'inherit', 'inherit', 'ipc'],
        });

        child.on('message', (msg: any) => {
          if (msg.type === 'done') {
            resolve({
              strategySums: msg.strategySums,
              flopNC: msg.flopNC,
            });
          } else if (msg.type === 'error') {
            reject(new Error(`Worker ${w}: ${msg.message}`));
          }
        });

        child.on('error', reject);
        child.on('exit', (code) => {
          if (code !== 0 && code !== null) {
            reject(new Error(`Worker ${w} exited with code ${code}`));
          }
        });

        // Send serialized params to worker
        child.send(serializeWasmParams(workerParams));
      }),
    );
  }

  try {
    const results = await Promise.all(workerPromises);

    // Aggregate strategySums from all workers
    const totalLen = results[0].strategySums.length;
    const aggregated = new Float32Array(totalLen);

    for (const result of results) {
      const sums = result.strategySums;
      for (let i = 0; i < sums.length; i++) {
        aggregated[i] += sums[i];
      }
    }

    console.log(`  All ${numWorkers} workers finished.`);

    return {
      strategySums: aggregated,
      flopNC: results[0].flopNC,
    };
  } catch (err) {
    console.error('  Parallel WASM solve failed:', (err as Error).message);
    return null;
  }
}
