import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  loadHUSRPRanges,
  loadMultiWayRanges,
  getWeightedRangeCombos,
} from '../integration/preflop-ranges.js';
import { getMultiWayRangeConfigs, type TreeConfigName } from '../tree/tree-config.js';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const CHARTS_PATH = resolve(__dirname, '../../../../data/preflop_charts.json');

describe('Coaching Range Loading (live data)', () => {
  it('should load HU SRP ranges for coach_hu_srp_100bb', () => {
    const ranges = loadHUSRPRanges(CHARTS_PATH, {
      ipSpot: 'BTN_unopened_open2.5x',
      ipAction: 'raise',
      oopSpot: 'BB_vs_BTN_facing_open2.5x',
      oopAction: 'call',
    });

    assert.ok(ranges.ipRange.combos.length > 0, 'IP range should have combos');
    assert.ok(ranges.oopRange.combos.length > 0, 'OOP range should have combos');
    assert.ok(
      ranges.ipRange.handClasses.size > 30,
      `IP should have >30 hand classes, got ${ranges.ipRange.handClasses.size}`,
    );
    assert.ok(
      ranges.oopRange.handClasses.size > 20,
      `OOP should have >20 hand classes, got ${ranges.oopRange.handClasses.size}`,
    );

    // Remove dead cards and check
    const deadCards = new Set([0, 1, 2]); // some flop
    const ipCombos = getWeightedRangeCombos(ranges.ipRange, deadCards);
    const oopCombos = getWeightedRangeCombos(ranges.oopRange, deadCards);
    assert.ok(ipCombos.length > 100, `IP combos after dead cards: ${ipCombos.length}`);
    assert.ok(oopCombos.length > 50, `OOP combos after dead cards: ${oopCombos.length}`);

    console.log(`  IP: ${ranges.ipRange.handClasses.size} hand classes, ${ipCombos.length} combos`);
    console.log(
      `  OOP: ${ranges.oopRange.handClasses.size} hand classes, ${oopCombos.length} combos`,
    );
  });

  it('should load HU 3BP ranges for coach_hu_3bp_100bb', () => {
    const ranges = loadHUSRPRanges(CHARTS_PATH, {
      oopSpot: 'BB_vs_BTN_facing_open2.5x',
      oopAction: 'raise', // BB 3-bet range
      ipSpot: 'BTN_unopened_open2.5x',
      ipAction: 'raise',
      minFrequency: 0.4,
    });

    assert.ok(ranges.ipRange.combos.length > 0, 'IP calling range should have combos');
    assert.ok(ranges.oopRange.combos.length > 0, 'OOP 3-bet range should have combos');

    console.log(`  IP (filtered): ${ranges.ipRange.handClasses.size} hand classes`);
    console.log(`  OOP (3-bet): ${ranges.oopRange.handClasses.size} hand classes`);
  });

  it('should load MW3 SRP ranges for coach_mw3_srp_100bb', () => {
    const mwConfigs = getMultiWayRangeConfigs('coach_mw3_srp_100bb' as TreeConfigName);
    const ranges = loadMultiWayRanges(CHARTS_PATH, mwConfigs, 3);

    assert.equal(ranges.length, 3, 'Should have 3 player ranges');
    for (let i = 0; i < 3; i++) {
      assert.ok(ranges[i].combos.length > 0, `Player ${i} should have combos`);
      console.log(
        `  Player ${i} (${mwConfigs[i].position}): ${ranges[i].handClasses.size} hand classes`,
      );
    }
  });
});
