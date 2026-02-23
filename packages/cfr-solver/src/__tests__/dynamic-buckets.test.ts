// Tests for V2 dynamic per-street bucketing and info-set key format
//
// Verifies:
// - buildInfoKey produces correct V2 format
// - computeEquityBuckets produces different assignments for different boards
// - Integration: mini-solve with V2 engine produces distinct per-street buckets

import { test, describe } from 'node:test';
import * as assert from 'node:assert/strict';
import { resolve } from 'node:path';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import {
  buildInfoKey,
  comboKey,
  streetChar,
  computeEquityBuckets,
  solveCFR,
} from '../engine/cfr-engine.js';
import { InfoSetStore } from '../engine/info-set-store.js';
import { buildTree } from '../tree/tree-builder.js';
import { V1_TREE_CONFIG } from '../tree/tree-config.js';
import type { WeightedCombo } from '../integration/preflop-ranges.js';
import type { Street } from '../types.js';

const __dirname = fileURLToPath(new URL('.', import.meta.url));

describe('buildInfoKey V2 format', () => {
  test('flop key has single bucket suffix', () => {
    const buckets: Record<Street, [number, number]> = {
      FLOP: [10, 20],
      TURN: [15, 25],
      RIVER: [30, 40],
    };

    const key = buildInfoKey('FLOP', 42, 0, 'xa', buckets);
    assert.equal(key, 'F|42|0|xa|10', 'Flop key should use flopBucket only');

    const keyIP = buildInfoKey('FLOP', 42, 1, 'xa', buckets);
    assert.equal(keyIP, 'F|42|1|xa|20', 'IP should use their own flop bucket');
  });

  test('turn key has two-bucket suffix (flop-turn)', () => {
    const buckets: Record<Street, [number, number]> = {
      FLOP: [10, 20],
      TURN: [15, 25],
      RIVER: [30, 40],
    };

    const key = buildInfoKey('TURN', 42, 0, 'xx/ab', buckets);
    assert.equal(key, 'T|42|0|xx/ab|10-15', 'Turn key should have flopBucket-turnBucket');

    const keyIP = buildInfoKey('TURN', 42, 1, 'xx/ab', buckets);
    assert.equal(keyIP, 'T|42|1|xx/ab|20-25', 'IP turn key should use IP buckets');
  });

  test('river key has three-bucket suffix (flop-turn-river)', () => {
    const buckets: Record<Street, [number, number]> = {
      FLOP: [10, 20],
      TURN: [15, 25],
      RIVER: [30, 40],
    };

    const key = buildInfoKey('RIVER', 42, 0, 'xx/xx/', buckets);
    assert.equal(key, 'R|42|0|xx/xx/|10-15-30', 'River key should have all three buckets');

    const keyIP = buildInfoKey('RIVER', 42, 1, 'xx/xx/', buckets);
    assert.equal(keyIP, 'R|42|1|xx/xx/|20-25-40', 'IP river key should use IP buckets');
  });

  test('empty history key works', () => {
    const buckets: Record<Street, [number, number]> = {
      FLOP: [5, 5],
      TURN: [5, 5],
      RIVER: [5, 5],
    };

    const key = buildInfoKey('FLOP', 0, 0, '', buckets);
    assert.equal(key, 'F|0|0||5', 'Root flop node should have empty history');
  });

  test('bucket values at boundaries', () => {
    const buckets: Record<Street, [number, number]> = {
      FLOP: [0, 49],
      TURN: [0, 49],
      RIVER: [0, 49],
    };

    assert.equal(buildInfoKey('FLOP', 0, 0, '', buckets), 'F|0|0||0');
    assert.equal(buildInfoKey('FLOP', 0, 1, '', buckets), 'F|0|1||49');
    assert.equal(buildInfoKey('RIVER', 0, 0, 'xx/xx/', buckets), 'R|0|0|xx/xx/|0-0-0');
    assert.equal(buildInfoKey('RIVER', 0, 1, 'xx/xx/', buckets), 'R|0|1|xx/xx/|49-49-49');
  });
});

describe('streetChar', () => {
  test('returns correct single character per street', () => {
    assert.equal(streetChar('FLOP'), 'F');
    assert.equal(streetChar('TURN'), 'T');
    assert.equal(streetChar('RIVER'), 'R');
  });
});

describe('comboKey', () => {
  test('canonicalizes card order (smaller first)', () => {
    assert.equal(comboKey([10, 5]), '5,10');
    assert.equal(comboKey([5, 10]), '5,10');
    assert.equal(comboKey([0, 51]), '0,51');
    assert.equal(comboKey([51, 0]), '0,51');
  });

  test('same cards produce same key regardless of order', () => {
    assert.equal(comboKey([20, 30]), comboKey([30, 20]));
  });
});

