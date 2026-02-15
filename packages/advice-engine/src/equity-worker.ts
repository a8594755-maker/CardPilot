import { parentPort } from "node:worker_threads";
import { calculateEquity, type Card, type EquityResult } from "@cardpilot/poker-evaluator";

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

if (!parentPort) {
  throw new Error("equity-worker must be run in a worker thread");
}

const port = parentPort;

port.on("message", (message: WorkerRequestMessage) => {
  const response: WorkerResultMessage = { id: message.id };

  try {
    response.result = calculateEquity(message.payload);
  } catch (error) {
    response.error = error instanceof Error ? error.message : "Unknown equity worker error";
  }

  port.postMessage(response);
});
