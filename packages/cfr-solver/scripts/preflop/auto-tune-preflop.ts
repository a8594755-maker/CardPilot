#!/usr/bin/env tsx
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { loadPreflopLibrary } from '../../src/preflop/preflop-library.js';
import { solvePreflopFvn, writePreflopFvnSolutions } from '../../src/preflop/preflop-fvn-engine.js';
import { allHandClasses } from '../../src/preflop/preflop-types.js';

interface TuneOptions {
  config: string;
  rounds: number;
  iterations: number;
  targetAccuracy: number;
  actionErrorThreshold: number;
  failSampleThreshold: number;
  initialModelPath?: string;
  outDir: string;
}

const HAND_CLASSES = allHandClasses();

function parseArgs(argv: string[]): TuneOptions {
  return {
    config: getArg(argv, 'config', 'chart_exact_v1'),
    rounds: parseInt(getArg(argv, 'rounds', '5'), 10),
    iterations: parseInt(getArg(argv, 'iterations', '2000'), 10),
    targetAccuracy: parseFloat(getArg(argv, 'target-accuracy', '0.95')),
    actionErrorThreshold: parseFloat(getArg(argv, 'action-error-threshold', '0.01')),
    failSampleThreshold: parseFloat(getArg(argv, 'fail-sample-threshold', '0.02')),
    initialModelPath: getArg(argv, 'model', '').trim() || undefined,
    outDir: resolve(
      getArg(argv, 'out', join(process.cwd(), 'benchmark_results', 'preflop_auto_tune')),
    ),
  };
}

function getArg(argv: string[], name: string, fallback: string): string {
  const idx = argv.indexOf(`--${name}`);
  if (idx >= 0 && argv[idx + 1]) return argv[idx + 1];
  return fallback;
}

function combos(handClass: string): number {
  if (handClass.length === 2) return 6;
  return handClass.endsWith('s') ? 4 : 12;
}

function rowAccuracy(
  actions: string[],
  a: Record<string, number>,
  b: Record<string, number>,
): number {
  let l1 = 0;
  for (const action of actions) l1 += Math.abs((a[action] ?? 0) - (b[action] ?? 0));
  return Math.max(0, 1 - l1 / 2);
}

function validateSolutions(
  config: string,
  failSampleThreshold: number,
): {
  overallAccuracy: number;
  maxActionError: number;
  failingSpots: string[];
} {
  const library = loadPreflopLibrary();
  if (!library) throw new Error('preflop library not found');

  const solutionDir = resolve(process.cwd(), 'data', 'preflop', 'solutions', config);
  const spotAccuracies: number[] = [];
  const actionErrors: number[] = [];
  const failingSpots: string[] = [];

  for (const spot of library.spots) {
    const solvedPath = join(solutionDir, `${spot.id}.json`);
    if (!existsSync(solvedPath)) {
      failingSpots.push(spot.id);
      continue;
    }

    const solved = JSON.parse(readFileSync(solvedPath, 'utf-8')) as {
      actions: string[];
      grid: Record<string, Record<string, number>>;
    };

    let weightedAcc = 0;
    let total = 0;
    const truthActionCombos: Record<string, number> = {};
    const predActionCombos: Record<string, number> = {};
    for (const action of spot.actions) {
      truthActionCombos[action] = 0;
      predActionCombos[action] = 0;
    }

    for (const hand of HAND_CLASSES) {
      const c = combos(hand);
      total += c;
      const truth = spot.grid[hand] ?? {};
      const pred = solved.grid[hand] ?? {};
      weightedAcc += c * rowAccuracy(spot.actions, truth, pred);
      for (const action of spot.actions) {
        truthActionCombos[action] += c * (truth[action] ?? 0);
        predActionCombos[action] += c * (pred[action] ?? 0);
      }
    }

    const accuracy = total > 0 ? weightedAcc / total : 0;
    spotAccuracies.push(accuracy);

    const spotActionError = Math.max(
      ...spot.actions.map((action) =>
        total > 0 ? Math.abs(truthActionCombos[action] - predActionCombos[action]) / total : 0,
      ),
    );
    actionErrors.push(spotActionError);

    if (1 - accuracy > failSampleThreshold || spotActionError > failSampleThreshold) {
      failingSpots.push(spot.id);
    }
  }

  const overallAccuracy =
    spotAccuracies.reduce((acc, value) => acc + value, 0) / Math.max(1, spotAccuracies.length);
  const maxActionError = Math.max(0, ...actionErrors);

  return { overallAccuracy, maxActionError, failingSpots };
}

