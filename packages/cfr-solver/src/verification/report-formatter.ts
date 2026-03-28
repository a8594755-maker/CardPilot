// Format verification results as console tables or JSON reports.

import type { ReferenceData } from './gto-reference.js';
import type { HandComparison, AggregateMetrics } from './strategy-comparator.js';

export interface VerificationReport {
  scenario: ReferenceData['scenario'];
  actions: string[];
  comparisons: HandComparison[];
  aggregate: AggregateMetrics;
  timestamp: string;
}

/**
 * Format a full console report for one reference scenario.
 */
export function formatConsoleReport(
  ref: ReferenceData,
  comparisons: HandComparison[],
  aggregate: AggregateMetrics,
): string {
  const lines: string[] = [];
  const { scenario, actions } = ref;

  // Header
  lines.push('');
  lines.push(
    `=== GTO Verification: ${scenario.board} | ${scenario.position} | ${scenario.spot} ${scenario.stack} ===`,
  );
  if (scenario.history) {
    lines.push(`    History: ${scenario.history}`);
  }
  lines.push('');

  // Build column headers
  const actionCols = actions.map((a) => padCenter(a, 8));
  const refCols = actions.map((a) => padCenter(`R:${a}`, 8));
  const ourCols = actions.map((a) => padCenter(`S:${a}`, 8));

  const header = [
    padRight('Hand', 6),
    padRight('#', 4),
    ...refCols,
    ...ourCols,
    padCenter('Match', 5),
    padCenter('JSD', 7),
  ].join(' | ');

  const separator = '-'.repeat(header.length);

  lines.push(header);
  lines.push(separator);

  // Hand rows
  for (const comp of comparisons) {
    const refFreqs = comp.refFrequencies.map((f) => padCenter(f.toFixed(2), 8));
    const solverFreqs = comp.solverFrequencies
      ? comp.solverFrequencies.map((f) => padCenter(f.toFixed(2), 8))
      : actions.map(() => padCenter('N/A', 8));

    const matchStr = comp.solverFrequencies ? (comp.actionMatch ? 'YES' : 'NO') : '---';

    const jsdStr = comp.solverFrequencies ? comp.jsd.toFixed(3) : 'N/A';

    const row = [
      padRight(comp.handClass, 6),
      padRight(String(comp.comboCount), 4),
      ...refFreqs,
      ...solverFreqs,
      padCenter(matchStr, 5),
      padCenter(jsdStr, 7),
    ].join(' | ');

    lines.push(row);
  }

  lines.push(separator);

  // Aggregate summary
  lines.push('');
  lines.push('--- Aggregate ---');
  lines.push(
    `Action agreement: ${(aggregate.actionAgreement * 100).toFixed(0)}% | ` +
      `Mean JSD: ${aggregate.meanJSD.toFixed(3)} | ` +
      `Pearson r: ${aggregate.pearsonR.toFixed(3)} | ` +
      `Coverage: ${(aggregate.coverageRate * 100).toFixed(0)}%`,
  );

  const verdictLabel =
    aggregate.verdict === 'PASS'
      ? 'PASS (JSD < 0.05, action agreement >= 80%)'
      : aggregate.verdict === 'MARGINAL'
        ? 'MARGINAL (JSD < 0.15, action agreement >= 60%)'
        : 'FAIL (high divergence from reference)';

  lines.push(`Verdict: ${verdictLabel}`);
  lines.push('');

  return lines.join('\n');
}

/**
 * Format a compact one-line summary for a scenario.
 */
export function formatOneLiner(ref: ReferenceData, aggregate: AggregateMetrics): string {
  const icon =
    aggregate.verdict === 'PASS' ? '[OK]' : aggregate.verdict === 'MARGINAL' ? '[??]' : '[FAIL]';

  return (
    `${icon} ${ref.scenario.board} | ${ref.scenario.position} ${ref.scenario.spot} ${ref.scenario.stack} | ` +
    `agreement: ${(aggregate.actionAgreement * 100).toFixed(0)}% | ` +
    `JSD: ${aggregate.meanJSD.toFixed(3)} | ` +
    `r: ${aggregate.pearsonR.toFixed(3)} | ` +
    `coverage: ${(aggregate.coverageRate * 100).toFixed(0)}%`
  );
}

/**
 * Build a JSON report object for programmatic consumption.
 */
export function buildJsonReport(
  ref: ReferenceData,
  comparisons: HandComparison[],
  aggregate: AggregateMetrics,
): VerificationReport {
  return {
    scenario: ref.scenario,
    actions: ref.actions,
    comparisons,
    aggregate,
    timestamp: new Date().toISOString(),
  };
}

// --- String padding helpers ---

function padRight(s: string, len: number): string {
  return s.length >= len ? s : s + ' '.repeat(len - s.length);
}

function padCenter(s: string, len: number): string {
  if (s.length >= len) return s;
  const left = Math.floor((len - s.length) / 2);
  const right = len - s.length - left;
  return ' '.repeat(left) + s + ' '.repeat(right);
}
