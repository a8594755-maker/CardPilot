#!/usr/bin/env tsx
/**
 * Convert V3 CFR data → training data, presample on-the-fly.
 *
 * For each flop:
 *   1. Convert CFR JSONL → training samples (in memory)
 *   2. Reservoir sample N samples per street
 *   3. Append to output files
 *
 * This avoids storing 1TB+ of raw training data.
 */

import { readdirSync, existsSync, mkdirSync, createWriteStream, statSync } from 'node:fs';
import { join } from 'node:path';
import { fork } from 'node:child_process';
import { cpus } from 'node:os';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);

// ── Config ──
const CFR_DIR = 'data/cfr/pipeline_v3_hu_srp_50bb/';
const OUTPUT_DIR = 'data/training/v3_srp_50bb_sampled/';
const CONFIG_NAME = 'pipeline_srp_v3';
const SAMPLES_PER_BUCKET = 3;
const WORKERS = 8;

// Presample budget per flop
const SAMPLES_PER_FLOP = 15000; // ~28.6M total for 1911 flops
const STREET_BALANCE = { FLOP: 0.03, TURN: 0.25, RIVER: 0.72 }; // V9.1 sweet spot
const VAL_FLOP_COUNT = 20; // hold out 20 flops for validation

// ── Discover flops ──
const cfrFiles = readdirSync(CFR_DIR)
  .filter((f) => f.endsWith('.meta.json'))
  .map((f) => {
    const match = f.match(/^board_(\d+)\.meta\.json$/);
    if (!match) return null;
    const boardId = parseInt(match[1], 10);
    const jsonlPath = join(CFR_DIR, `board_${boardId}.jsonl`);
    if (!existsSync(jsonlPath)) return null;
    return { boardId, metaPath: join(CFR_DIR, f), jsonlPath };
  })
  .filter(Boolean)
  .sort((a, b) => a!.boardId - b!.boardId) as {
  boardId: number;
  metaPath: string;
  jsonlPath: string;
}[];

console.log(`Found ${cfrFiles.length} solved flops in ${CFR_DIR}`);

// Pick val flops (evenly spaced)
const step = Math.max(1, Math.floor(cfrFiles.length / VAL_FLOP_COUNT));
const valSet = new Set<number>();
for (let i = 0; i < VAL_FLOP_COUNT; i++) {
  valSet.add(cfrFiles[Math.min(i * step, cfrFiles.length - 1)].boardId);
}

const trainFlops = cfrFiles.filter((f) => !valSet.has(f.boardId));
const valFlops = cfrFiles.filter((f) => valSet.has(f.boardId));
console.log(`Train: ${trainFlops.length} flops, Val: ${valFlops.length} flops`);
console.log(
  `Samples per flop: ${SAMPLES_PER_FLOP} (target ~${((trainFlops.length * SAMPLES_PER_FLOP) / 1e6).toFixed(1)}M train)`,
);

// Create output dir
if (!existsSync(OUTPUT_DIR)) mkdirSync(OUTPUT_DIR, { recursive: true });

// ── Worker management ──
// We'll use cfr-to-training-data.ts in single-flop mode, then presample the output

// Actually, simpler approach: call cfr-to-training-data conversion logic per-flop
// and pipe through reservoir sampling. But the converter uses fork() workers internally.

// Simplest reliable approach: convert 1 flop at a time, reservoir sample in-process

import { createInterface } from 'node:readline';
import { createReadStream } from 'node:fs';

type StreetKey = 'FLOP' | 'TURN' | 'RIVER';

interface ReservoirState {
  reservoirs: Record<StreetKey, string[]>;
  seen: Record<StreetKey, number>;
  budgets: Record<StreetKey, number>;
}

function initReservoir(totalSamples: number): ReservoirState {
  return {
    reservoirs: { FLOP: [], TURN: [], RIVER: [] },
    seen: { FLOP: 0, TURN: 0, RIVER: 0 },
    budgets: {
      FLOP: Math.round(totalSamples * STREET_BALANCE.FLOP),
      TURN: Math.round(totalSamples * STREET_BALANCE.TURN),
      RIVER: Math.round(totalSamples * STREET_BALANCE.RIVER),
    },
  };
}

function addToReservoir(state: ReservoirState, line: string, street: StreetKey): void {
  const budget = state.budgets[street];
  if (!budget) return;
  const s = state.seen[street];
  if (s < budget) {
    state.reservoirs[street].push(line);
  } else {
    const j = Math.floor(Math.random() * (s + 1));
    if (j < budget) {
      state.reservoirs[street][j] = line;
    }
  }
  state.seen[street]++;
}

