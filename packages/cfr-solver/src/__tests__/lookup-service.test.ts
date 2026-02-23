import { test } from 'node:test';
import * as assert from 'node:assert/strict';
import { existsSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { LookupService } from '../integration/lookup-service.js';

// Create a small test fixture instead of loading the full 513MB dataset
const TMP_DIR = join(tmpdir(), 'cfr-lookup-test-' + Date.now());

function setupFixture(): void {
  mkdirSync(TMP_DIR, { recursive: true });

  // Create a small JSONL file with known strategies
  const entries = [
    { key: 'F|0|0||0', probs: [0.6, 0.3, 0.1] },
    { key: 'F|0|0||25', probs: [0.3, 0.5, 0.2] },
    { key: 'F|0|0||49', probs: [0.1, 0.2, 0.7] },
    { key: 'F|0|1|x|10', probs: [0.4, 0.35, 0.25] },
    { key: 'T|0|0|xx/|20', probs: [0.5, 0.3, 0.2] },
    { key: 'R|0|0|xx/xx/|30', probs: [0.2, 0.3, 0.5] },
  ];
  writeFileSync(
    join(TMP_DIR, 'flop_000.jsonl'),
    entries.map(e => JSON.stringify(e)).join('\n') + '\n',
  );
  // As=51, 8d=25, 3c=4 in the card-index encoding (rank*4+suit)
  writeFileSync(
    join(TMP_DIR, 'flop_000.meta.json'),
    JSON.stringify({
      boardId: 0,
      flopCards: [51, 25, 4], // As 8d 3c
      iterations: 50000,
      bucketCount: 50,
      infoSets: entries.length,
    }),
  );
}

setupFixture();

test('LookupService loads solved strategies', () => {
  const service = new LookupService();
  service.load(TMP_DIR);

  assert.ok(service.isLoaded);
  assert.equal(service.size, 6, 'Should have loaded 6 strategies');
});

test('LookupService direct key lookup', () => {
  const service = new LookupService();
  service.load(TMP_DIR);

  const probs = service.getByKey('F|0|0||0');
  assert.ok(probs, 'Should find key');
  assert.deepEqual(probs, [0.6, 0.3, 0.1]);

  const probs2 = service.getByKey('F|0|0||25');
  assert.ok(probs2);
  assert.deepEqual(probs2, [0.3, 0.5, 0.2]);

  const missing = service.getByKey('F|99|0||0');
  assert.equal(missing, null, 'Non-existent key should return null');
});

test('LookupService query with hand and board', () => {
  const service = new LookupService();
  service.load(TMP_DIR);

  // Query for a hand on the exact solved flop As 8d 3c
  const result = service.query(
    ['As', '8d'],       // hand
    ['As', '8d', '3c'], // board matches flopCards [48, 29, 8]
    0,                   // OOP
    '',                  // root
  );

  assert.ok(result.strategy, 'Should find a strategy');
  assert.equal(result.source, 'exact', 'Should be exact match');
});

test('LookupService nearest flop fallback', () => {
  const service = new LookupService();
  service.load(TMP_DIR);

  // Query for a different board — should fallback to nearest
  const result = service.query(
    ['Ah', 'Kd'],
    ['Qs', '7d', '2c'], // different flop
    0,
    '',
  );

  // With only 1 solved flop, it should find it via nearest_flop
  assert.ok(
    result.source === 'exact' || result.source === 'nearest_flop',
    `Expected exact or nearest_flop, got ${result.source}`,
  );
});
