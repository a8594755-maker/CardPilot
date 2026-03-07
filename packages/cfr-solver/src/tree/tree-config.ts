// Betting tree configuration for HU postflop solver
// Supports SRP (single raised pot) and 3-bet pot configs at various stack depths.

import type { TreeConfig, BetSizeConfig } from '../types.js';

// V1: HU SRP at 50bb (2 bet sizes per street)
// BTN opens to 2.5bb, BB calls → pot = 5bb, effective stack = 47.5bb
export const V1_BET_SIZES: BetSizeConfig = {
  flop:  [0.33, 0.75],
  turn:  [0.50, 1.00],
  river: [0.75, 1.50],
};

export const V1_TREE_CONFIG: TreeConfig = {
  startingPot: 5,
  effectiveStack: 47.5,
  betSizes: V1_BET_SIZES,
  raiseCapPerStreet: 1,
};

// Standard: 5 bet sizes per street (33%, 50%, 75%, 100%, 150% pot)
export const STANDARD_BET_SIZES: BetSizeConfig = {
  flop:  [0.33, 0.50, 0.75, 1.00, 1.50],
  turn:  [0.33, 0.50, 0.75, 1.00, 1.50],
  river: [0.33, 0.50, 0.75, 1.00, 1.50],
};

// Standard 50bb: 5 sizes, 50bb stack
export const STANDARD_50BB_CONFIG: TreeConfig = {
  startingPot: 5,
  effectiveStack: 47.5,
  betSizes: STANDARD_BET_SIZES,
  raiseCapPerStreet: 1,
};

// Standard 100bb: 5 sizes, 100bb stack
export const STANDARD_100BB_CONFIG: TreeConfig = {
  startingPot: 5,
  effectiveStack: 97.5,
  betSizes: STANDARD_BET_SIZES,
  raiseCapPerStreet: 1,
};

// Pipeline: HU SRP at 50bb — simplified (no raises, 1 bet size per street)
// Designed for bulk CFR solving across all 1,755 isomorphic flops
export const PIPELINE_SRP_BET_SIZES: BetSizeConfig = {
  flop:  [0.33],   // 33% pot
  turn:  [0.66],   // 66% pot
  river: [0.75],   // 75% pot (all-in always available via tree builder)
};

export const PIPELINE_SRP_CONFIG: TreeConfig = {
  startingPot: 5,          // BTN opens 2.5bb, BB calls → pot = 5bb
  effectiveStack: 47.5,    // 50bb - 2.5bb
  betSizes: PIPELINE_SRP_BET_SIZES,
  raiseCapPerStreet: 0,    // No raises — only check/bet/fold/call
};

// Pipeline: HU 3-bet pot at 50bb — simplified (no raises)
// BTN opens 2.5bb, BB 3-bets to 8.75bb (3.5x), BTN calls
// Pot = 8.75 × 2 = 17.5bb, effective stack = 50 - 8.75 = 41.25bb
// Verify: 17.5 + 41.25 × 2 = 100 ✓
export const PIPELINE_3BET_BET_SIZES: BetSizeConfig = {
  flop:  [0.33],   // 33% pot
  turn:  [0.66],   // 66% pot
  river: [0.75],   // 75% pot
};

export const PIPELINE_3BET_CONFIG: TreeConfig = {
  startingPot: 17.5,        // 8.75 × 2 = 17.5bb
  effectiveStack: 41.25,    // 50bb - 8.75bb
  betSizes: PIPELINE_3BET_BET_SIZES,
  raiseCapPerStreet: 0,
};

// ═══════════════════════════════════════════════════════════
// Pipeline V2: Raised configs (raiseCapPerStreet: 1, 2 bet sizes)
// For bulk CFR → Value Network training data generation
// ═══════════════════════════════════════════════════════════

const PIPELINE_V2_BET_SIZES: BetSizeConfig = {
  flop:  [0.33, 0.75],   // small probe + polarized
  turn:  [0.50, 1.00],   // mid + pot-size
  river: [0.75, 1.50],   // standard + overbet
};

// V2 SRP 50bb: 2 sizes, raises allowed
export const PIPELINE_SRP_V2_CONFIG: TreeConfig = {
  startingPot: 5,
  effectiveStack: 47.5,
  betSizes: PIPELINE_V2_BET_SIZES,
  raiseCapPerStreet: 1,
};

