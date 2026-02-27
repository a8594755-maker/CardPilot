#!/usr/bin/env tsx
/**
 * CFR → Training Data Converter
 *
 * Reads solved flop .jsonl files from the CFR pipeline and produces
 * fast-model-compatible training samples (JSONL format).
 *
 * For each info-set in the CFR data:
 *   1. Parse the key → street, boardId, player, historyKey, buckets
 *   2. Replay the historyKey to reconstruct game state (pot, stacks, facingBet)
 *   3. Reverse-map buckets → representative hole card combos
 *   4. Encode features (54-dim V2 vector) and map CFR probs to V2 labels
 *   5. Output as training sample JSONL
 *
 * Usage:
 *   npx tsx packages/cfr-solver/src/scripts/cfr-to-training-data.ts \
 *     --cfr-dir data/cfr/pipeline_hu_srp_50bb/ \
 *     --output data/training/cfr_srp/ \
 *     --config pipeline_srp \
 *     --samples-per-bucket 3 \
 *     --workers 4
 */

import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fork, type ChildProcess } from 'node:child_process';
import { cpus } from 'node:os';
import { fileURLToPath } from 'node:url';

import { indexToCard } from '../abstraction/card-index.js';
import {
  loadHUSRPRanges,
  getWeightedRangeCombos,
  type WeightedCombo,
} from '../integration/preflop-ranges.js';
import {
  computeEquityBuckets,
  comboKey,
} from '../engine/cfr-engine.js';
import {
  getTreeConfig,
  calcBetAmount,
  calcRaiseAmount,
  type TreeConfigName,
} from '../tree/tree-config.js';
import type { Street, TreeConfig } from '../types.js';

// ══════════════════════════════════════════════
//   TYPES
// ══════════════════════════════════════════════

interface TrainingSample {
  f: number[];
  l: [number, number, number];
  sz?: [number, number, number, number, number];
  h: string;
  s: string;
}

interface GameState {
  pot: number;
  stacks: [number, number];
  facingBet: number;
  currentPlayer: 0 | 1;
  street: Street;
  toCall: number;
  isFirstAction: boolean;
}

interface ParsedInfoSetKey {
  street: Street;
  boardId: number;
  player: 0 | 1;
  historyKey: string;
  bucketStr: string; // e.g. "32" or "32-19" or "32-19-41"
}

interface FlopMeta {
  boardId: number;
  flopCards: [number, number, number];
  bucketCount: number;
  configName: string;
  iterations: number;
}

interface GenerateConfig {
  cfrDir: string;
  outputDir: string;
  configName: TreeConfigName;
  samplesPerBucket: number;
  workers: number;
  riverSamplesPerTurn: number;
  minProbDivergence: number;
  maxFlops: number;
}

// ══════════════════════════════════════════════
//   INFO-SET KEY PARSING
// ══════════════════════════════════════════════

const STREET_MAP: Record<string, Street> = { F: 'FLOP', T: 'TURN', R: 'RIVER' };

export function parseInfoSetKey(key: string): ParsedInfoSetKey {
  const parts = key.split('|');
  return {
    street: STREET_MAP[parts[0]],
    boardId: parseInt(parts[1], 10),
    player: parseInt(parts[2], 10) as 0 | 1,
    historyKey: parts[3],
    bucketStr: parts[4],
  };
}

// ══════════════════════════════════════════════
//   HISTORY REPLAY
// ══════════════════════════════════════════════

/**
 * Replay a history key string through the tree config to reconstruct
 * the full game state at that point.
 *
 * Action chars: x=check, c=call, f=fold, A=allin
 * bet_0 → '1', bet_1 → '2', raise_0 → '1', raise_1 → '2' etc.
 * '/' = street separator
 */
export function replayHistory(historyKey: string, config: TreeConfig): GameState {
  let pot = config.startingPot;
  let stacks: [number, number] = [config.effectiveStack, config.effectiveStack];
  let currentPlayer: 0 | 1 = 0; // OOP acts first
  let facingBet = 0;
  let street: Street = 'FLOP';
  let isFirstAction = true;

  for (const char of historyKey) {
    if (char === '/') {
      // Street separator — advance
      street = nextStreet(street);
      currentPlayer = 0; // OOP acts first each street
      facingBet = 0;
      isFirstAction = true;
      continue;
    }

    const p = currentPlayer;
    const opp = (1 - p) as 0 | 1;

    switch (char) {
      case 'x': // check
        currentPlayer = opp;
        isFirstAction = false;
        // facingBet stays 0 for checks
        break;

      case 'c': { // call
        const callAmt = Math.min(facingBet, stacks[p]);
        stacks = [stacks[0], stacks[1]] as [number, number];
        stacks[p] -= callAmt;
        pot += callAmt;
        currentPlayer = opp;
        facingBet = 0;
        break;
      }

      case 'f': // fold
        // Terminal — shouldn't appear in non-terminal histories
        break;

      case 'A': { // all-in
        const allInAmt = stacks[p];
        stacks = [stacks[0], stacks[1]] as [number, number];
        stacks[p] = 0;
        pot += allInAmt;
        facingBet = allInAmt;
        currentPlayer = opp;
        isFirstAction = false;
        break;
      }

      default: {
        // Numeric: '1' = bet_0/raise_0, '2' = bet_1/raise_1, etc.
        const sizeIdx = parseInt(char, 10) - 1;
        if (isNaN(sizeIdx) || sizeIdx < 0) break;

        const betSizes = getBetSizesForStreet(config, street);
        const fraction = betSizes[sizeIdx] ?? betSizes[betSizes.length - 1];

        let betAmount: number;
        if (facingBet > 0) {
          // Raise
          betAmount = calcRaiseAmount(pot, facingBet, fraction, stacks[p]);
        } else {
          // Bet
          betAmount = calcBetAmount(pot, fraction, stacks[p]);
        }

        stacks = [stacks[0], stacks[1]] as [number, number];
        stacks[p] -= betAmount;
        pot += betAmount;
        facingBet = betAmount;
        currentPlayer = opp;
        isFirstAction = false;
        break;
      }
    }
  }

  return {
    pot,
    stacks,
    facingBet,
    currentPlayer,
    street,
    toCall: facingBet,
    isFirstAction,
  };
}

