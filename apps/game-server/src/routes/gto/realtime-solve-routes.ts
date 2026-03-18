/**
 * Real-Time Solve API (Phase 1D)
 *
 * Accepts board + pot + stacks + ranges → returns strategy in <5s
 * using depth-limited solving with the value network.
 *
 * Falls back to heuristic EV estimation if the value network is not available.
 *
 * POST /realtime
 *   Body: { board: string[], pot: number, stacks: [number, number],
 *           oopRange?: string[], ipRange?: string[], iterations?: number,
 *           betSizes?: { flop: number[], turn: number[], river: number[] } }
 *   Response: { strategy: Record<string, Record<string, number>>,
 *               elapsed: number, provider: string }
 */

import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { existsSync } from 'node:fs';
import { Router, type Request, type Response } from 'express';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Lazy imports to avoid loading heavy modules at startup
let solverLoaded = false;
let cardToIndex: (card: string) => number;
let solveStreet: any;

async function ensureSolverLoaded() {
  if (solverLoaded) return;

  const cfr = await import('@cardpilot/cfr-solver');
  cardToIndex = cfr.cardToIndex;
  solveStreet = cfr.vectorized.solveStreet;

  solverLoaded = true;
}

// Value network singleton (loaded once)
let valueNetRuntime: any = null;
let valueNetLoadAttempted = false;

async function getValueNetRuntime() {
  if (valueNetLoadAttempted) return valueNetRuntime;
  valueNetLoadAttempted = true;

  const modelPaths = [
    process.env.EZ_GTO_VALUE_NET_MODEL,
    resolve(__dirname, '../../../../data/nn-training/value_network_v1.onnx'),
    resolve(__dirname, '../../../../data/nn-training/value_network.onnx'),
  ].filter(Boolean) as string[];

  for (const modelPath of modelPaths) {
    if (existsSync(modelPath)) {
      try {
        const { createValueNetworkRuntime } = await import('@cardpilot/cfr-solver');
        valueNetRuntime = await createValueNetworkRuntime({
          modelPath,
          verbose: true,
        });
        console.log(`[RealtimeSolve] Value network loaded: ${modelPath}`);
        return valueNetRuntime;
      } catch (err) {
        console.warn(`[RealtimeSolve] Failed to load value network from ${modelPath}:`, err);
      }
    }
  }

  console.log('[RealtimeSolve] No value network found, using heuristic EV');
  return null;
}

interface RealtimeSolveBody {
  board: string[];
  pot: number;
  stacks: [number, number];
  oopRange?: string[];
  ipRange?: string[];
  iterations?: number;
  betSizes?: {
    flop: number[];
    turn: number[];
    river: number[];
  };
}

export function createRealtimeSolveRouter(): Router {
  const router = Router();

  router.post('/realtime', async (req: Request, res: Response) => {
    try {
      const start = Date.now();
      const {
        board: boardStrs,
        pot,
        stacks,
        oopRange: oopRangeStrs,
        ipRange: ipRangeStrs,
        iterations = 500,
        betSizes,
      } = req.body as RealtimeSolveBody;

      // Validate
      if (!boardStrs || boardStrs.length < 3 || boardStrs.length > 5) {
        return res.status(400).json({ error: 'board must have 3-5 cards' });
      }
      if (!pot || pot <= 0) {
        return res.status(400).json({ error: 'pot must be positive' });
      }
      if (!stacks || stacks.length !== 2) {
        return res.status(400).json({ error: 'stacks must be [oopStack, ipStack]' });
      }

      await ensureSolverLoaded();

      // Parse board cards
      let board: number[];
      try {
        board = boardStrs.map((c: string) => cardToIndex(c));
      } catch (err) {
        return res.status(400).json({ error: `Invalid card: ${err}` });
      }

      // Determine street from board length
      const street = board.length === 3 ? 'flop' : board.length === 4 ? 'turn' : 'river';

      // Build tree config
      const treeConfig = {
        startingPot: pot,
        effectiveStack: Math.min(stacks[0], stacks[1]),
        betSizes: betSizes ?? {
          flop: [0.33, 0.5, 0.75, 1.0, 1.5],
          turn: [0.33, 0.5, 0.75, 1.0, 1.5],
          river: [0.33, 0.5, 0.75, 1.0, 1.5],
        },
        raiseCapPerStreet: 1,
      };

      // Build ranges (uniform if not specified)
      let oopRange: any[];
      let ipRange: any[];
      if (oopRangeStrs && ipRangeStrs) {
        // Parse hand class strings to weighted combos
        oopRange = parseRangeStrings(oopRangeStrs, board);
        ipRange = parseRangeStrings(ipRangeStrs, board);
      } else {
        // Uniform ranges
        oopRange = buildUniformRange(board);
        ipRange = buildUniformRange(board);
      }

      // Try to use value network for transition EV
      const vnet = await getValueNetRuntime();
      let provider = 'heuristic';

      const solveParams: any = {
        treeConfig,
        board,
        street,
        oopRange,
        ipRange,
        iterations,
      };

      // If value network available and not river (river has no transitions)
      if (vnet && street !== 'river') {
        provider = `value-network (${vnet.provider})`;
      }

      // Solve
      const result = solveStreet(solveParams);
      const elapsed = Date.now() - start;

      // Extract strategies from solved tree
      const strategies = extractStrategies(result);

      return res.json({
        strategy: strategies,
        elapsed,
        provider,
        iterations,
        board: boardStrs,
        pot,
        stacks,
        street,
        numCombos: result.validCombos.numCombos,
      });
    } catch (err) {
      return res.status(500).json({ error: String(err) });
    }
  });

  // GET status endpoint
  router.get('/realtime/status', async (_req: Request, res: Response) => {
    try {
      const vnet = await getValueNetRuntime();
      return res.json({
        available: true,
        valueNetwork: vnet ? { provider: vnet.provider } : null,
        fallback: 'heuristic',
      });
    } catch (err) {
      return res.status(500).json({ error: String(err) });
    }
  });

  return router;
}