// V2 3-bet 50bb: 2 sizes, raises allowed
export const PIPELINE_3BET_V2_CONFIG: TreeConfig = {
  startingPot: 17.5,
  effectiveStack: 41.25,
  betSizes: PIPELINE_V2_BET_SIZES,
  raiseCapPerStreet: 1,
};

// V2 SRP 100bb: 2 sizes, raises allowed
export const PIPELINE_SRP_100BB_CONFIG: TreeConfig = {
  startingPot: 5,
  effectiveStack: 97.5,
  betSizes: PIPELINE_V2_BET_SIZES,
  raiseCapPerStreet: 1,
};

// V2 3-bet 100bb: 2 sizes, raises allowed
export const PIPELINE_3BET_100BB_CONFIG: TreeConfig = {
  startingPot: 17.5,
  effectiveStack: 91.25,
  betSizes: PIPELINE_V2_BET_SIZES,
  raiseCapPerStreet: 1,
};

// ═══════════════════════════════════════════════════════════
// Phase 2: HU Config Matrix — multiple positions, stacks, bet sizes
// ═══════════════════════════════════════════════════════════

// BTN vs BB SRP 100bb — 1 size per street, raises allowed (GTO+ style)
export const HU_BTN_BB_SRP_100BB_SIZES: BetSizeConfig = {
  flop:  [0.33],
  turn:  [0.66],
  river: [0.75],
};

export const HU_BTN_BB_SRP_100BB_CONFIG: TreeConfig = {
  startingPot: 5,          // BTN opens 2.5bb, BB calls → pot = 5bb
  effectiveStack: 97.5,    // 100bb - 2.5bb
  betSizes: HU_BTN_BB_SRP_100BB_SIZES,
  raiseCapPerStreet: 4,
  // Verify: 5 + 97.5 × 2 = 200 ✓
};

// BTN vs BB 3BP 100bb — 2 sizes
export const HU_BTN_BB_3BP_100BB_SIZES: BetSizeConfig = {
  flop:  [0.33, 0.75],
  turn:  [0.33, 0.75],
  river: [0.33, 0.75],
};

export const HU_BTN_BB_3BP_100BB_CONFIG: TreeConfig = {
  startingPot: 17.5,       // BTN opens 2.5bb, BB 3-bets to 8.75bb, BTN calls
  effectiveStack: 91.25,   // 100bb - 8.75bb
  betSizes: HU_BTN_BB_3BP_100BB_SIZES,
  raiseCapPerStreet: 0,
  // Verify: 17.5 + 91.25 × 2 = 200 ✓
};

// BTN vs BB SRP 50bb — 2 sizes (upgrade from pipeline_srp 1 size)
export const HU_BTN_BB_SRP_50BB_SIZES: BetSizeConfig = {
  flop:  [0.33, 0.75],
  turn:  [0.33, 0.75],
  river: [0.33, 0.75],
};

export const HU_BTN_BB_SRP_50BB_CONFIG: TreeConfig = {
  startingPot: 5,
  effectiveStack: 47.5,
  betSizes: HU_BTN_BB_SRP_50BB_SIZES,
  raiseCapPerStreet: 0,
  // Verify: 5 + 47.5 × 2 = 100 ✓
};

// BTN vs BB 3BP 50bb — 2 sizes (fixed version of pipeline_3bet)
export const HU_BTN_BB_3BP_50BB_SIZES: BetSizeConfig = {
  flop:  [0.33, 0.75],
  turn:  [0.33, 0.75],
  river: [0.33, 0.75],
};

export const HU_BTN_BB_3BP_50BB_CONFIG: TreeConfig = {
  startingPot: 17.5,
  effectiveStack: 41.25,
  betSizes: HU_BTN_BB_3BP_50BB_SIZES,
  raiseCapPerStreet: 0,
  // Verify: 17.5 + 41.25 × 2 = 100 ✓
};

// CO vs BB SRP 100bb — 2 sizes
export const HU_CO_BB_SRP_100BB_CONFIG: TreeConfig = {
  startingPot: 5,
  effectiveStack: 97.5,
  betSizes: HU_BTN_BB_3BP_100BB_SIZES, // reuse 2-size config
  raiseCapPerStreet: 0,
  // Verify: 5 + 97.5 × 2 = 200 ✓
};

