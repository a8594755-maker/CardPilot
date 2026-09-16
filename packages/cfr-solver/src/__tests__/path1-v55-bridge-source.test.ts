import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { gzipSync } from 'node:zlib';

import {
  actionSlotsForV55,
  correctRoundedProbabilityMass,
  FULL_SCOPE,
  MAX_ROUNDING_RESIDUAL,
  parseArgs,
  sourceActionDescriptors,
  SMOKE_SCOPE,
  strictBoardAudit,
} from '../scripts/path1-to-v55-bridge-source.js';

test('exact Path-1 actions bind deterministically to v5.5 actor slots', () => {
  assert.deepEqual(
    actionSlotsForV55('', ['check', 'bet_0', 'bet_1', 'bet_2', 'allin']),
    [1, 2, 4, 6, 8],
  );
  const deep = actionSlotsForV55('33c/x3', ['fold', 'call', 'raise_0', 'allin']);
  assert.equal(deep[0], 0);
  assert.equal(deep[1], 1);
  assert.ok(deep[2] >= 2 && deep[2] <= 7);
  assert.equal(deep[3], 8);
});

test('deep source descriptors retain exact Path-1 amounts before legal projection', () => {
  const actions = ['fold', 'call', 'raise_0', 'allin'];
  const descriptors = sourceActionDescriptors('x13c/2c/2', actions, {
    startingPot: 5,
    effectiveStack: 197.5,
    betSizes: { flop: [0.33, 0.67, 1.0], turn: [0.5, 0.75, 1.25], river: [0.5, 1.0, 1.5] },
    raiseCapPerStreet: 1,
  });
  assert.equal(descriptors[2].source_action_name, 'raise_0');
  assert.equal(descriptors[2].exact_additional_amount, 165.93);
  assert.ok(
    Math.abs((descriptors[2].exact_amount_over_source_pot ?? 0) - 1.250037667620913) < 1e-12,
  );
  assert.equal(descriptors[2].nominal_v55_slot, 7);
});

test('bounded three-decimal rounding residual is restored to the first max action', () => {
  const corrected = correctRoundedProbabilityMass([0.333, 0.333, 0.333]);
  assert.equal(corrected.rawSum, 0.9990000000000001);
  assert.ok(Math.abs(corrected.residual - 0.0009999999999998899) < 1e-15);
  assert.equal(corrected.correctedIndex, 0);
  assert.ok(Math.abs(corrected.probabilities.reduce((a, b) => a + b, 0) - 1) < 1e-12);
  assert.ok(corrected.probabilities[0] > corrected.probabilities[1]);
});

test('negative rounding residual is removed only from the first max action', () => {
  const corrected = correctRoundedProbabilityMass([0.501, 0.501]);
  assert.equal(corrected.correctedIndex, 0);
  assert.deepEqual(corrected.probabilities, [0.499, 0.501]);
});

test('residual outside frozen bound fails closed', () => {
  assert.throws(
    () => correctRoundedProbabilityMass([0.49, 0.49]),
    /rounding_residual_out_of_contract/,
  );
  assert.ok(MAX_ROUNDING_RESIDUAL > 0.005);
});

test('invalid probabilities and action counts fail closed', () => {
  assert.throws(() => correctRoundedProbabilityMass([1]), /action_count/);
  assert.throws(() => correctRoundedProbabilityMass([0.5, -0.5, 1]), /invalid_probability/);
  assert.throws(() => correctRoundedProbabilityMass([0.5, Number.NaN, 0.5]), /invalid_probability/);
});

test('CLI distinguishes bounded smoke scope from full-board scope', () => {
  const base = [
    '--board-gz',
    'C:\\tmp\\flop_002.jsonl.gz',
    '--board-meta',
    'C:\\tmp\\flop_002.meta.json',
    '--output-jsonl',
    'C:\\tmp\\bridge.jsonl',
    '--manifest',
    'C:\\tmp\\bridge.manifest.json',
  ];
  const full = parseArgs(base);
  assert.equal(full.smokeRows, 0);
  assert.equal(FULL_SCOPE, 'FULL_BOARD_CORPUS');
  const smoke = parseArgs([...base, '--smoke-prefix-rows', '1000']);
  assert.equal(smoke.smokeRows, 1000);
  assert.equal(SMOKE_SCOPE, 'SMOKE_PREFIX_ONLY_FORBIDDEN_TRAINING');
  assert.throws(() => parseArgs([...base, '--smoke-prefix-rows', '10001']), /ceiling/);
});

test('streaming source QA passes exact corrected thresholds and rejects illegal post-allin rows', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'path1-bridge-qa-'));
  try {
    const meta = {
      game: 'HU_NLHE_SRP',
      stack: '200bb',
      config: 'pipeline_srp_v3_200bb',
      boardId: 2,
      flopCards: [0, 1, 5] as [number, number, number],
      iterations: 80000,
      bucketCount: 50,
      infoSets: 100001,
    };
    const flopLine = `${JSON.stringify({ key: 'F|2|0||1', probs: [0.6, 0.4] })}\n`;
    const turnLine = `${JSON.stringify({ key: 'T|2|1|xx|1-2', probs: [0.6, 0.4] })}\n`;
    const riverLine = `${JSON.stringify({ key: 'R|2|0|xx/x1c|1-2-3', probs: [0.6, 0.4] })}\n`;
    const passPath = join(dir, 'pass.jsonl.gz');
    writeFileSync(
      passPath,
      gzipSync(
        flopLine.repeat(119) + turnLine.repeat(26363) + riverLine.repeat(meta.infoSets - 26482),
      ),
    );
    const passed = await strictBoardAudit(passPath, meta);
    assert.equal(passed.classification, 'CORRECTED_LEGAL_ALLIN_QA_PASS');
    assert.equal(passed.physicalRows, meta.infoSets);
    assert.equal(passed.illegalPostAllinRows, 0);
    assert.deepEqual(passed.streetPrefixCounts, { F: 119, T: 26363, R: 73519 });
    assert.equal(passed.streetPlayerActionCounts['F|0|2'], 119);
    assert.equal(passed.streetPlayerActionCounts['T|1|2'], 26363);
    assert.equal(passed.streetPlayerActionCounts['R|0|2'], 73519);

    const illegalLine = `${JSON.stringify({ key: 'R|2|0|xx/x1A|1-2-3', probs: [0.6, 0.2, 0.2] })}\n`;
    const failPath = join(dir, 'fail.jsonl.gz');
    writeFileSync(failPath, gzipSync(riverLine.repeat(meta.infoSets - 1) + illegalLine));
    await assert.rejects(() => strictBoardAudit(failPath, meta), /strict_qa_fail_closed/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
