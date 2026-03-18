#!/usr/bin/env tsx
/**
 * Preflop Training Data → V3 Feature Format Converter
 *
 * Reads preflop CFR training records (hand-class level) and outputs
 * V3-compatible training samples with 54-dim V2 feature vectors.
 *
 * Each hand class (e.g. "AKs") is expanded to all concrete combos
 * (AhKh, AsKs, AdKd, AcKc) so the model sees diverse hole-card features.
 *
 * Usage:
 *   npx tsx packages/cfr-solver/src/scripts/preflop-to-training-data.ts \
 *     --preflop-dir data/preflop \
 *     --output data/training/preflop \
 *     --configs cash_6max_100bb,cash_6max_50bb,cash_6max_100bb_ante
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import {
  getPreflopConfig,
  compute3BetSize,
  compute4BetSize,
  computeInitialPot,
  isIPPostflop,
} from '../preflop/preflop-config.js';
import { POSITION_6MAX, NUM_PLAYERS } from '../preflop/preflop-types.js';
import type { PreflopSolveConfig } from '../preflop/preflop-types.js';

// ══════════════════════════════════════════════
//   TYPES
// ══════════════════════════════════════════════

interface TrainingRecord {
  format: string;
  spot: string;
  position: string;
  scenario: string;
  handClass: string;
  handClassIndex: number;
  actions: string[];
  frequencies: number[];
  pot: number;
  history: string;
}

interface TrainingSample {
  f: number[];
  l: [number, number, number];
  h: string;
  s: string;
}

interface ReplayState {
  pot: number;
  stacks: number[];
  investments: number[];
  activePlayers: boolean[];
  raiseLevel: number;
  lastRaiseTotal: number;
  lastRaiserSeat: number;
  raisesOnStreet: number;
  heroHasRaised: boolean;
}

// ══════════════════════════════════════════════
//   CONSTANTS
// ══════════════════════════════════════════════

const SUITS = ['h', 's', 'd', 'c'];

const RANK_VALUES: Record<string, number> = {
  '2': 2,
  '3': 3,
  '4': 4,
  '5': 5,
  '6': 6,
  '7': 7,
  '8': 8,
  '9': 9,
  T: 10,
  J: 11,
  Q: 12,
  K: 13,
  A: 14,
};

const POSITION_INDEX: Record<string, number> = {
  UTG: 0,
  MP: 1,
  HJ: 2,
  CO: 3,
  BTN: 4,
  SB: 5,
  BB: 6,
};

const POS_CHAR_TO_SEAT: Record<string, number> = {
  U: 0,
  H: 1,
  C: 2,
  B: 3,
  S: 4,
  b: 5,
};

// ══════════════════════════════════════════════
//   HAND CLASS → COMBOS
// ══════════════════════════════════════════════

/**
 * Expand a hand class (e.g. "AKs", "QQ", "T9o") to all concrete
 * 2-card combos: pairs→6, suited→4, offsuit→12.
 */
function expandHandClass(handClass: string): [string, string][] {
  const combos: [string, string][] = [];

  if (handClass.length === 2) {
    // Pair: 6 combos
    const r = handClass[0];
    for (let i = 0; i < 4; i++) {
      for (let j = i + 1; j < 4; j++) {
        combos.push([`${r}${SUITS[i]}`, `${r}${SUITS[j]}`]);
      }
    }
  } else if (handClass[2] === 's') {
    // Suited: 4 combos
    const r1 = handClass[0],
      r2 = handClass[1];
    for (const suit of SUITS) {
      combos.push([`${r1}${suit}`, `${r2}${suit}`]);
    }
  } else {
    // Offsuit: 12 combos
    const r1 = handClass[0],
      r2 = handClass[1];
    for (let i = 0; i < 4; i++) {
      for (let j = 0; j < 4; j++) {
        if (i !== j) combos.push([`${r1}${SUITS[i]}`, `${r2}${SUITS[j]}`]);
      }
    }
  }

  return combos;
}

// ══════════════════════════════════════════════
//   HISTORY REPLAY
// ══════════════════════════════════════════════

/**
 * Replay the preflop history string to reconstruct the game state
 * at the hero's decision point. Follows the same logic as
 * preflop-tree.ts applyAction().
 */