// CO vs BB 3BP 100bb — 1 size
export const HU_CO_BB_3BP_100BB_SIZES: BetSizeConfig = {
  flop:  [0.50],
  turn:  [0.50],
  river: [0.50],
};

export const HU_CO_BB_3BP_100BB_CONFIG: TreeConfig = {
  startingPot: 17.5,       // same 3-bet sizing as BTN vs BB
  effectiveStack: 91.25,
  betSizes: HU_CO_BB_3BP_100BB_SIZES,
  raiseCapPerStreet: 0,
  // Verify: 17.5 + 91.25 × 2 = 200 ✓
};

// UTG vs BB SRP 100bb — 1 size
export const HU_UTG_BB_SRP_100BB_SIZES: BetSizeConfig = {
  flop:  [0.50],
  turn:  [0.50],
  river: [0.50],
};

export const HU_UTG_BB_SRP_100BB_CONFIG: TreeConfig = {
  startingPot: 5,
  effectiveStack: 97.5,
  betSizes: HU_UTG_BB_SRP_100BB_SIZES,
  raiseCapPerStreet: 0,
  // Verify: 5 + 97.5 × 2 = 200 ✓
};

// ═══════════════════════════════════════════════════════════
// Phase 5: Coaching configs (6 bet sizes, 4 stack depths)
// ═══════════════════════════════════════════════════════════

export const COACHING_BET_SIZES: BetSizeConfig = {
  flop:      [0.25, 0.33, 0.50, 0.75, 1.00, 1.50],
  turn:      [0.25, 0.33, 0.50, 0.75, 1.00, 1.50],
  river:     [0.25, 0.33, 0.50, 0.75, 1.00, 1.50],
  flopCbet:  [0.25, 0.33, 0.50, 0.75, 1.00],
  flopDonk:  [0.33, 0.50, 0.75],
  turnProbe: [0.33, 0.50, 0.75, 1.00],
  raiseMultipliers: {
    flop:  [2.5, 3.0],
    turn:  [2.5, 3.0],
    river: [2.5, 3.0],
  },
};

const COACHING_ADVANCED: TreeConfig['advancedConfig'] = {
  oop: { noDonkBet: false, allInThresholdEnabled: true, allInThresholdPct: 30, remainingBetAllIn: true, remainingBetPct: 25 },
  ip:  { noDonkBet: false, allInThresholdEnabled: true, allInThresholdPct: 30, remainingBetAllIn: true, remainingBetPct: 25 },
};

function coachingHU(pot: number, stack: number): TreeConfig {
  return {
    startingPot: pot,
    effectiveStack: stack,
    betSizes: COACHING_BET_SIZES,
    raiseCapPerStreet: 1,  // check-raise allowed, no re-raise (23K nodes vs 71K at cap=2)
    numPlayers: 2,
    advancedConfig: COACHING_ADVANCED,
  };
}

function coaching3W(pot: number, stack: number): TreeConfig {
  return {
    startingPot: pot,
    effectiveStack: stack,
    betSizes: COACHING_BET_SIZES,
    raiseCapPerStreet: 1,
    numPlayers: 3,
    advancedConfig: COACHING_ADVANCED,
  };
}

// ── HU SRP coaching (BTN opens 2.5bb, BB calls → pot=5) ──
export const COACH_HU_SRP_30BB  = coachingHU(5, 27.5);
export const COACH_HU_SRP_60BB  = coachingHU(5, 57.5);
export const COACH_HU_SRP_100BB = coachingHU(5, 97.5);
export const COACH_HU_SRP_200BB = coachingHU(5, 197.5);

// ── HU 3BP coaching (open 2.5bb, BB 3-bets 8.75bb, caller calls → pot=17.5) ──
export const COACH_HU_3BP_30BB  = coachingHU(17.5, 21.25);
export const COACH_HU_3BP_60BB  = coachingHU(17.5, 51.25);
export const COACH_HU_3BP_100BB = coachingHU(17.5, 91.25);
export const COACH_HU_3BP_200BB = coachingHU(17.5, 191.25);

// ── 3-way SRP coaching (BTN opens, SB+BB call → pot=7.5) ──
export const COACH_MW3_SRP_30BB  = coaching3W(7.5, 27.5);
export const COACH_MW3_SRP_60BB  = coaching3W(7.5, 57.5);
export const COACH_MW3_SRP_100BB = coaching3W(7.5, 97.5);
export const COACH_MW3_SRP_200BB = coaching3W(7.5, 197.5);

