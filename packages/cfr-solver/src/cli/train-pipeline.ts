#!/usr/bin/env tsx
/**
 * Training Pipeline CLI — orchestrates CFR data → NN training → calibration.
 *
 * Commands:
 *   generate          — Convert CFR solver data to NN training samples
 *   generate-preflop  — Convert preflop CFR data to NN training samples
 *   train             — Train the neural network from generated data
 *   finetune          — Incrementally train on new flops
 *   calibrate         — Evaluate model against CFR ground truth
 *   full              — Run generate → train → calibrate end-to-end
 *
 * Usage:
 *   npx tsx packages/cfr-solver/src/cli/train-pipeline.ts <command> [options]
 */

import { resolve } from 'node:path';
import { existsSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const __dirname = fileURLToPath(new URL('.', import.meta.url));

function findProjectRoot(): string {
  const fromFile = resolve(__dirname, '../../../../');
  if (existsSync(resolve(fromFile, 'data/preflop_charts.json'))) return fromFile;
  if (existsSync(resolve(process.cwd(), 'data/preflop_charts.json'))) return process.cwd();
  const parent = resolve(process.cwd(), '../..');
  if (existsSync(resolve(parent, 'data/preflop_charts.json'))) return parent;
  return process.cwd();
}

const PROJECT_ROOT = findProjectRoot();

// Parse args
const args = process.argv.slice(2);
const command = args[0];

function getArg(name: string, defaultVal: string): string {
  const idx = args.indexOf(`--${name}`);
  if (idx !== -1 && args[idx + 1]) return args[idx + 1];
  return defaultVal;
}
function getNumArg(name: string, defaultVal: number): number {
  const idx = args.indexOf(`--${name}`);
  if (idx !== -1 && args[idx + 1]) return parseInt(args[idx + 1], 10);
  return defaultVal;
}
function hasFlag(name: string): boolean {
  return args.includes(`--${name}`);
}

function printUsage(): void {
  console.log(`
Usage: npx tsx train-pipeline.ts <command> [options]

Commands:
  generate          Convert postflop CFR data to NN training samples
  generate-preflop  Convert preflop CFR data to NN training samples
  train             Train the neural network from generated data
  finetune          Incrementally train on new flops
  calibrate         Evaluate model against CFR ground truth
  full              Run generate → train → calibrate end-to-end

Common options:
  --config <name>     Tree config name (default: pipeline_srp)
  --cfr-dir <path>    Path to CFR data directory
  --output <path>     Output directory for training data / model

Generate options:
  --samples-per-bucket <N>  Combos per bucket (default: 3)
  --workers <N>             Worker threads (default: CPU-1)
  --river-samples <N>       River cards to sample per turn (default: 10)
  --min-divergence <F>      Skip near-uniform strategies (default: 0.05)

Train options:
  --data <path>       Training data directory
  --hidden <sizes>    Hidden layer sizes (default: 256,128)
  --out <path>        Model output path
  --batch-size <N>    Batch size (default: 256)
  --max-epochs <N>    Max training epochs/passes (default: 100)
  --lr <F>            Initial learning rate (default: 0.01)
  --streaming         Enable streaming mode for large datasets
  --val-by-flop       Validate by held-out flops
  --val-flop-count <N>  Flops to hold out (default: 100)

Finetune options:
  --base <path>       Base model to fine-tune
  --new-data <path>   New training data directory
  --out <path>        Output model path
  --lr <F>            Learning rate (default: 0.001)

Generate-preflop options:
  --preflop-dir <path>  Preflop training data directory (default: data/preflop)
  --output <path>       Output directory (default: data/training/preflop)
  --configs <names>     Comma-separated config names (default: all 3 configs)

Calibrate options:
  --model <path>      Model to evaluate
  --cfr-dir <path>    CFR data directory
  --flops <N>         Number of flops to calibrate (default: 50)
`);
}

// ── Generate ──

function runGenerate(): void {
  const configName = getArg('config', 'pipeline_srp');
  const cfrDir = getArg('cfr-dir', resolve(PROJECT_ROOT, `data/cfr/pipeline_hu_srp_50bb`));
  const outputDir = getArg('output', resolve(PROJECT_ROOT, 'data/training/cfr_srp'));
  const samplesPerBucket = getNumArg('samples-per-bucket', 3);
  const workers = getNumArg('workers', 1);
  const riverSamples = getNumArg('river-samples', 10);
  const minDivergence = getArg('min-divergence', '0.05');

  const script = resolve(__dirname, '../scripts/cfr-to-training-data.ts');

  console.log('╔═══════════════════════════════════════════╗');
  console.log('║   Step 1: Generate Training Data          ║');
  console.log('╚═══════════════════════════════════════════╝');

  const tsxArgs = [
    script,
    '--cfr-dir',
    cfrDir,
    '--output',
    outputDir,
    '--config',
    configName,
    '--samples-per-bucket',
    String(samplesPerBucket),
    '--workers',
    String(workers),
    '--river-samples',
    String(riverSamples),
    '--min-divergence',
    minDivergence,
  ];

  const r = spawnSync(process.execPath, ['--import', 'tsx', ...tsxArgs], {
    cwd: PROJECT_ROOT,
    stdio: 'inherit',
  });
  if (r.status !== 0) process.exit(r.status ?? 1);
}

// ── Generate preflop ──

function runGeneratePreflop(): void {
  const preflopDir = getArg('preflop-dir', resolve(PROJECT_ROOT, 'data/preflop'));
  const outputDir = getArg('output', resolve(PROJECT_ROOT, 'data/training/preflop'));
  const configs = getArg('configs', 'cash_6max_100bb,cash_6max_50bb,cash_6max_100bb_ante');

  const script = resolve(__dirname, '../scripts/preflop-to-training-data.ts');

  const tsxArgs = [
    script,
    '--preflop-dir',
    preflopDir,
    '--output',
    outputDir,
    '--configs',
    configs,
  ];

  const r = spawnSync(process.execPath, ['--import', 'tsx', ...tsxArgs], {
    cwd: PROJECT_ROOT,
    stdio: 'inherit',
  });
  if (r.status !== 0) process.exit(r.status ?? 1);
}

// ── Train ──

function runTrain(): void {
  const srpDir = resolve(PROJECT_ROOT, 'data/training/cfr_srp');
  const threeBetDir = resolve(PROJECT_ROOT, 'data/training/cfr_3bet');
  const defaultData = existsSync(threeBetDir) ? `${srpDir},${threeBetDir}` : srpDir;
  const dataDir = getArg('data', defaultData);
  const hidden = getArg('hidden', '256,128');
  const outPath = getArg('out', resolve(PROJECT_ROOT, 'models/cfr-combined-v3.json'));
  const batchSize = getNumArg('batch-size', 256);
  const maxEpochs = getNumArg('max-epochs', 100);
  const lr = getArg('lr', '0.01');
  const streaming = hasFlag('streaming');
  const valByFlop = hasFlag('val-by-flop');
  const valFlopCount = getNumArg('val-flop-count', 100);
  const filesPerPass = getNumArg('files-per-pass', 0);

  const script = resolve(PROJECT_ROOT, 'packages/fast-model/src/trainer.ts');

  console.log('╔═══════════════════════════════════════════╗');
  console.log('║   Step 2: Train Model                     ║');
  console.log('╚═══════════════════════════════════════════╝');

  const tsxArgs = [
    script,
    '--v2',
    '--data',
    dataDir,
    '--hidden',
    hidden,
    '--out',
    outPath,
    '--batch-size',
    String(batchSize),
    '--max-epochs',
    String(maxEpochs),
    '--lr',
    lr,
    '--disable-hard-mining',
  ];

  if (streaming) tsxArgs.push('--streaming');
  if (valByFlop) tsxArgs.push('--val-by-flop');
  if (valByFlop) tsxArgs.push('--val-flop-count', String(valFlopCount));
  if (filesPerPass > 0) tsxArgs.push('--files-per-pass', String(filesPerPass));

  const r = spawnSync(process.execPath, ['--import', 'tsx', ...tsxArgs], {
    cwd: PROJECT_ROOT,
    stdio: 'inherit',
  });
  if (r.status !== 0) process.exit(r.status ?? 1);
}

// ── Finetune ──

function runFinetune(): void {
  const baseModel = getArg('base', '');
  const newData = getArg('new-data', '');
  const outPath = getArg('out', resolve(PROJECT_ROOT, 'models/cfr-srp-v3-finetuned.json'));
  const lr = getArg('lr', '0.001');
  const maxEpochs = getNumArg('max-epochs', 30);
  const batchSize = getNumArg('batch-size', 256);

  if (!baseModel) {
    console.error('Error: --base <model.json> is required for finetune');
    process.exit(1);
  }
  if (!newData) {
    console.error('Error: --new-data <dir> is required for finetune');
    process.exit(1);
  }

  const script = resolve(PROJECT_ROOT, 'packages/fast-model/src/trainer.ts');

  console.log('╔═══════════════════════════════════════════╗');
  console.log('║   Finetune Model                          ║');
  console.log('╚═══════════════════════════════════════════╝');

  const tsxArgs = [
    script,
    '--v2',
    '--data',
    newData,
    '--out',
    outPath,
    '--resume',
    baseModel,
    '--lr',
    lr,
    '--max-epochs',
    String(maxEpochs),
    '--batch-size',
    String(batchSize),
    '--disable-hard-mining',
    '--streaming',
    '--val-by-flop',
  ];

  const r = spawnSync(process.execPath, ['--import', 'tsx', ...tsxArgs], {
    cwd: PROJECT_ROOT,
    stdio: 'inherit',
  });
  if (r.status !== 0) process.exit(r.status ?? 1);
}

// ── Calibrate ──

async function runCalibrate(): Promise<void> {
  const modelPath = getArg('model', resolve(PROJECT_ROOT, 'models/cfr-srp-v3.json'));
  const cfrDir = getArg('cfr-dir', resolve(PROJECT_ROOT, 'data/cfr/pipeline_hu_srp_50bb'));
  const configName = getArg('config', 'pipeline_srp');
  const maxFlops = getNumArg('flops', 50);
  const chartsPath = resolve(PROJECT_ROOT, 'data/preflop_charts.json');

  console.log('╔═══════════════════════════════════════════╗');
  console.log('║   Step 3: Calibrate Model                 ║');
  console.log('╚═══════════════════════════════════════════╝');
  console.log(`  Model: ${modelPath}`);
  console.log(`  CFR:   ${cfrDir}`);
  console.log(`  Flops: ${maxFlops}`);

  const { calibrate, printCalibrationReport } = await import('../scripts/calibrate-model.js');
  const result = calibrate(modelPath, cfrDir, configName as any, chartsPath, maxFlops);
  printCalibrationReport(result);

  // Save calibration report
  const reportPath = modelPath.replace('.json', '-calibration.json');
  writeFileSync(reportPath, JSON.stringify(result, null, 2));
  console.log(`\nCalibration report saved: ${reportPath}`);
}

// ── Full pipeline ──

async function runFull(): Promise<void> {
  console.log('╔═══════════════════════════════════════════╗');
  console.log('║   Full Pipeline: Generate → Train → Cal.  ║');
  console.log('╚═══════════════════════════════════════════╝\n');

  runGenerate();
  console.log();
  runTrain();
  console.log();
  await runCalibrate();
}

// ── Main ──

async function main(): Promise<void> {
  if (!command || command === '--help' || command === '-h') {
    printUsage();
    process.exit(0);
  }

  switch (command) {
    case 'generate':
      runGenerate();
      break;
    case 'generate-preflop':
      runGeneratePreflop();
      break;
    case 'train':
      runTrain();
      break;
    case 'finetune':
      runFinetune();
      break;
    case 'calibrate':
      await runCalibrate();
      break;
    case 'full':
      await runFull();
      break;
    default:
      console.error(`Unknown command: ${command}`);
      printUsage();
      process.exit(1);
  }
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
