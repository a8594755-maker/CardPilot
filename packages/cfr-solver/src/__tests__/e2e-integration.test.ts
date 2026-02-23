import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { BinaryStrategyReader } from '../storage/binary-format.js';
import { buildTree, countNodes } from '../tree/tree-builder.js';
import { V1_TREE_CONFIG } from '../tree/tree-config.js';

const DATA_DIR = join(process.cwd(), 'data', 'cfr', 'v1_hu_srp_50bb');
const BIN_PATH = join(process.cwd(), 'data', 'cfr', 'v1_hu_srp_50bb.bin.gz');
const hasData = existsSync(DATA_DIR) && existsSync(BIN_PATH);

test('V1 tree structure is correct', () => {
  const root = buildTree(V1_TREE_CONFIG);
  const counts = countNodes(root);
  assert.equal(counts.action, 1008, 'Expected 1008 action nodes');
  assert.ok(counts.terminal > 1000, 'Expected many terminal nodes');
  assert.equal(root.player, 0, 'OOP acts first');
  assert.equal(root.street, 'FLOP');
  assert.deepEqual(root.actions, ['check', 'bet_small', 'bet_big', 'allin']);
});

test('Binary reader loads and queries correctly', { skip: !hasData && 'No solved data' }, () => {
  const reader = new BinaryStrategyReader(BIN_PATH);
  assert.equal(reader.numFlops, 200);
  assert.equal(reader.iterations, 50000);
  assert.equal(reader.bucketCount, 50);
  assert.ok(reader.entryCount > 9_000_000, `Expected >9M entries, got ${reader.entryCount}`);

  // Lookup a known key pattern
  const probs = reader.lookup('F|0|0||25');
  assert.ok(probs, 'Should find flop root for board 0, player 0, bucket 25');
  assert.ok(probs!.length >= 3, 'Should have at least 3 actions at flop root');
  const sum = probs!.reduce((a, b) => a + b, 0);
  assert.ok(Math.abs(sum - 1) < 0.05, `Probs should sum to ~1, got ${sum}`);
});

test('JSONL and binary agree on strategies', { skip: !hasData && 'No solved data' }, () => {
  const reader = new BinaryStrategyReader(BIN_PATH);

  // Load first JSONL file
  const jsonlContent = readFileSync(join(DATA_DIR, 'flop_000.jsonl'), 'utf-8');
  const lines = jsonlContent.split('\n').filter(l => l.trim());
  assert.ok(lines.length > 1000, 'Should have many info sets');

  // Check 10 random entries match
  let matches = 0;
  const step = Math.floor(lines.length / 10);
  for (let i = 0; i < lines.length; i += step) {
    const entry = JSON.parse(lines[i]) as { key: string; probs: number[] };
    const binProbs = reader.lookup(entry.key);
    if (!binProbs) continue;
    // Binary uses uint8 quantization so tolerance is ~1/255
    const maxDiff = Math.max(...entry.probs.map((p, j) => Math.abs(p - binProbs[j])));
    assert.ok(maxDiff < 0.01, `Key ${entry.key}: max diff ${maxDiff} should be <0.01`);
    matches++;
  }
  assert.ok(matches >= 5, `Should match at least 5 entries, got ${matches}`);
});

test('All 200 flops have metadata', { skip: !hasData && 'No solved data' }, () => {
  for (let i = 0; i < 200; i++) {
    const metaFile = join(DATA_DIR, `flop_${String(i).padStart(3, '0')}.meta.json`);
    assert.ok(existsSync(metaFile), `Missing meta for flop ${i}`);
    const meta = JSON.parse(readFileSync(metaFile, 'utf-8'));
    assert.equal(meta.boardId, i);
    assert.equal(meta.bucketCount, 50);
    assert.equal(meta.iterations, 50000);
    assert.ok(Array.isArray(meta.flopCards) && meta.flopCards.length === 3);
  }
});

test('Strategy coverage: all streets and players represented', { skip: !hasData && 'No solved data' }, () => {
  const reader = new BinaryStrategyReader(BIN_PATH);

  // Check strategies exist for typical nodes at each street/player.
  // Player 0 (OOP) acts first on each street; Player 1 (IP) acts after OOP.
  const testCases = [
    { label: 'Flop OOP root',    key: (bid: number, b: number) => `F|${bid}|0||${b}` },
    { label: 'Flop IP after check', key: (bid: number, b: number) => `F|${bid}|1|x|${b}` },
    { label: 'Turn OOP root',    key: (bid: number, b: number) => `T|${bid}|0|xx/|${b}` },
    { label: 'Turn IP after check', key: (bid: number, b: number) => `T|${bid}|1|xx/x|${b}` },
    { label: 'River OOP root',   key: (bid: number, b: number) => `R|${bid}|0|xx/xx/|${b}` },
    { label: 'River IP after check', key: (bid: number, b: number) => `R|${bid}|1|xx/xx/x|${b}` },
  ];

  for (const tc of testCases) {
    let found = false;
    for (let bid = 0; bid < 5 && !found; bid++) {
      for (let b = 0; b < 50 && !found; b++) {
        if (reader.lookup(tc.key(bid, b))) found = true;
      }
    }
    assert.ok(found, `Should have strategies for: ${tc.label}`);
  }
});
