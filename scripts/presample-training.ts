#!/usr/bin/env tsx
/**
 * Pre-sample training data for Value Network.
 * Street-balanced reservoir sampling: ensures flop/turn/river all get
 * adequate representation instead of the natural 0.5%/15%/85% split.
 *
 * Usage:
 *   npx tsx scripts/presample-training.ts \
 *     --input data/training/cfr_srp_v2/ \
 *     --output data/training/cfr_srp_v2_sampled/ \
 *     --samples-per-file 5000 \
 *     --val-flops 10 \
 *     --street-balance          # enable street-balanced sampling
 *     --flop-pct 20 --turn-pct 40 --river-pct 40
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
function hasFlag(name: string): boolean {
  return argv.includes(name);
}

const inputDir = getArg('--input', 'data/training/cfr_srp_v2/');
const outputDir = getArg('--output', 'data/training/cfr_srp_v2_sampled/');
const samplesPerFile = parseInt(getArg('--samples-per-file', '5000'), 10);
const valFlopCount = parseInt(getArg('--val-flops', '10'), 10);
const valSamplesPerFlop = parseInt(getArg('--val-samples-per-flop', '5000'), 10);
const streetBalance = hasFlag('--street-balance');
const flopPct = parseInt(getArg('--flop-pct', '20'), 10) / 100;
const turnPct = parseInt(getArg('--turn-pct', '40'), 10) / 100;
const riverPct = parseInt(getArg('--river-pct', '40'), 10) / 100;

type StreetKey = 'FLOP' | 'TURN' | 'RIVER';

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

/**
 * Street-balanced reservoir sampling.
 * Maintains separate reservoirs per street to guarantee target distribution.
 */
async function reservoirSampleFileBalanced(
  filepath: string,
  total: number,
  streetBudgets: Record<StreetKey, number>,
): Promise<{ samples: string[]; counts: Record<StreetKey, number> }> {
  const reservoirs: Record<StreetKey, string[]> = { FLOP: [], TURN: [], RIVER: [] };
  const seen: Record<StreetKey, number> = { FLOP: 0, TURN: 0, RIVER: 0 };

  const rl = createInterface({
    input: createReadStream(filepath, { encoding: 'utf-8', highWaterMark: 64 * 1024 }),
    crlfDelay: Infinity,
  });

  for await (const line of rl) {
    if (!line.trim()) continue;

    // Extract street from the "s" field — fast string search instead of JSON.parse
    let street: StreetKey;
    const sIdx = line.indexOf('"s":"');
    if (sIdx === -1) {
      // Fallback: try to parse
      try {
        const obj = JSON.parse(line);
        street = obj.s as StreetKey;
      } catch {
        continue;
      }
    } else {
      const valStart = sIdx + 5;
      const valEnd = line.indexOf('"', valStart);
      street = line.slice(valStart, valEnd) as StreetKey;
    }

    if (!streetBudgets[street]) continue;

    const budget = streetBudgets[street];
    const reservoir = reservoirs[street];
    const s = seen[street];

    if (s < budget) {
      reservoir.push(line);
    } else {
      const j = Math.floor(Math.random() * (s + 1));
      if (j < budget) {
        reservoir[j] = line;
      }
    }
    seen[street]++;
  }

  // Combine all reservoirs
  const samples = [...reservoirs.FLOP, ...reservoirs.TURN, ...reservoirs.RIVER];
  const counts: Record<StreetKey, number> = {
    FLOP: reservoirs.FLOP.length,
    TURN: reservoirs.TURN.length,
    RIVER: reservoirs.RIVER.length,
  };

  return { samples, counts };
}

