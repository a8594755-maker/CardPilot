import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  getMultiWayRangeConfigs,
  getCoachingConfigNames,
  getTreeConfig,
  type TreeConfigName,
} from '../tree/tree-config.js';

describe('Coaching Range Configs', () => {
  const coaching = getCoachingConfigNames();

  it('all 12 coaching configs should exist', () => {
    assert.equal(coaching.length, 12);
  });

  it('HU coaching configs should have numPlayers=2', () => {
    const huConfigs = coaching.filter((c) => c.includes('_hu_'));
    assert.equal(huConfigs.length, 8);
    for (const c of huConfigs) {
      const cfg = getTreeConfig(c);
      assert.equal(cfg.numPlayers ?? 2, 2, `${c} should be 2-player`);
    }
  });

  it('MW3 coaching configs should have numPlayers=3 and valid range configs', () => {
    const mw3Configs = coaching.filter((c) => c.includes('_mw3_'));
    assert.equal(mw3Configs.length, 4);
    for (const c of mw3Configs) {
      const cfg = getTreeConfig(c);
      assert.equal(cfg.numPlayers, 3, `${c} should be 3-player`);

      const ranges = getMultiWayRangeConfigs(c);
      assert.equal(ranges.length, 3, `${c} should have 3 range configs`);
      assert.deepEqual(
        ranges.map((r) => r.position),
        ['BB', 'SB', 'BTN'],
        `${c} positions should be BB, SB, BTN`,
      );
    }
  });

  it('all coaching configs should use COACHING_BET_SIZES (6 flop sizes)', () => {
    for (const c of coaching) {
      const cfg = getTreeConfig(c);
      assert.equal(cfg.betSizes.flop.length, 6, `${c} should have 6 flop sizes`);
    }
  });
});
