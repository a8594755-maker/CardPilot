import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import {
  expandHandClassToCombos,
  loadGtoWizardRangeFile,
  parseGtoWizardRangeJson,
} from '../data-loaders/gto-wizard-json.js';
import { loadHUSRPRanges } from '../integration/preflop-ranges.js';

function writeFixture(data: unknown): string {
  const dir = mkdtempSync(join(tmpdir(), 'cfr-gto-loader-'));
  const filePath = join(dir, 'preflop.json');
  writeFileSync(filePath, JSON.stringify(data, null, 2));
  return filePath;
}

test('parseGtoWizardRangeJson validates and normalizes entries', () => {
  const entries = parseGtoWizardRangeJson([
    {
      format: 'cash_6max_100bb',
      spot: 'BTN_unopened_open2.5x',
      hand: 'aks',
      mix: { raise: 0.75, call: 0.1, fold: 0.15 },
      notes: ['TEST'],
    },
  ]);

  assert.equal(entries.length, 1);
  assert.equal(entries[0].hand, 'AKs');
  assert.equal(entries[0].mix.raise, 0.75);
});

test('parseGtoWizardRangeJson rejects malformed rows', () => {
  assert.throws(() => parseGtoWizardRangeJson({ bad: true }), /must be an array/);
  assert.throws(
    () => parseGtoWizardRangeJson([{ format: 'x', spot: 'y', hand: 'AK', mix: { raise: 1 } }]),
    /suited\/offsuit suffix/,
  );
  assert.throws(
    () => parseGtoWizardRangeJson([{ format: 'x', spot: 'y', hand: 'AA', mix: { raise: 2 } }]),
    /in \[0, 1\]/,
  );
});

test('expandHandClassToCombos returns expected combo counts', () => {
  const pair = expandHandClassToCombos('AA');
  const suited = expandHandClassToCombos('AKs');
  const offsuit = expandHandClassToCombos('AKo');

  assert.equal(pair.length, 6);
  assert.equal(suited.length, 4);
  assert.equal(offsuit.length, 12);

  const uniq = new Set(offsuit.map((combo) => `${combo[0]},${combo[1]}`));
  assert.equal(uniq.size, 12, 'Offsuit combos should be unique');
});

test('loadHUSRPRanges uses loader output with configurable frequencies', () => {
  const filePath = writeFixture([
    {
      format: 'cash_6max_100bb',
      spot: 'BTN_unopened_open2.5x',
      hand: 'AA',
      mix: { raise: 1, call: 0, fold: 0 },
    },
    {
      format: 'cash_6max_100bb',
      spot: 'BTN_unopened_open2.5x',
      hand: 'AKo',
      mix: { raise: 0.5, call: 0.2, fold: 0.3 },
    },
    {
      format: 'cash_6max_100bb',
      spot: 'BB_vs_BTN_facing_open2.5x',
      hand: '22',
      mix: { call: 1, raise: 0, fold: 0 },
    },
    {
      format: 'cash_6max_100bb',
      spot: 'BB_vs_BTN_facing_open2.5x',
      hand: 'A5s',
      mix: { call: 0.2, raise: 0, fold: 0.8 },
    },
  ]);

  const loaded = loadGtoWizardRangeFile(filePath);
  assert.equal(loaded.length, 4);

  const { ipRange, oopRange } = loadHUSRPRanges(filePath, { minFrequency: 0.25 });
  assert.equal(ipRange.handClasses.size, 2, 'AA + AKo should be included');
  assert.equal(oopRange.handClasses.size, 1, 'A5s should be filtered by minFrequency');

  // AA (6 combos) + AKo (12 combos)
  assert.equal(ipRange.combos.length, 18);
  // 22 (6 combos)
  assert.equal(oopRange.combos.length, 6);
});
