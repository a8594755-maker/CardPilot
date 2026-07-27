// Map hand combos to solver equity buckets and look up strategies.
// Reuses the same bucketing algorithm the solver uses at training time.

import { indexToCard, comboIndex } from '../abstraction/card-index.js';
import { evaluateBestHand } from '@cardpilot/poker-evaluator';
import type { WeightedCombo } from '../integration/preflop-ranges.js';

/**
 * Compute equity bucket for a single hand relative to a range on a board.
 * Uses percentile rank within the range's hand strength distribution.
 * This is the same algorithm as computeSingleBucket in cfr-engine.ts.
 */
export function computeBucket(
  hand: [number, number],
  board: number[],
  range: WeightedCombo[],
  numBuckets: number,
): number {
  const handCards = [...hand.map(indexToCard), ...board.map(indexToCard)];
  const handEval = evaluateBestHand(handCards);
  const handValue = handEval.value;
  const boardSet = new Set(board);

  let weaker = 0;
  let total = 0;

  for (const { combo, weight } of range) {
    // Skip same hand and card conflicts
    if (combo[0] === hand[0] && combo[1] === hand[1]) continue;
    if (
      combo[0] === hand[0] ||
      combo[0] === hand[1] ||
      combo[1] === hand[0] ||
      combo[1] === hand[1]
    )
      continue;
    if (boardSet.has(combo[0]) || boardSet.has(combo[1])) continue;

    const comboCards = [...combo.map(indexToCard), ...board.map(indexToCard)];
    const comboEval = evaluateBestHand(comboCards);
    total += weight;
    if (comboEval.value < handValue) weaker += weight;
    else if (comboEval.value === handValue) weaker += weight * 0.5;
  }

  if (total === 0) return Math.floor(numBuckets / 2);
  const percentile = weaker / total;
  return Math.min(numBuckets - 1, Math.floor(percentile * numBuckets));
}

/**
 * Batch compute buckets for multiple combos on the same board.
 * Returns a Map from combo key "c1,c2" to bucket number.
 */
export function computeBucketsForCombos(
  combos: Array<[number, number]>,
  board: number[],
  range: WeightedCombo[],
  numBuckets: number,
): Map<string, number> {
  const result = new Map<string, number>();

  for (const combo of combos) {
    const key = `${Math.min(combo[0], combo[1])},${Math.max(combo[0], combo[1])}`;
    if (result.has(key)) continue;
    const bucket = computeBucket(combo, board, range, numBuckets);
    result.set(key, bucket);
  }

  return result;
}

/**
 * Look up solver strategy for a specific bucket from loaded JSONL strategies.
 *
 * Info-set key format (V2):
 * - Flop:  F|{boardId}|{player}|{history}|{flopBucket}
 * - Turn:  T|{boardId}|{player}|{history}|{flopBucket}-{turnBucket}
 * - River: R|{boardId}|{player}|{history}|{flopBucket}-{turnBucket}-{riverBucket}
 */
export function lookupBucketStrategy(
  strategies: Map<string, number[]>,
  street: 'flop' | 'turn' | 'river',
  boardId: number,
  player: 0 | 1,
  history: string,
  bucket: number,
): number[] | null {
  const streetChar = street === 'flop' ? 'F' : street === 'turn' ? 'T' : 'R';
  const key = `${streetChar}|${boardId}|${player}|${history}|${bucket}`;
  return strategies.get(key) ?? null;
}

/**
 * Look up strategy with fallback: try exact bucket, then search +-radius.
 */
export function lookupBucketStrategyFuzzy(
  strategies: Map<string, number[]>,
  street: 'flop' | 'turn' | 'river',
  boardId: number,
  player: 0 | 1,
  history: string,
  bucket: number,
  numBuckets: number,
  searchRadius = 3,
): { probs: number[]; actualBucket: number } | null {
  // Try exact match first
  const exact = lookupBucketStrategy(strategies, street, boardId, player, history, bucket);
  if (exact) return { probs: exact, actualBucket: bucket };

  // Search nearby buckets
  for (let delta = 1; delta <= searchRadius; delta++) {
    for (const d of [delta, -delta]) {
      const b = bucket + d;
      if (b < 0 || b >= numBuckets) continue;
      const probs = lookupBucketStrategy(strategies, street, boardId, player, history, b);
      if (probs) return { probs, actualBucket: b };
    }
  }

  return null;
}

/**
 * For each hand class, compute average solver strategy across all combos.
 * Each combo maps to a bucket, each bucket has a strategy.
 * We average strategies across all unblocked combos.
 */
export function getHandClassStrategy(
  combos: Array<[number, number]>,
  comboBuckets: Map<string, number>,
  strategies: Map<string, number[]>,
  street: 'flop' | 'turn' | 'river',
  boardId: number,
  player: 0 | 1,
  history: string,
  numBuckets: number,
): { avgStrategy: number[] | null; coverage: number; comboCount: number } {
  let found = 0;
  let sumStrategy: number[] | null = null;

  for (const combo of combos) {
    const key = `${Math.min(combo[0], combo[1])},${Math.max(combo[0], combo[1])}`;
    const bucket = comboBuckets.get(key);
    if (bucket === undefined) continue;

    const result = lookupBucketStrategyFuzzy(
      strategies,
      street,
      boardId,
      player,
      history,
      bucket,
      numBuckets,
    );
    if (!result) continue;

    found++;
    if (!sumStrategy) {
      sumStrategy = result.probs.map((p) => p);
    } else {
      for (let i = 0; i < result.probs.length; i++) {
        sumStrategy[i] = (sumStrategy[i] ?? 0) + (result.probs[i] ?? 0);
      }
    }
  }

  if (!sumStrategy || found === 0) {
    return { avgStrategy: null, coverage: 0, comboCount: combos.length };
  }

  const avgStrategy = sumStrategy.map((s) => s / found);
  return {
    avgStrategy,
    coverage: found / combos.length,
    comboCount: combos.length,
  };
}