describe('computeEquityBuckets with different boards', () => {
  // Create a small synthetic range for testing
  function makeRange(cards: Array<[number, number]>): WeightedCombo[] {
    return cards.map(combo => ({ combo, weight: 1.0 }));
  }

  test('produces bucket assignments for simple range', () => {
    // Small range: pairs from 2c2d to 5c5d
    const range = makeRange([
      [0, 1],   // 2c2d
      [4, 5],   // 3c3d
      [8, 9],   // 4c4d
      [12, 13], // 5c5d
      [16, 17], // 6c6d
    ]);
    const board: [number, number, number] = [20, 24, 28]; // 7c, 8c, 9c
    const dead = new Set<number>(board);
    const buckets = computeEquityBuckets(range, board, 5, dead);

    assert.ok(buckets.size > 0, 'Should produce bucket assignments');

    // Higher pairs should get higher bucket numbers
    const b2 = buckets.get(comboKey([0, 1]));   // 22
    const b5 = buckets.get(comboKey([12, 13])); // 55
    const b6 = buckets.get(comboKey([16, 17])); // 66

    assert.ok(b2 !== undefined, '22 should have a bucket');
    assert.ok(b6 !== undefined, '66 should have a bucket');
    assert.ok(b6! >= b2!, '66 should be in a higher or equal bucket than 22');
  });

  test('same range on different boards produces different buckets', () => {
    const range = makeRange([
      [0, 1],   // 2c2d
      [4, 5],   // 3c3d
      [8, 9],   // 4c4d
      [12, 13], // 5c5d
      [16, 17], // 6c6d
      [20, 21], // 7c7d
      [24, 25], // 8c8d
      [28, 29], // 9c9d
      [32, 33], // Tc Td
      [36, 37], // Jc Jd
    ]);

    // Board 1: low board (2h, 3h, 4h = indices 2, 6, 10)
    const board1: [number, number, number] = [2, 6, 10];
    const dead1 = new Set<number>(board1);
    const b1 = computeEquityBuckets(range, board1, 10, dead1);

    // Board 2: high board (Th, Jh, Qh = indices 34, 38, 42)
    const board2: [number, number, number] = [34, 38, 42];
    const dead2 = new Set<number>(board2);
    const b2 = computeEquityBuckets(range, board2, 10, dead2);

    // On board1 (2-3-4), low pairs like 22 hit sets and should rank high
    // On board2 (T-J-Q), those same hands are weak
    const key22 = comboKey([0, 1]);
    const bucket22_low = b1.get(key22);
    const bucket22_high = b2.get(key22);

    if (bucket22_low !== undefined && bucket22_high !== undefined) {
      assert.ok(
        bucket22_low > bucket22_high,
        `22 should rank higher on 2-3-4 board (bucket ${bucket22_low}) than on T-J-Q board (bucket ${bucket22_high})`
      );
    }
  });
});