function nextStreet(street: Street): Street {
  switch (street) {
    case 'FLOP': return 'TURN';
    case 'TURN': return 'RIVER';
    case 'RIVER': return 'RIVER'; // shouldn't happen
  }
}

function getBetSizesForStreet(config: TreeConfig, street: Street): number[] {
  switch (street) {
    case 'FLOP': return config.betSizes.flop;
    case 'TURN': return config.betSizes.turn;
    case 'RIVER': return config.betSizes.river;
  }
}

// ══════════════════════════════════════════════
//   ACTION MAPPING (CFR → V2 labels)
// ══════════════════════════════════════════════

/**
 * Determine what actions are available at a given history point.
 * Returns the action names that correspond to each prob index.
 */
export function inferActionsFromHistory(historyKey: string, config: TreeConfig): string[] {
  const state = replayHistory(historyKey, config);

  if (state.facingBet > 0) {
    // Facing a bet/raise: fold, call, (optionally raises)
    const actions: string[] = ['fold', 'call'];
    // In pipeline_srp, raiseCapPerStreet=0, so no raises after a bet
    if (config.raiseCapPerStreet > 0) {
      const betSizes = getBetSizesForStreet(config, state.street);
      for (let i = 0; i < betSizes.length; i++) {
        actions.push(`raise_${i}`);
      }
      actions.push('allin');
    }
    return actions;
  } else {
    // Opening action: check, bet sizes, allin
    const actions: string[] = ['check'];
    const betSizes = getBetSizesForStreet(config, state.street);
    for (let i = 0; i < betSizes.length; i++) {
      // Check if bet amount equals stack (would be allin)
      const betAmt = calcBetAmount(state.pot, betSizes[i], state.stacks[state.currentPlayer]);
      if (betAmt >= state.stacks[state.currentPlayer]) {
        if (!actions.includes('allin')) actions.push('allin');
        break;
      }
      actions.push(`bet_${i}`);
    }
    if (!actions.includes('allin') && state.stacks[state.currentPlayer] > 0) {
      actions.push('allin');
    }
    return actions;
  }
}

/**
 * Map CFR action probabilities to V2 training labels.
 *
 * V2 labels: l=[raise, call, fold], sz=[third, half, twoThirds, pot, allIn]
 *
 * Action mapping:
 *   check → call (passive action)
 *   bet_X / raise_X → raise (with sizing info)
 *   allin → raise (sizing = allIn)
 *   call → call
 *   fold → fold
 */
export function mapCfrProbsToV2Labels(
  actions: string[],
  probs: number[],
  config: TreeConfig,
  street: Street,
): { l: [number, number, number]; sz?: [number, number, number, number, number] } {
  let raiseProb = 0;
  let callProb = 0;
  let foldProb = 0;

  // Sizing distribution for raise actions
  // [third(33%), half(50%), twoThirds(66%), pot(100%), allIn]
  const sizingWeights: [number, number, number, number, number] = [0, 0, 0, 0, 0];

  const betSizes = getBetSizesForStreet(config, street);

  for (let i = 0; i < actions.length; i++) {
    const action = actions[i];
    const prob = probs[i] ?? 0;

    if (action === 'check' || action === 'call') {
      callProb += prob;
    } else if (action === 'fold') {
      foldProb += prob;
    } else if (action === 'allin') {
      raiseProb += prob;
      sizingWeights[4] += prob; // allIn bucket
    } else if (action.startsWith('bet_') || action.startsWith('raise_')) {
      raiseProb += prob;
      // Map bet/raise size fraction to sizing bucket
      const match = action.match(/^(?:bet|raise)_(\d+)$/);
      if (match) {
        const idx = parseInt(match[1], 10);
        const fraction = betSizes[idx] ?? 0.5;
        const sizingIdx = fractionToSizingIndex(fraction);
        sizingWeights[sizingIdx] += prob;
      }
    }
  }

  const l: [number, number, number] = [raiseProb, callProb, foldProb];

  // Normalize sizing if there's any raise probability
  let sz: [number, number, number, number, number] | undefined;
  if (raiseProb > 0.001) {
    const total = sizingWeights.reduce((a, b) => a + b, 0);
    if (total > 0) {
      sz = sizingWeights.map(w => w / total) as [number, number, number, number, number];
    }
  }

  return { l, sz };
}