function getStreetFromLine(line: string): StreetKey | null {
  const idx = line.indexOf('"s":"');
  if (idx === -1) return null;
  const start = idx + 5;
  const end = line.indexOf('"', start);
  return line.slice(start, end) as StreetKey;
}

// ── Main: convert each flop via subprocess, presample output ──

async function convertAndSampleFlop(
  flop: { boardId: number; metaPath: string; jsonlPath: string },
  reservoir: ReservoirState,
): Promise<number> {
  // Use cfr-to-training-data in single-worker mode for this one flop
  const tmpDir = join(OUTPUT_DIR, `_tmp_${flop.boardId}`);
  if (!existsSync(tmpDir)) mkdirSync(tmpDir, { recursive: true });

  // Run converter for single flop
  await new Promise<void>((resolve, reject) => {
    const child = fork(
      join('packages', 'cfr-solver', 'src', 'scripts', 'cfr-to-training-data.ts'),
      [
        '--cfr-dir',
        CFR_DIR,
        '--output',
        tmpDir,
        '--config',
        CONFIG_NAME,
        '--samples-per-bucket',
        String(SAMPLES_PER_BUCKET),
        '--workers',
        '1',
        '--single-flop',
        String(flop.boardId),
      ],
      {
        execArgv: ['--import', 'tsx'],
        stdio: ['pipe', 'pipe', 'pipe', 'ipc'],
      },
    );
    child.stdout?.on('data', () => {});
    child.stderr?.on('data', () => {});
    child.on('exit', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`Converter exit ${code} for board ${flop.boardId}`));
    });
    child.on('error', reject);
  });

  // Read the output file and reservoir sample
  const outFile = join(tmpDir, `flop_${String(flop.boardId).padStart(4, '0')}.jsonl`);
  if (!existsSync(outFile)) return 0;

  const rl = createInterface({
    input: createReadStream(outFile, { encoding: 'utf-8', highWaterMark: 64 * 1024 }),
    crlfDelay: Infinity,
  });

  let count = 0;
  for await (const line of rl) {
    if (!line.trim()) continue;
    const street = getStreetFromLine(line);
    if (!street) continue;
    addToReservoir(reservoir, line, street);
    count++;
  }

  // Delete tmp
  const { rmSync } = await import('node:fs');
  rmSync(tmpDir, { recursive: true, force: true });

  return count;
}

// Actually, the single-flop fork approach is too slow (1 flop at a time).
// Better: run the full converter in batches of 100, then presample the batch.

async function presampleFromDir(dir: string, reservoir: ReservoirState): Promise<number> {
  const files = readdirSync(dir)
    .filter((f) => f.endsWith('.jsonl'))
    .sort();
  let total = 0;

  for (const file of files) {
    const filepath = join(dir, file);
    const rl = createInterface({
      input: createReadStream(filepath, { encoding: 'utf-8', highWaterMark: 64 * 1024 }),
      crlfDelay: Infinity,
    });

    for await (const line of rl) {
      if (!line.trim()) continue;
      const street = getStreetFromLine(line);
      if (!street) continue;
      addToReservoir(reservoir, line, street);
      total++;
    }
  }
  return total;
}

