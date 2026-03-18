#!/usr/bin/env tsx
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import { join, resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';

type FlopMode = 'auto' | 'single_street' | 'full_game';
type RiverEvalMode = 'exact' | 'nn';

interface BaselineOptions {
  samplesDir: string;
  outputDir: string;
  samples: string[];
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

interface SampleResult {
  sample: string;
  accuracy: number;
  elapsedMs: number;
  meanDeviation: number;
  mse: number;
}

const __dirname = dirname(fileURLToPath(import.meta.url));
const DEFAULT_SAMPLES = ['Sample1', 'Sample 2', 'Sample 3'];

function parseArgs(argv: string[]): BaselineOptions {
  const opts: BaselineOptions = {
    samplesDir: resolve(__dirname, '..', '..', '..', 'GTO + sample'),
    outputDir: resolve(process.cwd(), 'benchmark_results', 'baseline'),
    samples: DEFAULT_SAMPLES,
    iterations: 1000,
    threads: 1,
    mccfr: true,
    useWasm: true,
    flopMode: 'auto',
    minItersPerWorker: 250,
    riverEvalMode: 'exact',
    seed: 42,
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    switch (a) {
      case '--samples':
        opts.samplesDir = resolve(argv[++i]);
        break;
      case '--output':
        opts.outputDir = resolve(argv[++i]);
        break;
      case '--sampleList':
        opts.samples = argv[++i]
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean);
        break;
      case '--iterations':
        opts.iterations = parseInt(argv[++i], 10);
        break;
      case '--threads':
        opts.threads = parseInt(argv[++i], 10);
        break;
      case '--mccfr':
        opts.mccfr = true;
        break;
      case '--no-mccfr':
        opts.mccfr = false;
        break;
      case '--useWasm':
      case '--wasm':
        opts.useWasm = true;
        break;
      case '--no-wasm':
        opts.useWasm = false;
        break;
      case '--flopMode': {
        const mode = argv[++i] as FlopMode;
        if (mode !== 'auto' && mode !== 'single_street' && mode !== 'full_game') {
          throw new Error(`Invalid --flopMode '${mode}'`);
        }
        opts.flopMode = mode;
        break;
      }
      case '--minItersPerWorker':
        opts.minItersPerWorker = parseInt(argv[++i], 10);
        break;
      case '--riverEval': {
        const mode = argv[++i] as RiverEvalMode;
        if (mode !== 'exact' && mode !== 'nn') {
          throw new Error(`Invalid --riverEval '${mode}'`);
        }
        opts.riverEvalMode = mode;
        break;
      }
      case '--nnModel':
        opts.nnModelPath = resolve(argv[++i]);
        break;
      case '--seed':
        opts.seed = parseInt(argv[++i], 10);
        break;
      default:
        break;
    }
  }

  return opts;
}

async function runBenchmarkForSample(
  options: BaselineOptions,
  sampleName: string,
  outputDir: string,
): Promise<void> {
  const scriptPath = resolve(__dirname, 'benchmark-gtoplus.ts');
  const args = [
    '--import',
    'tsx',
    scriptPath,
    '--samples',
    options.samplesDir,
    '--sample',
    sampleName,
    '--iterations',
    String(options.iterations),
    '--threads',
    String(options.threads),
    '--output',
    outputDir,
    '--flopMode',
    options.flopMode,
    '--minItersPerWorker',
    String(options.minItersPerWorker),
    '--riverEval',
    options.riverEvalMode,
    '--seed',
    String(options.seed),
  ];
  if (options.mccfr) args.push('--mccfr');
  if (options.useWasm) args.push('--useWasm');
  if (options.nnModelPath) args.push('--nnModel', options.nnModelPath);

  await new Promise<void>((resolveRun, rejectRun) => {
    const child = spawn(process.execPath, args, {
      stdio: 'inherit',
      cwd: resolve(__dirname, '..', '..', '..'),
    });
    child.on('exit', (code) => {
      if (code === 0) resolveRun();
      else rejectRun(new Error(`benchmark failed for ${sampleName} (exit=${code})`));
    });
    child.on('error', rejectRun);
  });
}

function readSampleResult(outputDir: string, sampleName: string): SampleResult {
  const filePath = join(outputDir, `${sampleName}.json`);
  if (!existsSync(filePath)) {
    throw new Error(`Missing output JSON: ${filePath}`);
  }

  const raw = readFileSync(filePath, 'utf8');
  const parsed = JSON.parse(raw) as {
    sample: string;
    accuracy: number;
    elapsedMs: number;
    meanDeviation: number;
    mse: number;
  };

  return {
    sample: parsed.sample,
    accuracy: parsed.accuracy,
    elapsedMs: parsed.elapsedMs,
    meanDeviation: parsed.meanDeviation,
    mse: parsed.mse,
  };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (!existsSync(options.outputDir)) {
    mkdirSync(options.outputDir, { recursive: true });
  }

  console.log('\n=== Baseline Benchmark ===');
  console.log(`samplesDir=${options.samplesDir}`);
  console.log(`outputDir=${options.outputDir}`);
  console.log(`samples=${options.samples.join(', ')}`);
  console.log(`iterations=${options.iterations}, threads=${options.threads}`);
  console.log(`mccfr=${options.mccfr}, wasm=${options.useWasm}, flopMode=${options.flopMode}`);
  console.log(`riverEval=${options.riverEvalMode}, minItersPerWorker=${options.minItersPerWorker}`);

  const results: SampleResult[] = [];
  for (const sample of options.samples) {
    await runBenchmarkForSample(options, sample, options.outputDir);
    results.push(readSampleResult(options.outputDir, sample));
  }

  const avgAccuracy = results.reduce((s, r) => s + r.accuracy, 0) / results.length;
  const minAccuracy = Math.min(...results.map((r) => r.accuracy));
  const totalElapsedMs = results.reduce((s, r) => s + r.elapsedMs, 0);

  console.log('\nSample            Accuracy    Time(s)   MeanDev');
  console.log('------------------------------------------------');
  for (const r of results) {
    console.log(
      `${r.sample.padEnd(16)} ${r.accuracy.toFixed(2).padStart(8)}  ${(r.elapsedMs / 1000).toFixed(2).padStart(8)}  ${(r.meanDeviation * 100).toFixed(2).padStart(7)}%`,
    );
  }

  const summary = {
    timestamp: new Date().toISOString(),
    config: options,
    aggregate: {
      avgAccuracy,
      minAccuracy,
      totalElapsedMs,
    },
    samples: results,
  };
  const summaryPath = join(options.outputDir, 'baseline-summary.json');
  writeFileSync(summaryPath, JSON.stringify(summary, null, 2));

  console.log('\nSummary:');
  console.log(`avgAccuracy=${avgAccuracy.toFixed(2)}%`);
  console.log(`minAccuracy=${minAccuracy.toFixed(2)}%`);
  console.log(`totalTime=${(totalElapsedMs / 1000).toFixed(2)}s`);
  console.log(`saved=${summaryPath}`);
}

main().catch((err) => {
  console.error('baseline failed:', err);
  process.exit(1);
});
