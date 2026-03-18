#!/usr/bin/env tsx
// Storage estimation script — sample a few flops per config to estimate total disk usage.
//
// Usage:
//   npx tsx estimate-storage.ts [--configs all] [--sample-count 5] [--iterations 5000]
//   npx tsx estimate-storage.ts --configs hu_btn_bb_srp_100bb,hu_btn_bb_3bp_100bb
//
// Solves a small number of sample flops with reduced iterations, then extrapolates
// the storage requirements for all 1,755 isomorphic flops.

import { buildTree, countNodes } from '../tree/tree-builder.js';
import {
  getTreeConfig,
  getSolveDefaults,
  getConfigLabel,
  getPipelineConfigNames,
  type TreeConfigName,
} from '../tree/tree-config.js';
import { InfoSetStore } from '../engine/info-set-store.js';
import { solveCFR } from '../engine/cfr-engine.js';
import {
  loadHUSRPRanges,
  getWeightedRangeCombos,
  type HUSRPRangesOptions,
} from '../integration/preflop-ranges.js';
import { enumerateIsomorphicFlops } from '../abstraction/suit-isomorphism.js';
import { exportToJSONL } from '../storage/json-export.js';
import { resolve } from 'node:path';
import { existsSync, mkdirSync, unlinkSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

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

// Reuse the range options logic from solve-worker
function getRangeOptions(configName: TreeConfigName): HUSRPRangesOptions {
  if (configName.includes('3bet') || configName.includes('3bp')) {
    if (configName.includes('co_bb')) {
      return {
        oopSpot: 'BB_vs_CO_facing_open2.5x',
        oopAction: 'raise',
        ipSpot: 'CO_unopened_open2.5x',
        ipAction: 'raise',
        minFrequency: 0.5,
      };
    }
    return {
      oopSpot: 'BB_vs_BTN_facing_open2.5x',
      oopAction: 'raise',
      ipSpot: 'BTN_unopened_open2.5x',
      ipAction: 'raise',
      minFrequency: 0.4,
    };
  }
  if (configName.includes('co_bb')) {
    return {
      ipSpot: 'CO_unopened_open2.5x',
      ipAction: 'raise',
      oopSpot: 'BB_vs_CO_facing_open2.5x',
      oopAction: 'call',
    };
  }
  if (configName.includes('utg_bb')) {
    return {
      ipSpot: 'UTG_unopened_open2.5x',
      ipAction: 'raise',
      oopSpot: 'BB_vs_UTG_facing_open2.5x',
      oopAction: 'call',
    };
  }
  return {};
}

// Parse CLI args
const args = process.argv.slice(2);
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

const TOTAL_FLOPS = 1755;

async function main(): Promise<void> {
  const configsArg = getArg('configs', 'all');
  const sampleCount = getNumArg('sample-count', 5);
  // Use fewer iterations for estimation — just enough to get representative info-set counts
  const estIterations = getNumArg('iterations', 5000);

  // Determine which configs to estimate
  let configNames: TreeConfigName[];
  if (configsArg === 'all') {
    configNames = getPipelineConfigNames();
  } else {
    configNames = configsArg.split(',').map((s) => s.trim()) as TreeConfigName[];
  }

  const chartsPath = resolve(PROJECT_ROOT, 'data/preflop_charts.json');
  const tmpDir = resolve(PROJECT_ROOT, 'data/cfr/_estimate_tmp');
  mkdirSync(tmpDir, { recursive: true });

  // Select sample flops spread across different textures
  const allFlops = enumerateIsomorphicFlops();
  const sampleIndices = selectSampleFlops(allFlops.length, sampleCount);

  console.log('╔═══════════════════════════════════════════════════════════════╗');
  console.log('║   CFR Storage Estimation                                     ║');
  console.log('╚═══════════════════════════════════════════════════════════════╝');
  console.log();
  console.log(`Configs to estimate: ${configNames.length}`);
  console.log(`Sample flops: ${sampleCount} (of ${TOTAL_FLOPS} total)`);
  console.log(`Estimation iterations: ${estIterations} (reduced for speed)`);
  console.log();

  const results: Array<{
    config: string;
    label: string;
    avgInfoSets: number;
    avgJsonlBytes: number;
    estTotalJsonlGB: number;
    estBinaryGB: number;
    treeSizes: { action: number; terminal: number };
    sampleTimeMs: number;
    estFullTimeHrs: number;
  }> = [];

  for (const configName of configNames) {
    const treeConfig = getTreeConfig(configName);
    const tree = buildTree(treeConfig);
    const nodes = countNodes(tree);
    const defaults = getSolveDefaults(configName);
    const rangeOpts = getRangeOptions(configName);
    const ranges = loadHUSRPRanges(chartsPath, rangeOpts);

    let totalInfoSets = 0;
    let totalJsonlBytes = 0;
    let totalTimeMs = 0;

    process.stdout.write(`  ${getConfigLabel(configName).padEnd(40)}`);

    for (let i = 0; i < sampleIndices.length; i++) {
      const flopIdx = sampleIndices[i];
      const flop = allFlops[flopIdx];
      const deadCards = new Set(flop.cards as number[]);
      const oopCombos = getWeightedRangeCombos(ranges.oopRange, deadCards);
      const ipCombos = getWeightedRangeCombos(ranges.ipRange, deadCards);

      const store = new InfoSetStore();
      const start = Date.now();

      solveCFR({
        root: tree,
        store,
        boardId: flopIdx,
        flopCards: flop.cards as [number, number, number],
        oopRange: oopCombos,
        ipRange: ipCombos,
        iterations: estIterations,
        bucketCount: defaults.buckets,
      });

      const elapsed = Date.now() - start;
      totalTimeMs += elapsed;

      // Export to temp file to measure actual JSONL size
      const tmpPath = resolve(tmpDir, `_est_${configName}_${flopIdx}.jsonl`);
      const exportResult = exportToJSONL(store, {
        outputPath: tmpPath,
        boardId: flopIdx,
        flopCards: flop.cards as [number, number, number],
        iterations: estIterations,
        bucketCount: defaults.buckets,
        elapsedMs: elapsed,
        configName,
        betSizes: treeConfig.betSizes,
      });

      totalInfoSets += exportResult.infoSets;
      totalJsonlBytes += exportResult.fileSize;

      // Clean up temp file
      try {
        unlinkSync(tmpPath);
      } catch {}

      process.stdout.write('.');
    }

    const avgInfoSets = Math.round(totalInfoSets / sampleCount);
    const avgJsonlBytes = totalJsonlBytes / sampleCount;
    const avgTimeMs = totalTimeMs / sampleCount;

    // Scale to full iterations: info-set count doesn't change much with iteration count
    // (tree shape is the same, just strategy quality improves)
    // JSONL size is proportional to info-set count
    const estTotalJsonlGB = (avgJsonlBytes * TOTAL_FLOPS) / 1024 ** 3;
    // Binary format is roughly 6-8x smaller than JSONL (quantized + compressed)
    const estBinaryGB = estTotalJsonlGB / 7;

    // Time estimation: scale by iteration ratio
    const iterScale = defaults.iterations / estIterations;
    const estFullTimeMsPerFlop = avgTimeMs * iterScale;
    const estFullTimeHrs = (estFullTimeMsPerFlop * TOTAL_FLOPS) / (1000 * 3600);

    results.push({
      config: configName,
      label: getConfigLabel(configName),
      avgInfoSets,
      avgJsonlBytes,
      estTotalJsonlGB,
      estBinaryGB,
      treeSizes: nodes,
      sampleTimeMs: avgTimeMs,
      estFullTimeHrs,
    });

    console.log(` ${avgInfoSets.toLocaleString()} info-sets/flop`);
  }

  // Clean up temp dir
  try {
    const { readdirSync, rmdirSync } = await import('node:fs');
    const remaining = readdirSync(tmpDir);
    for (const f of remaining) {
      try {
        unlinkSync(resolve(tmpDir, f));
      } catch {}
    }
    rmdirSync(tmpDir);
  } catch {}

  // Print report
  console.log();
  console.log(
    '╔═════════════════════════════════════════╦══════════╦══════════╦═══════════╦═══════════╗',
  );
  console.log(
    '║ Config                                  ║ JSONL    ║ Binary   ║ Info Sets ║ Time (90w)║',
  );
  console.log(
    '╠═════════════════════════════════════════╬══════════╬══════════╬═══════════╬═══════════╣',
  );

  let totalJsonl = 0;
  let totalBinary = 0;
  let totalTime = 0;

  for (const r of results) {
    const jsonlStr =
      r.estTotalJsonlGB < 1
        ? `${Math.round(r.estTotalJsonlGB * 1024)} MB`
        : `${r.estTotalJsonlGB.toFixed(1)} GB`;
    const binaryStr =
      r.estBinaryGB < 1
        ? `${Math.round(r.estBinaryGB * 1024)} MB`
        : `${r.estBinaryGB.toFixed(1)} GB`;
    const infoStr =
      r.avgInfoSets >= 1_000_000
        ? `${(r.avgInfoSets / 1_000_000).toFixed(1)}M`
        : `${(r.avgInfoSets / 1_000).toFixed(0)}k`;
    const workers = 90;
    const timeWithWorkers = r.estFullTimeHrs / workers;
    const timeStr =
      timeWithWorkers < 1
        ? `${Math.round(timeWithWorkers * 60)} min`
        : timeWithWorkers < 24
          ? `${timeWithWorkers.toFixed(1)} hrs`
          : `${(timeWithWorkers / 24).toFixed(1)} days`;

    console.log(
      `║ ${r.label.padEnd(39)} ║ ${jsonlStr.padStart(8)} ║ ${binaryStr.padStart(8)} ║ ${(infoStr + '/flop').padStart(9)} ║ ${timeStr.padStart(9)} ║`,
    );

    totalJsonl += r.estTotalJsonlGB;
    totalBinary += r.estBinaryGB;
    totalTime += r.estFullTimeHrs;
  }

  console.log(
    '╠═════════════════════════════════════════╬══════════╬══════════╬═══════════╬═══════════╣',
  );

  const totalJsonlStr =
    totalJsonl < 1 ? `${Math.round(totalJsonl * 1024)} MB` : `${totalJsonl.toFixed(1)} GB`;
  const totalBinaryStr =
    totalBinary < 1 ? `${Math.round(totalBinary * 1024)} MB` : `${totalBinary.toFixed(1)} GB`;
  const totalTimeStr =
    totalTime / 90 < 24
      ? `${(totalTime / 90).toFixed(1)} hrs`
      : `${(totalTime / 90 / 24).toFixed(1)} days`;

  console.log(
    `║ ${'TOTAL'.padEnd(39)} ║ ${totalJsonlStr.padStart(8)} ║ ${totalBinaryStr.padStart(8)} ║ ${''.padStart(9)} ║ ${totalTimeStr.padStart(9)} ║`,
  );
  console.log(
    '╚═════════════════════════════════════════╩══════════╩══════════╩═══════════╩═══════════╝',
  );

  console.log();
  const neededGB = Math.ceil(totalJsonl + totalBinary + 10); // +10 GB working space
  console.log(`Recommended free disk space: ${neededGB} GB per cluster machine`);
  console.log(
    `(JSONL: ${totalJsonl.toFixed(1)} GB + Binary: ${totalBinary.toFixed(1)} GB + ~10 GB working space)`,
  );

  if (totalJsonl > 50) {
    console.log();
    console.log('⚠️  JSONL output is large. Consider:');
    console.log('   1. Deleting JSONL after binary export (binary is the final format)');
    console.log('   2. Running fewer configs initially (Tier 1 priority)');
  }
}

/** Select sample flop indices spread evenly across the range */
function selectSampleFlops(totalFlops: number, count: number): number[] {
  if (count >= totalFlops) return Array.from({ length: totalFlops }, (_, i) => i);
  const step = Math.floor(totalFlops / count);
  const indices: number[] = [];
  for (let i = 0; i < count; i++) {
    indices.push(i * step);
  }
  return indices;
}

main().catch((err) => {
  console.error('[FATAL]', err);
  process.exit(1);
});
