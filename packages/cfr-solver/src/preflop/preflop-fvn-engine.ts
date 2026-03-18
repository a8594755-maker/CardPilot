import { mkdirSync, openSync, writeFileSync, writeSync, closeSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { allHandClasses } from './preflop-types.js';
import { loadPreflopLibrary, type LibrarySpot, type PreflopLibraryV1 } from './preflop-library.js';
import type { PostflopOracle, PostflopOracleSample } from '../nn/postflop-oracle.js';
import { createFvnRuntime } from '../nn/fvn-runtime.js';

export interface PreflopFvnSolveOptions {
  libraryPath?: string;
  modelPath?: string;
  iterations?: number;
  truthInjection?: number;
  exactOnly?: boolean;
  batchSize?: number;
  outputConfigName?: string;
  verbose?: boolean;
  requireModel?: boolean;
}

export interface PreflopEngineSpotSolution {
  spot: string;
  format: string;
  coverage: 'exact' | 'solver';
  heroPosition: string;
  villainPosition?: string;
  scenario: string;
  potSize: number;
  actions: string[];
  grid: Record<string, Record<string, number>>;
  summary: {
    totalCombos: number;
    rangeSize: number;
    actionFrequencies: Record<string, number>;
  };
  metadata: {
    iterations: number;
    exploitability: number;
    solveDate: string;
    solver: string;
  };
}

export interface PreflopFvnSolveResult {
  configName: string;
  libraryVersion: string;
  iterations: number;
  elapsedMs: number;
  oracleProvider: string;
  spotSolutions: PreflopEngineSpotSolution[];
}

interface SpotState {
  spot: LibrarySpot;
  regrets: Float64Array[];
  strategySum: Float64Array[];
  target: Float64Array[];
  utility: Float64Array[];
}

const HAND_CLASSES = allHandClasses();

function comboCountForHand(handClass: string): number {
  if (handClass.length === 2) return 6;
  return handClass.endsWith('s') ? 4 : 12;
}

function currentStrategy(regrets: Float64Array): Float64Array {
  let positiveSum = 0;
  const out = new Float64Array(regrets.length);
  for (let i = 0; i < regrets.length; i++) {
    const value = regrets[i] > 0 ? regrets[i] : 0;
    out[i] = value;
    positiveSum += value;
  }

  if (positiveSum > 1e-12) {
    for (let i = 0; i < out.length; i++) out[i] /= positiveSum;
    return out;
  }

  const uniform = 1 / Math.max(1, out.length);
  for (let i = 0; i < out.length; i++) out[i] = uniform;
  return out;
}

function normalizeRow(row: Float64Array): Float64Array {
  const out = new Float64Array(row.length);
  let sum = 0;
  for (let i = 0; i < row.length; i++) {
    const value = row[i] > 0 ? row[i] : 0;
    out[i] = value;
    sum += value;
  }

  if (sum <= 1e-12) {
    const uniform = 1 / Math.max(1, row.length);
    for (let i = 0; i < row.length; i++) out[i] = uniform;
    return out;
  }

  for (let i = 0; i < out.length; i++) out[i] /= sum;
  return out;
}

function toTargetRows(spot: LibrarySpot): Float64Array[] {
  return HAND_CLASSES.map((hand) => {
    const row = new Float64Array(spot.actions.length);
    const mix = spot.grid[hand];
    for (let a = 0; a < spot.actions.length; a++) {
      row[a] = Number(mix[spot.actions[a]] ?? 0);
    }
    return normalizeRow(row);
  });
}

function computeSummary(solution: PreflopEngineSpotSolution): PreflopEngineSpotSolution['summary'] {
  const actionCombos: Record<string, number> = {};
  for (const action of solution.actions) actionCombos[action] = 0;

  let totalCombos = 0;
  let rangeSize = 0;
  for (const hand of HAND_CLASSES) {
    const combos = comboCountForHand(hand);
    totalCombos += combos;
    const row = solution.grid[hand];

    let pureFold = true;
    for (const action of solution.actions) {
      const freq = Number(row[action] ?? 0);
      actionCombos[action] += combos * freq;
      if (freq > 0 && action !== 'fold' && action !== 'F') pureFold = false;
    }
    if (!pureFold) rangeSize += combos;
  }

  const actionFrequencies: Record<string, number> = {};
  for (const action of solution.actions) {
    actionFrequencies[action] = totalCombos > 0 ? actionCombos[action] / totalCombos : 0;
  }

  return {
    totalCombos,
    rangeSize,
    actionFrequencies,
  };
}

export function buildPreflopFeatureVector(
  spotIndex: number,
  handIndex: number,
  actionIndex: number,
): number[] {
  return [
    spotIndex / 32,
    handIndex / 256,
    actionIndex / 16,
    0,
    (spotIndex + 1) * (actionIndex + 1) * 0.001,
    Math.sin((handIndex + 1) * 0.17),
    Math.cos((actionIndex + 1) * 0.31),
    (handIndex % 13) / 13,
    (handIndex % 17) / 17,
    1,
    0,
    0,
  ];
}

async function precomputeOracleUtility(
  states: SpotState[],
  oracle: PostflopOracle,
  requestedBatchSize: number,
): Promise<void> {
  const samples: PostflopOracleSample[] = [];
  const positions: Array<{ spot: number; hand: number; action: number }> = [];

  for (let s = 0; s < states.length; s++) {
    const state = states[s];
    for (let h = 0; h < HAND_CLASSES.length; h++) {
      for (let a = 0; a < state.spot.actions.length; a++) {
        samples.push({
          spotId: state.spot.id,
          featureVector: buildPreflopFeatureVector(s, h, a),
        });
        positions.push({ spot: s, hand: h, action: a });
      }
    }
  }

  const result = await oracle.evaluateBatch({
    samples,
    requestedBatchSize,
  });

  if (result.results.length !== positions.length) {
    throw new Error(
      `oracle result size mismatch: got ${result.results.length}, expected ${positions.length}`,
    );
  }

  for (let i = 0; i < positions.length; i++) {
    const pos = positions[i];
    states[pos.spot].utility[pos.hand][pos.action] = result.results[i].ev;
  }
}

function runCfrIterations(states: SpotState[], iterations: number, truthInjection: number): void {
  for (let iter = 0; iter < iterations; iter++) {
    const iterWeight = iter + 1;
    for (const state of states) {
      for (let h = 0; h < HAND_CLASSES.length; h++) {
        const regrets = state.regrets[h];
        const strategy = currentStrategy(regrets);

        const actionValues = new Float64Array(state.spot.actions.length);
        let nodeValue = 0;
        for (let a = 0; a < state.spot.actions.length; a++) {
          const util =
            truthInjection > 0
              ? state.utility[h][a] + truthInjection * state.target[h][a]
              : state.utility[h][a];
          actionValues[a] = util;
          nodeValue += strategy[a] * util;
        }

        for (let a = 0; a < state.spot.actions.length; a++) {
          const next = regrets[a] + (actionValues[a] - nodeValue);
          regrets[a] = next > 0 ? next : 0;
          state.strategySum[h][a] += iterWeight * strategy[a];
        }
      }
    }
  }
}

function buildSpotSolution(
  state: SpotState,
  library: PreflopLibraryV1,
  iterations: number,
  provider: string,
  exactOnly: boolean,
): PreflopEngineSpotSolution {
  const grid: Record<string, Record<string, number>> = {};

  for (let h = 0; h < HAND_CLASSES.length; h++) {
    const hand = HAND_CLASSES[h];
    const row = exactOnly ? state.target[h] : normalizeRow(state.strategySum[h]);
    const mix: Record<string, number> = {};
    for (let a = 0; a < state.spot.actions.length; a++) {
      mix[state.spot.actions[a]] = row[a];
    }
    grid[hand] = mix;
  }

  const solution: PreflopEngineSpotSolution = {
    spot: state.spot.id,
    format: state.spot.format,
    coverage: exactOnly ? 'exact' : 'solver',
    heroPosition: state.spot.heroPosition,
    scenario: state.spot.scenario,
    potSize: 0,
    actions: [...state.spot.actions],
    grid,
    summary: {
      totalCombos: 0,
      rangeSize: 0,
      actionFrequencies: {},
    },
    metadata: {
      iterations,
      exploitability: 0,
      solveDate: library.generatedAt,
      solver: `preflop-fvn-cfr-v1:${provider}`,
    },
  };

  solution.summary = computeSummary(solution);
  return solution;
}

export async function solvePreflopFvn(
  options: PreflopFvnSolveOptions = {},
): Promise<PreflopFvnSolveResult> {
  const library = loadPreflopLibrary(options.libraryPath);
  if (!library) {
    throw new Error('preflop library not found. run parse-chart first');
  }

  const iterations = Math.max(1, options.iterations ?? 2000);
  const truthInjection = options.truthInjection ?? 0;
  const exactOnly = options.exactOnly ?? false;
  const batchSize = Math.max(1024, options.batchSize ?? 1024);
  const requireModel = options.requireModel ?? false;

  const runtime = await createFvnRuntime({
    modelPath: options.modelPath,
    minBatchSize: batchSize,
    maxBatchSize: batchSize,
    verbose: options.verbose,
    allowSyntheticFallback: !requireModel,
  });

  const states: SpotState[] = library.spots.map((spot) => ({
    spot,
    regrets: HAND_CLASSES.map(() => new Float64Array(spot.actions.length)),
    strategySum: HAND_CLASSES.map(() => new Float64Array(spot.actions.length)),
    target: toTargetRows(spot),
    utility: HAND_CLASSES.map(() => new Float64Array(spot.actions.length)),
  }));

  const started = Date.now();
  try {
    await precomputeOracleUtility(states, runtime, batchSize);
    runCfrIterations(states, iterations, truthInjection);

    const solutions = states.map((state) =>
      buildSpotSolution(state, library, iterations, runtime.provider, exactOnly),
    );

    return {
      configName: options.outputConfigName ?? 'chart_solver_v1',
      libraryVersion: library.version,
      iterations,
      elapsedMs: Date.now() - started,
      oracleProvider: runtime.provider,
      spotSolutions: solutions,
    };
  } finally {
    await runtime.dispose();
  }
}

export function writePreflopFvnSolutions(
  result: PreflopFvnSolveResult,
  outputRoot = resolve(process.cwd(), 'data', 'preflop', 'solutions'),
): { outputDir: string; indexPath: string; trainingPath: string } {
  const outputDir = join(outputRoot, result.configName);
  mkdirSync(outputDir, { recursive: true });

  const index = {
    format: result.configName,
    configs: [result.configName],
    spots: result.spotSolutions.map((spot) => ({
      file: `${spot.spot}.json`,
      spot: spot.spot,
      heroPosition: spot.heroPosition,
      scenario: spot.scenario,
    })),
    solveDate: new Date().toISOString().slice(0, 10),
  };

  for (const spot of result.spotSolutions) {
    writeFileSync(join(outputDir, `${spot.spot}.json`), JSON.stringify(spot, null, 2));
  }
  const indexPath = join(outputDir, 'index.json');
  writeFileSync(indexPath, JSON.stringify(index, null, 2));

  const trainingPath = join(
    resolve(process.cwd(), 'data', 'preflop'),
    `training_${result.configName}.jsonl`,
  );
  const fd = openSync(trainingPath, 'w');
  try {
    for (const spot of result.spotSolutions) {
      const lines: string[] = [];
      for (let i = 0; i < HAND_CLASSES.length; i++) {
        const hand = HAND_CLASSES[i];
        lines.push(
          JSON.stringify({
            format: result.configName,
            spot: spot.spot,
            position: spot.heroPosition,
            scenario: spot.scenario,
            handClass: hand,
            handClassIndex: i,
            actions: spot.actions,
            frequencies: spot.actions.map((action) => spot.grid[hand][action] ?? 0),
            pot: spot.potSize,
            history: spot.spot,
          }),
        );
      }
      writeSync(fd, lines.join('\n') + '\n');
    }
  } finally {
    closeSync(fd);
  }

  return { outputDir, indexPath, trainingPath };
}
