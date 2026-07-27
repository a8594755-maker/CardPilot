#!/usr/bin/env tsx
// GTO Verification CLI — compare solver output against GTO Wizard reference data,
// run analytical game-theoretic checks, and compute per-board exploitability.
//
// Usage:
//   npx tsx verify-gto.ts --ref data/cfr/reference/my-spot.json
//   npx tsx verify-gto.ts --ref data/cfr/reference/         # all files in dir
//   npx tsx verify-gto.ts --self-only --config hu_btn_bb_srp_100bb
//   npx tsx verify-gto.ts --ref ... --json report.json
//   npx tsx verify-gto.ts --pick-boards                     # print template files
//   npx tsx verify-gto.ts --analytical --config hu_btn_bb_srp_100bb
//   npx tsx verify-gto.ts --exploitability --config hu_btn_bb_srp_100bb --board 13
//   npx tsx verify-gto.ts --exploitability --config hu_btn_bb_srp_100bb --all-boards

import { resolve, join, basename } from 'node:path';
import { existsSync, readdirSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { createReadStream } from 'node:fs';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';

import { parseReference, parseBoardString } from '../verification/gto-reference.js';
import { computeBucketsForCombos, getHandClassStrategy } from '../verification/bucket-mapper.js';
import { compareHand, computeAggregateMetrics } from '../verification/strategy-comparator.js';
import {
  formatConsoleReport,
  formatOneLiner,
  buildJsonReport,
} from '../verification/report-formatter.js';
import { runAnalyticalChecks, formatAnalyticalReport } from '../verification/analytical-checks.js';
import { computeBoardExploitability } from '../verification/board-exploitability.js';
import type { ReferenceData } from '../verification/gto-reference.js';
import type { HandComparison, AggregateMetrics } from '../verification/strategy-comparator.js';
import type { VerificationReport } from '../verification/report-formatter.js';
import type { TreeConfigName } from '../tree/tree-config.js';
import type { BoardExploitabilityResult } from '../verification/board-exploitability.js';
import type { AnalyticalResult } from '../verification/analytical-checks.js';

const __dirname = fileURLToPath(new URL('.', import.meta.url));

function findProjectRoot(): string {
  const fromFile = resolve(__dirname, '../../../../');
  if (existsSync(resolve(fromFile, 'data'))) return fromFile;
  if (existsSync(resolve(process.cwd(), 'data'))) return process.cwd();
  const parent = resolve(process.cwd(), '../..');
  if (existsSync(resolve(parent, 'data'))) return parent;
  return process.cwd();
}

const PROJECT_ROOT = findProjectRoot();
const args = process.argv.slice(2);

function getArg(name: string, defaultVal: string): string {
  const idx = args.indexOf(`--${name}`);
  if (idx !== -1 && args[idx + 1]) return args[idx + 1];
  return defaultVal;
}

function printUsage(): void {
  console.log(`
GTO Verification Tool — Compare solver output vs GTO Wizard reference data,
run analytical game-theoretic checks, and compute per-board exploitability.

Usage:
  npx tsx verify-gto.ts --ref <path>             Compare against reference file(s)
  npx tsx verify-gto.ts --ref <dir>               Compare all JSON files in directory
  npx tsx verify-gto.ts --self-only               Self-validation only (no reference)
  npx tsx verify-gto.ts --pick-boards             Print template reference files
  npx tsx verify-gto.ts --ref ... --json out.json  Write JSON report
  npx tsx verify-gto.ts --analytical              Analytical game-theoretic checks
  npx tsx verify-gto.ts --exploitability --board N  Per-board exploitability
  npx tsx verify-gto.ts --exploitability --all-boards  All boards exploitability

Options:
  --ref PATH          Reference file or directory
  --config NAME       Solver config name (default: hu_btn_bb_srp_100bb)
  --json PATH         Write JSON report to file
  --self-only         Run self-validation checks only
  --pick-boards       Generate template reference files for solved boards
  --analytical        Run game-theoretic property checks (monotonicity, MDF, etc.)
  --exploitability    Compute best-response exploitability
  --board N           Specific board ID for exploitability (use with --exploitability)
  --all-boards        Compute exploitability for all solved boards
  --samples N         Number of samples per board for exploitability (default: 200)
  --verbose           Show detailed per-combo output
`);
}

// ---------- Find board info from meta files ----------

interface BoardInfo {
  boardId: number;
  flopCards: number[];
  jsonlFile: string;
  bucketCount: number;
}

function findBoard(flopIndices: number[], dir: string): BoardInfo | null {
  if (!existsSync(dir)) return null;

  const metaFiles = readdirSync(dir).filter((f) => f.endsWith('.meta.json'));
  const flopSet = new Set(flopIndices);

  for (const file of metaFiles) {
    try {
      const meta = JSON.parse(readFileSync(join(dir, file), 'utf-8'));
      if (meta.flopCards && Array.isArray(meta.flopCards)) {
        const metaSet = new Set(meta.flopCards as number[]);
        if (flopSet.size === metaSet.size && [...flopSet].every((c: number) => metaSet.has(c))) {
          const jsonlFile = file.replace('.meta.json', '.jsonl');
          return {
            boardId: meta.boardId,
            flopCards: meta.flopCards,
            jsonlFile,
            bucketCount: meta.bucketCount ?? 100,
          };
        }
      }
    } catch {
      /* skip */
    }
  }

  return null;
}

/**
 * Count available solved boards in a directory.
 */
function countSolvedBoards(dir: string): number {
  if (!existsSync(dir)) return 0;
  return readdirSync(dir).filter((f) => f.match(/^flop_\d+\.meta\.json$/)).length;
}

// ---------- Load strategies for a single board ----------

async function loadBoardStrategies(dir: string, jsonlFile: string): Promise<Map<string, number[]>> {
  const strategies = new Map<string, number[]>();
  const filePath = join(dir, jsonlFile);

  if (!existsSync(filePath)) {
    console.error(`JSONL file not found: ${filePath}`);
    return strategies;
  }

  const rl = createInterface({
    input: createReadStream(filePath, 'utf-8'),
    crlfDelay: Infinity,
  });

  let count = 0;
  for await (const line of rl) {
    if (!line.trim()) continue;
    try {
      const entry = JSON.parse(line) as { key: string; probs: number[] };
      strategies.set(entry.key, entry.probs);
      count++;
    } catch {
      /* skip bad lines */
    }
  }

  console.log(`Loaded ${count.toLocaleString()} strategies from ${jsonlFile}`);
  return strategies;
}

// ---------- Resolve config from reference scenario ----------

async function resolveConfig(
  ref: ReferenceData,
  overrideConfig?: string,
): Promise<{
  configName: TreeConfigName;
  outputDir: string;
  betSizes: { flop: number[]; turn: number[]; river: number[] };
}> {
  const { getTreeConfig, getConfigOutputDir } = await import('../tree/tree-config.js');

  if (overrideConfig) {
    const config = getTreeConfig(overrideConfig as TreeConfigName);
    return {
      configName: overrideConfig as TreeConfigName,
      outputDir: resolve(
        PROJECT_ROOT,
        'data/cfr',
        getConfigOutputDir(overrideConfig as TreeConfigName),
      ),
      betSizes: config.betSizes,
    };
  }

  // Auto-detect config from scenario
  const { spot, stack } = ref.scenario;
  const is3bp = spot.toLowerCase().includes('3b') || spot.toLowerCase().includes('3-bet');
  const is100bb = stack.includes('100');

  // Default to most common configs
  let configName: TreeConfigName;
  if (is3bp && is100bb) {
    configName = 'hu_btn_bb_3bp_100bb';
  } else if (is3bp) {
    configName = 'hu_btn_bb_3bp_50bb';
  } else if (is100bb) {
    configName = 'hu_btn_bb_srp_100bb';
  } else {
    configName = 'hu_btn_bb_srp_50bb';
  }

  const config = getTreeConfig(configName);
  return {
    configName,
    outputDir: resolve(PROJECT_ROOT, 'data/cfr', getConfigOutputDir(configName)),
    betSizes: config.betSizes,
  };
}

// ---------- Run comparison for one reference file ----------

async function verifyReference(
  ref: ReferenceData,
  overrideConfig?: string,
): Promise<{ comparisons: HandComparison[]; aggregate: AggregateMetrics } | null> {
  const resolved = await resolveConfig(ref, overrideConfig);
  console.log(`Config: ${resolved.configName}`);
  console.log(`Output dir: ${resolved.outputDir}`);

  // Find the specific board in solver output
  const flopIndices = ref.boardIndices.slice(0, 3);
  const boardInfo = findBoard(flopIndices, resolved.outputDir);
  if (!boardInfo) {
    const totalBoards = countSolvedBoards(resolved.outputDir);
    console.error(`Board ${ref.scenario.board} not found in solver output`);
    console.error(`Available boards: ${totalBoards} flops solved`);
    return null;
  }
  const { boardId, bucketCount } = boardInfo;
  console.log(`Board ID: ${boardId} (${boardInfo.jsonlFile})`);

  // Load only this board's strategies
  const strategies = await loadBoardStrategies(resolved.outputDir, boardInfo.jsonlFile);
  if (strategies.size === 0) {
    console.error(`No solver data found for board ${boardId}`);
    return null;
  }

  // Load preflop ranges for bucketing
  const { loadHUSRPRanges } = await import('../integration/preflop-ranges.js');
  const chartsPath = resolve(PROJECT_ROOT, 'data/preflop_charts.json');
  const { oopRange, ipRange } = loadHUSRPRanges(chartsPath);

  const player: 0 | 1 = ref.scenario.position === 'OOP' ? 0 : 1;
  const range = player === 0 ? oopRange : ipRange;

  // Compute buckets for all combos in reference hands
  const allCombos = ref.hands.flatMap((h) => h.combos);
  console.log(`Computing buckets for ${allCombos.length} combos...`);
  const comboBuckets = computeBucketsForCombos(
    allCombos,
    ref.boardIndices.slice(0, 3),
    range.combos,
    bucketCount,
  );

  // Get bet sizes for the current street
  const streetBetSizes = resolved.betSizes[ref.scenario.street];

  // Compare each hand
  const comparisons: HandComparison[] = [];

  for (const hand of ref.hands) {
    const { avgStrategy, coverage, comboCount } = getHandClassStrategy(
      hand.combos,
      comboBuckets,
      strategies,
      ref.scenario.street,
      boardId,
      player,
      ref.scenario.history,
      bucketCount,
    );

    // Map solver strategy to reference action order
    // The solver probs array order: check/fold, bet_0/call, bet_1, ..., allin
    // We need to align with reference actions
    let mappedStrategy: number[] | null = null;
    if (avgStrategy) {
      mappedStrategy = mapSolverToRefActions(
        avgStrategy,
        ref.actions,
        streetBetSizes,
        ref.scenario.history,
      );
    }

    comparisons.push(
      compareHand(hand.handClass, hand.frequencies, mappedStrategy, hand.totalCombos, coverage),
    );
  }

  const aggregate = computeAggregateMetrics(comparisons);
  return { comparisons, aggregate };
}

/**
 * Map solver probability array to reference action order.
 *
 * Solver action order (no facing bet): check, bet_0, bet_1, ..., allin
 * Solver action order (facing bet):    fold, call, raise_0, ..., allin
 *
 * Reference actions use labels like "check", "bet33", "bet75", "fold", "call", etc.
 */
function mapSolverToRefActions(
  solverProbs: number[],
  refActions: string[],
  betSizes: number[],
  history: string,
): number[] {
  // Determine if facing a bet
  const streetHistory = history.split('/').pop() ?? '';
  const lastChar = streetHistory.slice(-1);
  const facingBet = lastChar !== '' && '12345A'.includes(lastChar);

  // Build solver action names in order
  const solverActions: string[] = [];
  if (facingBet) {
    solverActions.push('fold', 'call');
    for (let i = 0; i < betSizes.length; i++) solverActions.push(`raise_${i}`);
    solverActions.push('allin');
  } else {
    solverActions.push('check');
    for (let i = 0; i < betSizes.length; i++) solverActions.push(`bet_${i}`);
    solverActions.push('allin');
  }

  // Trim solver probs to match solver actions count (may have fewer actions)
  const trimmedProbs = solverProbs.slice(0, solverActions.length);

  // Map each reference action to a solver action index
  return refActions.map((label) => {
    const lower = label.toLowerCase().trim();

    if (lower === 'check') return trimmedProbs[solverActions.indexOf('check')] ?? 0;
    if (lower === 'fold') return trimmedProbs[solverActions.indexOf('fold')] ?? 0;
    if (lower === 'call') return trimmedProbs[solverActions.indexOf('call')] ?? 0;
    if (lower === 'allin') return trimmedProbs[solverActions.indexOf('allin')] ?? 0;

    // betXX → closest bet_N
    const betMatch = lower.match(/^bet(\d+)$/);
    if (betMatch) {
      const pct = parseInt(betMatch[1], 10) / 100;
      let bestIdx = -1;
      let bestDist = Infinity;
      for (let i = 0; i < betSizes.length; i++) {
        const dist = Math.abs(betSizes[i] - pct);
        if (dist < bestDist) {
          bestDist = dist;
          bestIdx = i;
        }
      }
      if (bestIdx >= 0) {
        const actionIdx = solverActions.indexOf(`bet_${bestIdx}`);
        return actionIdx >= 0 ? (trimmedProbs[actionIdx] ?? 0) : 0;
      }
    }

    // raiseXX → closest raise_N
    const raiseMatch = lower.match(/^raise(\d+)$/);
    if (raiseMatch) {
      const pct = parseInt(raiseMatch[1], 10) / 100;
      let bestIdx = -1;
      let bestDist = Infinity;
      for (let i = 0; i < betSizes.length; i++) {
        const dist = Math.abs(betSizes[i] - pct);
        if (dist < bestDist) {
          bestDist = dist;
          bestIdx = i;
        }
      }
      if (bestIdx >= 0) {
        const actionIdx = solverActions.indexOf(`raise_${bestIdx}`);
        return actionIdx >= 0 ? (trimmedProbs[actionIdx] ?? 0) : 0;
      }
    }

    return 0;
  });
}

// ---------- Self-validation checks ----------

async function runSelfValidation(configName: TreeConfigName): Promise<void> {
  const { getConfigOutputDir } = await import('../tree/tree-config.js');
  const outputDir = resolve(PROJECT_ROOT, 'data/cfr', getConfigOutputDir(configName));

  console.log('');
  console.log('=== Self-Validation ===');
  console.log(`Config: ${configName}`);
  console.log(`Dir: ${outputDir}`);
  console.log('');

  if (!existsSync(outputDir)) {
    console.error(`Output directory not found: ${outputDir}`);
    return;
  }

  const files = readdirSync(outputDir).filter((f) => f.endsWith('.jsonl'));
  console.log(`Found ${files.length} solved flops`);

  let totalEntries = 0;
  let probSumErrors = 0;
  let uniformRows = 0;
  let nonUniformRows = 0;
  const monotonicity = { checks: 0, violations: 0 };

  for (const file of files) {
    const rl = createInterface({
      input: createReadStream(join(outputDir, file), 'utf-8'),
      crlfDelay: Infinity,
    });

    const bucketStrategies = new Map<number, number[]>();

    for await (const line of rl) {
      if (!line.trim()) continue;
      try {
        const entry = JSON.parse(line) as { key: string; probs: number[] };
        totalEntries++;

        // Prob sum check
        const sum = entry.probs.reduce((a, b) => a + b, 0);
        if (Math.abs(sum - 1.0) > 0.05) probSumErrors++;

        // Convergence check
        const allEqual = entry.probs.every((p) => Math.abs(p - entry.probs[0]) < 0.01);
        if (allEqual) uniformRows++;
        else nonUniformRows++;

        // Track flop OOP root strategies by bucket for monotonicity
        const keyParts = entry.key.split('|');
        if (keyParts[0] === 'F' && keyParts[2] === '0' && keyParts[3] === '') {
          const bucket = parseInt(keyParts[4] ?? '-1');
          if (!isNaN(bucket) && entry.probs.length >= 2) {
            // probs[0] = check, probs[1] = bet_0 (usually 33% pot)
            bucketStrategies.set(bucket, entry.probs);
          }
        }
      } catch {
        /* skip */
      }
    }

    // Check monotonicity: higher buckets should bet more
    const sortedBuckets = [...bucketStrategies.entries()].sort((a, b) => a[0] - b[0]);
    for (let i = 1; i < sortedBuckets.length; i++) {
      monotonicity.checks++;
      const prevBetFreq = 1 - (sortedBuckets[i - 1][1][0] ?? 0); // 1 - check freq = bet freq
      const currBetFreq = 1 - (sortedBuckets[i][1][0] ?? 0);
      // Allow small violations (5% tolerance)
      if (currBetFreq < prevBetFreq - 0.05) {
        monotonicity.violations++;
      }
    }
  }

  // Report
  console.log(`Total info sets: ${totalEntries.toLocaleString()}`);
  console.log(
    `Prob sum errors: ${probSumErrors} (${((probSumErrors / totalEntries) * 100).toFixed(3)}%)`,
  );
  console.log(
    `Convergence: ${nonUniformRows.toLocaleString()} non-uniform / ${totalEntries.toLocaleString()} total (${((nonUniformRows / totalEntries) * 100).toFixed(1)}%)`,
  );
  console.log(
    `Monotonicity: ${monotonicity.violations} violations / ${monotonicity.checks} checks (${monotonicity.checks > 0 ? ((monotonicity.violations / monotonicity.checks) * 100).toFixed(1) : 0}%)`,
  );
  console.log('');

  // Verdict
  const convergenceRate = nonUniformRows / totalEntries;
  const probOk = probSumErrors / totalEntries < 0.01;
  const convergenceOk = convergenceRate > 0.5;
  const monotonicOk =
    monotonicity.checks === 0 || monotonicity.violations / monotonicity.checks < 0.2;

  if (probOk && convergenceOk && monotonicOk) {
    console.log('Self-validation: PASS');
  } else {
    if (!probOk) console.log('  [FAIL] Too many probability sum errors');
    if (!convergenceOk) console.log('  [FAIL] Low convergence rate');
    if (!monotonicOk)
      console.log('  [WARN] High monotonicity violations (may indicate bucketing issues)');
  }
}

// ---------- Pick boards: generate template files ----------

async function pickBoards(configName: TreeConfigName): Promise<void> {
  const { getConfigOutputDir, getConfigLabel, getTreeConfig } =
    await import('../tree/tree-config.js');
  const { indexToCard } = await import('../abstraction/card-index.js');
  const outputDir = resolve(PROJECT_ROOT, 'data/cfr', getConfigOutputDir(configName));

  console.log('');
  console.log('=== Template Generator ===');
  console.log(`Config: ${configName} (${getConfigLabel(configName)})`);
  console.log('');

  if (!existsSync(outputDir)) {
    console.error(`Output directory not found: ${outputDir}`);
    return;
  }

  const metaFiles = readdirSync(outputDir)
    .filter((f) => f.endsWith('.meta.json'))
    .sort();
  console.log(`Found ${metaFiles.length} solved flops`);
  console.log('');

  // Pick representative boards (first 8)
  const picks = metaFiles.slice(0, 8);
  const config = getTreeConfig(configName);
  const betSizes = config.betSizes.flop;

  // Build action labels from config bet sizes
  const actionLabels = ['check'];
  for (const size of betSizes) {
    actionLabels.push(`bet${Math.round(size * 100)}`);
  }

  const refDir = resolve(PROJECT_ROOT, 'data/cfr/reference');
  mkdirSync(refDir, { recursive: true });

  for (const file of picks) {
    try {
      const meta = JSON.parse(readFileSync(join(outputDir, file), 'utf-8'));
      const boardStr = (meta.flopCards as number[]).map(indexToCard).join(' ');
      const boardId = meta.boardId;

      const template = {
        scenario: {
          board: boardStr,
          street: 'flop',
          position: 'OOP',
          spot: configName.includes('3b') ? '3BP' : 'SRP',
          stack: configName.includes('100bb') ? '100bb' : '50bb',
          history: '',
        },
        actions: actionLabels,
        hands: {
          AA: Object.fromEntries(actionLabels.map((a) => [a, 0])),
          AKs: Object.fromEntries(actionLabels.map((a) => [a, 0])),
          AKo: Object.fromEntries(actionLabels.map((a) => [a, 0])),
          KK: Object.fromEntries(actionLabels.map((a) => [a, 0])),
          QQ: Object.fromEntries(actionLabels.map((a) => [a, 0])),
          JJ: Object.fromEntries(actionLabels.map((a) => [a, 0])),
          AQs: Object.fromEntries(actionLabels.map((a) => [a, 0])),
          AQo: Object.fromEntries(actionLabels.map((a) => [a, 0])),
          KQs: Object.fromEntries(actionLabels.map((a) => [a, 0])),
          '72o': Object.fromEntries(actionLabels.map((a) => [a, 0])),
        },
      };

      const filename = `${configName}_flop_${boardId}.json`;
      const filepath = join(refDir, filename);
      writeFileSync(filepath, JSON.stringify(template, null, 2));
      console.log(`  Created: ${filename} (${boardStr})`);
    } catch (err) {
      console.error(`  Error processing ${file}: ${err}`);
    }
  }

  console.log('');
  console.log(`Templates saved to: ${refDir}`);
  console.log('Fill in GTO Wizard frequencies, then run:');
  console.log(`  npx tsx verify-gto.ts --ref ${refDir}`);
}

// ---------- Analytical checks ----------

async function runAnalytical(configName: TreeConfigName): Promise<AnalyticalResult> {
  const { getTreeConfig, getConfigOutputDir, getConfigLabel } =
    await import('../tree/tree-config.js');
  const config = getTreeConfig(configName);
  const outputDir = resolve(PROJECT_ROOT, 'data/cfr', getConfigOutputDir(configName));

  console.log('');
  console.log(`=== Analytical GTO Verification: ${configName} ===`);
  console.log(`  ${getConfigLabel(configName)}`);
  console.log(`  Dir: ${outputDir}`);
  console.log('');

  if (!existsSync(outputDir)) {
    console.error(`Output directory not found: ${outputDir}`);
    process.exit(1);
  }

  const jsonlFiles = readdirSync(outputDir).filter((f) => f.endsWith('.jsonl'));
  if (jsonlFiles.length === 0) {
    console.error('No JSONL files found in output directory');
    process.exit(1);
  }
  console.log(`Scanning ${jsonlFiles.length} solved boards...`);
  console.log('');

  const result = await runAnalyticalChecks(
    outputDir,
    jsonlFiles,
    config.betSizes,
    config.numBuckets ?? 100,
  );

  console.log(formatAnalyticalReport(result));
  return result;
}

// ---------- Exploitability ----------

async function runExploitability(
  configName: TreeConfigName,
  boardIdFilter: number | 'all',
  sampleCount: number,
): Promise<BoardExploitabilityResult[]> {
  const { getTreeConfig, getConfigOutputDir, getConfigLabel } =
    await import('../tree/tree-config.js');
  const config = getTreeConfig(configName);
  const outputDir = resolve(PROJECT_ROOT, 'data/cfr', getConfigOutputDir(configName));

  console.log('');
  console.log(`=== Per-Board Exploitability: ${configName} ===`);
  console.log(`  ${getConfigLabel(configName)}`);
  console.log(`  Dir: ${outputDir}`);
  console.log(`  Samples per board: ${sampleCount}`);
  console.log('');

  if (!existsSync(outputDir)) {
    console.error(`Output directory not found: ${outputDir}`);
    process.exit(1);
  }

  // Discover boards
  const metaFiles = readdirSync(outputDir)
    .filter((f) => f.match(/^flop_\d+\.meta\.json$/))
    .sort();
  const boards: Array<{
    boardId: number;
    flopCards: number[];
    jsonlFile: string;
    bucketCount: number;
  }> = [];

  for (const file of metaFiles) {
    try {
      const meta = JSON.parse(readFileSync(join(outputDir, file), 'utf-8'));
      const boardId = meta.boardId as number;
      if (boardIdFilter !== 'all' && boardId !== boardIdFilter) continue;
      boards.push({
        boardId,
        flopCards: meta.flopCards,
        jsonlFile: file.replace('.meta.json', '.jsonl'),
        bucketCount: meta.bucketCount ?? 100,
      });
    } catch {
      /* skip */
    }
  }

  if (boards.length === 0) {
    if (boardIdFilter !== 'all') {
      console.error(`Board ${boardIdFilter} not found. Available boards:`);
      for (const file of metaFiles.slice(0, 10)) {
        try {
          const meta = JSON.parse(readFileSync(join(outputDir, file), 'utf-8'));
          console.error(`  Board ${meta.boardId}: ${(meta.flopCards as number[]).join(',')}`);
        } catch {
          /* skip */
        }
      }
    } else {
      console.error('No solved boards found');
    }
    process.exit(1);
  }

  console.log(`Computing exploitability for ${boards.length} board(s)...`);
  console.log('');

  const results: BoardExploitabilityResult[] = [];

  for (const board of boards) {
    const strategies = await loadBoardStrategies(outputDir, board.jsonlFile);
    if (strategies.size === 0) {
      console.log(`  Board ${board.boardId}: no strategies, skipping`);
      continue;
    }

    const result = computeBoardExploitability(
      config,
      board.boardId,
      board.flopCards,
      strategies,
      [],
      [],
      board.bucketCount,
      sampleCount,
    );

    results.push(result);

    const { indexToCard } = await import('../abstraction/card-index.js');
    const boardStr = board.flopCards.map(indexToCard).join(' ');
    console.log(
      `  Board ${board.boardId} (${boardStr}): ` +
        `BR OOP=${result.brValueOOP.toFixed(4)}bb  BR IP=${result.brValueIP.toFixed(4)}bb  ` +
        `Exploit=${result.exploitabilityPctPot.toFixed(2)}% pot  ` +
        `[${result.rating}]  coverage=${(result.keyCoverage * 100).toFixed(1)}%  ` +
        `(${result.samples} samples)`,
    );
  }

  // Summary
  const avgCoverage = results.reduce((s, r) => s + r.keyCoverage, 0) / results.length;
  if (results.length > 0) {
    console.log('');
    console.log('--- Summary ---');
    const avgExploit = results.reduce((s, r) => s + r.exploitabilityPctPot, 0) / results.length;
    const excellent = results.filter((r) => r.rating === 'EXCELLENT').length;
    const good = results.filter((r) => r.rating === 'GOOD').length;
    const acceptable = results.filter((r) => r.rating === 'ACCEPTABLE').length;
    const poor = results.filter((r) => r.rating === 'POOR').length;

    console.log(`  Avg exploitability: ${avgExploit.toFixed(2)}% of pot`);
    console.log(`  Avg key coverage: ${(avgCoverage * 100).toFixed(1)}%`);
    console.log(
      `  Ratings: ${excellent} EXCELLENT, ${good} GOOD, ${acceptable} ACCEPTABLE, ${poor} POOR`,
    );

    let overallRating: string;
    if (avgExploit < 0.3) overallRating = 'EXCELLENT';
    else if (avgExploit < 1.0) overallRating = 'GOOD';
    else if (avgExploit < 3.0) overallRating = 'ACCEPTABLE';
    else overallRating = 'POOR';
    console.log(`  Overall: ${overallRating}`);

    if (avgCoverage < 0.1) {
      console.log('');
      console.log('  NOTE: Low key coverage (<10%) means most info-set lookups fell back to');
      console.log('  uniform strategy. This is expected with 100-bucket V2 abstraction and');
      console.log('  limited MCCFR iterations. The exploitability number reflects the sparse');
      console.log('  training coverage, not necessarily strategy quality at visited info-sets.');
      console.log('  Use --analytical for more meaningful quality checks on trained data.');
    }
  }

  return results;
}

// ---------- Main ----------

async function main(): Promise<void> {
  console.log('=== GTO Verification Tool ===');
  console.log('');

  if (args.includes('--help') || args.includes('-h')) {
    printUsage();
    return;
  }

  const configOverride = args.includes('--config')
    ? getArg('config', 'hu_btn_bb_srp_100bb')
    : undefined;

  // Pick boards mode
  if (args.includes('--pick-boards')) {
    const configName = (configOverride ?? 'hu_btn_bb_srp_100bb') as TreeConfigName;
    await pickBoards(configName);
    return;
  }

  // Self-validation only mode
  if (args.includes('--self-only')) {
    const configName = (configOverride ?? 'hu_btn_bb_srp_100bb') as TreeConfigName;
    await runSelfValidation(configName);
    return;
  }

  // Analytical checks mode
  if (args.includes('--analytical')) {
    const configName = (configOverride ?? 'hu_btn_bb_srp_100bb') as TreeConfigName;
    const analyticalResult = await runAnalytical(configName);

    // Also run exploitability if requested
    if (args.includes('--exploitability')) {
      const sampleCount = parseInt(getArg('samples', '200'));
      const boardArg = getArg('board', '');
      const boardFilter: number | 'all' = args.includes('--all-boards')
        ? 'all'
        : boardArg
          ? parseInt(boardArg)
          : 'all';
      const exploitResults = await runExploitability(configName, boardFilter, sampleCount);

      // Write combined JSON if requested
      const jsonPath = args.includes('--json') ? getArg('json', 'gto-report.json') : null;
      if (jsonPath) {
        const fullJsonPath = resolve(process.cwd(), jsonPath);
        writeFileSync(
          fullJsonPath,
          JSON.stringify(
            {
              config: configName,
              analytical: analyticalResult,
              exploitability: exploitResults,
            },
            null,
            2,
          ),
        );
        console.log(`\nJSON report written to: ${fullJsonPath}`);
      }
    } else {
      // JSON output for analytical only
      const jsonPath = args.includes('--json') ? getArg('json', 'gto-report.json') : null;
      if (jsonPath) {
        const fullJsonPath = resolve(process.cwd(), jsonPath);
        writeFileSync(
          fullJsonPath,
          JSON.stringify(
            {
              config: configName,
              analytical: analyticalResult,
            },
            null,
            2,
          ),
        );
        console.log(`\nJSON report written to: ${fullJsonPath}`);
      }
    }
    return;
  }

  // Exploitability only mode
  if (args.includes('--exploitability')) {
    const configName = (configOverride ?? 'hu_btn_bb_srp_100bb') as TreeConfigName;
    const sampleCount = parseInt(getArg('samples', '200'));
    const boardArg = getArg('board', '');
    const boardFilter: number | 'all' = args.includes('--all-boards')
      ? 'all'
      : boardArg
        ? parseInt(boardArg)
        : 0;

    if (boardFilter === 0 && !args.includes('--all-boards') && !boardArg) {
      console.error('Specify --board N or --all-boards for exploitability computation');
      process.exit(1);
    }

    const results = await runExploitability(configName, boardFilter, sampleCount);

    const jsonPath = args.includes('--json') ? getArg('json', 'gto-report.json') : null;
    if (jsonPath) {
      const fullJsonPath = resolve(process.cwd(), jsonPath);
      writeFileSync(
        fullJsonPath,
        JSON.stringify(
          {
            config: configName,
            exploitability: results,
          },
          null,
          2,
        ),
      );
      console.log(`\nJSON report written to: ${fullJsonPath}`);
    }
    return;
  }

  // Reference comparison mode
  const refPath = getArg('ref', '');
  if (!refPath) {
    printUsage();
    process.exit(1);
  }

  const fullRefPath = resolve(process.cwd(), refPath);
  if (!existsSync(fullRefPath)) {
    console.error(`Reference path not found: ${fullRefPath}`);
    process.exit(1);
  }

  // Collect reference files
  const refFiles: string[] = [];
  const { statSync } = await import('node:fs');
  const stat = statSync(fullRefPath);
  if (stat.isDirectory()) {
    const files = readdirSync(fullRefPath).filter((f) => f.endsWith('.json'));
    refFiles.push(...files.map((f) => join(fullRefPath, f)));
  } else {
    refFiles.push(fullRefPath);
  }

  if (refFiles.length === 0) {
    console.error('No JSON reference files found');
    process.exit(1);
  }

  console.log(`Found ${refFiles.length} reference file(s)`);
  console.log('');

  const allReports: VerificationReport[] = [];
  let totalPassed = 0;
  let totalFailed = 0;

  for (const file of refFiles) {
    console.log(`--- ${basename(file)} ---`);

    // Parse reference
    let ref: ReferenceData;
    try {
      const raw = JSON.parse(readFileSync(file, 'utf-8'));
      ref = parseReference(raw, file);
    } catch (err: any) {
      console.error(`  Parse error: ${err.message}`);
      totalFailed++;
      continue;
    }

    // Run comparison
    const result = await verifyReference(ref, configOverride);
    if (!result) {
      totalFailed++;
      continue;
    }

    // Output
    console.log(formatConsoleReport(ref, result.comparisons, result.aggregate));
    console.log(formatOneLiner(ref, result.aggregate));
    console.log('');

    if (result.aggregate.verdict === 'FAIL') totalFailed++;
    else totalPassed++;

    allReports.push(buildJsonReport(ref, result.comparisons, result.aggregate));
  }

  // Write JSON report if requested
  const jsonPath = args.includes('--json') ? getArg('json', 'gto-report.json') : null;
  if (jsonPath) {
    const fullJsonPath = resolve(process.cwd(), jsonPath);
    writeFileSync(fullJsonPath, JSON.stringify(allReports, null, 2));
    console.log(`JSON report written to: ${fullJsonPath}`);
  }

  // Summary
  console.log('');
  console.log('=== Summary ===');
  console.log(`Passed: ${totalPassed} | Failed: ${totalFailed}`);

  if (totalFailed > 0) {
    process.exit(1);
  }
}

main().catch((err) => {
  console.error('[FATAL]', err);
  process.exit(1);
});
