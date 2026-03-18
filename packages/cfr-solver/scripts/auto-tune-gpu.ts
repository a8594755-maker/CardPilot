#!/usr/bin/env tsx
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import { join, resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';

type FlopMode = 'auto' | 'single_street' | 'full_game';
type RiverEvalMode = 'exact' | 'nn';

interface TuneOptions {
  samplesDir: string;
  outputDir: string;
  targetAccuracy: number;
  minSpeedup: number;
  sampleList: string[];
}

interface TrialConfig {
  name: string;
  iterations: number;
  threads: number;
  mccfr: boolean;
  useWasm: boolean;
  flopMode: FlopMode;
  minItersPerWorker: number;
  riverEvalMode: RiverEvalMode;
  nnModelPath?: string;
  seed: number;
}

interface SummaryFile {
  aggregate: {
    avgAccuracy: number;
    minAccuracy: number;
    totalElapsedMs: number;
  };
}

const __dirname = dirname(fileURLToPath(import.meta.url));

function parseArgs(argv: string[]): TuneOptions {
  const opts: TuneOptions = {
    samplesDir: resolve(__dirname, '..', '..', '..', 'GTO + sample'),
    outputDir: resolve(process.cwd(), 'benchmark_results', 'auto_tune'),
    targetAccuracy: 95,
    minSpeedup: 1.0,
    sampleList: ['Sample1', 'Sample 2', 'Sample 3'],
  };

  for (let i = 0; i < argv.length; i++) {
    switch (argv[i]) {
      case '--samples':
        opts.samplesDir = resolve(argv[++i]);
        break;
      case '--output':
        opts.outputDir = resolve(argv[++i]);
        break;
      case '--targetAccuracy':
        opts.targetAccuracy = parseFloat(argv[++i]);
        break;
      case '--minSpeedup':
        opts.minSpeedup = parseFloat(argv[++i]);
        break;
      case '--sampleList':
        opts.sampleList = argv[++i]
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean);
        break;
      default:
        break;
    }
  }

  return opts;
}

async function runTrial(
  options: TuneOptions,
  config: TrialConfig,
  trialIndex: number,
): Promise<SummaryFile> {
  const trialDir = join(
    options.outputDir,
    `trial_${String(trialIndex + 1).padStart(2, '0')}_${config.name}`,
  );
  if (!existsSync(trialDir)) mkdirSync(trialDir, { recursive: true });

  const scriptPath = resolve(__dirname, 'benchmark-baseline.ts');
  const args = [
    '--import',
    'tsx',
    scriptPath,
    '--samples',
    options.samplesDir,
    '--output',
    trialDir,
    '--sampleList',
    options.sampleList.join(','),
    '--iterations',
    String(config.iterations),
    '--threads',
    String(config.threads),
    '--flopMode',
    config.flopMode,
    '--minItersPerWorker',
    String(config.minItersPerWorker),
    '--riverEval',
    config.riverEvalMode,
    '--seed',
    String(config.seed),
  ];
  if (config.mccfr) args.push('--mccfr');
  else args.push('--no-mccfr');
  if (config.useWasm) args.push('--useWasm');
  else args.push('--no-wasm');
  if (config.nnModelPath) args.push('--nnModel', config.nnModelPath);

  await new Promise<void>((resolveRun, rejectRun) => {
    const child = spawn(process.execPath, args, {
      stdio: 'inherit',
      cwd: resolve(__dirname, '..', '..', '..'),
    });
    child.on('exit', (code) => {
      if (code === 0) resolveRun();
      else rejectRun(new Error(`trial ${config.name} failed (exit=${code})`));
    });
    child.on('error', rejectRun);
  });

  const summaryPath = join(trialDir, 'baseline-summary.json');
  if (!existsSync(summaryPath)) {
    throw new Error(`missing summary for trial ${config.name}`);
  }
  return JSON.parse(readFileSync(summaryPath, 'utf8')) as SummaryFile;
}