/**
 * Map a pot fraction to the closest V2 sizing index.
 * V2 sizing buckets: [0.33, 0.50, 0.66, 1.00, allIn]
 */
function fractionToSizingIndex(fraction: number): number {
  if (fraction <= 0.40) return 0; // third (33%)
  if (fraction <= 0.58) return 1; // half (50%)
  if (fraction <= 0.83) return 2; // twoThirds (66%)
  return 3; // pot (100%)
  // allIn (index 4) is handled separately
}

// ══════════════════════════════════════════════
//   FEATURE ENCODING (CFR-specific adapter)
// ══════════════════════════════════════════════

const RANK_VALUES: Record<string, number> = {
  '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8,
  '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14,
};
const SUIT_INDEX: Record<string, number> = { 's': 0, 'h': 1, 'd': 2, 'c': 3 };

/**
 * Encode CFR game state into a 54-dim V2 feature vector.
 * Reimplements the fast-model feature-encoder logic to avoid circular dependency.
 */
export function encodeCfrFeatures(
  holeCards: [number, number],
  boardCards: number[],
  gameState: GameState,
  player: 0 | 1,
  historyKey: string,
): number[] {
  const h0 = indexToCard(holeCards[0]);
  const h1 = indexToCard(holeCards[1]);
  const board = boardCards.map(indexToCard);

  const features: number[] = [];

  // ── Hole cards (5 features) ──
  const r1 = RANK_VALUES[h0[0]] ?? 0;
  const r2 = RANK_VALUES[h1[0]] ?? 0;
  const suited = h0[1] === h1[1] ? 1 : 0;
  const paired = h0[0] === h1[0] ? 1 : 0;
  const gap = Math.abs(r1 - r2) / 12;
  features.push(r1 / 14, r2 / 14, suited, paired, gap);

  // ── Board cards (25 features: 5 slots × 5) ──
  for (let i = 0; i < 5; i++) {
    if (i < board.length && board[i]) {
      const r = (RANK_VALUES[board[i][0]] ?? 0) / 14;
      const sIdx = SUIT_INDEX[board[i][1]] ?? 0;
      features.push(r, sIdx === 0 ? 1 : 0, sIdx === 1 ? 1 : 0, sIdx === 2 ? 1 : 0, sIdx === 3 ? 1 : 0);
    } else {
      features.push(0, 0, 0, 0, 0);
    }
  }

  // ── Street one-hot (3 features) ──
  const st = gameState.street;
  features.push(st === 'FLOP' ? 1 : 0, st === 'TURN' ? 1 : 0, st === 'RIVER' ? 1 : 0);

  // ── Position one-hot (7 features) ──
  // In HU: player 0 = BB (index 6), player 1 = BTN (index 4)
  const posIdx = player === 0 ? 6 : 4; // BB=6, BTN=4
  for (let i = 0; i < 7; i++) {
    features.push(i === posIdx ? 1 : 0);
  }

  // ── In position (1 feature) ──
  features.push(player === 1 ? 1 : 0); // BTN is in position

  // ── Pot geometry (4 features) ──
  const bb = 1; // normalized to 1bb
  const potNorm = Math.min(gameState.pot / (100 * bb), 5);
  const toCallNorm = Math.min(gameState.toCall / (100 * bb), 5);
  const spr = gameState.pot > 0
    ? Math.min(gameState.stacks[player] / gameState.pot, 20) / 20
    : 1;
  const potOdds = (gameState.pot + gameState.toCall) > 0
    ? gameState.toCall / (gameState.pot + gameState.toCall)
    : 0;
  features.push(potNorm, toCallNorm, spr, potOdds);

  // ── Action context (3 features) ──
  features.push(
    1 / 5, // numVillains = 1 (HU), divided by 5
    gameState.toCall > 0 ? 1 : 0, // facing bet
    player === 1 ? 1 : 0, // isAggressor: BTN was preflop aggressor in SRP
  );

  // ── V2 betting history (6 features) ──
  const histAgg = aggregateHistoryKey(historyKey, gameState.street);

  // [48] is3betPot
  features.push(histAgg.preflopRaises >= 2 ? 1 : 0);
  // [49] isCheckRaised
  features.push(histAgg.isCheckRaised ? 1 : 0);
  // [50] raiseCountStreet / 5
  features.push(Math.min(histAgg.raisesOnStreet, 5) / 5);
  // [51] raiseCountTotal / 10
  features.push(Math.min(histAgg.totalRaises, 10) / 10);
  // [52] lastBetPotFrac / 2
  const lastBetFrac = (histAgg.lastBetAmount > 0 && gameState.pot > 0)
    ? Math.min(histAgg.lastBetAmount / gameState.pot, 2.0) / 2.0
    : 0;
  features.push(lastBetFrac);
  // [53] allInPressure
  features.push(histAgg.hasAllIn ? 1 : 0);

  return features;
}

interface HistoryAggregates {
  preflopRaises: number;
  isCheckRaised: boolean;
  raisesOnStreet: number;
  totalRaises: number;
  lastBetAmount: number;
  hasAllIn: boolean;
}

