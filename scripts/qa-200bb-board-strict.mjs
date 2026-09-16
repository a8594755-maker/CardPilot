#!/usr/bin/env node
// Strict, bounded-memory structural and convergence-proxy audit for one CFR board.
import { createHash } from 'node:crypto';
import { createGunzip } from 'node:zlib';
import { createReadStream, readFileSync, writeFileSync } from 'node:fs';
import { createInterface } from 'node:readline';
import { performance } from 'node:perf_hooks';

function fail(message) {
  console.error(message);
  process.exit(1);
}

const [gzPath, metaPath, outPath] = process.argv.slice(2);
if (!gzPath || !metaPath || !outPath) {
  fail('usage: node scripts/qa-200bb-board-strict.mjs <board.jsonl.gz> <board.meta.json> <out.json>');
}

let meta;
try {
  meta = JSON.parse(readFileSync(metaPath, 'utf8'));
} catch (error) {
  fail(`metadata load failed: ${error}`);
}

const startedAt = new Date().toISOString();
const started = performance.now();
const compressedSha = createHash('sha256');
const contentSha = createHash('sha256');
const raw = createReadStream(gzPath);
raw.on('data', chunk => compressedSha.update(chunk));
const gunzip = createGunzip();
const lines = createInterface({ input: raw.pipe(gunzip), crlfDelay: Infinity });

let physicalLines = 0;
let validRows = 0;
let blankLines = 0;
let parseErrors = 0;
let schemaErrors = 0;
let probabilityErrors = 0;
let decisive = 0;
let nearPure = 0;
let sumMax = 0;
let minProbability = Infinity;
let maxProbability = -Infinity;
let maxSumError = 0;
const actionLengths = {};
const examples = [];

function record(kind, line, detail) {
  if (examples.length < 20) examples.push({ kind, line, detail });
}

try {
  for await (const line of lines) {
    physicalLines += 1;
    contentSha.update(line);
    contentSha.update('\n');
    if (!line.trim()) {
      blankLines += 1;
      record('blank_line', physicalLines, 'blank rows are forbidden');
      continue;
    }
    let row;
    try {
      row = JSON.parse(line);
    } catch (error) {
      parseErrors += 1;
      record('json_parse', physicalLines, String(error));
      continue;
    }
    if (!row || typeof row !== 'object' || typeof row.key !== 'string' || row.key.length === 0 || !Array.isArray(row.probs)) {
      schemaErrors += 1;
      record('schema', physicalLines, 'expected non-empty string key and probs array');
      continue;
    }
    if (!/^[FTR]\|/.test(row.key) || row.probs.length < 2 || row.probs.length > 16) {
      schemaErrors += 1;
      record('schema', physicalLines, `unexpected key prefix or action count=${row.probs.length}`);
      continue;
    }
    let sum = 0;
    let max = -Infinity;
    let rowProbabilityError = false;
    for (const value of row.probs) {
      if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > 1) {
        rowProbabilityError = true;
        break;
      }
      sum += value;
      max = Math.max(max, value);
      minProbability = Math.min(minProbability, value);
      maxProbability = Math.max(maxProbability, value);
    }
    const sumError = Math.abs(sum - 1);
    maxSumError = Math.max(maxSumError, sumError);
    // Export probabilities are rounded to three decimals; 0.005 covers worst-case accumulation.
    if (rowProbabilityError || sumError > 0.0050000001) {
      probabilityErrors += 1;
      record('probability', physicalLines, `count=${row.probs.length} sum=${sum}`);
      continue;
    }
    validRows += 1;
    actionLengths[row.probs.length] = (actionLengths[row.probs.length] || 0) + 1;
    sumMax += max;
    if (max >= 0.6) decisive += 1;
    if (max >= 0.95) nearPure += 1;
  }
} catch (error) {
  record('stream', physicalLines, String(error));
  const failed = {
    schema: 'path1_board_strict_qa_v1',
    checked_at: new Date().toISOString(),
    status: 'FAIL_STREAM',
    gz_path: gzPath,
    meta_path: metaPath,
    error: String(error),
    physical_lines: physicalLines,
    examples,
  };
  writeFileSync(outPath, `${JSON.stringify(failed, null, 2)}\n`, { flag: 'wx' });
  process.exit(3);
}