function replayHistory(history: string, heroSeat: number, config: PreflopSolveConfig): ReplayState {
  const initialPot = computeInitialPot(config);
  const stacks: number[] = [];
  const investments: number[] = [];

  for (let i = 0; i < NUM_PLAYERS; i++) {
    let invested = config.ante;
    if (i === 4) invested += config.sbSize; // SB
    if (i === 5) invested += config.bbSize; // BB
    stacks.push(config.stackSize - invested);
    investments.push(invested);
  }

  const state: ReplayState = {
    pot: initialPot,
    stacks,
    investments,
    activePlayers: Array(NUM_PLAYERS).fill(true),
    raiseLevel: 0,
    lastRaiseTotal: config.bbSize,
    lastRaiserSeat: -1,
    raisesOnStreet: 0,
    heroHasRaised: false,
  };

  if (!history) return state;

  const tokens = history.split('-');
  let prevRaiserSeat = -1;

  for (const token of tokens) {
    if (token.length < 2) continue;
    const seat = POS_CHAR_TO_SEAT[token[0]];
    const actionChar = token[1];
    if (seat === undefined) continue;

    switch (actionChar) {
      case 'f': // fold
        state.activePlayers[seat] = false;
        break;

      case 'x': // check
        break;

      case 'c': {
        // call
        const toCall = Math.max(0, state.lastRaiseTotal - state.investments[seat]);
        const actual = Math.min(toCall, state.stacks[seat]);
        state.stacks[seat] -= actual;
        state.investments[seat] += actual;
        state.pot += actual;
        break;
      }

      case 'o': {
        // open
        const cost = config.openSize - state.investments[seat];
        const actual = Math.min(cost, state.stacks[seat]);
        state.stacks[seat] -= actual;
        state.investments[seat] += actual;
        state.pot += actual;
        prevRaiserSeat = state.lastRaiserSeat;
        state.lastRaiserSeat = seat;
        state.lastRaiseTotal = config.openSize;
        state.raiseLevel = 1;
        state.raisesOnStreet++;
        if (seat === heroSeat) state.heroHasRaised = true;
        break;
      }

      case '3': {
        // 3bet
        const isIP = state.lastRaiserSeat >= 0 ? isIPPostflop(seat, state.lastRaiserSeat) : false;
        const size = compute3BetSize(config, isIP);
        const cost = size - state.investments[seat];
        const actual = Math.min(cost, state.stacks[seat]);
        state.stacks[seat] -= actual;
        state.investments[seat] += actual;
        state.pot += actual;
        prevRaiserSeat = state.lastRaiserSeat;
        state.lastRaiserSeat = seat;
        state.lastRaiseTotal = size;
        state.raiseLevel = 2;
        state.raisesOnStreet++;
        if (seat === heroSeat) state.heroHasRaised = true;
        // After 3bet: auto-fold uninvolved players
        for (let i = 0; i < NUM_PLAYERS; i++) {
          if (!state.activePlayers[i]) continue;
          if (i === seat || i === prevRaiserSeat) continue;
          state.activePlayers[i] = false;
        }
        break;
      }

      case '4': {
        // 4bet
        const size = compute4BetSize(config, state.lastRaiseTotal);
        const cost = size - state.investments[seat];
        const actual = Math.min(cost, state.stacks[seat]);
        state.stacks[seat] -= actual;
        state.investments[seat] += actual;
        state.pot += actual;
        prevRaiserSeat = state.lastRaiserSeat;
        state.lastRaiserSeat = seat;
        state.lastRaiseTotal = size;
        state.raiseLevel = 3;
        state.raisesOnStreet++;
        if (seat === heroSeat) state.heroHasRaised = true;
        // After 4bet: auto-fold uninvolved
        for (let i = 0; i < NUM_PLAYERS; i++) {
          if (!state.activePlayers[i]) continue;
          if (i === seat || i === prevRaiserSeat) continue;
          state.activePlayers[i] = false;
        }
        break;
      }

      case 'A': {
        // all-in
        const amount = state.stacks[seat];
        const newTotal = state.investments[seat] + amount;
        state.pot += amount;
        state.investments[seat] = newTotal;
        state.stacks[seat] = 0;
        if (newTotal > state.lastRaiseTotal) {
          prevRaiserSeat = state.lastRaiserSeat;
          state.lastRaiserSeat = seat;
          state.lastRaiseTotal = newTotal;
          state.raiseLevel = Math.min(state.raiseLevel + 1, 4);
          state.raisesOnStreet++;
          if (seat === heroSeat) state.heroHasRaised = true;
          // After 3bet+ level: auto-fold uninvolved
          if (state.raiseLevel >= 2) {
            for (let i = 0; i < NUM_PLAYERS; i++) {
              if (!state.activePlayers[i]) continue;
              if (i === seat || i === prevRaiserSeat) continue;
              state.activePlayers[i] = false;
            }
          }
        }
        break;
      }
    }
  }

  return state;
}

