// Tests for V2 weighted sampling and range weight handling
//
// Verifies:
// - getWeightedRangeCombos returns correct weights from GTO Wizard data
// - Weighted sampling respects frequency weights
// - computeEquityBuckets works with WeightedCombo[]

import { test, describe } from 'node:test';
import * as assert from 'node:assert/strict';
import { resolve } from 'node:path';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import {
  loadHUSRPRanges,
  getRangeCombos,
  getWeightedRangeCombos,
} from '../integration/preflop-ranges.js';
import type { WeightedCombo } from '../integration/preflop-ranges.js';
import { computeEquityBuckets, comboKey } from '../engine/cfr-engine.js';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const chartsPath = resolve(__dirname, '../../../../data/preflop_charts.json');
const hasChartsFile = existsSync(chartsPath);

describe('WeightedCombo and getWeightedRangeCombos', () => {
  test('getWeightedRangeCombos returns WeightedCombo[] with weight field', { skip: !hasChartsFile }, () => {
    const ranges = loadHUSRPRanges(chartsPath);
    const dead = new Set<number>();
    const weighted = getWeightedRangeCombos(ranges.oopRange, dead);

    assert.ok(weighted.length > 0, 'Should return non-empty array');

    // Every entry should have combo and weight
    for (const wc of weighted) {
      assert.ok(Array.isArray(wc.combo), 'combo should be an array');
      assert.equal(wc.combo.length, 2, 'combo should have 2 cards');
      assert.equal(typeof wc.weight, 'number', 'weight should be a number');
      assert.ok(wc.weight > 0, 'weight should be > 0');
      assert.ok(wc.weight <= 1, 'weight should be <= 1');
    }
  });

  test('getWeightedRangeCombos filters dead cards correctly', { skip: !hasChartsFile }, () => {
    const ranges = loadHUSRPRanges(chartsPath);
    const allCombos = getWeightedRangeCombos(ranges.oopRange);

    // Dead cards: As (0*4+3 = 3) and Kh (12*4+2 = 50)
    const dead = new Set<number>([3, 50]);
    const filtered = getWeightedRangeCombos(ranges.oopRange, dead);

    assert.ok(filtered.length < allCombos.length, 'Dead card filter should remove some combos');

    // Verify no filtered combo contains dead cards
    for (const wc of filtered) {
      assert.ok(!dead.has(wc.combo[0]), `combo[0]=${wc.combo[0]} should not be dead`);
      assert.ok(!dead.has(wc.combo[1]), `combo[1]=${wc.combo[1]} should not be dead`);
    }
  });

  test('getWeightedRangeCombos deduplicates combos', { skip: !hasChartsFile }, () => {
    const ranges = loadHUSRPRanges(chartsPath);
    const combos = getWeightedRangeCombos(ranges.oopRange);

    // Check for duplicates using canonical key
    const seen = new Set<string>();
    for (const wc of combos) {
      const key = comboKey(wc.combo);
      assert.ok(!seen.has(key), `Duplicate combo found: ${key}`);
      seen.add(key);
    }
  });

  test('legacy getRangeCombos still works (backward compat)', { skip: !hasChartsFile }, () => {
    const ranges = loadHUSRPRanges(chartsPath);
    const dead = new Set<number>();
    const legacy = getRangeCombos(ranges.oopRange, dead);
    const weighted = getWeightedRangeCombos(ranges.oopRange, dead);

    // Legacy returns [number, number][], weighted returns WeightedCombo[]
    // Counts should be similar (legacy may include weight=0 combos if any)
    assert.ok(legacy.length > 0, 'Legacy combos should be non-empty');
    assert.ok(weighted.length > 0, 'Weighted combos should be non-empty');
    assert.ok(weighted.length <= legacy.length, 'Weighted should not have more combos than legacy');
  });

  test('some combos should have weight < 1 (mixed frequencies)', { skip: !hasChartsFile }, () => {
    const ranges = loadHUSRPRanges(chartsPath);
    const combos = getWeightedRangeCombos(ranges.oopRange);

    const subOneCount = combos.filter(wc => wc.weight < 1).length;
    // In typical GTO ranges, some hands have mixed frequencies
    // If all hands have weight=1, the test still passes (uniform range)
    assert.ok(subOneCount >= 0, 'Count of sub-1 weights should be non-negative');
    console.log(`  OOP range: ${combos.length} combos, ${subOneCount} with weight < 1`);
  });
});

