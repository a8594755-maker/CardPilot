import { test } from 'node:test';
import * as assert from 'node:assert/strict';
import { enumerateIsomorphicFlops } from '../abstraction/suit-isomorphism.js';
import { selectRepresentativeFlops, printFlopStats } from '../abstraction/flop-selector.js';
import { indexToCard } from '../abstraction/card-index.js';

test('enumerate isomorphic flops', () => {
  const flops = enumerateIsomorphicFlops();
  console.log(`Total isomorphic flops: ${flops.length}`);
  // Should be ~1,755 (known value)
  assert.ok(
    flops.length > 1700 && flops.length < 2000,
    `Expected ~1,755-1,911 isomorphic flops, got ${flops.length}`,
  );
});

test('select 200 representative flops', () => {
  const flops = selectRepresentativeFlops(200);
  assert.equal(flops.length, 200);
  printFlopStats(flops);

  // Print first 10
  console.log('\nFirst 10 flops:');
  for (const f of flops.slice(0, 10)) {
    const cards = f.cards.map(indexToCard).join(' ');
    console.log(`  ${cards} (${f.textureKey})`);
  }
});

test('select 20 representative flops', () => {
  const flops = selectRepresentativeFlops(20);
  assert.equal(flops.length, 20);
  printFlopStats(flops);

  console.log('\nAll 20 flops:');
  for (const f of flops) {
    const cards = f.cards.map(indexToCard).join(' ');
    console.log(`  ${cards} | ${f.textureKey}`);
  }
});