// ══════════════════════════════════════════════
//   ACTION MAPPING
// ══════════════════════════════════════════════

/**
 * Map preflop actions + frequencies to V2 labels [raise, call, fold].
 * Aggregates all raise-type actions into a single "raise" probability.
 */
function mapActionsToV2Labels(actions: string[], frequencies: number[]): [number, number, number] {
  let raise = 0,
    call = 0,
    fold = 0;

  for (let i = 0; i < actions.length; i++) {
    const a = actions[i];
    const f = frequencies[i];
    if (a === 'fold') {
      fold += f;
    } else if (a === 'call' || a === 'check') {
      call += f;
    } else {
      // open_X, 3bet_X, 4bet_X, allin → raise
      raise += f;
    }
  }

  return [raise, call, fold];
}

// ══════════════════════════════════════════════
//   FEATURE ENCODING (54-dim V2, inline)
// ══════════════════════════════════════════════

/**
 * Encode preflop game state to 54-dim V2 feature vector.
 * Replicates feature-encoder.ts logic inline to avoid cross-package imports.
 */
function encodePreflop(
  holeCards: [string, string],
  heroPosition: string,
  heroInPosition: boolean,
  pot: number,
  toCall: number,
  effectiveStack: number,
  numVillains: number,
  isAggressor: boolean,
  is3betPot: boolean,
  raisesOnStreet: number,
  lastRaiseTotal: number,
  allInPressure: boolean,
): number[] {
  const bb = 1;
  const features: number[] = [];

  // [0-4] Hole cards
  const r1 = RANK_VALUES[holeCards[0][0]] ?? 0;
  const r2 = RANK_VALUES[holeCards[1][0]] ?? 0;
  const suited = holeCards[0][1] === holeCards[1][1] ? 1 : 0;
  const paired = holeCards[0][0] === holeCards[1][0] ? 1 : 0;
  const gap = Math.abs(r1 - r2) / 12;
  features.push(r1 / 14, r2 / 14, suited, paired, gap);

  // [5-29] Board: 5 empty slots × 5 features = all zeros
  for (let i = 0; i < 25; i++) features.push(0);

  // [30-32] Street one-hot: PREFLOP = [0, 0, 0]
  features.push(0, 0, 0);

  // [33-39] Position one-hot (7 positions)
  const posIdx = POSITION_INDEX[heroPosition.toUpperCase()] ?? -1;
  for (let i = 0; i < 7; i++) features.push(i === posIdx ? 1 : 0);

  // [40] In position
  features.push(heroInPosition ? 1 : 0);

  // [41-44] Pot geometry
  const potNorm = Math.min(pot / (100 * bb), 5);
  const toCallNorm = Math.min(toCall / (100 * bb), 5);
  const spr = pot > 0 ? Math.min(effectiveStack / pot, 20) / 20 : 1;
  const potOdds = pot + toCall > 0 ? toCall / (pot + toCall) : 0;
  features.push(potNorm, toCallNorm, spr, potOdds);

  // [45-47] Action context
  features.push(
    Math.min(numVillains, 5) / 5,
    toCall > 0 ? 1 : 0, // facingBet
    isAggressor ? 1 : 0,
  );

  // [48-53] V2 betting history
  features.push(is3betPot ? 1 : 0); // is3betPot
  features.push(0); // isCheckRaised (never in preflop)
  features.push(Math.min(raisesOnStreet, 5) / 5); // raisesOnStreet/5
  features.push(Math.min(raisesOnStreet, 10) / 10); // totalRaises/10 (same as street for preflop)
  const lastBetFrac = lastRaiseTotal > 0 && pot > 0 ? Math.min(lastRaiseTotal / pot, 2.0) / 2.0 : 0;
  features.push(lastBetFrac); // lastBetPotFrac/2
  features.push(allInPressure ? 1 : 0); // allInPressure

  return features;
}

// ══════════════════════════════════════════════
//   MAIN CONVERSION
// ══════════════════════════════════════════════