/**
 * Aggregate betting history stats from a historyKey string.
 * This is the CFR equivalent of the game-server's aggregateActions().
 */
function aggregateHistoryKey(historyKey: string, currentStreet: Street): HistoryAggregates {
  let preflopRaises = 0;
  let raisesOnStreet = 0;
  let totalRaises = 0;
  let lastBetAmount = 0;
  let isCheckRaised = false;
  let hasAllIn = false;

  let street: Street = 'FLOP';
  let checkedOnStreet = false;

  for (const char of historyKey) {
    if (char === '/') {
      street = nextStreet(street);
      checkedOnStreet = false;
      continue;
    }

    const isRaise = char === 'A' || (char >= '1' && char <= '9');

    if (isRaise) {
      totalRaises++;
      if (street === currentStreet) {
        raisesOnStreet++;
        // Check-raise: if someone checked earlier on this street
        if (checkedOnStreet) isCheckRaised = true;
      }
      if (char === 'A') hasAllIn = true;
    } else if (char === 'x') {
      if (street === currentStreet) checkedOnStreet = true;
    }
  }

  // Approximate lastBetAmount — we don't have exact amounts in the key,
  // but we can infer from the tree config if needed.
  // For now, mark as 0 and let the model rely on other features.
  return {
    preflopRaises, // always 0 for postflop-only CFR data (SRP = no preflop raises)
    isCheckRaised,
    raisesOnStreet,
    totalRaises,
    lastBetAmount,
    hasAllIn,
  };
}

// ══════════════════════════════════════════════
//   BUCKET → COMBO REVERSE MAPPING
// ══════════════════════════════════════════════

interface BucketComboMap {
  /** Flop bucket → array of valid combos */
  flop: Map<number, Array<[number, number]>>;
  /** "flopBucket-turnBucket" → array of {combo, turnCard} */
  turn: Map<string, Array<{ combo: [number, number]; turnCard: number }>>;
  /** "flopBucket-turnBucket-riverBucket" → array of {combo, turnCard, riverCard} */
  river: Map<string, Array<{ combo: [number, number]; turnCard: number; riverCard: number }>>;
}

/**
 * Build the reverse mapping from bucket(s) → concrete hole card combos.
 *
 * This is the most CPU-intensive part of data generation.
 * For flop: O(N) where N = valid combos (~1000).
 * For turn: O(49 * N) — one pass per valid turn card.
 * For river: O(49 * riverSamples * N) — sampled river cards per turn card.
 */
export function buildBucketComboMap(
  flopCards: [number, number, number],
  oopRange: WeightedCombo[],
  ipRange: WeightedCombo[],
  bucketCount: number,
  riverSamplesPerTurn: number,
): { oopMap: BucketComboMap; ipMap: BucketComboMap } {
  const deadCards = new Set<number>(flopCards);

  // ── Flop bucket mapping ──
  const oopFlopBuckets = computeEquityBuckets(oopRange, flopCards, bucketCount, deadCards);
  const ipFlopBuckets = computeEquityBuckets(ipRange, flopCards, bucketCount, deadCards);

  const oopFlopMap = invertBucketMap(oopFlopBuckets, oopRange, deadCards);
  const ipFlopMap = invertBucketMap(ipFlopBuckets, ipRange, deadCards);

  // ── Turn bucket mapping ──
  // Enumerate all valid turn cards
  const turnCards: number[] = [];
  for (let c = 0; c < 52; c++) {
    if (!deadCards.has(c)) turnCards.push(c);
  }

  const oopTurnMap = new Map<string, Array<{ combo: [number, number]; turnCard: number }>>();
  const ipTurnMap = new Map<string, Array<{ combo: [number, number]; turnCard: number }>>();

  for (const turnCard of turnCards) {
    const turnBoard = [...flopCards, turnCard];
    const turnDead = new Set([...deadCards, turnCard]);

    // Compute turn buckets for all valid combos in each range
    buildTurnBuckets(oopRange, turnBoard, turnDead, bucketCount, oopFlopBuckets, turnCard, oopTurnMap);
    buildTurnBuckets(ipRange, turnBoard, turnDead, bucketCount, ipFlopBuckets, turnCard, ipTurnMap);
  }

  // ── River bucket mapping (sampled) ──
  const oopRiverMap = new Map<string, Array<{ combo: [number, number]; turnCard: number; riverCard: number }>>();
  const ipRiverMap = new Map<string, Array<{ combo: [number, number]; turnCard: number; riverCard: number }>>();

  for (const turnCard of turnCards) {
    const turnDead = new Set([...deadCards, turnCard]);
    // Sample N river cards for this turn
    const riverCandidates: number[] = [];
    for (let c = 0; c < 52; c++) {
      if (!turnDead.has(c)) riverCandidates.push(c);
    }

    // Sample up to riverSamplesPerTurn river cards
    const riverCards = sampleN(riverCandidates, riverSamplesPerTurn);

    for (const riverCard of riverCards) {
      const riverBoard = [...flopCards, turnCard, riverCard];
      const riverDead = new Set([...turnDead, riverCard]);

      buildRiverBuckets(oopRange, riverBoard, riverDead, bucketCount, oopFlopBuckets, turnCard, riverCard, oopRiverMap);
      buildRiverBuckets(ipRange, riverBoard, riverDead, bucketCount, ipFlopBuckets, turnCard, riverCard, ipRiverMap);
    }
  }

  return {
    oopMap: { flop: oopFlopMap, turn: oopTurnMap, river: oopRiverMap },
    ipMap: { flop: ipFlopMap, turn: ipTurnMap, river: ipRiverMap },
  };
}

