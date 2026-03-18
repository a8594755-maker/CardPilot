/**
 * Leak Detector
 *
 * Identifies systematic weaknesses in a player's game by clustering
 * decision points using learned embeddings from the coaching model.
 *
 * After collecting enough reviewed hands (100+), clusters spots by
 * strategic similarity (embedding space) and identifies clusters
 * where the player consistently loses EV.
 */

// ── Types ──

export interface DecisionRecord {
  /** 64-dim strategic embedding from coaching model. */
  embedding: Float32Array;
  /** EV lost at this decision (negative = mistake). */
  deltaEV: number;
  /** User's chosen action. */
  userAction: string;
  /** GTO's recommended action. */
  bestAction: string;
  /** Pot size in BB. */
  potSize: number;
  /** Game context metadata. */
  street: string;
  position: number;
  spr: number;
  facingBet: number;
  /** Hand example for display. */
  holeCards?: string;
  boardCards?: string;
}

export interface LeakCluster {
  /** Cluster ID (0-based). */
  id: number;
  /** 64-dim centroid embedding. */
  centroid: Float32Array;
  /** Human-readable spot description. */
  spotDescription: string;
  /** Number of decisions in this cluster. */
  sampleCount: number;
  /** Average ΔEV (negative = leak). */
  avgDeltaEV: number;
  /** Total EV lost in BB. */
  totalEVLost: number;
  /** Most common mistake type. */
  commonMistake: string;
  /** Example hands from this cluster. */
  examples: Array<{
    holeCards: string;
    boardCards: string;
    userAction: string;
    bestAction: string;
    deltaEV: number;
  }>;
}

export interface LeakReport {
  /** Total hands reviewed. */
  handsReviewed: number;
  /** Total decisions analyzed. */
  decisionsAnalyzed: number;
  /** Total EV lost in BB. */
  totalEVLost: number;
  /** Identified leak clusters, sorted by severity. */
  leaks: LeakCluster[];
  /** Timestamp. */
  generatedAt: string;
}

// ── K-means clustering (simple CPU implementation) ──

function euclidean(a: Float32Array, b: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < a.length; i++) {
    const d = a[i] - b[i];
    sum += d * d;
  }
  return Math.sqrt(sum);
}

function centroid(points: Float32Array[], dim: number): Float32Array {
  const c = new Float32Array(dim);
  if (points.length === 0) return c;
  for (const p of points) {
    for (let i = 0; i < dim; i++) c[i] += p[i];
  }
  for (let i = 0; i < dim; i++) c[i] /= points.length;
  return c;
}

function kmeans(
  embeddings: Float32Array[],
  k: number,
  maxIter = 50,
): { assignments: number[]; centroids: Float32Array[] } {
  const n = embeddings.length;
  const dim = embeddings[0].length;

  // Init: pick k random centroids
  const indices = Array.from({ length: n }, (_, i) => i);
  for (let i = indices.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [indices[i], indices[j]] = [indices[j], indices[i]];
  }
  let centroids: Float32Array[] = indices.slice(0, k).map((i) => new Float32Array(embeddings[i]));
  const assignments = new Array(n).fill(0);

  for (let iter = 0; iter < maxIter; iter++) {
    // Assign
    let changed = false;
    for (let i = 0; i < n; i++) {
      let bestDist = Infinity;
      let bestCluster = 0;
      for (let c = 0; c < k; c++) {
        const d = euclidean(embeddings[i], centroids[c]);
        if (d < bestDist) {
          bestDist = d;
          bestCluster = c;
        }
      }
      if (assignments[i] !== bestCluster) {
        assignments[i] = bestCluster;
        changed = true;
      }
    }

    if (!changed) break;

    // Update centroids
    const groups: Array<Float32Array[]> = Array.from({ length: k }, () => [] as Float32Array[]);
    for (let i = 0; i < n; i++) {
      groups[assignments[i]].push(embeddings[i] as Float32Array);
    }
    centroids = groups.map((g) => centroid(g as Float32Array[], dim));
  }

  return { assignments, centroids };
}

// ── Spot description generator ──