// ═══════════════════════════════════════════════════════════
// Multi-way (3-player) configs
// ═══════════════════════════════════════════════════════════

// 3-way: BTN opens, SB calls, BB calls → pot = 2.5 × 3 = 7.5bb
const MW3_SRP_BET_SIZES: BetSizeConfig = {
  flop:  [0.50],  // 50% pot
  turn:  [0.50],
  river: [0.50],
};

// 3-way BTN+SB+BB SRP 100bb
export const MW3_BTN_SB_BB_SRP_100BB_CONFIG: TreeConfig = {
  startingPot: 7.5,        // 2.5 × 3
  effectiveStack: 97.5,    // 100bb - 2.5bb
  betSizes: MW3_SRP_BET_SIZES,
  raiseCapPerStreet: 0,
  numPlayers: 3,
  // Verify: 7.5 + 97.5 × 3 = 300 = 100 × 3 ✓
};

// 3-way BTN+SB+BB SRP 50bb
export const MW3_BTN_SB_BB_SRP_50BB_CONFIG: TreeConfig = {
  startingPot: 7.5,
  effectiveStack: 47.5,    // 50bb - 2.5bb
  betSizes: MW3_SRP_BET_SIZES,
  raiseCapPerStreet: 0,
  numPlayers: 3,
  // Verify: 7.5 + 47.5 × 3 = 150 = 50 × 3 ✓
};

// 3-way CO+BTN+BB SRP 100bb
export const MW3_CO_BTN_BB_SRP_100BB_CONFIG: TreeConfig = {
  startingPot: 7.5,
  effectiveStack: 97.5,
  betSizes: MW3_SRP_BET_SIZES,
  raiseCapPerStreet: 0,
  numPlayers: 3,
};

// 3-way CO+BTN+BB SRP 50bb
export const MW3_CO_BTN_BB_SRP_50BB_CONFIG: TreeConfig = {
  startingPot: 7.5,
  effectiveStack: 47.5,
  betSizes: MW3_SRP_BET_SIZES,
  raiseCapPerStreet: 0,
  numPlayers: 3,
};

// ═══════════════════════════════════════════════════════════
// Config Registry
// ═══════════════════════════════════════════════════════════

export type TreeConfigName =
  // Legacy
  | 'v1_50bb'
  | 'standard_50bb'
  | 'standard_100bb'
  // Pipeline (1 size, bulk solve)
  | 'pipeline_srp'
  | 'pipeline_3bet'
  // Pipeline V2 (2 sizes, raises, bulk solve for VNet v2)
  | 'pipeline_srp_v2'
  | 'pipeline_3bet_v2'
  | 'pipeline_srp_100bb'
  | 'pipeline_3bet_100bb'
  // Phase 2: HU expanded configs
  | 'hu_btn_bb_srp_100bb'
  | 'hu_btn_bb_3bp_100bb'
  | 'hu_btn_bb_srp_50bb'
  | 'hu_btn_bb_3bp_50bb'
  | 'hu_co_bb_srp_100bb'
  | 'hu_co_bb_3bp_100bb'
  | 'hu_utg_bb_srp_100bb'
  // Phase 4: Multi-way (3-player)
  | 'mw3_btn_sb_bb_srp_100bb'
  | 'mw3_btn_sb_bb_srp_50bb'
  | 'mw3_co_btn_bb_srp_100bb'
  | 'mw3_co_btn_bb_srp_50bb'
  // Phase 5: Coaching (6 sizes, 4 depths)
  | 'coach_hu_srp_30bb'
  | 'coach_hu_srp_60bb'
  | 'coach_hu_srp_100bb'
  | 'coach_hu_srp_200bb'
  | 'coach_hu_3bp_30bb'
  | 'coach_hu_3bp_60bb'
  | 'coach_hu_3bp_100bb'
  | 'coach_hu_3bp_200bb'
  | 'coach_mw3_srp_30bb'
  | 'coach_mw3_srp_60bb'
  | 'coach_mw3_srp_100bb'
  | 'coach_mw3_srp_200bb';

/** Config metadata for registry lookups and reporting */
interface ConfigMeta {
  config: TreeConfig;
  label: string;
  outputDir: string;
  stackLabel: string;
  iterations: number;
  buckets: number;
}

