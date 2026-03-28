// Game-theoretic property validation from JSONL solver output.
// Verifies mathematical invariants that ANY correct Nash equilibrium must satisfy.

import { createReadStream } from 'node:fs';
import { createInterface } from 'node:readline';
import { join } from 'node:path';

export interface AnalyticalResult {
  monotonicity: MonotonicityResult;
  mdf: MdfResult;
  bluffRatio: BluffRatioResult;
  cbetFrequency: CbetResult;
  positionAdvantage: PositionResult;
  overall: 'PASS' | 'FAIL';
}

export interface MonotonicityResult {
  totalChecks: number;
  violations: number;
  violationRate: number;
  pass: boolean;
}

export interface MdfResult {
  checks: MdfCheck[];
  pass: boolean;
}

export interface MdfCheck {
  betSizeLabel: string;
  theoreticalMdf: number;
  actualDefense: number;
  sampleCount: number;
  pass: boolean;
}

export interface BluffRatioResult {
  checks: BluffCheck[];
  pass: boolean;
}

export interface BluffCheck {
  betSizeLabel: string;
  theoreticalBluffPct: number;
  actualBluffPct: number;
  sampleCount: number;
  pass: boolean;
}

export interface CbetResult {
  oopCbet: number;
  ipCbet: number;
  oopBoards: number;
  ipBoards: number;
  pass: boolean;
}

export interface PositionResult {
  ipBetsMoreCount: number;
  totalBoards: number;
  rate: number;
  pass: boolean;
}

interface ParsedKey {
  street: string; // F, T, R
  boardId: number;
  player: number; // 0 = OOP, 1 = IP
  history: string;
  bucketSuffix: string;
}

function parseInfoKey(key: string): ParsedKey | null {
  const parts = key.split('|');
  if (parts.length < 5) return null;
  return {
    street: parts[0],
    boardId: parseInt(parts[1]),
    player: parseInt(parts[2]),
    history: parts[3],
    bucketSuffix: parts[4],
  };
}

/**
 * Get the primary (first) bucket from a V2 bucket suffix like "82-73-69"
 */
function getPrimaryBucket(suffix: string): number {
  const parts = suffix.split('-');
  return parseInt(parts[parts.length - 1]); // last component is the current-street bucket
}

/**
 * Determine what actions are available based on history context.
 * Returns action names for interpreting probs array.
 */
function getActionContext(history: string): 'betting' | 'defense' {
  const streetHist = history.split('/').pop() ?? '';
  const lastChar = streetHist.slice(-1);
  if (lastChar !== '' && '12345A'.includes(lastChar)) return 'defense';
  return 'betting';
}

/**
 * Infer the bet size fraction from the action character.
 * '1' → bet_0, '2' → bet_1, '3' → bet_2, 'A' → all-in
 */
function betCharToIndex(ch: string): number {
  if (ch === 'A') return -1; // all-in
  return parseInt(ch) - 1; // '1' → 0, '2' → 1, '3' → 2
}

/**
 * Run all analytical checks on a set of JSONL files.
 */
