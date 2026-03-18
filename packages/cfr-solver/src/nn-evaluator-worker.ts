/**
 * nn-evaluator-worker.ts
 *
 * Worker thread that owns the ONNX InferenceSession for the river CFV model.
 * Communicates with the main thread via SharedArrayBuffer + Atomics.
 *
 * SharedArrayBuffer layout (bytes):
 *   [0..3]   Int32: signal  (0=idle, 1=run, -1=exit)
 *   [4..7]   Int32: reserved
 *   [8 ..]   Float32 data — offsets calculated from constants below
 *
 * After main thread writes inputs and sets signal=1 + notify,
 * worker runs inference, writes outputs, resets signal=0, notifies main thread.
 */

import { workerData, parentPort } from 'worker_threads';
// @ts-expect-error onnxruntime-node is an optional peer dependency
import * as ort from 'onnxruntime-node';

const NUM_COMBOS = 1326;
const BOARD_DIM = 208;
const POT_DIM = 3;

// Byte offsets into the SharedArrayBuffer
const SIGNAL_OFFSET = 0; // Int32[2]
const DATA_OFFSET = 8; // Float32 data starts here
const BOARD_OFFSET = DATA_OFFSET;
const POT_OFFSET = BOARD_OFFSET + BOARD_DIM * 4;
const OOP_OFFSET = POT_OFFSET + POT_DIM * 4;
const IP_OFFSET = OOP_OFFSET + NUM_COMBOS * 4;
const CFV_OOP_OFFSET = IP_OFFSET + NUM_COMBOS * 4;
const CFV_IP_OFFSET = CFV_OOP_OFFSET + NUM_COMBOS * 4;

const { sabBuffer, modelPath } = workerData as {
  sabBuffer: SharedArrayBuffer;
  modelPath: string;
};

const signalArr = new Int32Array(sabBuffer, SIGNAL_OFFSET, 2);
const boardArr = new Float32Array(sabBuffer, BOARD_OFFSET, BOARD_DIM);
const potArr = new Float32Array(sabBuffer, POT_OFFSET, POT_DIM);
const oopArr = new Float32Array(sabBuffer, OOP_OFFSET, NUM_COMBOS);
const ipArr = new Float32Array(sabBuffer, IP_OFFSET, NUM_COMBOS);
const cfvOopArr = new Float32Array(sabBuffer, CFV_OOP_OFFSET, NUM_COMBOS);
const cfvIpArr = new Float32Array(sabBuffer, CFV_IP_OFFSET, NUM_COMBOS);

async function main(): Promise<void> {
  const session = await ort.InferenceSession.create(modelPath, {
    executionProviders: ['cpu'],
    graphOptimizationLevel: 'all',
  });

  // Warm-up inference to JIT-compile the graph
  const dummy = (n: number): ort.Tensor => new ort.Tensor('float32', new Float32Array(n), [1, n]);
  await session.run({
    board_onehot: dummy(BOARD_DIM),
    pot_features: dummy(POT_DIM),
    oop_reach: dummy(NUM_COMBOS),
    ip_reach: dummy(NUM_COMBOS),
  });

  parentPort!.postMessage('ready');

  // Inference loop
  while (true) {
    // Wait until signal changes from 0
    Atomics.wait(signalArr, 0, 0);
    const sig = Atomics.load(signalArr, 0);
    if (sig === -1) break; // Exit signal

    try {
      const results = await session.run({
        board_onehot: new ort.Tensor('float32', boardArr.slice(), [1, BOARD_DIM]),
        pot_features: new ort.Tensor('float32', potArr.slice(), [1, POT_DIM]),
        oop_reach: new ort.Tensor('float32', oopArr.slice(), [1, NUM_COMBOS]),
        ip_reach: new ort.Tensor('float32', ipArr.slice(), [1, NUM_COMBOS]),
      });
      cfvOopArr.set(results['cfv_oop_norm'].data as Float32Array);
      cfvIpArr.set(results['cfv_ip_norm'].data as Float32Array);
    } catch (err) {
      // On error: write zeros so main thread doesn't get stale data
      cfvOopArr.fill(0);
      cfvIpArr.fill(0);
      console.error('[nn-worker] inference error:', err);
    }

    // Reset signal to idle and wake main thread
    Atomics.store(signalArr, 0, 0);
    Atomics.notify(signalArr, 0, 1);
  }
}

main().catch((err) => {
  console.error('[nn-worker] fatal:', err);
  process.exit(1);
});