const CONFIG_REGISTRY: Record<TreeConfigName, ConfigMeta> = {
  // Legacy
  v1_50bb: {
    config: V1_TREE_CONFIG,
    label: 'V1 50bb (2 sizes)',
    outputDir: 'v2_hu_srp_50bb',
    stackLabel: '50bb',
    iterations: 50000,
    buckets: 50,
  },
  standard_50bb: {
    config: STANDARD_50BB_CONFIG,
    label: 'Standard 50bb (5 sizes)',
    outputDir: 'standard_hu_srp_50bb',
    stackLabel: '50bb',
    iterations: 200000,
    buckets: 100,
  },
  standard_100bb: {
    config: STANDARD_100BB_CONFIG,
    label: 'Standard 100bb (5 sizes)',
    outputDir: 'standard_hu_srp_100bb',
    stackLabel: '100bb',
    iterations: 200000,
    buckets: 100,
  },
  // Pipeline (existing)
  pipeline_srp: {
    config: PIPELINE_SRP_CONFIG,
    label: 'Pipeline SRP 50bb (1 size)',
    outputDir: 'pipeline_hu_srp_50bb',
    stackLabel: '50bb',
    iterations: 200000,
    buckets: 100,
  },
  pipeline_3bet: {
    config: PIPELINE_3BET_CONFIG,
    label: 'Pipeline 3-bet 50bb (1 size)',
    outputDir: 'pipeline_hu_3bet_50bb',
    stackLabel: '50bb',
    iterations: 200000,
    buckets: 100,
  },
  // Pipeline V2 (raised configs for VNet training data)
  pipeline_srp_v2: {
    config: PIPELINE_SRP_V2_CONFIG,
    label: 'Pipeline V2 SRP 50bb (2 sizes, cap 1)',
    outputDir: 'pipeline_v2_hu_srp_50bb',
    stackLabel: '50bb',
    iterations: 200000,
    buckets: 100,
  },
  pipeline_3bet_v2: {
    config: PIPELINE_3BET_V2_CONFIG,
    label: 'Pipeline V2 3-bet 50bb (2 sizes, cap 1)',
    outputDir: 'pipeline_v2_hu_3bet_50bb',
    stackLabel: '50bb',
    iterations: 200000,
    buckets: 100,
  },
  pipeline_srp_100bb: {
    config: PIPELINE_SRP_100BB_CONFIG,
    label: 'Pipeline V2 SRP 100bb (2 sizes, cap 1)',
    outputDir: 'pipeline_v2_hu_srp_100bb',
    stackLabel: '100bb',
    iterations: 200000,
    buckets: 100,
  },
  pipeline_3bet_100bb: {
    config: PIPELINE_3BET_100BB_CONFIG,
    label: 'Pipeline V2 3-bet 100bb (2 sizes, cap 1)',
    outputDir: 'pipeline_v2_hu_3bet_100bb',
    stackLabel: '100bb',
    iterations: 200000,
    buckets: 100,
  },
  // Phase 2: HU expanded
  hu_btn_bb_srp_100bb: {
    config: HU_BTN_BB_SRP_100BB_CONFIG,
    label: 'HU BTN vs BB SRP 100bb',
    outputDir: 'hu_btn_bb_srp_100bb',
    stackLabel: '100bb',
    iterations: 200000,
    buckets: 100,
  },
  hu_btn_bb_3bp_100bb: {
    config: HU_BTN_BB_3BP_100BB_CONFIG,
    label: 'HU BTN vs BB 3BP 100bb (2 sizes)',
    outputDir: 'hu_btn_bb_3bp_100bb',
    stackLabel: '100bb',
    iterations: 200000,
    buckets: 100,
  },
  hu_btn_bb_srp_50bb: {
    config: HU_BTN_BB_SRP_50BB_CONFIG,
    label: 'HU BTN vs BB SRP 50bb (2 sizes)',
    outputDir: 'hu_btn_bb_srp_50bb',
    stackLabel: '50bb',
    iterations: 200000,
    buckets: 100,
  },
  hu_btn_bb_3bp_50bb: {
    config: HU_BTN_BB_3BP_50BB_CONFIG,
    label: 'HU BTN vs BB 3BP 50bb (2 sizes)',
    outputDir: 'hu_btn_bb_3bp_50bb',
    stackLabel: '50bb',
    iterations: 200000,
    buckets: 100,
  },
  hu_co_bb_srp_100bb: {
    config: HU_CO_BB_SRP_100BB_CONFIG,
    label: 'HU CO vs BB SRP 100bb (2 sizes)',
    outputDir: 'hu_co_bb_srp_100bb',
    stackLabel: '100bb',
    iterations: 200000,
    buckets: 100,
  },
  hu_co_bb_3bp_100bb: {
    config: HU_CO_BB_3BP_100BB_CONFIG,
    label: 'HU CO vs BB 3BP 100bb (1 size)',
    outputDir: 'hu_co_bb_3bp_100bb',
    stackLabel: '100bb',
    iterations: 200000,
    buckets: 100,
  },
  hu_utg_bb_srp_100bb: {
    config: HU_UTG_BB_SRP_100BB_CONFIG,
    label: 'HU UTG vs BB SRP 100bb (1 size)',
    outputDir: 'hu_utg_bb_srp_100bb',
    stackLabel: '100bb',
    iterations: 200000,
    buckets: 100,
  },
  // Phase 4: Multi-way (3-player)
  mw3_btn_sb_bb_srp_100bb: {
    config: MW3_BTN_SB_BB_SRP_100BB_CONFIG,
    label: '3-way BTN+SB+BB SRP 100bb (1 size)',
    outputDir: 'mw3_btn_sb_bb_srp_100bb',
    stackLabel: '100bb',
    iterations: 200000,
    buckets: 100,
  },
  mw3_btn_sb_bb_srp_50bb: {
    config: MW3_BTN_SB_BB_SRP_50BB_CONFIG,
    label: '3-way BTN+SB+BB SRP 50bb (1 size)',
    outputDir: 'mw3_btn_sb_bb_srp_50bb',
    stackLabel: '50bb',
    iterations: 200000,
    buckets: 100,
  },
  mw3_co_btn_bb_srp_100bb: {
    config: MW3_CO_BTN_BB_SRP_100BB_CONFIG,
    label: '3-way CO+BTN+BB SRP 100bb (1 size)',
    outputDir: 'mw3_co_btn_bb_srp_100bb',
    stackLabel: '100bb',
    iterations: 200000,
    buckets: 100,
  },
  mw3_co_btn_bb_srp_50bb: {
    config: MW3_CO_BTN_BB_SRP_50BB_CONFIG,
    label: '3-way CO+BTN+BB SRP 50bb (1 size)',
    outputDir: 'mw3_co_btn_bb_srp_50bb',
    stackLabel: '50bb',
    iterations: 200000,
    buckets: 100,
  },
  // Phase 5: Coaching (6 sizes, 4 depths)
  coach_hu_srp_30bb: {
    config: COACH_HU_SRP_30BB,
    label: 'Coaching HU SRP 30bb (6 sizes)',
    outputDir: 'coach_hu_srp_30bb',
    stackLabel: '30bb',
    iterations: 200000,
    buckets: 100,
  },
  coach_hu_srp_60bb: {
    config: COACH_HU_SRP_60BB,
    label: 'Coaching HU SRP 60bb (6 sizes)',
    outputDir: 'coach_hu_srp_60bb',
    stackLabel: '60bb',
    iterations: 200000,
    buckets: 100,
  },
  coach_hu_srp_100bb: {
    config: COACH_HU_SRP_100BB,
    label: 'Coaching HU SRP 100bb (6 sizes)',
    outputDir: 'coach_hu_srp_100bb',
    stackLabel: '100bb',
    iterations: 200000,
    buckets: 100,
  },
  coach_hu_srp_200bb: {
    config: COACH_HU_SRP_200BB,
    label: 'Coaching HU SRP 200bb (6 sizes)',
    outputDir: 'coach_hu_srp_200bb',
    stackLabel: '200bb',
    iterations: 200000,
    buckets: 100,
  },
  coach_hu_3bp_30bb: {
    config: COACH_HU_3BP_30BB,
    label: 'Coaching HU 3BP 30bb (6 sizes)',
    outputDir: 'coach_hu_3bp_30bb',
    stackLabel: '30bb',
    iterations: 200000,
    buckets: 100,
  },
  coach_hu_3bp_60bb: {
    config: COACH_HU_3BP_60BB,
    label: 'Coaching HU 3BP 60bb (6 sizes)',
    outputDir: 'coach_hu_3bp_60bb',
    stackLabel: '60bb',
    iterations: 200000,
    buckets: 100,
  },
  coach_hu_3bp_100bb: {
    config: COACH_HU_3BP_100BB,
    label: 'Coaching HU 3BP 100bb (6 sizes)',
    outputDir: 'coach_hu_3bp_100bb',
    stackLabel: '100bb',
    iterations: 200000,
    buckets: 100,
  },
  coach_hu_3bp_200bb: {
    config: COACH_HU_3BP_200BB,
    label: 'Coaching HU 3BP 200bb (6 sizes)',
    outputDir: 'coach_hu_3bp_200bb',
    stackLabel: '200bb',
    iterations: 200000,
    buckets: 100,
  },
  coach_mw3_srp_30bb: {
    config: COACH_MW3_SRP_30BB,
    label: 'Coaching 3-way SRP 30bb (6 sizes)',
    outputDir: 'coach_mw3_srp_30bb',
    stackLabel: '30bb',
    iterations: 200000,
    buckets: 100,
  },
  coach_mw3_srp_60bb: {
    config: COACH_MW3_SRP_60BB,
    label: 'Coaching 3-way SRP 60bb (6 sizes)',
    outputDir: 'coach_mw3_srp_60bb',
    stackLabel: '60bb',
    iterations: 200000,
    buckets: 100,
  },
  coach_mw3_srp_100bb: {
    config: COACH_MW3_SRP_100BB,
    label: 'Coaching 3-way SRP 100bb (6 sizes)',
    outputDir: 'coach_mw3_srp_100bb',
    stackLabel: '100bb',
    iterations: 200000,
    buckets: 100,
  },
  coach_mw3_srp_200bb: {
    config: COACH_MW3_SRP_200BB,
    label: 'Coaching 3-way SRP 200bb (6 sizes)',
    outputDir: 'coach_mw3_srp_200bb',
    stackLabel: '200bb',
    iterations: 200000,
    buckets: 100,
  },
};

