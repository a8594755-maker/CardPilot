/**
 * Worker process for parallel WASM CFR solving.
 *
 * Spawned via child_process.fork(). Each worker independently loads the
 * WASM module, builds subtrees, and solves its assigned iteration range.
 * Sends back flop strategySums via IPC for aggregation.
 */

import { solveWithWasm } from './wasm-cfr-bridge.js';
import { deserializeWasmParams } from './wasm-cfr-bridge.js';

process.on('message', async (data: any) => {
  try {
    const params = deserializeWasmParams(data);

    const result = await solveWithWasm(params);

    if (result) {
      process.send?.({
        type: 'done',
        strategySums: Array.from(result.strategySums),
        flopNC: result.flopNC,
      });
    } else {
      process.send?.({ type: 'error', message: 'WASM module not available' });
    }
  } catch (err) {
    process.send?.({ type: 'error', message: (err as Error).message });
  }

  process.exit(0);
});