function defaultTrialConfigs(): TrialConfig[] {
  return [
    {
      name: 'fg_wasm_mccfr_i500_t1',
      iterations: 500,
      threads: 1,
      mccfr: true,
      useWasm: true,
      flopMode: 'full_game',
      minItersPerWorker: 250,
      riverEvalMode: 'exact',
      seed: 42,
    },
    {
      name: 'fg_wasm_mccfr_i1000_t1',
      iterations: 1000,
      threads: 1,
      mccfr: true,
      useWasm: true,
      flopMode: 'full_game',
      minItersPerWorker: 250,
      riverEvalMode: 'exact',
      seed: 43,
    },
    {
      name: 'fg_wasm_mccfr_i2000_t1',
      iterations: 2000,
      threads: 1,
      mccfr: true,
      useWasm: true,
      flopMode: 'full_game',
      minItersPerWorker: 250,
      riverEvalMode: 'exact',
      seed: 44,
    },
    {
      name: 'fg_wasm_mccfr_i4000_t1',
      iterations: 4000,
      threads: 1,
      mccfr: true,
      useWasm: true,
      flopMode: 'full_game',
      minItersPerWorker: 250,
      riverEvalMode: 'exact',
      seed: 45,
    },
    {
      name: 'fg_wasm_mccfr_i6000_t1',
      iterations: 6000,
      threads: 1,
      mccfr: true,
      useWasm: true,
      flopMode: 'full_game',
      minItersPerWorker: 250,
      riverEvalMode: 'exact',
      seed: 46,
    },
    {
      name: 'fg_wasm_mccfr_i8000_t1',
      iterations: 8000,
      threads: 1,
      mccfr: true,
      useWasm: true,
      flopMode: 'full_game',
      minItersPerWorker: 250,
      riverEvalMode: 'exact',
      seed: 47,
    },
    {
      name: 'fg_wasm_mccfr_i10000_t1',
      iterations: 10000,
      threads: 1,
      mccfr: true,
      useWasm: true,
      flopMode: 'full_game',
      minItersPerWorker: 250,
      riverEvalMode: 'exact',
      seed: 48,
    },
    {
      name: 'fg_wasm_mccfr_i12000_t1',
      iterations: 12000,
      threads: 1,
      mccfr: true,
      useWasm: true,
      flopMode: 'full_game',
      minItersPerWorker: 250,
      riverEvalMode: 'exact',
      seed: 49,
    },
    {
      name: 'fg_wasm_mccfr_i15000_t1',
      iterations: 15000,
      threads: 1,
      mccfr: true,
      useWasm: true,
      flopMode: 'full_game',
      minItersPerWorker: 250,
      riverEvalMode: 'exact',
      seed: 50,
    },
    {
      name: 'fg_wasm_mccfr_i20000_t1',
      iterations: 20000,
      threads: 1,
      mccfr: true,
      useWasm: true,
      flopMode: 'full_game',
      minItersPerWorker: 250,
      riverEvalMode: 'exact',
      seed: 51,
    },
    {
      name: 'fg_wasm_fullenum_i300_t1',
      iterations: 300,
      threads: 1,
      mccfr: false,
      useWasm: true,
      flopMode: 'full_game',
      minItersPerWorker: 250,
      riverEvalMode: 'exact',
      seed: 52,
    },
    {
      name: 'fg_wasm_mccfr_i3000_t1_nn',
      iterations: 3000,
      threads: 1,
      mccfr: true,
      useWasm: true,
      flopMode: 'full_game',
      minItersPerWorker: 250,
      riverEvalMode: 'nn',
      seed: 53,
    },
  ];
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (!existsSync(options.outputDir)) mkdirSync(options.outputDir, { recursive: true });

  console.log('\n=== Auto Tune GPU/NN ===');
  console.log(`samplesDir=${options.samplesDir}`);
  console.log(`outputDir=${options.outputDir}`);
  console.log(`targetAccuracy=${options.targetAccuracy}`);
  console.log(`minSpeedup=${options.minSpeedup}`);
  console.log(`samples=${options.sampleList.join(', ')}`);

  const trials = defaultTrialConfigs();
  let baselineTimeMs = 0;
  let bestIdx = -1;
  let bestScore = -Infinity;
  let bestSummary: SummaryFile | null = null;

  for (let i = 0; i < trials.length; i++) {
    const config = trials[i];
    console.log(`\n--- Trial ${i + 1}/${trials.length}: ${config.name} ---`);
    const summary = await runTrial(options, config, i);

    if (i === 0) baselineTimeMs = summary.aggregate.totalElapsedMs;
    const speedup = baselineTimeMs > 0 ? baselineTimeMs / summary.aggregate.totalElapsedMs : 1;
    const minAcc = summary.aggregate.minAccuracy;
    const avgAcc = summary.aggregate.avgAccuracy;
    const score = minAcc * 1000 + speedup;

    console.log(
      `Result: minAcc=${minAcc.toFixed(2)} avgAcc=${avgAcc.toFixed(2)} ` +
        `time=${(summary.aggregate.totalElapsedMs / 1000).toFixed(2)}s speedup=${speedup.toFixed(2)}x`,
    );

    if (score > bestScore) {
      bestScore = score;
      bestIdx = i;
      bestSummary = summary;
    }

    if (minAcc >= options.targetAccuracy && speedup >= options.minSpeedup) {
      console.log('\nTarget reached. Stopping auto-tune.');
      const success = {
        timestamp: new Date().toISOString(),
        status: 'success',
        winningTrial: config,
        summary,
      };
      writeFileSync(
        join(options.outputDir, 'auto-tune-result.json'),
        JSON.stringify(success, null, 2),
      );
      return;
    }
  }

  const failure = {
    timestamp: new Date().toISOString(),
    status: 'not_reached',
    targetAccuracy: options.targetAccuracy,
    minSpeedup: options.minSpeedup,
    bestTrialIndex: bestIdx,
    bestTrial: bestIdx >= 0 ? trials[bestIdx] : null,
    bestSummary,
  };
  writeFileSync(join(options.outputDir, 'auto-tune-result.json'), JSON.stringify(failure, null, 2));

  console.error('\nTarget not reached within trial budget.');
  process.exit(1);
}

main().catch((err) => {
  console.error('auto-tune failed:', err);
  process.exit(1);
});
