// Statistical comparison metrics for solver vs GTO reference strategies.

export interface HandComparison {
  handClass: string;
  comboCount: number;
  coverage: number; // fraction of combos with solver data
  refFrequencies: number[]; // GTO Wizard frequencies
  solverFrequencies: number[] | null; // our solver's averaged strategy
  actionMatch: boolean; // does top action match?
  jsd: number; // Jensen-Shannon divergence
  l1: number; // L1 (total variation) distance
  maxDelta: number; // max absolute difference for any action
}

export interface AggregateMetrics {
  totalHands: number;
  totalCombos: number; // total unblocked combos
  coveredCombos: number; // combos with solver data
  coverageRate: number; // coveredCombos / totalCombos
  actionAgreement: number; // fraction of hands where top action matches
  meanJSD: number; // combo-weighted mean JSD
  meanL1: number; // combo-weighted mean L1
  pearsonR: number; // overall frequency correlation
  verdict: 'PASS' | 'MARGINAL' | 'FAIL';
}

/**
 * Jensen-Shannon divergence between two probability distributions.
 * JSD is a symmetric, bounded [0, ln(2)] measure.
 * Returns value in [0, 1] (normalized by ln(2)).
 */
export function jensenShannonDivergence(p: number[], q: number[]): number {
  const n = Math.max(p.length, q.length);
  let jsd = 0;
  const ln2 = Math.log(2);

  for (let i = 0; i < n; i++) {
    const pi = p[i] ?? 0;
    const qi = q[i] ?? 0;
    const mi = (pi + qi) / 2;

    if (mi === 0) continue;
    if (pi > 0) jsd += 0.5 * pi * Math.log(pi / mi);
    if (qi > 0) jsd += 0.5 * qi * Math.log(qi / mi);
  }

  return Math.max(0, jsd / ln2); // normalize to [0, 1]
}

/**
 * L1 distance (total variation distance) between two distributions.
 */
export function l1Distance(p: number[], q: number[]): number {
  const n = Math.max(p.length, q.length);
  let sum = 0;
  for (let i = 0; i < n; i++) {
    sum += Math.abs((p[i] ?? 0) - (q[i] ?? 0));
  }
  return sum;
}

/**
 * Max absolute difference across all actions.
 */
export function maxDelta(p: number[], q: number[]): number {
  const n = Math.max(p.length, q.length);
  let max = 0;
  for (let i = 0; i < n; i++) {
    const d = Math.abs((p[i] ?? 0) - (q[i] ?? 0));
    if (d > max) max = d;
  }
  return max;
}

/**
 * Check if the primary (highest frequency) action matches.
 */
export function actionMatches(p: number[], q: number[]): boolean {
  if (p.length === 0 || q.length === 0) return false;

  let pMax = 0,
    pIdx = 0;
  for (let i = 0; i < p.length; i++) {
    if ((p[i] ?? 0) > pMax) {
      pMax = p[i] ?? 0;
      pIdx = i;
    }
  }

  let qMax = 0,
    qIdx = 0;
  for (let i = 0; i < q.length; i++) {
    if ((q[i] ?? 0) > qMax) {
      qMax = q[i] ?? 0;
      qIdx = i;
    }
  }

  return pIdx === qIdx;
}

/**
 * Compare a single hand class between reference and solver.
 */
export function compareHand(
  handClass: string,
  refFreqs: number[],
  solverFreqs: number[] | null,
  comboCount: number,
  coverage: number,
): HandComparison {
  if (!solverFreqs) {
    return {
      handClass,
      comboCount,
      coverage,
      refFrequencies: refFreqs,
      solverFrequencies: null,
      actionMatch: false,
      jsd: 1.0,
      l1: 2.0,
      maxDelta: 1.0,
    };
  }

  // Normalize both distributions to sum to 1
  const refNorm = normalizeDistribution(refFreqs);
  const solverNorm = normalizeDistribution(solverFreqs);

  return {
    handClass,
    comboCount,
    coverage,
    refFrequencies: refFreqs,
    solverFrequencies: solverFreqs,
    actionMatch: actionMatches(refNorm, solverNorm),
    jsd: jensenShannonDivergence(refNorm, solverNorm),
    l1: l1Distance(refNorm, solverNorm),
    maxDelta: maxDelta(refNorm, solverNorm),
  };
}

/**
 * Normalize a frequency array to sum to 1.0.
 * If sum is 0, returns uniform distribution.
 */
function normalizeDistribution(freqs: number[]): number[] {
  const sum = freqs.reduce((a, b) => a + b, 0);
  if (sum <= 0) return freqs.map(() => 1 / freqs.length);
  return freqs.map((f) => f / sum);
}

/**
 * Compute aggregate metrics across all hand comparisons.
 */
export function computeAggregateMetrics(comparisons: HandComparison[]): AggregateMetrics {
  const covered = comparisons.filter((c) => c.solverFrequencies !== null);
  const totalHands = comparisons.length;
  const totalCombos = comparisons.reduce((s, c) => s + c.comboCount, 0);
  const coveredCombos = covered.reduce((s, c) => s + Math.round(c.comboCount * c.coverage), 0);

  // Action agreement (among covered hands)
  const actionAgreement =
    covered.length > 0 ? covered.filter((c) => c.actionMatch).length / covered.length : 0;

  // Combo-weighted mean JSD
  const totalWeight = covered.reduce((s, c) => s + c.comboCount, 0);
  const meanJSD =
    totalWeight > 0 ? covered.reduce((s, c) => s + c.jsd * c.comboCount, 0) / totalWeight : 1.0;

  // Combo-weighted mean L1
  const meanL1 =
    totalWeight > 0 ? covered.reduce((s, c) => s + c.l1 * c.comboCount, 0) / totalWeight : 2.0;

  // Pearson correlation across all action frequencies
  const pearsonR = computePearsonCorrelation(covered);

  // Coverage rate
  const coverageRate = totalCombos > 0 ? coveredCombos / totalCombos : 0;

  // Verdict
  let verdict: 'PASS' | 'MARGINAL' | 'FAIL';
  if (meanJSD < 0.05 && actionAgreement >= 0.8) {
    verdict = 'PASS';
  } else if (meanJSD < 0.15 && actionAgreement >= 0.6) {
    verdict = 'MARGINAL';
  } else {
    verdict = 'FAIL';
  }

  return {
    totalHands,
    totalCombos,
    coveredCombos,
    coverageRate,
    actionAgreement,
    meanJSD,
    meanL1,
    pearsonR,
    verdict,
  };
}

/**
 * Compute Pearson correlation coefficient between all ref and solver frequencies.
 */
function computePearsonCorrelation(comparisons: HandComparison[]): number {
  const xs: number[] = [];
  const ys: number[] = [];

  for (const c of comparisons) {
    if (!c.solverFrequencies) continue;
    const n = Math.max(c.refFrequencies.length, c.solverFrequencies.length);
    for (let i = 0; i < n; i++) {
      xs.push(c.refFrequencies[i] ?? 0);
      ys.push(c.solverFrequencies[i] ?? 0);
    }
  }

  if (xs.length < 3) return 0;

  const n = xs.length;
  const sumX = xs.reduce((a, b) => a + b, 0);
  const sumY = ys.reduce((a, b) => a + b, 0);
  const sumXY = xs.reduce((a, x, i) => a + x * ys[i], 0);
  const sumX2 = xs.reduce((a, x) => a + x * x, 0);
  const sumY2 = ys.reduce((a, y) => a + y * y, 0);

  const numerator = n * sumXY - sumX * sumY;
  const denominator = Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));

  if (denominator === 0) return 0;
  return numerator / denominator;
}
