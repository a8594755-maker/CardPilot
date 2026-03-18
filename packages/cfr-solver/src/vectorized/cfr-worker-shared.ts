/**
 * Worker thread for parallel CFR+ solving using worker_threads.
 *
 * Receives solve parameters via workerData (including SharedArrayBuffers),
 * rebuilds data structures locally, runs CFR+ iterations, and writes
 * strategySums directly into shared memory -- no IPC serialization needed.
 *
 * Uses Linear CFR weighting (not DCFR) for correct parallel aggregation:
 * each worker's weighted strategy sums can be simply added together.
 */

import { workerData, parentPort } from 'worker_threads';
import type { FlatTree } from './flat-tree.js';
import { ArrayStore } from './array-store.js';
import { solveVectorized } from './vectorized-cfr.js';

interface WorkerData {
  workerId: number;
  // FlatTree fields as plain arrays
  treeNumNodes: number;
  treeNumTerminals: number;
  treeNumPlayers: number;
  treeTotalActions: number;
  treeNodePlayer: number[];
  treeNodeStreet: number[];
  treeNodeNumActions: number[];
  treeNodeActionOffset: number[];
  treeNodePot: number[];
  treeNodeStacks: number[];
  treeChildNodeId: number[];
  treeActionType: number[];
  treeTerminalPot: number[];
  treeTerminalIsShowdown: number[];
  treeTerminalFolder: number[];
  treeTerminalStacks: number[];
  treeTerminalWinner: number[];
  treeTerminalFolded: number[];
  numCombos: number;
  board: number[];
  oopRange: Array<{ combo: [number, number]; weight: number }>;
  ipRange: Array<{ combo: [number, number]; weight: number }>;
  iterations: number;
  globalIterOffset: number;
  warmupFraction: number;
  // SharedArrayBuffer for this worker's strategySums output
  sharedStrategySumsBuffer: SharedArrayBuffer;
  strategySliceOffset: number; // byte offset into shared buffer
  strategySliceLength: number; // number of float32 elements
  // Pre-built matrices via SharedArrayBuffer (read-only, shared across workers)
  sharedEquityBuffer?: SharedArrayBuffer;
  sharedBlockerBuffer?: SharedArrayBuffer;
  sharedShowdownBuffer?: SharedArrayBuffer;
  equityLength: number;
  blockerLength: number;
  showdownLength: number;
}

function reconstructTree(msg: WorkerData): FlatTree {
  return {
    numNodes: msg.treeNumNodes,
    numTerminals: msg.treeNumTerminals,
    numPlayers: msg.treeNumPlayers,
    totalActions: msg.treeTotalActions,
    nodePlayer: new Uint8Array(msg.treeNodePlayer),
    nodeStreet: new Uint8Array(msg.treeNodeStreet),
    nodeNumActions: new Uint8Array(msg.treeNodeNumActions),
    nodeActionOffset: new Uint32Array(msg.treeNodeActionOffset),
    nodePot: new Float32Array(msg.treeNodePot),
    nodeStacks: new Float32Array(msg.treeNodeStacks),
    childNodeId: new Int32Array(msg.treeChildNodeId),
    actionType: new Uint8Array(msg.treeActionType),
    terminalPot: new Float32Array(msg.treeTerminalPot),
    terminalIsShowdown: new Uint8Array(msg.treeTerminalIsShowdown),
    terminalFolder: new Int8Array(msg.treeTerminalFolder),
    terminalStacks: new Float32Array(msg.treeTerminalStacks),
    terminalWinner: new Int8Array(msg.treeTerminalWinner),
    terminalFolded: new Uint8Array(msg.treeTerminalFolded),
    nodeHistoryKey: new Array(msg.treeNumNodes).fill(''),
    nodeActionLabels: new Array(msg.treeTotalActions).fill(''),
  };
}

const data = workerData as WorkerData;
const { workerId, numCombos, board, oopRange, ipRange, iterations } = data;

// Reconstruct FlatTree
const tree = reconstructTree(data);

// Create local store (each worker has its own regrets + strategySums)
const store = new ArrayStore(tree, numCombos);

// Reconstruct pre-built matrices from SharedArrayBuffers (zero-copy views)
const equityMatrix = data.sharedEquityBuffer
  ? new Float32Array(data.sharedEquityBuffer, 0, data.equityLength)
  : undefined;
const blockerMatrix = data.sharedBlockerBuffer
  ? new Uint8Array(data.sharedBlockerBuffer, 0, data.blockerLength)
  : undefined;
const showdownMatrix = data.sharedShowdownBuffer
  ? new Int8Array(data.sharedShowdownBuffer, 0, data.showdownLength)
  : undefined;

// Run CFR+ iterations with Linear CFR weighting.
// Each worker builds its own equity cache + WASM instance (fast: ~100ms).
// Linear weighting ensures parallel strategy sums are correctly aggregatable.
solveVectorized({
  tree,
  store,
  board,
  oopRange,
  ipRange,
  iterations,
  globalIterOffset: data.globalIterOffset,
  warmupFraction: data.warmupFraction,
  equityMatrix,
  blockerMatrix,
  showdownMatrix,
  useLinearWeighting: true,
  onProgress: (iter) => {
    if (parentPort) {
      parentPort.postMessage({ type: 'progress', workerId, iter });
    }
  },
});

// Write strategySums directly into shared memory (zero-copy)
const sharedView = new Float32Array(
  data.sharedStrategySumsBuffer,
  data.strategySliceOffset,
  data.strategySliceLength,
);
sharedView.set(store.strategySums);

// Signal completion
if (parentPort) {
  parentPort.postMessage({ type: 'done', workerId });
}
