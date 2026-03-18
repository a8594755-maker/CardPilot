#!/usr/bin/env tsx
/**
 * Pre-sample training data for Value Network V2.
 * Samples N lines per flop file for even coverage.
 * Uses streaming to avoid OOM.
 *
 * Usage:
 *   npx tsx scripts/presample-training.ts \
 *     --input data/training/cfr_srp_v2/ \
 *     --output data/training/cfr_srp_v2_sampled/ \
 *     --samples-per-file 1100 \
 *     --val-flops 10
 */

import {
  createReadStream,
  createWriteStream,
  readdirSync,
  mkdirSync,
  existsSync,
  statSync,
} from 'node:fs';
import { join } from 'node:path';
import { createInterface } from 'node:readline';

// ── CLI args ──
const argv = process.argv.slice(2);
function getArg(name: string, fallback: string): string {
  const idx = argv.indexOf(name);
  return idx >= 0 && argv[idx + 1] ? argv[idx + 1] : fallback;
}

const inputDir = getArg('--input', 'data/training/cfr_srp_v2/');
const outputDir = getArg('--output', 'data/training/cfr_srp_v2_sampled/');
const samplesPerFile = parseInt(getArg('--samples-per-file', '1100'), 10);
const valFlopCount = parseInt(getArg('--val-flops', '10'), 10);
const valSamplesPerFlop = parseInt(getArg('--val-samples-per-flop', '5000'), 10);

/**
 * Reservoir sample N lines from a file using streaming.
 * Returns array of raw JSONL strings.
 */
async function reservoirSampleFile(filepath: string, n: number): Promise<string[]> {
  const reservoir: string[] = [];
  let seen = 0;

  const rl = createInterface({
    input: createReadStream(filepath, { encoding: 'utf-8', highWaterMark: 64 * 1024 }),
    crlfDelay: Infinity,
  });

  for await (const line of rl) {
    if (!line.trim()) continue;

    if (seen < n) {
      reservoir.push(line);
    } else {
      const j = Math.floor(Math.random() * (seen + 1));
      if (j < n) {
        reservoir[j] = line;
      }
    }
    seen++;
  }

  return reservoir;
}

async function main() {
  const startTime = Date.now();

  // Collect all flop files
  const allFiles = readdirSync(inputDir)
    .filter((f) => /^flop_\d+\.jsonl$/.test(f))
    .sort();

  console.log(`Found ${allFiles.length} flop files in ${inputDir}`);

  // Pick validation flops (evenly spaced for diversity)
  const step = Math.max(1, Math.floor(allFiles.length / valFlopCount));
  const valIndices = new Set<number>();
  for (let i = 0; i < valFlopCount; i++) {
    valIndices.add(Math.min(i * step, allFiles.length - 1));
  }

  const valFiles: string[] = [];
  const trainFiles: string[] = [];
  for (let i = 0; i < allFiles.length; i++) {
    if (valIndices.has(i)) {
      valFiles.push(allFiles[i]);
    } else {
      trainFiles.push(allFiles[i]);
    }
  }

  console.log(`Train files: ${trainFiles.length}, Val files: ${valFiles.length}`);
  console.log(
    `Samples per train file: ${samplesPerFile} (target total: ~${(trainFiles.length * samplesPerFile).toLocaleString()})`,
  );
  console.log(`Samples per val file: ${valSamplesPerFlop}`);

  // Create output directory
  if (!existsSync(outputDir)) mkdirSync(outputDir, { recursive: true });

  // ── Phase 1: Sample from each train file ──
  console.log('\n--- Phase 1: Sampling training data ---');
  const trainOutPath = join(outputDir, 'train.jsonl');
  const trainStream = createWriteStream(trainOutPath, { encoding: 'utf-8' });
  let totalTrainSamples = 0;

  for (let i = 0; i < trainFiles.length; i++) {
    const filepath = join(inputDir, trainFiles[i]);
    const samples = await reservoirSampleFile(filepath, samplesPerFile);

    for (const s of samples) {
      trainStream.write(s + '\n');
    }
    totalTrainSamples += samples.length;

    if ((i + 1) % 100 === 0 || i === trainFiles.length - 1) {
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(0);
      console.log(
        `  [${i + 1}/${trainFiles.length}] ${totalTrainSamples.toLocaleString()} samples (${elapsed}s)`,
      );
    }
  }

  // Wait for train stream to finish
  trainStream.end();
  await new Promise<void>((resolve) => trainStream.on('finish', resolve));
  const trainSizeMB = (statSync(trainOutPath).size / 1024 / 1024).toFixed(1);
  console.log(
    `\nTrain: ${totalTrainSamples.toLocaleString()} samples → ${trainOutPath} (${trainSizeMB} MB)`,
  );

  // ── Phase 2: Sample validation data ──
  console.log('\n--- Phase 2: Sampling validation data ---');
  const valOutPath = join(outputDir, 'val.jsonl');
  const valStream = createWriteStream(valOutPath, { encoding: 'utf-8' });
  let totalValSamples = 0;

  for (const file of valFiles) {
    const filepath = join(inputDir, file);
    const samples = await reservoirSampleFile(filepath, valSamplesPerFlop);

    for (const s of samples) {
      valStream.write(s + '\n');
    }
    totalValSamples += samples.length;
    console.log(`  ${file}: ${samples.length.toLocaleString()} samples`);
  }

  valStream.end();
  await new Promise<void>((resolve) => valStream.on('finish', resolve));
  const valSizeMB = (statSync(valOutPath).size / 1024 / 1024).toFixed(1);
  console.log(
    `\nVal: ${totalValSamples.toLocaleString()} samples → ${valOutPath} (${valSizeMB} MB)`,
  );

  // ── Summary ──
  const totalTime = ((Date.now() - startTime) / 1000).toFixed(0);
  console.log('\n=== Summary ===');
  console.log(`Train: ${totalTrainSamples.toLocaleString()} samples (${trainSizeMB} MB)`);
  console.log(`Val:   ${totalValSamples.toLocaleString()} samples (${valSizeMB} MB)`);
  console.log(`Time:  ${totalTime}s`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