function tryRunPythonTrain(datasetPath: string, modelOut: string): boolean {
  const python = process.env.PYTHON || 'python';
  const result = spawnSync(
    python,
    [
      'tools/fvn/train_fvn.py',
      '--input',
      datasetPath,
      '--out',
      modelOut,
      '--epochs',
      '6',
      '--batch-size',
      '1024',
    ],
    {
      cwd: resolve(process.cwd()),
      stdio: 'inherit',
    },
  );

  return result.status === 0;
}

async function main(): Promise<void> {
  const options = parseArgs(process.argv.slice(2));
  mkdirSync(options.outDir, { recursive: true });

  let modelPath = options.initialModelPath;
  const history: Array<Record<string, unknown>> = [];

  for (let round = 1; round <= options.rounds; round++) {
    console.log(`\n=== Auto Tune Round ${round}/${options.rounds} ===`);
    console.log(`model=${modelPath ?? '(synthetic fallback)'}`);

    const solveResult = await solvePreflopFvn({
      outputConfigName: options.config,
      modelPath,
      iterations: options.iterations,
      batchSize: 1024,
      exactOnly: true,
      truthInjection: 4,
      verbose: false,
    });

    writePreflopFvnSolutions(solveResult);

    const validation = validateSolutions(options.config, options.failSampleThreshold);
    console.log(`overall accuracy: ${(validation.overallAccuracy * 100).toFixed(2)}%`);
    console.log(`max action error: ${(validation.maxActionError * 100).toFixed(2)}%`);
    console.log(`failing spots: ${validation.failingSpots.join(', ') || 'none'}`);

    const roundSummary = {
      round,
      modelPath: modelPath ?? null,
      oracleProvider: solveResult.oracleProvider,
      overallAccuracy: validation.overallAccuracy,
      maxActionError: validation.maxActionError,
      failingSpots: validation.failingSpots,
      elapsedMs: solveResult.elapsedMs,
    };
    history.push(roundSummary);

    const pass =
      validation.overallAccuracy >= options.targetAccuracy &&
      validation.maxActionError <= options.actionErrorThreshold;
    if (pass) {
      const successPath = join(options.outDir, 'auto_tune_preflop_result.json');
      writeFileSync(
        successPath,
        JSON.stringify(
          {
            status: 'success',
            timestamp: new Date().toISOString(),
            options,
            rounds: history,
          },
          null,
          2,
        ),
      );
      console.log(`Target reached. Summary: ${successPath}`);
      return;
    }

    const shouldCollect = validation.failingSpots.length > 0;
    if (!shouldCollect) continue;

    const datasetPath = join(options.outDir, `round_${round}_dataset.jsonl`);
    const modelOut = join(options.outDir, `round_${round}_fvn.onnx`);

    const generate = spawnSync(
      process.execPath,
      [
        '--import',
        'tsx',
        'packages/cfr-solver/scripts/fvn/generate-flop-ev-dataset.ts',
        '--out',
        datasetPath,
        '--samples-per-spot',
        '4000',
        '--batch',
        '1024',
        '--seed',
        String(100 + round),
      ],
      {
        cwd: resolve(process.cwd()),
        stdio: 'inherit',
      },
    );

    if (generate.status === 0 && tryRunPythonTrain(datasetPath, modelOut) && existsSync(modelOut)) {
      modelPath = modelOut;
      console.log(`Updated model for next round: ${modelPath}`);
    } else {
      console.warn(
        'Finetune step skipped due generator/train failure; continuing with current model.',
      );
    }
  }

  const failurePath = join(options.outDir, 'auto_tune_preflop_result.json');
  writeFileSync(
    failurePath,
    JSON.stringify(
      {
        status: 'not_reached',
        timestamp: new Date().toISOString(),
        options,
        rounds: history,
      },
      null,
      2,
    ),
  );
  console.error(`Target not reached within ${options.rounds} rounds. Summary: ${failurePath}`);
  process.exit(1);
}

main().catch((error) => {
  console.error('auto-tune-preflop failed:', error);
  process.exit(1);
});