export async function runAnalyticalChecks(
  dir: string,
  jsonlFiles: string[],
  betSizes: { flop: number[]; turn: number[]; river: number[] },
  numBuckets: number,
): Promise<AnalyticalResult> {
  // Accumulators
  const boardMonotonicity = new Map<number, { checks: number; violations: number }>();
  const mdfData: Map<string, { callSum: number; count: number }> = new Map();
  const bluffData: Map<
    string,
    { lowBucketBetSum: number; highBucketBetSum: number; totalBetSum: number; count: number }
  > = new Map();
  const boardCbets = new Map<
    number,
    { oopBetSum: number; oopCount: number; ipBetSum: number; ipCount: number }
  >();

  for (const file of jsonlFiles) {
    const boardMatch = file.match(/flop_(\d+)\.jsonl$/);
    if (!boardMatch) continue;
    const boardId = parseInt(boardMatch[1]);

    const flopOopStrategies = new Map<number, number[]>(); // bucket → probs
    const flopIpStrategies = new Map<number, number[]>(); // bucket → probs after OOP check

    const rl = createInterface({
      input: createReadStream(join(dir, file), 'utf-8'),
      crlfDelay: Infinity,
    });

    for await (const line of rl) {
      if (!line.trim()) continue;
      let entry: { key: string; probs: number[] };
      try {
        entry = JSON.parse(line);
      } catch {
        continue;
      }

      const parsed = parseInfoKey(entry.key);
      if (!parsed) continue;

      // --- Flop OOP root strategies (for monotonicity + c-bet) ---
      if (parsed.street === 'F' && parsed.player === 0 && parsed.history === '') {
        const bucket = parseInt(parsed.bucketSuffix);
        if (!isNaN(bucket)) {
          flopOopStrategies.set(bucket, entry.probs);
        }
      }

      // --- Flop IP after OOP check (for IP c-bet + position advantage) ---
      if (parsed.street === 'F' && parsed.player === 1 && parsed.history === 'x') {
        const bucket = parseInt(parsed.bucketSuffix);
        if (!isNaN(bucket)) {
          flopIpStrategies.set(bucket, entry.probs);
        }
      }

      // --- River defense nodes (for MDF check) ---
      if (parsed.street === 'R' && getActionContext(parsed.history) === 'defense') {
        const streetHist = parsed.history.split('/').pop() ?? '';
        const lastChar = streetHist.slice(-1);
        const betIdx = betCharToIndex(lastChar);
        const betSizeKey = betIdx >= 0 ? `bet_${betIdx}` : 'allin';

        // probs = [fold, call] (since raiseCapPerStreet = 0)
        if (entry.probs.length >= 2) {
          const callFreq = entry.probs[1]; // index 1 = call
          const existing = mdfData.get(betSizeKey) ?? { callSum: 0, count: 0 };
          existing.callSum += callFreq;
          existing.count++;
          mdfData.set(betSizeKey, existing);
        }
      }

      // --- River betting nodes (for bluff ratio) ---
      if (parsed.street === 'R' && getActionContext(parsed.history) === 'betting') {
        const primaryBucket = getPrimaryBucket(parsed.bucketSuffix);
        // probs = [check, bet_0, bet_1, ..., allin]
        const betFreq = entry.probs.slice(1).reduce((a, b) => a + b, 0); // sum of all bets

        for (let i = 0; i < betSizes.river.length; i++) {
          const betProb = entry.probs[1 + i] ?? 0;
          const sizeKey = `bet_${i}`;
          const existing = bluffData.get(sizeKey) ?? {
            lowBucketBetSum: 0,
            highBucketBetSum: 0,
            totalBetSum: 0,
            count: 0,
          };
          existing.totalBetSum += betProb;
          existing.count++;
          // Bottom 30% = bluffs, top 40% = value
          if (primaryBucket < numBuckets * 0.3) {
            existing.lowBucketBetSum += betProb;
          } else if (primaryBucket > numBuckets * 0.6) {
            existing.highBucketBetSum += betProb;
          }
          bluffData.set(sizeKey, existing);
        }
      }
    }

    // --- Compute per-board monotonicity ---
    const sorted = [...flopOopStrategies.entries()].sort((a, b) => a[0] - b[0]);
    let checks = 0;
    let violations = 0;
    for (let i = 1; i < sorted.length; i++) {
      checks++;
      const prevBet = 1 - (sorted[i - 1][1][0] ?? 0); // 1 - check_freq
      const currBet = 1 - (sorted[i][1][0] ?? 0);
      if (currBet < prevBet - 0.05) violations++;
    }
    boardMonotonicity.set(boardId, { checks, violations });

    // --- Compute per-board c-bet frequencies ---
    let oopBetSum = 0,
      oopCount = 0;
    for (const probs of flopOopStrategies.values()) {
      oopBetSum += 1 - (probs[0] ?? 0); // 1 - check freq
      oopCount++;
    }
    let ipBetSum = 0,
      ipCount = 0;
    for (const probs of flopIpStrategies.values()) {
      ipBetSum += 1 - (probs[0] ?? 0); // 1 - check freq
      ipCount++;
    }
    boardCbets.set(boardId, { oopBetSum, oopCount, ipBetSum, ipCount });
  }

  // --- Aggregate monotonicity ---
  let totalMonoChecks = 0,
    totalMonoViolations = 0;
  for (const { checks, violations } of boardMonotonicity.values()) {
    totalMonoChecks += checks;
    totalMonoViolations += violations;
  }
  const monoResult: MonotonicityResult = {
    totalChecks: totalMonoChecks,
    violations: totalMonoViolations,
    violationRate: totalMonoChecks > 0 ? totalMonoViolations / totalMonoChecks : 0,
    pass: totalMonoChecks === 0 || totalMonoViolations / totalMonoChecks < 0.2,
  };

  // --- MDF checks ---
  const mdfChecks: MdfCheck[] = [];
  for (let i = 0; i < betSizes.river.length; i++) {
    const sizeKey = `bet_${i}`;
    const data = mdfData.get(sizeKey);
    if (!data || data.count === 0) continue;

    const betFraction = betSizes.river[i];
    // MDF = P / (P + B) where B = betFraction * P, so MDF = 1 / (1 + betFraction)
    const theoreticalMdf = 1 / (1 + betFraction);
    const actualDefense = data.callSum / data.count;

    mdfChecks.push({
      betSizeLabel: `${Math.round(betFraction * 100)}% pot`,
      theoreticalMdf,
      actualDefense,
      sampleCount: data.count,
      pass: Math.abs(actualDefense - theoreticalMdf) < 0.15,
    });
  }
  const mdfResult: MdfResult = {
    checks: mdfChecks,
    pass: mdfChecks.length === 0 || mdfChecks.every((c) => c.pass),
  };

  // --- Bluff ratio checks ---
  const bluffChecks: BluffCheck[] = [];
  for (let i = 0; i < betSizes.river.length; i++) {
    const sizeKey = `bet_${i}`;
    const data = bluffData.get(sizeKey);
    if (!data || data.count === 0 || data.totalBetSum === 0) continue;

    const betFraction = betSizes.river[i];
    // Theoretical bluff% = B / (2B + P) where B = fraction * P
    // = fraction / (2 * fraction + 1)
    const theoreticalBluff = betFraction / (2 * betFraction + 1);
    const actualBluff = data.lowBucketBetSum / data.totalBetSum;

    bluffChecks.push({
      betSizeLabel: `${Math.round(betFraction * 100)}% pot`,
      theoreticalBluffPct: theoreticalBluff,
      actualBluffPct: actualBluff,
      sampleCount: data.count,
      pass: Math.abs(actualBluff - theoreticalBluff) < 0.2,
    });
  }
  const bluffResult: BluffRatioResult = {
    checks: bluffChecks,
    pass: bluffChecks.length === 0 || bluffChecks.every((c) => c.pass),
  };

  // --- C-bet frequency ---
  let totalOopCbet = 0,
    totalOopCount = 0;
  let totalIpCbet = 0,
    totalIpCount = 0;
  for (const { oopBetSum, oopCount, ipBetSum, ipCount } of boardCbets.values()) {
    if (oopCount > 0) {
      totalOopCbet += oopBetSum / oopCount;
      totalOopCount++;
    }
    if (ipCount > 0) {
      totalIpCbet += ipBetSum / ipCount;
      totalIpCount++;
    }
  }
  const avgOopCbet = totalOopCount > 0 ? totalOopCbet / totalOopCount : 0;
  const avgIpCbet = totalIpCount > 0 ? totalIpCbet / totalIpCount : 0;
  const cbetResult: CbetResult = {
    oopCbet: avgOopCbet,
    ipCbet: avgIpCbet,
    oopBoards: totalOopCount,
    ipBoards: totalIpCount,
    // Wide bounds: mainly catches degenerate strategies (always check or always bet)
    pass: avgOopCbet >= 0.05 && avgOopCbet <= 0.95 && avgIpCbet >= 0.05 && avgIpCbet <= 0.95,
  };

  // --- Position advantage ---
  let ipBetsMore = 0;
  for (const { oopBetSum, oopCount, ipBetSum, ipCount } of boardCbets.values()) {
    if (oopCount === 0 || ipCount === 0) continue;
    const oopRate = oopBetSum / oopCount;
    const ipRate = ipBetSum / ipCount;
    if (ipRate >= oopRate) ipBetsMore++;
  }
  const totalBoardsWithBoth = [...boardCbets.values()].filter(
    (b) => b.oopCount > 0 && b.ipCount > 0,
  ).length;
  const positionResult: PositionResult = {
    ipBetsMoreCount: ipBetsMore,
    totalBoards: totalBoardsWithBoth,
    rate: totalBoardsWithBoth > 0 ? ipBetsMore / totalBoardsWithBoth : 0,
    pass: totalBoardsWithBoth === 0 || ipBetsMore / totalBoardsWithBoth >= 0.5,
  };

  const overall =
    monoResult.pass && mdfResult.pass && bluffResult.pass && cbetResult.pass && positionResult.pass
      ? 'PASS'
      : 'FAIL';

  return {
    monotonicity: monoResult,
    mdf: mdfResult,
    bluffRatio: bluffResult,
    cbetFrequency: cbetResult,
    positionAdvantage: positionResult,
    overall,
  };
}

