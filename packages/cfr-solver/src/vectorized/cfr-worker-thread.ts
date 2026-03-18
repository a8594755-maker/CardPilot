/**
 * Fork worker for parallel CFR+ solving.
 *
 * Receives solve parameters via IPC, rebuilds data structures locally,
 * runs CFR+ iterations, and sends back strategySums for aggregation.
 */

import type { FlatTree } from './flat-tree.js';
import { ArrayStore } from './array-store.js';
import { solveVectorized } from './vectorized-cfr.js';

interface SolveMessage {
  type: 'solve';
  workerId: number;
  // FlatTree fields as plain arrays (TypedArrays lose type in IPC)
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
  globalIterOffset?: number;
  warmupFraction?: number;
}

function reconstructTree(msg: SolveMessage): FlatTree {
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

process.on('message', (msg: SolveMessage) => {
  if (msg.type !== 'solve') return;

  const { workerId, numCombos, board, oopRange, ipRange, iterations } = msg;

  // Reconstruct FlatTree
  const tree = reconstructTree(msg);

  // Create local store (each worker has its own)
  const store = new ArrayStore(tree, numCombos);

  // Run CFR+ iterations -- solveVectorized rebuilds matrices internally
  // (cheap for river: ~200ms, and runs in parallel across workers)
  solveVectorized({
    tree,
    store,
    board,
    oopRange,
    ipRange,
    iterations,
    globalIterOffset: msg.globalIterOffset ?? 0,
    warmupFraction: msg.warmupFraction ?? 0.5,
    onProgress: (iter) => {
      // Report every callback (already rate-limited to every 100 iters by solveVectorized)
      if (process.send) {
        process.send({ type: 'progress', workerId, iter });
      }
    },
  });

  // Send back strategySums for aggregation
  if (process.send) {
    process.send({
      type: 'done',
      workerId,
      strategySumsArr: Array.from(store.strategySums),
    });
  }
});