function invertBucketMap(
  bucketMap: Map<string, number>,
  range: WeightedCombo[],
  deadCards: Set<number>,
): Map<number, Array<[number, number]>> {
  const result = new Map<number, Array<[number, number]>>();
  for (const { combo } of range) {
    if (deadCards.has(combo[0]) || deadCards.has(combo[1])) continue;
    const key = comboKey(combo);
    const bucket = bucketMap.get(key);
    if (bucket === undefined) continue;
    if (!result.has(bucket)) result.set(bucket, []);
    result.get(bucket)!.push(combo);
  }
  return result;
}

function buildTurnBuckets(
  range: WeightedCombo[],
  turnBoard: number[],
  deadCards: Set<number>,
  bucketCount: number,
  flopBuckets: Map<string, number>,
  turnCard: number,
  output: Map<string, Array<{ combo: [number, number]; turnCard: number }>>,
): void {
  // Compute turn equity buckets for all valid combos
  const turnBuckets = computeEquityBuckets(range, turnBoard, bucketCount, deadCards);

  for (const { combo } of range) {
    if (deadCards.has(combo[0]) || deadCards.has(combo[1])) continue;
    const key = comboKey(combo);
    const flopB = flopBuckets.get(key);
    const turnB = turnBuckets.get(key);
    if (flopB === undefined || turnB === undefined) continue;

    const bucketKey = `${flopB}-${turnB}`;
    if (!output.has(bucketKey)) output.set(bucketKey, []);
    output.get(bucketKey)!.push({ combo, turnCard });
  }
}

function buildRiverBuckets(
  range: WeightedCombo[],
  riverBoard: number[],
  deadCards: Set<number>,
  bucketCount: number,
  flopBuckets: Map<string, number>,
  turnCard: number,
  riverCard: number,
  output: Map<string, Array<{ combo: [number, number]; turnCard: number; riverCard: number }>>,
): void {
  // Compute river equity buckets
  const riverBuckets = computeEquityBuckets(range, riverBoard, bucketCount, deadCards);

  // For turn bucket, we need to re-compute (or we could cache)
  const turnBoard = riverBoard.slice(0, 4);
  const turnDead = new Set([...Array.from(deadCards), riverCard]); // note: deadCards already excludes turnCard
  // Actually deadCards already has the turn card removed issue... let's just recompute
  const turnBoardDead = new Set(turnBoard);
  const turnBuckets = computeEquityBuckets(range, turnBoard, bucketCount, turnBoardDead);

  for (const { combo } of range) {
    if (deadCards.has(combo[0]) || deadCards.has(combo[1])) continue;
    const key = comboKey(combo);
    const flopB = flopBuckets.get(key);
    const turnB = turnBuckets.get(key);
    const riverB = riverBuckets.get(key);
    if (flopB === undefined || turnB === undefined || riverB === undefined) continue;

    const bucketKey = `${flopB}-${turnB}-${riverB}`;
    if (!output.has(bucketKey)) output.set(bucketKey, []);
    output.get(bucketKey)!.push({ combo, turnCard, riverCard });
  }
}