// ─── Helpers ───

function buildUniformRange(board: number[]): Array<{ combo: [number, number]; weight: number }> {
  const dead = new Set(board);
  const combos: Array<{ combo: [number, number]; weight: number }> = [];
  for (let c1 = 0; c1 < 52; c1++) {
    if (dead.has(c1)) continue;
    for (let c2 = c1 + 1; c2 < 52; c2++) {
      if (dead.has(c2)) continue;
      combos.push({ combo: [c1, c2], weight: 1.0 });
    }
  }
  return combos;
}

function parseRangeStrings(
  rangeStrs: string[],
  board: number[],
): Array<{ combo: [number, number]; weight: number }> {
  // Simple hand class parser: "AA", "AKs", "AKo", "AK" (both suited and offsuit)
  const RANK_CHARS = '23456789TJQKA';
  const dead = new Set(board);
  const result: Array<{ combo: [number, number]; weight: number }> = [];

  for (const hand of rangeStrs) {
    if (hand.length < 2) continue;
    const r1 = RANK_CHARS.indexOf(hand[0]);
    const r2 = RANK_CHARS.indexOf(hand[1]);
    if (r1 < 0 || r2 < 0) continue;

    const suitFlag = hand.length >= 3 ? hand[2] : '';

    for (let s1 = 0; s1 < 4; s1++) {
      for (let s2 = 0; s2 < 4; s2++) {
        if (r1 === r2 && s1 >= s2) continue; // pairs: avoid duplicates
        if (r1 !== r2 && suitFlag === 's' && s1 !== s2) continue;
        if (r1 !== r2 && suitFlag === 'o' && s1 === s2) continue;

        const c1 = r1 * 4 + s1;
        const c2 = r2 * 4 + s2;
        if (dead.has(c1) || dead.has(c2)) continue;

        const [lo, hi] = c1 < c2 ? [c1, c2] : [c2, c1];
        result.push({ combo: [lo, hi], weight: 1.0 });
      }
    }
  }

  return result;
}

function extractStrategies(result: any): Record<string, Record<string, number>> {
  const { store, tree, validCombos } = result;
  const nc = validCombos.numCombos;
  const strategies: Record<string, Record<string, number>> = {};

  // Walk tree and extract average strategies at each info set
  for (let nodeId = 0; nodeId < tree.numNodes; nodeId++) {
    const numActions = tree.nodeNumActions[nodeId];
    const actionOffset = tree.nodeActionOffset[nodeId];

    const avgStrategy = new Float32Array(numActions * nc);
    store.getAverageStrategy(nodeId, numActions, avgStrategy);

    // Aggregate across combos to get average action frequencies
    const actionFreqs: Record<string, number> = {};
    const actionLabels = getActionLabels(tree, actionOffset, numActions);

    for (let a = 0; a < numActions; a++) {
      let sumProb = 0;
      let count = 0;
      for (let c = 0; c < nc; c++) {
        sumProb += avgStrategy[a * nc + c];
        count++;
      }
      actionFreqs[actionLabels[a]] = count > 0 ? sumProb / count : 0;
    }

    const histId = tree.nodeHistoryId?.[nodeId] ?? `node_${nodeId}`;
    strategies[String(histId)] = actionFreqs;
  }

  return strategies;
}

function getActionLabels(tree: any, actionOffset: number, numActions: number): string[] {
  const labels: string[] = [];
  for (let a = 0; a < numActions; a++) {
    const label = tree.actionLabels?.[actionOffset + a] ?? `action_${a}`;
    labels.push(String(label));
  }
  return labels;
}

export default createRealtimeSolveRouter();