function describeSpot(records: DecisionRecord[]): string {
  if (records.length === 0) return 'unknown spot';

  // Aggregate characteristics
  const streets = new Map<string, number>();
  let avgSPR = 0;
  let facingBetCount = 0;
  let ipCount = 0;

  for (const r of records) {
    streets.set(r.street, (streets.get(r.street) ?? 0) + 1);
    avgSPR += r.spr;
    if (r.facingBet > 0) facingBetCount++;
    if (r.position === 1) ipCount++;
  }

  avgSPR /= records.length;
  const mainStreet = [...streets.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? 'flop';
  const posLabel =
    ipCount > records.length * 0.6 ? 'IP' : ipCount < records.length * 0.4 ? 'OOP' : 'mixed';
  const situation = facingBetCount > records.length * 0.5 ? 'facing bet' : 'opening action';
  const sprLabel = avgSPR < 3 ? 'low SPR' : avgSPR < 8 ? 'medium SPR' : 'deep SPR';

  return `${mainStreet}, ${posLabel}, ${situation}, ${sprLabel}`;
}

function describeMistake(records: DecisionRecord[]): string {
  const mistakeTypes = new Map<string, number>();

  for (const r of records) {
    if (r.deltaEV >= -0.01 * r.potSize) continue; // not a mistake

    const key = `${r.userAction} instead of ${r.bestAction}`;
    mistakeTypes.set(key, (mistakeTypes.get(key) ?? 0) + 1);
  }

  if (mistakeTypes.size === 0) return 'generally accurate';

  const sorted = [...mistakeTypes.entries()].sort((a, b) => b[1] - a[1]);
  return sorted[0][0];
}

// ── Public API ──

/**
 * Analyze a collection of reviewed decisions and identify leaks.
 *
 * @param records - All reviewed decisions with embeddings and ΔEV
 * @param k - Number of clusters (default 15)
 * @param minClusterSize - Minimum decisions in a cluster to be reported (default 5)
 * @returns Leak report with clusters sorted by severity
 */
export function detectLeaks(records: DecisionRecord[], k = 15, minClusterSize = 5): LeakReport {
  if (records.length < minClusterSize) {
    return {
      handsReviewed: 0,
      decisionsAnalyzed: records.length,
      totalEVLost: 0,
      leaks: [],
      generatedAt: new Date().toISOString(),
    };
  }

  // Cluster by embedding
  const effectiveK = Math.min(k, Math.floor(records.length / minClusterSize));
  const embeddings = records.map((r) => r.embedding);
  const { assignments, centroids } = kmeans(embeddings, effectiveK);

  // Group records by cluster
  const groups: DecisionRecord[][] = Array.from({ length: effectiveK }, () => []);
  for (let i = 0; i < records.length; i++) {
    groups[assignments[i]].push(records[i]);
  }

  // Build leak clusters
  const leaks: LeakCluster[] = [];
  for (let c = 0; c < effectiveK; c++) {
    const group = groups[c];
    if (group.length < minClusterSize) continue;

    const avgDelta = group.reduce((s, r) => s + r.deltaEV, 0) / group.length;
    const totalLost = group.reduce((s, r) => s + Math.abs(Math.min(0, r.deltaEV)), 0);

    // Only report clusters with significant mistakes
    const avgPotPct =
      group.reduce((s, r) => s + Math.abs(r.deltaEV) / Math.max(r.potSize, 0.01), 0) / group.length;
    if (avgPotPct < 0.02) continue; // less than 2% of pot on average

    // Pick worst examples
    const sorted = [...group].sort((a, b) => a.deltaEV - b.deltaEV);
    const examples = sorted.slice(0, 3).map((r) => ({
      holeCards: r.holeCards ?? '??',
      boardCards: r.boardCards ?? '??',
      userAction: r.userAction,
      bestAction: r.bestAction,
      deltaEV: r.deltaEV,
    }));

    leaks.push({
      id: c,
      centroid: centroids[c],
      spotDescription: describeSpot(group),
      sampleCount: group.length,
      avgDeltaEV: avgDelta,
      totalEVLost: totalLost,
      commonMistake: describeMistake(group),
      examples,
    });
  }

  // Sort by total EV lost (worst first)
  leaks.sort((a, b) => b.totalEVLost - a.totalEVLost);

  const totalEVLost = records.reduce((s, r) => s + Math.abs(Math.min(0, r.deltaEV)), 0);

  return {
    handsReviewed: 0, // caller should set this
    decisionsAnalyzed: records.length,
    totalEVLost,
    leaks,
    generatedAt: new Date().toISOString(),
  };
}