function sampleN<T>(arr: T[], n: number): T[] {
  if (arr.length <= n) return arr;
  // Fisher-Yates partial shuffle
  const copy = [...arr];
  for (let i = 0; i < n; i++) {
    const j = i + Math.floor(Math.random() * (copy.length - i));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy.slice(0, n);
}

// ══════════════════════════════════════════════
//   FLOP PROCESSOR (generates training samples for one flop)
// ══════════════════════════════════════════════

export function processFlop(
  meta: FlopMeta,
  infoSets: Map<string, number[]>,
  config: TreeConfig,
  oopRange: WeightedCombo[],
  ipRange: WeightedCombo[],
  samplesPerBucket: number,
  riverSamplesPerTurn: number,
  minProbDivergence: number,
): TrainingSample[] {
  const startTime = Date.now();
  const { flopCards, boardId, bucketCount } = meta;

  // Step 1: Build bucket → combo reverse mapping
  const { oopMap, ipMap } = buildBucketComboMap(
    flopCards, oopRange, ipRange, bucketCount, riverSamplesPerTurn,
  );

  const samples: TrainingSample[] = [];

  // Step 2: Process each info-set
  for (const [key, probs] of infoSets) {
    const parsed = parseInfoSetKey(key);

    // Skip if probs are near-uniform (not interesting)
    if (isNearUniform(probs, minProbDivergence)) continue;

    // Determine actions for this node
    const actions = inferActionsFromHistory(parsed.historyKey, config);
    if (actions.length !== probs.length) {
      // Mismatch — skip (shouldn't happen if config matches)
      continue;
    }

    // Map to V2 labels
    const { l, sz } = mapCfrProbsToV2Labels(actions, probs, config, parsed.street);

    // Replay history to get game state
    const gameState = replayHistory(parsed.historyKey, config);

    // Get the bucket→combo map for this player
    const bucketMap = parsed.player === 0 ? oopMap : ipMap;

    // Look up combos for this bucket string
    const combos = lookupCombos(
      bucketMap, parsed.street, parsed.bucketStr, flopCards,
    );
    if (!combos || combos.length === 0) continue;

    // Sample N representative combos
    const sampled = sampleN(combos, samplesPerBucket);

    for (const entry of sampled) {
      const holeCards = entry.combo;
      // Build the board for this street
      const boardCards = buildBoardForEntry(flopCards, parsed.street, entry);

      // Check for card conflicts
      if (boardCards.some(c => c === holeCards[0] || c === holeCards[1])) continue;

      // Encode features
      const f = encodeCfrFeatures(holeCards, boardCards, gameState, parsed.player, parsed.historyKey);

      const sample: TrainingSample = {
        f,
        l,
        h: `flop${String(boardId).padStart(4, '0')}_${parsed.street[0]}${parsed.player}_b${parsed.bucketStr}`,
        s: parsed.street,
      };
      if (sz) sample.sz = sz;
      samples.push(sample);
    }
  }

  const elapsed = Date.now() - startTime;
  console.log(`  Flop ${boardId}: ${samples.length} samples in ${(elapsed / 1000).toFixed(1)}s`);

  return samples;
}

interface ComboEntry {
  combo: [number, number];
  turnCard?: number;
  riverCard?: number;
}

function lookupCombos(
  bucketMap: BucketComboMap,
  street: Street,
  bucketStr: string,
  _flopCards: [number, number, number],
): ComboEntry[] | null {
  switch (street) {
    case 'FLOP': {
      const bucket = parseInt(bucketStr, 10);
      const combos = bucketMap.flop.get(bucket);
      if (!combos) return null;
      return combos.map(combo => ({ combo }));
    }
    case 'TURN': {
      const entries = bucketMap.turn.get(bucketStr);
      if (!entries) return null;
      return entries.map(e => ({ combo: e.combo, turnCard: e.turnCard }));
    }
    case 'RIVER': {
      const entries = bucketMap.river.get(bucketStr);
      if (!entries) return null;
      return entries.map(e => ({ combo: e.combo, turnCard: e.turnCard, riverCard: e.riverCard }));
    }
  }
}

function buildBoardForEntry(
  flopCards: [number, number, number],
  street: Street,
  entry: ComboEntry,
): number[] {
  switch (street) {
    case 'FLOP':
      return [...flopCards];
    case 'TURN':
      return [...flopCards, entry.turnCard!];
    case 'RIVER':
      return [...flopCards, entry.turnCard!, entry.riverCard!];
  }
}

function isNearUniform(probs: number[], minDivergence: number): boolean {
  if (probs.length === 0) return true;
  const uniform = 1 / probs.length;
  const maxDev = Math.max(...probs.map(p => Math.abs(p - uniform)));
  return maxDev < minDivergence;
}

// ══════════════════════════════════════════════
//   FILE I/O
// ══════════════════════════════════════════════

function loadFlopMeta(metaPath: string): FlopMeta {
  const raw = JSON.parse(readFileSync(metaPath, 'utf-8'));
  return {
    boardId: raw.boardId,
    flopCards: raw.flopCards,
    bucketCount: raw.bucketCount,
    configName: raw.config,
    iterations: raw.iterations,
  };
}

function loadFlopInfoSets(jsonlPath: string): Map<string, number[]> {
  const map = new Map<string, number[]>();
  const lines = readFileSync(jsonlPath, 'utf-8').split('\n');
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const entry = JSON.parse(trimmed);
      if (entry.key && entry.probs) {
        map.set(entry.key, entry.probs);
      }
    } catch {
      // skip malformed lines
    }
  }
  return map;
}

function discoverSolvedFlops(cfrDir: string): Array<{ boardId: number; metaPath: string; jsonlPath: string }> {
  const files = readdirSync(cfrDir).filter(f => f.endsWith('.meta.json'));
  const result: Array<{ boardId: number; metaPath: string; jsonlPath: string }> = [];

  for (const metaFile of files) {
    const jsonlFile = metaFile.replace('.meta.json', '.jsonl');
    const jsonlPath = join(cfrDir, jsonlFile);
    if (!existsSync(jsonlPath)) continue;

    const metaPath = join(cfrDir, metaFile);
    const match = metaFile.match(/flop_(\d+)\.meta\.json/);
    if (!match) continue;

    result.push({
      boardId: parseInt(match[1], 10),
      metaPath,
      jsonlPath,
    });
  }

  return result.sort((a, b) => a.boardId - b.boardId);
}

function writeSamples(outputPath: string, samples: TrainingSample[]): void {
  const lines = samples.map(s => JSON.stringify(s));
  writeFileSync(outputPath, lines.join('\n') + '\n', 'utf-8');
}

// ══════════════════════════════════════════════
//   CHILD PROCESS WORKER SUPPORT (fork-based)
// ══════════════════════════════════════════════