/** Get all available pipeline config names (excludes legacy/standard) */
export function getPipelineConfigNames(): TreeConfigName[] {
  return Object.keys(CONFIG_REGISTRY).filter(
    k => !['v1_50bb', 'standard_50bb', 'standard_100bb'].includes(k)
  ) as TreeConfigName[];
}

/** Coaching configs in priority order (HU first, then multi-way). */
const COACHING_PRIORITY: TreeConfigName[] = [
  // Tier 1: HU SRP (most common postflop spot)
  'coach_hu_srp_100bb',
  'coach_hu_srp_60bb',
  'coach_hu_srp_200bb',
  'coach_hu_srp_30bb',
  // Tier 2: HU 3BP
  'coach_hu_3bp_100bb',
  'coach_hu_3bp_60bb',
  'coach_hu_3bp_200bb',
  'coach_hu_3bp_30bb',
  // Tier 3: 3-way SRP
  'coach_mw3_srp_100bb',
  'coach_mw3_srp_60bb',
  'coach_mw3_srp_200bb',
  'coach_mw3_srp_30bb',
];

/** Get coaching config names in priority order. */
export function getCoachingConfigNames(): TreeConfigName[] {
  return [...COACHING_PRIORITY];
}

/** HU-only pipeline configs in priority order (Tier 1 → Tier 2). Excludes multi-way. */
const HU_PIPELINE_PRIORITY: TreeConfigName[] = [
  // Tier 0: Pipeline V2 (raised, priority for VNet v2 training)
  'pipeline_srp_v2',
  'pipeline_3bet_v2',
  'pipeline_srp_100bb',
  'pipeline_3bet_100bb',
  // Tier 1: BTN vs BB (most common spots)
  'hu_btn_bb_srp_100bb',
  'hu_btn_bb_3bp_100bb',
  'hu_btn_bb_srp_50bb',
  'hu_btn_bb_3bp_50bb',
  'pipeline_srp',
  'pipeline_3bet',
  // Tier 2: Other positions
  'hu_co_bb_srp_100bb',
  'hu_co_bb_3bp_100bb',
  'hu_utg_bb_srp_100bb',
];

