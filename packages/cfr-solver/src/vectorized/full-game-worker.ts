/**
 * Worker process for parallel full-game CFR solving.
 *
 * Spawned via child_process.fork(). Each worker independently builds
 * the complete game tree and runs its assigned iterations (MCCFR or full-enum).
 * Sends back the flop store's strategySums via IPC for aggregation.
 */

import { solveFullGameCFR } from './full-game-cfr.js';
import type { TreeConfig } from '../types.js';
import type { WeightedCombo } from '../integration/preflop-ranges.js';

interface WorkerInput {
  workerId: number;
  board: number[];
  treeConfig: TreeConfig;
  oopRange: WeightedCombo[];
  ipRange: WeightedCombo[];
  iterations: number;
  globalIterOffset: number;
  mccfr: boolean;
}

process.on('message', (data: WorkerInput) => {
  const { workerId, board, treeConfig, oopRange, ipRange, iterations, globalIterOffset, mccfr } =
    data;

  const result = solveFullGameCFR({
    board,
    treeConfig,
    oopRange,
    ipRange,
    iterations,
    mccfr,
    globalIterOffset,
    onProgress: (_phase, detail, pct) => {
      process.send?.({ type: 'progress', workerId, pct });
    },
  });

  // Send flop strategySums back as array (IPC serializes automatically)
  process.send?.({
    type: 'done',
    workerId,
    strategySums: Array.from(result.store.strategySums),
    elapsedMs: result.elapsedMs,
    memoryMB: result.memoryMB,
  });

  // Exit cleanly
  process.exit(0);
});