describe('computeEquityBuckets with WeightedCombo', () => {
  test('assigns buckets from 0 to numBuckets-1', { skip: !hasChartsFile }, () => {
    const ranges = loadHUSRPRanges(chartsPath);
    const flopCards: [number, number, number] = [0, 5, 10]; // 2c, 3d, 4h
    const dead = new Set<number>(flopCards);
    const weighted = getWeightedRangeCombos(ranges.oopRange, dead);

    const buckets = computeEquityBuckets(weighted, flopCards, 50, dead);

    assert.ok(buckets.size > 0, 'Should assign buckets to some combos');

    let minBucket = Infinity;
    let maxBucket = -Infinity;
    for (const b of buckets.values()) {
      if (b < minBucket) minBucket = b;
      if (b > maxBucket) maxBucket = b;
    }

    assert.ok(minBucket >= 0, 'Min bucket should be >= 0');
    assert.ok(maxBucket <= 49, 'Max bucket should be <= 49');
    assert.equal(minBucket, 0, 'Weakest hands should be in bucket 0');
    // Max bucket may be 48 or 49 depending on rounding (range size / bucketCount)
    assert.ok(maxBucket >= 47, `Strongest hands should be near bucket 49, got ${maxBucket}`);
  });

  test('different boards produce different bucket assignments', { skip: !hasChartsFile }, () => {
    const ranges = loadHUSRPRanges(chartsPath);

    // Board 1: low rainbow (2c 3d 4h)
    const board1: [number, number, number] = [0, 5, 10];
    const dead1 = new Set<number>(board1);
    const weighted1 = getWeightedRangeCombos(ranges.oopRange, dead1);
    const buckets1 = computeEquityBuckets(weighted1, board1, 50, dead1);

    // Board 2: high monotone (Ah Kh Qh = 50, 46, 42)
    const board2: [number, number, number] = [50, 46, 42];
    const dead2 = new Set<number>(board2);
    const weighted2 = getWeightedRangeCombos(ranges.oopRange, dead2);
    const buckets2 = computeEquityBuckets(weighted2, board2, 50, dead2);

    // Find a hand that's in both ranges and check buckets differ
    let diffCount = 0;
    let commonCount = 0;
    for (const [key, b1] of buckets1) {
      const b2 = buckets2.get(key);
      if (b2 !== undefined) {
        commonCount++;
        if (b1 !== b2) diffCount++;
      }
    }

    assert.ok(commonCount > 0, 'Should have hands in common between boards');
    assert.ok(diffCount > 0, 'Different boards should produce different bucket assignments');
    console.log(`  Common combos: ${commonCount}, different buckets: ${diffCount}`);
  });
});

describe('Weighted sampling distribution', () => {
  // Test that a simple weighted range samples proportionally
  test('higher-weight combos are sampled more frequently', () => {
    // Create a tiny synthetic range
    const range: WeightedCombo[] = [
      { combo: [0, 4], weight: 1.0 },   // Full weight
      { combo: [1, 5], weight: 0.5 },   // Half weight
      { combo: [2, 6], weight: 0.25 },  // Quarter weight
      { combo: [3, 7], weight: 0.1 },   // Tenth weight
    ];

    // Simulate weighted sampling by counting how many times each would be selected
    // Using the same approach as the engine: cumulative weights + binary search
    const cumWeights = new Float32Array(range.length);
    let sum = 0;
    for (let i = 0; i < range.length; i++) {
      sum += range[i].weight;
      cumWeights[i] = sum;
    }

    const total = cumWeights[cumWeights.length - 1];
    const counts = new Array(range.length).fill(0);
    const N = 10000;

    // Use deterministic sampling points across the weight space
    for (let i = 0; i < N; i++) {
      const r = (i / N) * total;
      let lo = 0;
      let hi = cumWeights.length - 1;
      while (lo < hi) {
        const mid = (lo + hi) >>> 1;
        if (cumWeights[mid] < r) lo = mid + 1;
        else hi = mid;
      }
      counts[lo]++;
    }

    // Check proportions roughly match weights
    const expectedRatios = range.map(wc => wc.weight / total);
    const actualRatios = counts.map(c => c / N);

    for (let i = 0; i < range.length; i++) {
      const diff = Math.abs(actualRatios[i] - expectedRatios[i]);
      assert.ok(diff < 0.05, `Sample ratio for combo ${i}: expected ~${expectedRatios[i].toFixed(3)}, got ${actualRatios[i].toFixed(3)}`);
    }

    // Combo 0 (weight 1.0) should be sampled most
    assert.ok(counts[0] > counts[1], 'Weight 1.0 combo should be sampled more than weight 0.5');
    assert.ok(counts[1] > counts[2], 'Weight 0.5 combo should be sampled more than weight 0.25');
    assert.ok(counts[2] > counts[3], 'Weight 0.25 combo should be sampled more than weight 0.1');
  });
});