const expectedRows = Number(meta.infoSets);
const metadataChecks = {
  game: meta.game === 'HU_NLHE_SRP',
  stack: meta.stack === '200bb',
  config: meta.config === 'pipeline_srp_v3_200bb',
  board_id_integer: Number.isInteger(meta.boardId) && meta.boardId >= 0,
  flop_cards: Array.isArray(meta.flopCards) && meta.flopCards.length === 3 && new Set(meta.flopCards).size === 3,
  iterations: Number.isInteger(meta.iterations) && meta.iterations > 0,
  bucket_count: Number.isInteger(meta.bucketCount) && meta.bucketCount > 0,
  info_sets: Number.isInteger(expectedRows) && expectedRows > 0,
};
const metadataPass = Object.values(metadataChecks).every(Boolean);
const structuralPass = metadataPass && physicalLines === expectedRows && validRows === expectedRows
  && blankLines === 0 && parseErrors === 0 && schemaErrors === 0 && probabilityErrors === 0;
const meanMax = validRows ? sumMax / validRows : 0;
const decisiveRate = validRows ? decisive / validRows : 0;
const nearPureRate = validRows ? nearPure / validRows : 0;
const convergenceProxyPass = validRows > 100000 && meanMax >= 0.55 && decisiveRate >= 0.35;
const elapsedSeconds = (performance.now() - started) / 1000;

const report = {
  schema: 'path1_board_strict_qa_v1',
  checked_at: new Date().toISOString(),
  started_at: startedAt,
  status: structuralPass && convergenceProxyPass ? 'PASS_STRUCTURAL_AND_PROXY' : 'FAIL',
  scope: 'structural_integrity_and_convergence_proxy_only',
  limitations: [
    'Does not prove exploitability or equilibrium convergence.',
    'Does not prove global key uniqueness; exact uniqueness requires an external-sort audit.',
    'Does not prove downstream V5 distillation semantic compatibility.',
  ],
  gz_path: gzPath,
  meta_path: metaPath,
  compressed_sha256: compressedSha.digest('hex'),
  normalized_content_sha256: contentSha.digest('hex'),
  metadata: meta,
  metadata_checks: metadataChecks,
  counts: {
    expected_rows: expectedRows,
    physical_lines: physicalLines,
    valid_rows: validRows,
    blank_lines: blankLines,
    parse_errors: parseErrors,
    schema_errors: schemaErrors,
    probability_errors: probabilityErrors,
  },
  probability_summary: {
    min_probability: Number.isFinite(minProbability) ? minProbability : null,
    max_probability: Number.isFinite(maxProbability) ? maxProbability : null,
    max_sum_error: maxSumError,
    action_lengths: actionLengths,
  },
  convergence_proxy: {
    pass: convergenceProxyPass,
    mean_max_probability: meanMax,
    decisive_rate_ge_0_6: decisiveRate,
    near_pure_rate_ge_0_95: nearPureRate,
    thresholds: { min_rows: 100000, min_mean_max_probability: 0.55, min_decisive_rate: 0.35 },
  },
  structural_pass: structuralPass,
  elapsed_seconds: elapsedSeconds,
  rows_per_second: validRows / Math.max(elapsedSeconds, 1e-9),
  examples,
};

writeFileSync(outPath, `${JSON.stringify(report, null, 2)}\n`, { flag: 'wx' });
console.log(JSON.stringify({ status: report.status, board_id: meta.boardId, rows: validRows, elapsed_seconds: elapsedSeconds }));
process.exit(report.status === 'PASS_STRUCTURAL_AND_PROXY' ? 0 : 2);