async function main() {
  const startTime = Date.now();
  const BATCH_SIZE = 50; // Convert 50 flops at a time
  const tmpRawDir = join(OUTPUT_DIR, '_raw_batch');

  // Global reservoir for training data
  const trainReservoir = initReservoir(SAMPLES_PER_FLOP * trainFlops.length);
  const valReservoir = initReservoir(SAMPLES_PER_FLOP * valFlops.length);

  // Process train flops in batches
  console.log(`\n--- Converting & presampling train flops (${BATCH_SIZE} per batch) ---`);

  for (let batchStart = 0; batchStart < trainFlops.length; batchStart += BATCH_SIZE) {
    const batch = trainFlops.slice(batchStart, batchStart + BATCH_SIZE);
    const batchEnd = Math.min(batchStart + BATCH_SIZE, trainFlops.length);

    // Convert batch
    if (!existsSync(tmpRawDir)) mkdirSync(tmpRawDir, { recursive: true });

    const boardIds = batch.map((f) => f.boardId).join(',');
    await new Promise<void>((resolve, reject) => {
      const child = fork(
        join('packages', 'cfr-solver', 'src', 'scripts', 'cfr-to-training-data.ts'),
        [
          '--cfr-dir',
          CFR_DIR,
          '--output',
          tmpRawDir,
          '--config',
          CONFIG_NAME,
          '--samples-per-bucket',
          String(SAMPLES_PER_BUCKET),
          '--workers',
          String(WORKERS),
          '--board-ids',
          boardIds,
        ],
        {
          execArgv: ['--import', 'tsx', '--max-old-space-size=8192'],
          stdio: 'inherit',
        },
      );
      child.on('exit', (code) => {
        if (code === 0) resolve();
        else reject(new Error(`Batch converter exit ${code}`));
      });
      child.on('error', reject);
    });

    // Presample batch
    const batchSamples = await presampleFromDir(tmpRawDir, trainReservoir);

    // Delete batch raw data
    const { rmSync } = await import('node:fs');
    rmSync(tmpRawDir, { recursive: true, force: true });

    const elapsed = ((Date.now() - startTime) / 1000 / 60).toFixed(1);
    const { FLOP: f, TURN: t, RIVER: r } = trainReservoir.reservoirs;
    console.log(
      `  Batch ${batchStart / BATCH_SIZE + 1}: flops ${batchStart}-${batchEnd - 1} | ` +
        `${batchSamples.toLocaleString()} raw → reservoir [F:${f.length} T:${t.length} R:${r.length}] | ${elapsed}min`,
    );
  }

  // Write train data
  console.log('\n--- Writing train data ---');
  const trainPath = join(OUTPUT_DIR, 'train.jsonl');
  const trainStream = createWriteStream(trainPath, { encoding: 'utf-8' });
  const allTrain = [
    ...trainReservoir.reservoirs.FLOP,
    ...trainReservoir.reservoirs.TURN,
    ...trainReservoir.reservoirs.RIVER,
  ];
  // Shuffle
  for (let i = allTrain.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [allTrain[i], allTrain[j]] = [allTrain[j], allTrain[i]];
  }
  for (const line of allTrain) trainStream.write(line + '\n');
  trainStream.end();
  await new Promise<void>((r) => trainStream.on('finish', r));
  console.log(`Train: ${allTrain.length.toLocaleString()} samples → ${trainPath}`);
  console.log(
    `  Flop: ${trainReservoir.reservoirs.FLOP.length} | Turn: ${trainReservoir.reservoirs.TURN.length} | River: ${trainReservoir.reservoirs.RIVER.length}`,
  );

  // Process val flops
  console.log('\n--- Converting & presampling val flops ---');
  const tmpValDir = join(OUTPUT_DIR, '_raw_val');
  if (!existsSync(tmpValDir)) mkdirSync(tmpValDir, { recursive: true });

  const valBoardIds = valFlops.map((f) => f.boardId).join(',');
  await new Promise<void>((resolve, reject) => {
    const child = fork(
      join('packages', 'cfr-solver', 'src', 'scripts', 'cfr-to-training-data.ts'),
      [
        '--cfr-dir',
        CFR_DIR,
        '--output',
        tmpValDir,
        '--config',
        CONFIG_NAME,
        '--samples-per-bucket',
        String(SAMPLES_PER_BUCKET),
        '--workers',
        String(WORKERS),
        '--board-ids',
        valBoardIds,
      ],
      {
        execArgv: ['--import', 'tsx', '--max-old-space-size=8192'],
        stdio: 'inherit',
      },
    );
    child.on('exit', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`Val converter exit ${code}`));
    });
    child.on('error', reject);
  });

  const valSamples = await presampleFromDir(tmpValDir, valReservoir);
  const { rmSync } = await import('node:fs');
  rmSync(tmpValDir, { recursive: true, force: true });

  // Write val data
  const valPath = join(OUTPUT_DIR, 'val.jsonl');
  const valStream = createWriteStream(valPath, { encoding: 'utf-8' });
  const allVal = [
    ...valReservoir.reservoirs.FLOP,
    ...valReservoir.reservoirs.TURN,
    ...valReservoir.reservoirs.RIVER,
  ];
  for (let i = allVal.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [allVal[i], allVal[j]] = [allVal[j], allVal[i]];
  }
  for (const line of allVal) valStream.write(line + '\n');
  valStream.end();
  await new Promise<void>((r) => valStream.on('finish', r));
  console.log(`Val: ${allVal.length.toLocaleString()} samples → ${valPath}`);
  console.log(
    `  Flop: ${valReservoir.reservoirs.FLOP.length} | Turn: ${valReservoir.reservoirs.TURN.length} | River: ${valReservoir.reservoirs.RIVER.length}`,
  );

  const totalMin = ((Date.now() - startTime) / 1000 / 60).toFixed(1);
  console.log(`\nDone in ${totalMin} min`);
}

main().catch(console.error);
