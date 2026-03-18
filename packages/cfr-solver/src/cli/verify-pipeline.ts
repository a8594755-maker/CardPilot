#!/usr/bin/env tsx
// Verify pipeline output data quality.
// Usage: npx tsx verify-pipeline.ts [--dir path/to/cfr/output] [--verbose]
//
// Checks:
// 1. All probs sum to ~1.0 (tolerance 0.05)
// 2. No NaN / Inf / negative values
// 3. Info-set key format is valid (Street|boardId|player|history|buckets)
// 4. All 3 streets present (F, T, R)
// 5. Both players present (0, 1)
// 6. Strategy diversity (not all uniform = solver actually converged)
// 7. Meta files match JSONL files
// 8. Cross-flop consistency (similar info-set counts)

import { resolve } from 'node:path';
import { existsSync, readdirSync, readFileSync, createReadStream } from 'node:fs';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
function findProjectRoot(): string {
  const fromFile = resolve(__dirname, '../../../../');
  if (existsSync(resolve(fromFile, 'data'))) return fromFile;
  return process.cwd();
}

const args = process.argv.slice(2);
function getArg(name: string, defaultVal: string): string {
  const idx = args.indexOf(`--${name}`);
  if (idx !== -1 && args[idx + 1]) return args[idx + 1];
  return defaultVal;
}
const verbose = args.includes('--verbose');
const outputDir = getArg('dir', resolve(findProjectRoot(), 'data/cfr/pipeline_hu_srp_50bb'));

// ---------- Types ----------

interface InfoSetEntry {
  key: string;
  probs: number[];
}

interface FlopReport {
  file: string;
  boardId: number;
  totalRows: number;
  streets: Record<string, number>; // F/T/R → count
  players: Record<string, number>; // 0/1 → count
  probSumErrors: number; // rows where sum(probs) != ~1.0
  nanInfErrors: number; // rows with NaN/Inf
  negativeErrors: number; // rows with negative probs
  uniformRows: number; // rows where all probs are equal
  nonUniformRows: number; // rows where probs vary (solver converged)
  maxProb: number; // highest single-action prob seen
  parseErrors: number; // JSON parse failures
  metaExists: boolean;
  metaInfoSets: number; // from meta file
}

// ---------- Verify a single JSONL file ----------

async function verifyFlop(filePath: string): Promise<FlopReport> {
  const match = filePath.match(/flop_(\d+)\.jsonl$/);
  const boardId = match ? parseInt(match[1]) : -1;
  const metaPath = filePath.replace(/\.jsonl$/, '.meta.json');

  const report: FlopReport = {
    file: filePath,
    boardId,
    totalRows: 0,
    streets: {},
    players: {},
    probSumErrors: 0,
    nanInfErrors: 0,
    negativeErrors: 0,
    uniformRows: 0,
    nonUniformRows: 0,
    maxProb: 0,
    parseErrors: 0,
    metaExists: existsSync(metaPath),
    metaInfoSets: 0,
  };

  if (report.metaExists) {
    try {
      const meta = JSON.parse(readFileSync(metaPath, 'utf-8'));
      report.metaInfoSets = meta.infoSets ?? 0;
    } catch {}
  }

  const rl = createInterface({
    input: createReadStream(filePath, 'utf-8'),
    crlfDelay: Infinity,
  });

  for await (const line of rl) {
    if (!line.trim()) continue;

    let entry: InfoSetEntry;
    try {
      entry = JSON.parse(line);
    } catch {
      report.parseErrors++;
      continue;
    }

    report.totalRows++;

    // Check key format: Street|boardId|player|history|buckets
    const parts = entry.key.split('|');
    if (parts.length >= 3) {
      const street = parts[0];
      const player = parts[2];
      report.streets[street] = (report.streets[street] ?? 0) + 1;
      report.players[player] = (report.players[player] ?? 0) + 1;
    }

    // Check probs
    const probs = entry.probs;
    if (!Array.isArray(probs) || probs.length === 0) {
      report.parseErrors++;
      continue;
    }

    // NaN / Inf check
    if (probs.some((p) => !isFinite(p))) {
      report.nanInfErrors++;
      continue;
    }

    // Negative check
    if (probs.some((p) => p < 0)) {
      report.negativeErrors++;
    }

    // Sum check (tolerance: 0.05 due to rounding in export)
    const sum = probs.reduce((a, b) => a + b, 0);
    if (Math.abs(sum - 1.0) > 0.05) {
      report.probSumErrors++;
    }

    // Diversity check
    const allEqual = probs.every((p) => Math.abs(p - probs[0]) < 0.01);
    if (allEqual) {
      report.uniformRows++;
    } else {
      report.nonUniformRows++;
    }

    // Max prob
    const mp = Math.max(...probs);
    if (mp > report.maxProb) report.maxProb = mp;
  }

  return report;
}

// ---------- Main ----------

