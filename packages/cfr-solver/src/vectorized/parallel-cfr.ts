/**
 * Parallel CFR+ solver using worker_threads + SharedArrayBuffer.
 *
 * Spawns N worker threads, each running iterations/N CFR+ iterations
 * with its own ArrayStore. Workers write strategySums directly into
 * SharedArrayBuffer -- no IPC serialization/deserialization overhead.
 *
 * Uses Linear CFR weighting for correct parallel aggregation:
 *   - Each worker applies linear weights (globalIterOffset + iter + 1)
 *   - Sum of all workers' weighted strategies = sequential weighted sum
 *   - DCFR multiplicative discounting is NOT used for parallel workers
 *     (it's not compatible with split-iteration solving)
 *
 * Performance vs child_process.fork():
 *   - ~10x faster startup (no V8 bootstrap per worker)
 *   - Zero-copy strategySums aggregation (shared memory)
 *   - No JSON serialization for large arrays
 */

import { Worker } from 'worker_threads';
import { cpus } from 'os';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import type { FlatTree } from './flat-tree.js';
import type { ArrayStore } from './array-store.js';
import type { WeightedCombo } from '../integration/preflop-ranges.js';

export interface ParallelSolveParams {
  tree: FlatTree;
  store: ArrayStore;
  board: number[];
  oopRange: WeightedCombo[];
  ipRange: WeightedCombo[];
  iterations: number;
  numWorkers?: number;
  onProgress?: (totalIter: number, elapsed: number) => void;
  showdownMatrix?: Int8Array;
  equityMatrix?: Float32Array;
  blockerMatrix?: Uint8Array;
}

/** Serialize FlatTree TypedArrays to plain arrays for worker_threads transfer. */
function serializeTree(tree: FlatTree) {
  return {
    treeNumNodes: tree.numNodes,
    treeNumTerminals: tree.numTerminals,
    treeNumPlayers: tree.numPlayers,
    treeTotalActions: tree.totalActions,
    treeNodePlayer: Array.from(tree.nodePlayer),
    treeNodeStreet: Array.from(tree.nodeStreet),
    treeNodeNumActions: Array.from(tree.nodeNumActions),
    treeNodeActionOffset: Array.from(tree.nodeActionOffset),
    treeNodePot: Array.from(tree.nodePot),
    treeNodeStacks: Array.from(tree.nodeStacks),
    treeChildNodeId: Array.from(tree.childNodeId),
    treeActionType: Array.from(tree.actionType),
    treeTerminalPot: Array.from(tree.terminalPot),
    treeTerminalIsShowdown: Array.from(tree.terminalIsShowdown),
    treeTerminalFolder: Array.from(tree.terminalFolder),
    treeTerminalStacks: Array.from(tree.terminalStacks),
    treeTerminalWinner: Array.from(tree.terminalWinner),
    treeTerminalFolded: Array.from(tree.terminalFolded),
  };
}