interface WorkerTask {
  metaPath: string;
  jsonlPath: string;
  boardId: number;
}

interface WorkerConfig {
  configName: TreeConfigName;
  samplesPerBucket: number;
  riverSamplesPerTurn: number;
  minProbDivergence: number;
  outputDir: string;
  chartsPath: string;
}

const IS_WORKER = process.argv.includes('--worker-mode');
const IS_MAIN_SCRIPT = process.argv[1] && resolve(process.argv[1]).replace(/\\/g, '/').includes('cfr-to-training-data');

if (IS_WORKER) {
  // Child process worker mode
  const config = JSON.parse(process.env.WORKER_CONFIG!) as WorkerConfig;
  const treeConfig = getTreeConfig(config.configName);
  const { oopRange, ipRange } = loadHUSRPRanges(config.chartsPath);
  const oopCombos = getWeightedRangeCombos(oopRange);
  const ipCombos = getWeightedRangeCombos(ipRange);

  process.on('message', (task: WorkerTask | 'exit') => {
    if (task === 'exit') {
      process.exit(0);
    }

    try {
      const meta = loadFlopMeta(task.metaPath);
      const infoSets = loadFlopInfoSets(task.jsonlPath);

      const samples = processFlop(
        meta, infoSets, treeConfig,
        oopCombos, ipCombos,
        config.samplesPerBucket,
        config.riverSamplesPerTurn,
        config.minProbDivergence,
      );

      const outputPath = join(config.outputDir, `flop_${String(task.boardId).padStart(4, '0')}.jsonl`);
      writeSamples(outputPath, samples);

      process.send!({ boardId: task.boardId, samples: samples.length, ok: true });
    } catch (err) {
      process.send!({
        boardId: task.boardId,
        samples: 0,
        ok: false,
        error: (err as Error).message,
      });
    }
  });
}

// ══════════════════════════════════════════════
//   MAIN (single-threaded fallback or coordinator)
// ══════════════════════════════════════════════

function parseArgs(): GenerateConfig {
  const argv = process.argv.slice(2);
  let cfrDir = '';
  let outputDir = '';
  let configName: TreeConfigName = 'pipeline_srp';
  let samplesPerBucket = 3;
  let workers = Math.max(1, cpus().length - 1);
  let riverSamplesPerTurn = 10;
  let minProbDivergence = 0.05;
  let maxFlops = Infinity;

  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--cfr-dir' && argv[i + 1]) cfrDir = argv[++i];
    if (argv[i] === '--output' && argv[i + 1]) outputDir = argv[++i];
    if (argv[i] === '--config' && argv[i + 1]) configName = argv[++i] as TreeConfigName;
    if (argv[i] === '--samples-per-bucket' && argv[i + 1]) samplesPerBucket = parseInt(argv[++i], 10);
    if (argv[i] === '--workers' && argv[i + 1]) workers = parseInt(argv[++i], 10);
    if (argv[i] === '--river-samples' && argv[i + 1]) riverSamplesPerTurn = parseInt(argv[++i], 10);
    if (argv[i] === '--min-divergence' && argv[i + 1]) minProbDivergence = parseFloat(argv[++i]);
    if (argv[i] === '--max-flops' && argv[i + 1]) maxFlops = parseInt(argv[++i], 10);
  }

  if (!cfrDir) cfrDir = resolve(process.cwd(), 'data/cfr/pipeline_hu_srp_50bb');
  if (!outputDir) outputDir = resolve(process.cwd(), 'data/training/cfr_srp');

  return { cfrDir, outputDir, configName, samplesPerBucket, workers, riverSamplesPerTurn, minProbDivergence, maxFlops };
}

async function runWithWorkers(
  tasks: WorkerTask[],
  workerConfig: WorkerConfig,
  numWorkers: number,
): Promise<{ totalSamples: number; processedFlops: number }> {
  const scriptPath = fileURLToPath(import.meta.url);
  let totalSamples = 0;
  let processedFlops = 0;
  let taskIdx = 0;

  return new Promise((resolvePromise) => {
    const activeWorkers = new Set<ChildProcess>();

    function spawnWorker() {
      if (taskIdx >= tasks.length && activeWorkers.size === 0) {
        resolvePromise({ totalSamples, processedFlops });
        return;
      }

      const child = fork(scriptPath, ['--worker-mode'], {
        env: { ...process.env, WORKER_CONFIG: JSON.stringify(workerConfig) },
        stdio: ['pipe', 'inherit', 'inherit', 'ipc'],
      });
      activeWorkers.add(child);

      child.on('message', (msg: { boardId: number; samples: number; ok: boolean; error?: string }) => {
        if (msg.ok) {
          totalSamples += msg.samples;
          processedFlops++;
        } else {
          console.error(`  ERROR flop ${msg.boardId}: ${msg.error}`);
        }

        // Send next task
        if (taskIdx < tasks.length) {
          child.send(tasks[taskIdx++]);
        } else {
          child.send('exit');
          activeWorkers.delete(child);
          if (activeWorkers.size === 0) {
            resolvePromise({ totalSamples, processedFlops });
          }
        }
      });

      child.on('error', (err) => {
        console.error(`Worker error:`, err);
        activeWorkers.delete(child);
        if (activeWorkers.size === 0 && taskIdx >= tasks.length) {
          resolvePromise({ totalSamples, processedFlops });
        }
      });

      child.on('exit', (code) => {
        activeWorkers.delete(child);
        if (code !== 0 && code !== null) {
          console.error(`Worker exited with code ${code}`);
        }
        if (activeWorkers.size === 0 && taskIdx >= tasks.length) {
          resolvePromise({ totalSamples, processedFlops });
        }
      });

      // Send first task
      if (taskIdx < tasks.length) {
        child.send(tasks[taskIdx++]);
      }
    }

    // Spawn workers
    const actual = Math.min(numWorkers, tasks.length);
    for (let i = 0; i < actual; i++) {
      spawnWorker();
    }
  });
}