function convertConfig(
  preflopDir: string,
  configName: string,
  outputDir: string,
): { samples: number; records: number } {
  const inputPath = join(preflopDir, `training_${configName}.jsonl`);
  if (!existsSync(inputPath)) {
    console.warn(`  Skipping ${configName}: file not found at ${inputPath}`);
    return { samples: 0, records: 0 };
  }

  const config = getPreflopConfig(configName);
  const lines = readFileSync(inputPath, 'utf-8').trim().split('\n');
  const outputLines: string[] = [];
  let totalRecords = 0;
  let totalSamples = 0;

  for (const line of lines) {
    const record: TrainingRecord = JSON.parse(line);
    totalRecords++;

    // Find hero seat from position
    const heroSeat = POSITION_6MAX.indexOf(record.position as any);
    if (heroSeat === -1) {
      console.warn(`  Unknown position: ${record.position}, skipping`);
      continue;
    }

    // Replay history to reconstruct game state
    const state = replayHistory(record.history, heroSeat, config);

    // Compute derived features
    const toCall = Math.max(0, state.lastRaiseTotal - state.investments[heroSeat]);
    const effectiveStack = state.stacks[heroSeat];
    const numVillains = state.activePlayers.filter((a, i) => a && i !== heroSeat).length;

    // Determine isIP: for RFI (no villain yet), default to false.
    // For facing_open/3bet/4bet, compute relative to last raiser.
    let heroInPosition = false;
    if (state.lastRaiserSeat >= 0 && state.lastRaiserSeat !== heroSeat) {
      heroInPosition = isIPPostflop(heroSeat, state.lastRaiserSeat);
    }

    // Check if any opponent is all-in
    let allInPressure = false;
    for (let i = 0; i < NUM_PLAYERS; i++) {
      if (i !== heroSeat && state.activePlayers[i] && state.stacks[i] <= 0) {
        allInPressure = true;
        break;
      }
    }

    // Map actions → V2 labels
    const labels = mapActionsToV2Labels(record.actions, record.frequencies);

    // Expand hand class → combos
    const combos = expandHandClass(record.handClass);

    for (let ci = 0; ci < combos.length; ci++) {
      const combo = combos[ci];

      const features = encodePreflop(
        combo,
        record.position,
        heroInPosition,
        state.pot, // use replayed pot (should match record.pot)
        toCall,
        effectiveStack,
        numVillains,
        state.heroHasRaised,
        state.raiseLevel >= 2,
        state.raisesOnStreet,
        state.lastRaiseTotal,
        allInPressure,
      );

      const sample: TrainingSample = {
        f: features,
        l: labels,
        h: `preflop_${record.spot}_${record.handClass}_${ci}`,
        s: 'PREFLOP',
      };

      outputLines.push(JSON.stringify(sample));
      totalSamples++;
    }
  }

  // Write output
  const outputPath = join(outputDir, `preflop_${configName}.jsonl`);
  writeFileSync(outputPath, outputLines.join('\n') + '\n');
  console.log(`  ${configName}: ${totalRecords} records → ${totalSamples} samples → ${outputPath}`);

  return { samples: totalSamples, records: totalRecords };
}

// ══════════════════════════════════════════════
//   CLI
// ══════════════════════════════════════════════

function main(): void {
  const args = process.argv.slice(2);

  function getArg(name: string, defaultVal: string): string {
    const idx = args.indexOf(`--${name}`);
    if (idx !== -1 && args[idx + 1]) return args[idx + 1];
    return defaultVal;
  }

  const preflopDir = getArg('preflop-dir', 'data/preflop');
  const outputDir = getArg('output', 'data/training/preflop');
  const configsStr = getArg('configs', 'cash_6max_100bb,cash_6max_50bb,cash_6max_100bb_ante');
  const configs = configsStr.split(',').map((c) => c.trim());

  console.log('╔═══════════════════════════════════════════╗');
  console.log('║   Preflop → V3 Training Data              ║');
  console.log('╚═══════════════════════════════════════════╝');
  console.log(`  Input:   ${resolve(preflopDir)}`);
  console.log(`  Output:  ${resolve(outputDir)}`);
  console.log(`  Configs: ${configs.join(', ')}`);
  console.log();

  mkdirSync(outputDir, { recursive: true });

  let grandTotalRecords = 0;
  let grandTotalSamples = 0;

  for (const configName of configs) {
    const { samples, records } = convertConfig(preflopDir, configName, outputDir);
    grandTotalRecords += records;
    grandTotalSamples += samples;
  }

  // Write manifest
  const manifest = {
    type: 'preflop_training',
    configs,
    totalRecords: grandTotalRecords,
    totalSamples: grandTotalSamples,
    streets: ['PREFLOP'],
    featureCount: 54,
    generatedAt: new Date().toISOString(),
  };
  writeFileSync(join(outputDir, 'manifest.json'), JSON.stringify(manifest, null, 2));

  console.log();
  console.log(`Total: ${grandTotalRecords} records → ${grandTotalSamples} samples`);
  console.log(`Manifest: ${join(outputDir, 'manifest.json')}`);
}

main();
