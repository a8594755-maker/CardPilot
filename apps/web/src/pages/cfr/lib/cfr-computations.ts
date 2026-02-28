// CFR data computation utilities.
// Ported from packages/cfr-solver/viewer/index.html lines 732-840, 1268-1291.

/** Detect if loaded data uses V2 multi-dimensional bucket keys (contain '-' in suffix). */
export function detectKeyFormat(indexed: Map<string, number[]>): boolean {
  for (const key of indexed.keys()) {
    const parts = key.split('|');
    if (parts.length >= 5) {
      const suffix = parts[parts.length - 1];
      if (suffix.includes('-')) return true;
    }
  }
  return false;
}

/** Extract the primary (current street) bucket from a key suffix. */
export function extractPrimaryBucket(key: string): number {
  const parts = key.split('|');
  const suffix = parts[parts.length - 1];
  const dims = suffix.split('-');
  return parseInt(dims[dims.length - 1], 10);
}

/** Find any single entry matching the prefix (for numActions detection). */
export function findSampleEntry(
  indexed: Map<string, number[]>,
  prefix: string,
  bucketCount: number,
  isV2: boolean,
  prefixIndex?: Map<string, string[]>,
): { key: string; probs: number[]; bucket: number } | null {
  if (!isV2) {
    for (let b = 0; b < bucketCount; b++) {
      const probs = indexed.get(prefix + b);
      if (probs) return { key: prefix + b, probs, bucket: b };
    }
    return null;
  }
  // V2: use prefix index for O(1) lookup instead of O(n) scan
  if (prefixIndex) {
    const keys = prefixIndex.get(prefix);
    if (keys && keys.length > 0) {
      const key = keys[0];
      const probs = indexed.get(key);
      if (probs) return { key, probs, bucket: extractPrimaryBucket(key) };
    }
    return null;
  }
  for (const [key, probs] of indexed) {
    if (key.startsWith(prefix)) return { key, probs, bucket: extractPrimaryBucket(key) };
  }
  return null;
}

/** Check if any entry exists with the given prefix. */
export function hasEntryWithPrefix(
  indexed: Map<string, number[]>,
  prefix: string,
  bucketCount: number,
  isV2: boolean,
  prefixIndex?: Map<string, string[]>,
): boolean {
  if (!isV2) {
    for (let b = 0; b < bucketCount; b++) {
      if (indexed.has(prefix + b)) return true;
    }
    return false;
  }
  // V2: O(1) check via prefix index
  if (prefixIndex) {
    return (prefixIndex.get(prefix)?.length ?? 0) > 0;
  }
  for (const key of indexed.keys()) {
    if (key.startsWith(prefix)) return true;
  }
  return false;
}

/** Aggregate strategy data by primary bucket. Returns Map<bucket, avgProbs[]>. */
export function aggregateByPrimaryBucket(
  indexed: Map<string, number[]>,
  prefix: string,
  bucketCount: number,
  isV2: boolean,
  prefixIndex?: Map<string, string[]>,
): Map<number, number[]> {
  const result = new Map<number, { sums: number[]; count: number }>();

  if (!isV2) {
    for (let b = 0; b < bucketCount; b++) {
      const probs = indexed.get(prefix + b);
      if (probs) result.set(b, { sums: [...probs], count: 1 });
    }
  } else {
    // V2: iterate only matching keys via prefix index
    const keys = prefixIndex?.get(prefix);
    if (keys) {
      for (const key of keys) {
        const probs = indexed.get(key);
        if (!probs) continue;
        const pb = extractPrimaryBucket(key);
        if (!result.has(pb)) {
          result.set(pb, { sums: new Array(probs.length).fill(0), count: 0 });
        }
        const entry = result.get(pb)!;
        for (let i = 0; i < probs.length; i++) entry.sums[i] += probs[i];
        entry.count++;
      }
    } else {
      // Fallback: full scan
      for (const [key, probs] of indexed) {
        if (!key.startsWith(prefix)) continue;
        const pb = extractPrimaryBucket(key);
        if (!result.has(pb)) {
          result.set(pb, { sums: new Array(probs.length).fill(0), count: 0 });
        }
        const entry = result.get(pb)!;
        for (let i = 0; i < probs.length; i++) entry.sums[i] += probs[i];
        entry.count++;
      }
    }
  }

  const averaged = new Map<number, number[]>();
  for (const [b, { sums, count }] of result) {
    averaged.set(b, sums.map(s => s / count));
  }
  return averaged;
}

/** Get aggregated strategy probs for a specific primary bucket. */
export function getAggregatedProbs(
  indexed: Map<string, number[]>,
  prefix: string,
  primaryBucket: number,
  isV2: boolean,
  prefixIndex?: Map<string, string[]>,
): number[] | null {
  if (!isV2) {
    return indexed.get(prefix + primaryBucket) || null;
  }

  // V2: iterate only matching keys via prefix index
  let sums: number[] | null = null;
  let count = 0;
  const keys = prefixIndex?.get(prefix);
  if (keys) {
    for (const key of keys) {
      if (extractPrimaryBucket(key) !== primaryBucket) continue;
      const probs = indexed.get(key);
      if (!probs) continue;
      if (!sums) sums = new Array(probs.length).fill(0);
      for (let i = 0; i < probs.length; i++) sums[i] += probs[i];
      count++;
    }
  } else {
    // Fallback: full scan
    for (const [key, probs] of indexed) {
      if (!key.startsWith(prefix)) continue;
      if (extractPrimaryBucket(key) !== primaryBucket) continue;
      if (!sums) sums = new Array(probs.length).fill(0);
      for (let i = 0; i < probs.length; i++) sums[i] += probs[i];
      count++;
    }
  }
  if (!sums || count === 0) return null;
  return sums.map(s => s / count);
}

/** Build strength labels scaled to the actual bucket count. */
export function buildStrengthLabels(bc: number): Array<{
  from: number; to: number; label: string; cls: string;
}> {
  if (bc === 50) {
    return [
      { from: 0, to: 5, label: 'Trash', cls: 'weak' },
      { from: 5, to: 12, label: 'Weak', cls: 'weak' },
      { from: 12, to: 20, label: 'Marginal', cls: 'mid' },
      { from: 20, to: 30, label: 'Medium', cls: 'mid' },
      { from: 30, to: 40, label: 'Good', cls: 'strong' },
      { from: 40, to: 47, label: 'Strong', cls: 'strong' },
      { from: 47, to: 50, label: 'Nuts', cls: 'nuts' },
    ];
  }
  const scale = bc / 50;
  return [
    { from: 0, to: Math.round(5 * scale), label: 'Trash', cls: 'weak' },
    { from: Math.round(5 * scale), to: Math.round(12 * scale), label: 'Weak', cls: 'weak' },
    { from: Math.round(12 * scale), to: Math.round(20 * scale), label: 'Marginal', cls: 'mid' },
    { from: Math.round(20 * scale), to: Math.round(30 * scale), label: 'Medium', cls: 'mid' },
    { from: Math.round(30 * scale), to: Math.round(40 * scale), label: 'Good', cls: 'strong' },
    { from: Math.round(40 * scale), to: Math.round(47 * scale), label: 'Strong', cls: 'strong' },
    { from: Math.round(47 * scale), to: bc, label: 'Nuts', cls: 'nuts' },
  ];
}