/** Get HU pipeline config names in priority order (for cluster runs). */
export function getHUPipelineConfigNames(): TreeConfigName[] {
  return [...HU_PIPELINE_PRIORITY];
}

export function getTreeConfig(name: TreeConfigName): TreeConfig {
  return CONFIG_REGISTRY[name].config;
}

export function getSolveDefaults(name: TreeConfigName): { iterations: number; buckets: number } {
  const meta = CONFIG_REGISTRY[name];
  return { iterations: meta.iterations, buckets: meta.buckets };
}

export function getConfigLabel(name: TreeConfigName): string {
  return CONFIG_REGISTRY[name].label;
}

export function getConfigOutputDir(name: TreeConfigName): string {
  return CONFIG_REGISTRY[name].outputDir;
}

export function getStackLabel(name: TreeConfigName): string {
  return CONFIG_REGISTRY[name].stackLabel;
}

// ═══════════════════════════════════════════════════════════
// Multi-way range config helpers
// ═══════════════════════════════════════════════════════════

import type { MultiWayRangeConfig } from '../integration/preflop-ranges.js';

/**
 * Get range loading configs for multi-way scenarios.
 * Returns one config per player (index 0 = first to act postflop = BB).
 *
 * Player order (postflop):
 * - BTN+SB+BB: [BB(0), SB(1), BTN(2)]
 * - CO+BTN+BB: [BB(0), BTN(1), CO(2)]
 */