/**
 * Format analytical results for console output.
 */
export function formatAnalyticalReport(result: AnalyticalResult): string {
  const lines: string[] = [];

  // Monotonicity
  lines.push('--- Strategy Monotonicity ---');
  lines.push(
    `  ${result.monotonicity.violations}/${result.monotonicity.totalChecks} violations ` +
      `(${(result.monotonicity.violationRate * 100).toFixed(1)}%) | ` +
      `${result.monotonicity.pass ? 'PASS' : 'FAIL'} (threshold: < 20%)`,
  );
  lines.push('');

  // MDF
  lines.push('--- River MDF Compliance ---');
  if (result.mdf.checks.length === 0) {
    lines.push('  No river defense nodes found');
  }
  for (const c of result.mdf.checks) {
    lines.push(
      `  ${c.betSizeLabel}: MDF = ${(c.theoreticalMdf * 100).toFixed(1)}% | ` +
        `Actual: ${(c.actualDefense * 100).toFixed(1)}% | ` +
        `${c.pass ? 'PASS' : 'FAIL'} (${c.sampleCount} samples)`,
    );
  }
  lines.push('');

  // Bluff ratio
  lines.push('--- River Bluff Structure ---');
  if (result.bluffRatio.checks.length === 0) {
    lines.push('  No river betting nodes found');
  }
  for (const c of result.bluffRatio.checks) {
    lines.push(
      `  ${c.betSizeLabel}: Theory = ${(c.theoreticalBluffPct * 100).toFixed(1)}% | ` +
        `Actual: ${(c.actualBluffPct * 100).toFixed(1)}% | ` +
        `${c.pass ? 'PASS' : 'FAIL'} (${c.sampleCount} samples)`,
    );
  }
  lines.push('');

  // C-bet frequency
  lines.push('--- Aggregate C-bet Frequency ---');
  lines.push(
    `  OOP avg c-bet: ${(result.cbetFrequency.oopCbet * 100).toFixed(1)}% ` +
      `(${result.cbetFrequency.oopBoards} boards, range: 5-95%) | ` +
      `${result.cbetFrequency.pass ? 'PASS' : 'FAIL'}`,
  );
  lines.push(
    `  IP avg c-bet after check: ${(result.cbetFrequency.ipCbet * 100).toFixed(1)}% ` +
      `(${result.cbetFrequency.ipBoards} boards, range: 5-95%)`,
  );
  lines.push('');

  // Position advantage
  lines.push('--- Position Advantage ---');
  lines.push(
    `  IP bets more on ${result.positionAdvantage.ipBetsMoreCount}/${result.positionAdvantage.totalBoards} boards ` +
      `(${(result.positionAdvantage.rate * 100).toFixed(1)}%) | ` +
      `${result.positionAdvantage.pass ? 'PASS' : 'FAIL'} (threshold: > 50%)`,
  );
  lines.push('');

  // Overall
  lines.push(`=== OVERALL: ${result.overall} ===`);

  return lines.join('\n');
}