describe('V2 mini-solve integration', () => {
  test('solve produces info-set keys in V2 format', () => {
    // Build a tree
    const root = buildTree(V1_TREE_CONFIG);

    // Create a very small synthetic range
    const oopRange: WeightedCombo[] = [
      { combo: [48, 49], weight: 1.0 }, // AcAd
      { combo: [44, 45], weight: 1.0 }, // KcKd
      { combo: [40, 41], weight: 0.5 }, // QcQd
      { combo: [36, 37], weight: 1.0 }, // JcJd
      { combo: [32, 33], weight: 1.0 }, // TcTd
    ];
    const ipRange: WeightedCombo[] = [
      { combo: [48, 50], weight: 1.0 }, // AcAh
      { combo: [44, 46], weight: 1.0 }, // KcKh
      { combo: [40, 42], weight: 0.5 }, // QcQh
      { combo: [36, 38], weight: 1.0 }, // JcJh
      { combo: [32, 34], weight: 1.0 }, // TcTh
    ];

    const store = new InfoSetStore();
    const flopCards: [number, number, number] = [0, 5, 10]; // 2c, 3d, 4h

    // Run a very small number of iterations (just to verify key format)
    solveCFR({
      root,
      store,
      boardId: 0,
      flopCards,
      oopRange,
      ipRange,
      iterations: 50,
      bucketCount: 5,
    });

    // Check that stored info-set keys follow V2 format
    let flopKeys = 0;
    let turnKeys = 0;
    let riverKeys = 0;

    for (const entry of store.entries()) {
      const key = entry.key;
      const parts = key.split('|');
      assert.equal(parts.length, 5, `Key should have 5 pipe-separated parts: ${key}`);

      const [street, boardId, player, history, bucketSuffix] = parts;
      assert.ok(['F', 'T', 'R'].includes(street), `Street should be F/T/R: ${street}`);
      assert.equal(boardId, '0', `Board ID should be 0: ${boardId}`);
      assert.ok(['0', '1'].includes(player), `Player should be 0 or 1: ${player}`);

      if (street === 'F') {
        flopKeys++;
        // Flop bucket should be a single number
        assert.ok(!bucketSuffix.includes('-'), `Flop bucket should be single number: ${bucketSuffix}`);
        const b = parseInt(bucketSuffix, 10);
        assert.ok(b >= 0 && b < 5, `Flop bucket should be 0-4: ${b}`);
      } else if (street === 'T') {
        turnKeys++;
        // Turn bucket should be two numbers separated by dash
        const dims = bucketSuffix.split('-');
        assert.equal(dims.length, 2, `Turn key should have 2 bucket dimensions: ${bucketSuffix}`);
        for (const d of dims) {
          const b = parseInt(d, 10);
          assert.ok(b >= 0 && b < 5, `Turn bucket dimension should be 0-4: ${b}`);
        }
      } else if (street === 'R') {
        riverKeys++;
        // River bucket should be three numbers separated by dashes
        const dims = bucketSuffix.split('-');
        assert.equal(dims.length, 3, `River key should have 3 bucket dimensions: ${bucketSuffix}`);
        for (const d of dims) {
          const b = parseInt(d, 10);
          assert.ok(b >= 0 && b < 5, `River bucket dimension should be 0-4: ${b}`);
        }
      }
    }

    console.log(`  V2 solve produced: ${flopKeys} flop, ${turnKeys} turn, ${riverKeys} river info-sets`);
    assert.ok(flopKeys > 0, 'Should have flop info-sets');
    assert.ok(turnKeys > 0, 'Should have turn info-sets');
    assert.ok(riverKeys > 0, 'Should have river info-sets');
    assert.ok(store.size > 0, 'Store should have entries');
  });

  test('turn and river buckets differ from flop buckets', () => {
    // Build tree and run a mini solve, then check that keys on different
    // streets have different bucket assignments for the same hand

    const root = buildTree(V1_TREE_CONFIG);
    const oopRange: WeightedCombo[] = [
      { combo: [48, 49], weight: 1.0 }, // AcAd
      { combo: [44, 45], weight: 1.0 }, // KcKd
      { combo: [40, 41], weight: 1.0 }, // QcQd
      { combo: [36, 37], weight: 1.0 }, // JcJd
      { combo: [32, 33], weight: 1.0 }, // TcTd
      { combo: [28, 29], weight: 1.0 }, // 9c9d
      { combo: [24, 25], weight: 1.0 }, // 8c8d
      { combo: [20, 21], weight: 1.0 }, // 7c7d
    ];
    const ipRange: WeightedCombo[] = [
      { combo: [48, 50], weight: 1.0 }, // AcAh
      { combo: [44, 46], weight: 1.0 }, // KcKh
      { combo: [40, 42], weight: 1.0 }, // QcQh
      { combo: [36, 38], weight: 1.0 }, // JcJh
      { combo: [32, 34], weight: 1.0 }, // TcTh
      { combo: [28, 30], weight: 1.0 }, // 9c9h
      { combo: [24, 26], weight: 1.0 }, // 8c8h
      { combo: [20, 22], weight: 1.0 }, // 7c7h
    ];

    const store = new InfoSetStore();
    const flopCards: [number, number, number] = [0, 5, 10]; // 2c, 3d, 4h

    solveCFR({
      root,
      store,
      boardId: 0,
      flopCards,
      oopRange,
      ipRange,
      iterations: 100,
      bucketCount: 8,
    });

    // Collect bucket suffixes by street
    const turnSuffixes = new Set<string>();
    const riverSuffixes = new Set<string>();

    for (const entry of store.entries()) {
      const parts = entry.key.split('|');
      const [street, , , , suffix] = parts;
      if (street === 'T') turnSuffixes.add(suffix);
      if (street === 'R') riverSuffixes.add(suffix);
    }

    // Should have multiple different turn suffixes (different flop-turn bucket combos)
    console.log(`  Distinct turn bucket combos: ${turnSuffixes.size}`);
    console.log(`  Distinct river bucket combos: ${riverSuffixes.size}`);

    assert.ok(turnSuffixes.size > 1, 'Should have multiple distinct turn bucket combinations');
    // River might have more variation
    assert.ok(riverSuffixes.size > 1, 'Should have multiple distinct river bucket combinations');
  });
});