async function main() {
  const startTime = Date.now();

  // Collect all flop files
  const allFiles = readdirSync(inputDir)
    .filter((f) => /^flop_\d+\.jsonl$/.test(f))
    .sort();

  console.log(`Found ${allFiles.length} flop files in ${inputDir}`);
  if (streetBalance) {
    console.log(
      `Street-balanced mode: flop=${(flopPct * 100).toFixed(0)}% turn=${(turnPct * 100).toFixed(0)}% river=${(riverPct * 100).toFixed(0)}%`,
    );
  }

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

  // Street budgets per file
  const streetBudgets: Record<StreetKey, number> = {
    FLOP: Math.round(samplesPerFile * flopPct),
    TURN: Math.round(samplesPerFile * turnPct),
    RIVER: Math.round(samplesPerFile * riverPct),
  };

  // ── Phase 1: Sample from each train file ──
  console.log('\n--- Phase 1: Sampling training data ---');
  const trainOutPath = join(outputDir, 'train.jsonl');
  const trainStream = createWriteStream(trainOutPath, { encoding: 'utf-8' });
  let totalTrainSamples = 0;
  const globalStreetCounts: Record<StreetKey, number> = { FLOP: 0, TURN: 0, RIVER: 0 };

  for (let i = 0; i < trainFiles.length; i++) {
    const filepath = join(inputDir, trainFiles[i]);

    let samples: string[];
    if (streetBalance) {
      const result = await reservoirSampleFileBalanced(filepath, samplesPerFile, streetBudgets);
      samples = result.samples;
      globalStreetCounts.FLOP += result.counts.FLOP;
      globalStreetCounts.TURN += result.counts.TURN;
      globalStreetCounts.RIVER += result.counts.RIVER;
    } else {
      samples = await reservoirSampleFile(filepath, samplesPerFile);
    }

    for (const s of samples) {
      trainStream.write(s + '\n');
    }
    totalTrainSamples += samples.length;

    if ((i + 1) % 100 === 0 || i === trainFiles.length - 1) {
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(0);
      const streetInfo = streetBalance
        ? ` [F:${globalStreetCounts.FLOP.toLocaleString()} T:${globalStreetCounts.TURN.toLocaleString()} R:${globalStreetCounts.RIVER.toLocaleString()}]`
        : '';
      console.log(
        `  [${i + 1}/${trainFiles.length}] ${totalTrainSamples.toLocaleString()} samples${streetInfo} (${elapsed}s)`,
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
  if (streetBalance) {
    const total = totalTrainSamples || 1;
    console.log(
      `  Flop: ${globalStreetCounts.FLOP.toLocaleString()} (${((globalStreetCounts.FLOP / total) * 100).toFixed(1)}%)` +
        `  Turn: ${globalStreetCounts.TURN.toLocaleString()} (${((globalStreetCounts.TURN / total) * 100).toFixed(1)}%)` +
        `  River: ${globalStreetCounts.RIVER.toLocaleString()} (${((globalStreetCounts.RIVER / total) * 100).toFixed(1)}%)`,
    );
  }

  // ── Phase 2: Sample validation data (always street-balanced if flag set) ──
  console.log('\n--- Phase 2: Sampling validation data ---');
  const valOutPath = join(outputDir, 'val.jsonl');
  const valStream = createWriteStream(valOutPath, { encoding: 'utf-8' });
  let totalValSamples = 0;
  const valStreetCounts: Record<StreetKey, number> = { FLOP: 0, TURN: 0, RIVER: 0 };

  const valStreetBudgets: Record<StreetKey, number> = {
    FLOP: Math.round(valSamplesPerFlop * flopPct),
    TURN: Math.round(valSamplesPerFlop * turnPct),
    RIVER: Math.round(valSamplesPerFlop * riverPct),
  };

  for (const file of valFiles) {
    const filepath = join(inputDir, file);

    let samples: string[];
    if (streetBalance) {
      const result = await reservoirSampleFileBalanced(
        filepath,
        valSamplesPerFlop,
        valStreetBudgets,
      );
      samples = result.samples;
      valStreetCounts.FLOP += result.counts.FLOP;
      valStreetCounts.TURN += result.counts.TURN;
      valStreetCounts.RIVER += result.counts.RIVER;
    } else {
      samples = await reservoirSampleFile(filepath, valSamplesPerFlop);
    }

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
  if (streetBalance) {
    const total = totalValSamples || 1;
    console.log(
      `  Flop: ${valStreetCounts.FLOP.toLocaleString()} (${((valStreetCounts.FLOP / total) * 100).toFixed(1)}%)` +
        `  Turn: ${valStreetCounts.TURN.toLocaleString()} (${((valStreetCounts.TURN / total) * 100).toFixed(1)}%)` +
        `  River: ${valStreetCounts.RIVER.toLocaleString()} (${((valStreetCounts.RIVER / total) * 100).toFixed(1)}%)`,
    );
  }

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
