/**
 * Solver worker — runs solveVectorized in a Worker thread
 * so the main event-loop is never blocked.
 *
 * Plain ESM (.mjs) — imports cfr-solver from its compiled dist/ directory
 * to avoid needing tsx in the worker thread.
 *
 * Communication protocol (parentPort messages):
 *   Worker → Main:  { type: 'progress', iter, elapsed }
 *   Worker → Main:  { type: 'complete', elapsed, infoSets, exploitability }
 *   Worker → Main:  { type: 'error', message }
 */
import { parentPort, workerData } from 'node:worker_threads';
import { resolve, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Resolve cfr-solver's compiled dist/ via Node module resolution
const require = createRequire(import.meta.url);
const cfrPkgPath = require.resolve('@cardpilot/cfr-solver/package.json');
const cfrDistIndex = pathToFileURL(resolve(dirname(cfrPkgPath), 'dist', 'index.js')).href;

// ─── helpers ───

const RANKS = '23456789TJQKA';
const SUIT_MAP = { c: 0, d: 1, h: 2, s: 3 };

function cardStringToIndex(card) {
  const rank = RANKS.indexOf(card[0].toUpperCase());
  const suit = SUIT_MAP[card[1].toLowerCase()];
  if (rank < 0 || suit === undefined) throw new Error(`Invalid card: ${card}`);
  return rank * 4 + suit;
}

function expandHandClasses(handClasses, expandFn) {
  const result = [];
  const seen = new Set();
  for (const hc of handClasses) {
    const combos = expandFn(hc);
    for (const combo of combos) {
      const c1 = Math.min(combo[0], combo[1]);
      const c2 = Math.max(combo[0], combo[1]);
      const key = `${c1},${c2}`;
      if (seen.has(key)) continue;
      seen.add(key);
      result.push({ combo: [c1, c2], weight: 1.0 });
    }
  }
  return result;
}

// ─── main ───

async function run() {
  const input = workerData;

  // Import from compiled dist/ (not source TS)
  const cfr = await import(cfrDistIndex);
  const { vectorized, getTreeConfig, buildTree, expandHandClassToCombos, exportArrayStoreToJSONL } =
    cfr;
  const {
    flattenTree,
    ArrayStore,
    enumerateValidCombos,
    solveVectorized,
    computeExploitability,
    buildBlockerMatrix,
    buildReachFromRange,
    buildShowdownMatrix,
    applyRakeToTree,
  } = vectorized;

  // 1. Tree config
  const treeConfig = input.treeConfig ? input.treeConfig : getTreeConfig(input.configName);
  if (!treeConfig) throw new Error(`Unknown tree config: ${input.configName}`);

  // 2. Parse board
  const board = input.board.map(cardStringToIndex);

  // 3. Expand ranges
  const oopRange = expandHandClasses(input.oopRange, expandHandClassToCombos);
  const ipRange = expandHandClasses(input.ipRange, expandHandClassToCombos);

  // 4. Build & flatten tree
  const tree = buildTree(treeConfig);
  const flatTree = flattenTree(tree);

  if (treeConfig.rake && treeConfig.rake.percentage > 0) {
    applyRakeToTree(flatTree, treeConfig.rake.percentage, treeConfig.rake.cap);
  }

  // 5. Valid combos & store
  const validCombos = enumerateValidCombos(board);
  const store = new ArrayStore(flatTree, validCombos.numCombos);

  // 6. Solve (synchronous but now in worker thread — doesn't block main)
  const startTime = Date.now();
  solveVectorized({
    tree: flatTree,
    store,
    board,
    oopRange,
    ipRange,
    iterations: input.iterations,
    onProgress: (iter, elapsed) => {
      parentPort.postMessage({ type: 'progress', iter, elapsed });
    },
    startingPot: treeConfig.startingPot,
  });
  const elapsedMs = Date.now() - startTime;

  // 7. Exploitability
  const oopReach = buildReachFromRange(oopRange, validCombos);
  const ipReach = buildReachFromRange(ipRange, validCombos);
  const blockerMatrix = buildBlockerMatrix(validCombos.combos);
  const showdownMatrix = buildShowdownMatrix(validCombos.combos, board, blockerMatrix);

  let exploitabilityPct = Infinity;
  try {
    const devResult = computeExploitability(
      flatTree,
      store,
      showdownMatrix,
      blockerMatrix,
      oopReach,
      ipReach,
      treeConfig.startingPot,
    );
    exploitabilityPct = devResult.exploitabilityPctPot;
  } catch {
    // Non-critical
  }

  // 8. Export results
  const flopLabel = input.board
    .slice(0, 3)
    .map((c) => c.toLowerCase())
    .join('');
  const outputPath = resolve(input.cwd, 'data', 'cfr', input.configName, `${flopLabel}.jsonl`);

  const exportResult = exportArrayStoreToJSONL(store, flatTree, validCombos, {
    outputPath,
    board,
    boardCards: input.board,
    configName: input.configName,
    iterations: input.iterations,
    elapsedMs,
  });

  // 9. Report completion
  parentPort.postMessage({
    type: 'complete',
    elapsed: elapsedMs,
    infoSets: exportResult.infoSets,
    exploitability: exploitabilityPct,
  });
}

run().catch((err) => {
  parentPort.postMessage({
    type: 'error',
    message: err instanceof Error ? err.message : String(err),
  });
});