export async function solveVectorizedParallel(params: ParallelSolveParams): Promise<void> {
  const { tree, store, board, oopRange, ipRange, iterations, onProgress } = params;
  const numWorkers = Math.min(params.numWorkers ?? cpus().length, iterations);

  if (numWorkers <= 1) {
    throw new Error('solveVectorizedParallel requires numWorkers > 1');
  }

  const nc = store.numCombos;
  const totalSize = store.strategySums.length;

  // Serialize tree (small: ~200 numbers for a typical tree)
  const treeData = serializeTree(tree);

  // Worker file path -- use compiled JS from dist/ (avoids tsx loader issues in worker_threads)
  const __dirname = dirname(fileURLToPath(import.meta.url));
  const workerPath = join(__dirname, '..', '..', 'dist', 'vectorized', 'cfr-worker-shared.js');

  // Create SharedArrayBuffer for all workers' strategySums
  // Each worker gets its own slice to avoid contention
  const bytesPerWorker = totalSize * Float32Array.BYTES_PER_ELEMENT;
  const sharedBuffer = new SharedArrayBuffer(bytesPerWorker * numWorkers);

  // Share pre-built equity/blocker matrices via SharedArrayBuffer (read-only, shared by all workers)
  let sharedEquityBuffer: SharedArrayBuffer | undefined;
  if (params.equityMatrix) {
    sharedEquityBuffer = new SharedArrayBuffer(params.equityMatrix.byteLength);
    new Float32Array(sharedEquityBuffer).set(params.equityMatrix);
  }
  let sharedBlockerBuffer: SharedArrayBuffer | undefined;
  if (params.blockerMatrix) {
    sharedBlockerBuffer = new SharedArrayBuffer(params.blockerMatrix.byteLength);
    new Uint8Array(sharedBlockerBuffer).set(params.blockerMatrix);
  }
  let sharedShowdownBuffer: SharedArrayBuffer | undefined;
  if (params.showdownMatrix) {
    sharedShowdownBuffer = new SharedArrayBuffer(params.showdownMatrix.byteLength);
    new Int8Array(sharedShowdownBuffer).set(params.showdownMatrix);
  }

  // Distribute iterations with Linear CFR weighting
  // Each worker gets a contiguous slice of iterations with correct globalIterOffset.
  // Linear weighting ensures sum of worker strategies = sequential weighted strategy.
  const startTime = Date.now();
  const baseIters = Math.floor(iterations / numWorkers);
  const extraIters = iterations % numWorkers;

  // Track progress per worker
  const workerProgress = new Array(numWorkers).fill(0);

  // Spawn worker threads with split iterations + linear weighting.
  const workerPromises: Promise<void>[] = [];
  let cumulativeIters = 0;

  for (let w = 0; w < numWorkers; w++) {
    const workerIters = baseIters + (w < extraIters ? 1 : 0);
    if (workerIters <= 0) continue;

    const globalIterOffset = cumulativeIters;
    cumulativeIters += workerIters;

    workerPromises.push(
      new Promise<void>((resolve, reject) => {
        const worker = new Worker(workerPath, {
          workerData: {
            workerId: w,
            ...treeData,
            numCombos: nc,
            board,
            oopRange,
            ipRange,
            iterations: workerIters,
            globalIterOffset,
            warmupFraction: 0, // No warmup needed with linear weighting
            // SharedArrayBuffer -- worker writes directly into its slice
            sharedStrategySumsBuffer: sharedBuffer,
            strategySliceOffset: w * bytesPerWorker,
            strategySliceLength: totalSize,
            // Pre-built matrices via SharedArrayBuffer (read-only)
            sharedEquityBuffer,
            sharedBlockerBuffer,
            sharedShowdownBuffer,
            equityLength: params.equityMatrix?.length ?? 0,
            blockerLength: params.blockerMatrix?.length ?? 0,
            showdownLength: params.showdownMatrix?.length ?? 0,
          },
        });

        worker.on('message', (msg: any) => {
          if (msg.type === 'progress') {
            workerProgress[msg.workerId] = msg.iter;
          } else if (msg.type === 'done') {
            resolve();
          }
        });

        worker.on('error', reject);
        worker.on('exit', (code) => {
          if (code !== 0) {
            reject(new Error(`Worker ${w} exited with code ${code}`));
          }
        });
      }),
    );
  }

  // Poll progress
  let timer: ReturnType<typeof setInterval> | null = null;
  if (onProgress) {
    timer = setInterval(() => {
      const total = workerProgress.reduce((a, b) => a + b, 0);
      onProgress(total, Date.now() - startTime);
    }, 500);
  }

  // Wait for all workers
  try {
    await Promise.all(workerPromises);

    // Aggregate strategySums from shared memory -- simple sum.
    // With linear weighting, the sum of all workers' weighted strategies
    // equals the full sequential weighted strategy. No re-normalization needed.
    store.strategySums.fill(0);
    for (let w = 0; w < numWorkers; w++) {
      const workerView = new Float32Array(sharedBuffer, w * bytesPerWorker, totalSize);
      for (let i = 0; i < totalSize; i++) {
        store.strategySums[i] += workerView[i];
      }
    }
  } finally {
    if (timer) clearInterval(timer);
  }

  // Final progress report
  if (onProgress) {
    onProgress(iterations, Date.now() - startTime);
  }
}