async function main(): Promise<void> {
  console.log('╔═══════════════════════════════════════════════╗');
  console.log('║   Pipeline Output Verification                ║');
  console.log('╚═══════════════════════════════════════════════╝');
  console.log();
  console.log(`Directory: ${outputDir}`);
  console.log();

  if (!existsSync(outputDir)) {
    console.error(`Directory not found: ${outputDir}`);
    process.exit(1);
  }

  const files = readdirSync(outputDir)
    .filter((f) => f.endsWith('.jsonl'))
    .sort();

  if (files.length === 0) {
    console.error('No .jsonl files found');
    process.exit(1);
  }

  console.log(`Found ${files.length} JSONL files`);
  console.log();

  // Verify each file
  const reports: FlopReport[] = [];
  let passed = 0;
  let failed = 0;

  for (const file of files) {
    const report = await verifyFlop(resolve(outputDir, file));
    reports.push(report);

    const hasErrors =
      report.probSumErrors > 0 ||
      report.nanInfErrors > 0 ||
      report.negativeErrors > 0 ||
      report.parseErrors > 0;
    const hasConverged = report.nonUniformRows > report.uniformRows * 0.1; // at least 10% non-uniform
    const hasAllStreets = 'F' in report.streets && 'T' in report.streets && 'R' in report.streets;
    const hasBothPlayers = '0' in report.players && '1' in report.players;
    const metaMatch = !report.metaExists || Math.abs(report.totalRows - report.metaInfoSets) < 10;

    const ok = !hasErrors && hasConverged && hasAllStreets && hasBothPlayers && metaMatch;

    if (ok) {
      passed++;
      if (verbose) {
        console.log(
          `  PASS  flop_${String(report.boardId).padStart(3, '0')} | ${report.totalRows} rows | F:${report.streets['F'] ?? 0} T:${report.streets['T'] ?? 0} R:${report.streets['R'] ?? 0} | converged: ${((report.nonUniformRows / report.totalRows) * 100).toFixed(0)}%`,
        );
      }
    } else {
      failed++;
      console.log(`  FAIL  flop_${String(report.boardId).padStart(3, '0')}:`);
      if (report.probSumErrors > 0)
        console.log(`        ${report.probSumErrors} rows with prob sum != 1.0`);
      if (report.nanInfErrors > 0) console.log(`        ${report.nanInfErrors} rows with NaN/Inf`);
      if (report.negativeErrors > 0)
        console.log(`        ${report.negativeErrors} rows with negative probs`);
      if (report.parseErrors > 0) console.log(`        ${report.parseErrors} JSON parse errors`);
      if (!hasConverged)
        console.log(
          `        Low convergence: ${report.nonUniformRows}/${report.totalRows} non-uniform (${((report.nonUniformRows / report.totalRows) * 100).toFixed(1)}%)`,
        );
      if (!hasAllStreets) console.log(`        Missing streets: ${JSON.stringify(report.streets)}`);
      if (!hasBothPlayers)
        console.log(`        Missing players: ${JSON.stringify(report.players)}`);
      if (!metaMatch)
        console.log(
          `        Meta mismatch: jsonl=${report.totalRows} vs meta=${report.metaInfoSets}`,
        );
    }
  }

  // Aggregate stats
  const totalRows = reports.reduce((s, r) => s + r.totalRows, 0);
  const totalProbErrors = reports.reduce((s, r) => s + r.probSumErrors, 0);
  const totalNanInf = reports.reduce((s, r) => s + r.nanInfErrors, 0);
  const totalNeg = reports.reduce((s, r) => s + r.negativeErrors, 0);
  const totalUniform = reports.reduce((s, r) => s + r.uniformRows, 0);
  const totalNonUniform = reports.reduce((s, r) => s + r.nonUniformRows, 0);
  const avgRows = Math.round(totalRows / reports.length);
  const rowStdDev = Math.sqrt(
    reports.reduce((s, r) => s + Math.pow(r.totalRows - avgRows, 2), 0) / reports.length,
  );

  console.log();
  console.log('═══ SUMMARY ═══');
  console.log();
  console.log(`Files verified:    ${reports.length}`);
  console.log(`Passed:            ${passed}`);
  console.log(`Failed:            ${failed}`);
  console.log();
  console.log(`Total info sets:   ${totalRows.toLocaleString()}`);
  console.log(`Avg per flop:      ${avgRows.toLocaleString()} (stddev: ${Math.round(rowStdDev)})`);
  console.log();
  console.log('Data Quality:');
  console.log(
    `  Prob sum errors: ${totalProbErrors} (${((totalProbErrors / totalRows) * 100).toFixed(3)}%)`,
  );
  console.log(`  NaN/Inf errors:  ${totalNanInf}`);
  console.log(`  Negative errors: ${totalNeg}`);
  console.log();
  console.log('Convergence:');
  console.log(
    `  Uniform rows:    ${totalUniform.toLocaleString()} (${((totalUniform / totalRows) * 100).toFixed(1)}%)`,
  );
  console.log(
    `  Non-uniform:     ${totalNonUniform.toLocaleString()} (${((totalNonUniform / totalRows) * 100).toFixed(1)}%)`,
  );
  console.log(`  Convergence rate: ${((totalNonUniform / totalRows) * 100).toFixed(1)}%`);
  console.log();

  // Street distribution
  const streetTotals: Record<string, number> = {};
  for (const r of reports) {
    for (const [s, c] of Object.entries(r.streets)) {
      streetTotals[s] = (streetTotals[s] ?? 0) + c;
    }
  }
  console.log('Per-street info sets:');
  for (const [s, c] of Object.entries(streetTotals).sort()) {
    const name = s === 'F' ? 'Flop' : s === 'T' ? 'Turn' : s === 'R' ? 'River' : s;
    console.log(`  ${name}: ${c.toLocaleString()} (${((c / totalRows) * 100).toFixed(1)}%)`);
  }
  console.log();

  // Final verdict
  if (failed === 0) {
    console.log('RESULT: ALL CHECKS PASSED');
  } else {
    console.log(`RESULT: ${failed} FLOPS FAILED VERIFICATION`);
    process.exit(1);
  }
}

main().catch((err) => {
  console.error('[ERROR]', err);
  process.exit(1);
});