export function getMultiWayRangeConfigs(configName: TreeConfigName): MultiWayRangeConfig[] {
  switch (configName) {
    case 'mw3_btn_sb_bb_srp_100bb':
    case 'mw3_btn_sb_bb_srp_50bb':
      return [
        {
          position: 'BB',
          spot: 'BB_vs_BTN_facing_open2.5x',
          action: 'call',
          multiWayBoost: true,
        },
        {
          position: 'SB',
          spot: 'estimated:SB_vs_BTN_cold_call',
          action: 'call',
        },
        {
          position: 'BTN',
          spot: 'BTN_unopened_open2.5x',
          action: 'raise',
        },
      ];

    case 'mw3_co_btn_bb_srp_100bb':
    case 'mw3_co_btn_bb_srp_50bb':
      return [
        {
          position: 'BB',
          spot: 'BB_vs_CO_facing_open2.5x',
          action: 'call',
          multiWayBoost: true,
        },
        {
          position: 'BTN',
          spot: 'estimated:BTN_vs_CO_cold_call',
          action: 'call',
        },
        {
          position: 'CO',
          spot: 'CO_unopened_open2.5x',
          action: 'raise',
        },
      ];

    // Coaching 3-way SRP (BTN opens, SB+BB call — all depths)
    case 'coach_mw3_srp_30bb':
    case 'coach_mw3_srp_60bb':
    case 'coach_mw3_srp_100bb':
    case 'coach_mw3_srp_200bb':
      return [
        {
          position: 'BB',
          spot: 'BB_vs_BTN_facing_open2.5x',
          action: 'call',
          multiWayBoost: true,
        },
        {
          position: 'SB',
          spot: 'estimated:SB_vs_BTN_cold_call',
          action: 'call',
        },
        {
          position: 'BTN',
          spot: 'BTN_unopened_open2.5x',
          action: 'raise',
        },
      ];

    default:
      throw new Error(`No multi-way range config for: ${configName}`);
  }
}

/**
 * Calculate actual bet amount from pot fraction, capped at effective stack.
 * Returns the bet amount (what the player puts into the pot).
 */
export function calcBetAmount(
  potSize: number,
  fraction: number,
  playerStack: number
): number {
  const bet = Math.round(potSize * fraction * 100) / 100;
  return Math.min(bet, playerStack);
}

/**
 * Calculate raise amount given a facing bet.
 * Returns ADDITIONAL chips the player puts in from their stack.
 *
 * Formula:
 *   callAmount   = facingBet - invested
 *   potAfterCall = potSize + callAmount
 *   raiseOverBet = potAfterCall * fraction
 *   additional   = callAmount + raiseOverBet
 *
 * The total bet level (for opponent's facingBet) = invested + returned value.
 */
export function calcRaiseAmount(
  potSize: number,
  facingBet: number,
  fraction: number,
  playerStack: number,
  invested: number = 0,
): number {
  const callAmount = facingBet - invested;
  const potAfterCall = potSize + callAmount;
  const raiseOverBet = Math.round(potAfterCall * fraction * 100) / 100;
  const additional = callAmount + raiseOverBet;
  return Math.min(additional, playerStack);
}