async function runSingleThreaded(
  tasks: WorkerTask[],
  config: GenerateConfig,
): Promise<{ totalSamples: number; processedFlops: number }> {
  const treeConfig = getTreeConfig(config.configName);
  const chartsPath = resolve(process.cwd(), 'data/preflop_charts.json');
  const { oopRange, ipRange } = loadHUSRPRanges(chartsPath);
  const oopCombos = getWeightedRangeCombos(oopRange);
  const ipCombos = getWeightedRangeCombos(ipRange);

  let totalSamples = 0;
  let processedFlops = 0;

  for (const task of tasks) {
    const meta = loadFlopMeta(task.metaPath);
    const infoSets = loadFlopInfoSets(task.jsonlPath);

    const samples = processFlop(
      meta, infoSets, treeConfig,
      oopCombos, ipCombos,
      config.samplesPerBucket,
      config.riverSamplesPerTurn,
      config.minProbDivergence,
    );

    const outputPath = join(config.outputDir, `flop_${String(task.boardId).padStart(4, '0')}.jsonl`);
    writeSamples(outputPath, samples);

    totalSamples += samples.length;
    processedFlops++;
  }

  return { totalSamples, processedFlops };
}

async function main() {
  const config = parseArgs();

  console.log('╔═══════════════════════════════════════════╗');
  console.log('║   CFR → Training Data Generator          ║');
  console.log('╚═══════════════════════════════════════════╝');
  console.log(`  CFR dir:   ${config.cfrDir}`);
  console.log(`  Output:    ${config.outputDir}`);
  console.log(`  Config:    ${config.configName}`);
  console.log(`  Samples/bucket: ${config.samplesPerBucket}`);
  console.log(`  River samples/turn: ${config.riverSamplesPerTurn}`);
  console.log(`  Min divergence: ${config.minProbDivergence}`);
  console.log(`  Workers:   ${config.workers}`);
  console.log();

  // Discover solved flops
  let flops = discoverSolvedFlops(config.cfrDir);
  if (flops.length === 0) {
    console.error('No solved flops found in:', config.cfrDir);
    process.exit(1);
  }
  if (config.maxFlops < flops.length) {
    console.log(`Found ${flops.length} solved flops, limiting to ${config.maxFlops}`);
    flops = flops.slice(0, config.maxFlops);
  } else {
    console.log(`Found ${flops.length} solved flops`);
  }

  // Create output directory
  mkdirSync(config.outputDir, { recursive: true });

  const startTime = Date.now();

  // Build worker tasks
  const tasks: WorkerTask[] = flops.map(f => ({
    metaPath: f.metaPath,
    jsonlPath: f.jsonlPath,
    boardId: f.boardId,
  }));

  let result: { totalSamples: number; processedFlops: number };

  if (config.workers > 1) {
    const chartsPath = resolve(process.cwd(), 'data/preflop_charts.json');
    result = await runWithWorkers(tasks, {
      configName: config.configName,
      samplesPerBucket: config.samplesPerBucket,
      riverSamplesPerTurn: config.riverSamplesPerTurn,
      minProbDivergence: config.minProbDivergence,
      outputDir: config.outputDir,
      chartsPath,
    }, config.workers);
  } else {
    result = await runSingleThreaded(tasks, config);
  }

  const elapsed = (Date.now() - startTime) / 1000;

  // Write manifest
  const manifest = {
    config: config.configName,
    flopIds: flops.map(f => f.boardId),
    totalSamples: result.totalSamples,
    processedFlops: result.processedFlops,
    streets: ['FLOP', 'TURN', 'RIVER'],
    samplesPerBucket: config.samplesPerBucket,
    riverSamplesPerTurn: config.riverSamplesPerTurn,
    minProbDivergence: config.minProbDivergence,
    generatedAt: new Date().toISOString(),
  };
  writeFileSync(join(config.outputDir, 'manifest.json'), JSON.stringify(manifest, null, 2));

  console.log();
  console.log('════════════════════════════════════════════');
  console.log(`  Done! ${result.processedFlops} flops → ${result.totalSamples.toLocaleString()} training samples`);
  console.log(`  Time: ${elapsed.toFixed(1)}s`);
  console.log(`  Output: ${config.outputDir}`);
  console.log('════════════════════════════════════════════');
}

if (!IS_WORKER && IS_MAIN_SCRIPT) {
  main().catch(err => {
    console.error('Fatal error:', err);
    process.exit(1);
  });
}
