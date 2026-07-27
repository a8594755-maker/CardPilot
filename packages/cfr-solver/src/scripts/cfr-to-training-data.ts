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

import {
  readFileSync,
  writeFileSync,
  appendFileSync,
  readdirSync,
  existsSync,
  mkdirSync,
} from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { join, resolve } from 'node:path';
import { fork, type ChildProcess } from 'node:child_process';
import { cpus } from 'node:os';
import { fileURLToPath } from 'node:url';

import { indexToCard } from '../abstraction/card-index.js';
import { evaluateHandBoard, evaluateBestHand, HandRank } from '@cardpilot/poker-evaluator';
import {
  loadHUSRPRanges,
  getWeightedRangeCombos,
  type WeightedCombo,
} from '../integration/preflop-ranges.js';
import { computeEquityBuckets, comboKey } from '../engine/cfr-engine.js';
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

interface V55CompactSample {
  schema: 'cfr.v55.compact.v1';
  boardId: number;
  player: 0 | 1;
  street: Street;
  historyKey: string;
  bucket: string;
  holeCards: [number, number];
  boardCards: number[];
  state: GameState;
  events: Path1HistoryEvent[];
  legalMask: number[];
  target: number[];
  h: string;
  s: string;
}

type OutputSample = TrainingSample | V55CompactSample;
type OutputFormat = 'fast-v2' | 'v55-compact';

export interface GameState {
  pot: number;
  stacks: [number, number];
  facingBet: number;
  currentPlayer: 0 | 1;
  street: Street;
  toCall: number;
  isFirstAction: boolean;
  raiseCount: number;
}

export interface Path1HistoryEvent {
  street: Street;
  player: 0 | 1;
  actionType: 'CHECK' | 'CALL' | 'FOLD' | 'BET' | 'RAISE' | 'ALLIN';
  additionalAmount: number | null;
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
  skipFlops: number;
  maxFlops: number;
  selectionSeed: number;
  outputFormat: OutputFormat;
  outputSampleRate: number;
  outputSampleRates: Record<Street, number>;
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
export function replayHistoryTrace(
  historyKey: string,
  config: TreeConfig,
): {
  state: GameState;
  events: Path1HistoryEvent[];
} {
  let pot = config.startingPot;
  let stacks: [number, number] = [config.effectiveStack, config.effectiveStack];
  let currentPlayer: 0 | 1 = 0; // OOP acts first
  let facingBet = 0;
  let street: Street = 'FLOP';
  let isFirstAction = true;
  let raiseCount = 0;
  const events: Path1HistoryEvent[] = [];

  for (const char of historyKey) {
    if (char === '/') {
      // Street separator — advance
      street = nextStreet(street);
      currentPlayer = 0; // OOP acts first each street
      facingBet = 0;
      isFirstAction = true;
      raiseCount = 0;
      continue;
    }

    const p = currentPlayer;
    const opp = (1 - p) as 0 | 1;

    switch (char) {
      case 'x': // check
        events.push({ street, player: p, actionType: 'CHECK', additionalAmount: null });
        currentPlayer = opp;
        isFirstAction = false;
        // facingBet stays 0 for checks
        break;

      case 'c': {
        // call
        const callAmt = Math.min(facingBet, stacks[p]);
        events.push({ street, player: p, actionType: 'CALL', additionalAmount: callAmt });
        stacks = [stacks[0], stacks[1]] as [number, number];
        stacks[p] -= callAmt;
        pot += callAmt;
        currentPlayer = opp;
        facingBet = 0;
        break;
      }

      case 'f': // fold
        events.push({ street, player: p, actionType: 'FOLD', additionalAmount: null });
        // Terminal — shouldn't appear in non-terminal histories
        break;

      case 'A': {
        // all-in
        const isRaise = facingBet > 0;
        const allInAmt = stacks[p];
        events.push({ street, player: p, actionType: 'ALLIN', additionalAmount: allInAmt });
        stacks = [stacks[0], stacks[1]] as [number, number];
        stacks[p] = 0;
        pot += allInAmt;
        facingBet = allInAmt;
        if (isRaise) raiseCount++;
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
        const isRaise = facingBet > 0;
        if (isRaise) {
          // Raise
          betAmount = calcRaiseAmount(pot, facingBet, fraction, stacks[p]);
        } else {
          // Bet
          betAmount = calcBetAmount(pot, fraction, stacks[p]);
        }

        events.push({
          street,
          player: p,
          actionType: isRaise ? 'RAISE' : 'BET',
          additionalAmount: betAmount,
        });

        stacks = [stacks[0], stacks[1]] as [number, number];
        stacks[p] -= betAmount;
        pot += betAmount;
        facingBet = betAmount;
        if (isRaise) raiseCount++;
        currentPlayer = opp;
        isFirstAction = false;
        break;
      }
    }
  }

  return {
    state: {
      pot,
      stacks,
      facingBet,
      currentPlayer,
      street,
      toCall: facingBet,
      isFirstAction,
      raiseCount,
    },
    events,
  };
}

export function replayHistory(historyKey: string, config: TreeConfig): GameState {
  return replayHistoryTrace(historyKey, config).state;
}

function nextStreet(street: Street): Street {
  switch (street) {
    case 'FLOP':
      return 'TURN';
    case 'TURN':
      return 'RIVER';
    case 'RIVER':
      return 'RIVER'; // shouldn't happen
  }
}

function getBetSizesForStreet(config: TreeConfig, street: Street): number[] {
  switch (street) {
    case 'FLOP':
      return config.betSizes.flop;
    case 'TURN':
      return config.betSizes.turn;
    case 'RIVER':
      return config.betSizes.river;
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
    const opponentStack = state.stacks[1 - state.currentPlayer];
    if (
      opponentStack > 0 &&
      state.raiseCount < config.raiseCapPerStreet &&
      state.stacks[state.currentPlayer] > state.facingBet
    ) {
      const betSizes = getBetSizesForStreet(config, state.street);
      for (let i = 0; i < betSizes.length; i++) {
        const amount = calcRaiseAmount(
          state.pot,
          state.facingBet,
          betSizes[i],
          state.stacks[state.currentPlayer],
        );
        if (amount >= state.stacks[state.currentPlayer]) {
          actions.push('allin');
          break;
        }
        actions.push(`raise_${i}`);
      }
      if (!actions.includes('allin')) actions.push('allin');
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

export const V55_RAISE_FRACTIONS = [0.33, 0.5, 0.67, 0.75, 1.0, 1.5] as const;

function closestV55RaiseSlot(potFraction: number): number {
  let best = 0;
  let distance = Number.POSITIVE_INFINITY;
  for (let i = 0; i < V55_RAISE_FRACTIONS.length; i++) {
    const candidate = Math.abs(potFraction - V55_RAISE_FRACTIONS[i]);
    if (candidate < distance) {
      best = i;
      distance = candidate;
    }
  }
  return best + 2;
}

/**
 * Map one exact CFR node strategy to AlphaHoldem v55's 9 action slots.
 * This preserves probability mass but does not by itself prove that a separately
 * reconstructed v55 state has the same legal mask; that is an H3 bridge gate.
 */
export function mapCfrProbsToV55Actions(
  historyKey: string,
  actions: string[],
  probs: number[],
  config: TreeConfig,
): number[] {
  if (actions.length !== probs.length) throw new Error('CFR action/probability length mismatch');
  const state = replayHistory(historyKey, config);
  const target = Array<number>(9).fill(0);
  const sizes = getBetSizesForStreet(config, state.street);
  for (let i = 0; i < actions.length; i++) {
    const action = actions[i];
    const probability = probs[i] ?? 0;
    if (action === 'fold') target[0] += probability;
    else if (action === 'check' || action === 'call') target[1] += probability;
    else if (action === 'allin') target[8] += probability;
    else {
      const match = action.match(/^(bet|raise)_(\d+)$/);
      if (!match) throw new Error(`unsupported CFR action: ${action}`);
      const size = sizes[Number.parseInt(match[2], 10)];
      const amount =
        match[1] === 'bet'
          ? calcBetAmount(state.pot, size, state.stacks[state.currentPlayer])
          : calcRaiseAmount(state.pot, state.facingBet, size, state.stacks[state.currentPlayer]);
      target[closestV55RaiseSlot(amount / Math.max(state.pot, 1e-9))] += probability;
    }
  }
  return target;
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
      sz = sizingWeights.map((w) => w / total) as [number, number, number, number, number];
    }
  }

  return { l, sz };
}

/**
 * Map a pot fraction to the closest V2 sizing index.
 * V2 sizing buckets: [0.33, 0.50, 0.66, 1.00, allIn]
 */
function fractionToSizingIndex(fraction: number): number {
  if (fraction <= 0.4) return 0; // third (33%)
  if (fraction <= 0.58) return 1; // half (50%)
  if (fraction <= 0.83) return 2; // twoThirds (66%)
  return 3; // pot (100%)
  // allIn (index 4) is handled separately
}

// ══════════════════════════════════════════════
//   FEATURE ENCODING (CFR-specific adapter)
// ══════════════════════════════════════════════

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
const SUIT_INDEX: Record<string, number> = { s: 0, h: 1, d: 2, c: 3 };

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
      features.push(
        r,
        sIdx === 0 ? 1 : 0,
        sIdx === 1 ? 1 : 0,
        sIdx === 2 ? 1 : 0,
        sIdx === 3 ? 1 : 0,
      );
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
  const spr = gameState.pot > 0 ? Math.min(gameState.stacks[player] / gameState.pot, 20) / 20 : 1;
  const potOdds =
    gameState.pot + gameState.toCall > 0
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
  const lastBetFrac =
    histAgg.lastBetAmount > 0 && gameState.pot > 0
      ? Math.min(histAgg.lastBetAmount / gameState.pot, 2.0) / 2.0
      : 0;
  features.push(lastBetFrac);
  // [53] allInPressure
  features.push(histAgg.hasAllIn ? 1 : 0);

  return features;
}

// ── V3 equity/draw/blocker helpers (card-index based) ──

/**
 * Compute hand strength (equity vs uniform random) on current board.
 * Exhaustive enumeration of all valid opponent combos.
 */
function computeHandStrengthIdx(hero: [number, number], board: number[]): number {
  if (board.length < 3) return 0.5;
  const dead = new Set([hero[0], hero[1], ...board]);
  const heroValue = evaluateHandBoard(hero[0], hero[1], board);

  let wins = 0,
    ties = 0,
    total = 0;
  for (let c1 = 0; c1 < 52; c1++) {
    if (dead.has(c1)) continue;
    for (let c2 = c1 + 1; c2 < 52; c2++) {
      if (dead.has(c2)) continue;
      const oppValue = evaluateHandBoard(c1, c2, board);
      if (heroValue > oppValue) wins++;
      else if (heroValue === oppValue) ties++;
      total++;
    }
  }
  return total > 0 ? (wins + ties * 0.5) / total : 0.5;
}

/** rank index 0=2..12=A from card index */
function rankOf(cardIdx: number): number {
  return cardIdx >> 2;
}

/** suit index 0=c,1=d,2=h,3=s from card index */
function suitOf(cardIdx: number): number {
  return cardIdx & 3;
}

/**
 * Detect flush draw: hero + board has exactly 4 of same suit, hero contributes.
 */
function hasFlushDrawIdx(hero: [number, number], board: number[]): boolean {
  const suitCounts = [0, 0, 0, 0];
  for (const c of [hero[0], hero[1], ...board]) suitCounts[suitOf(c)]++;
  for (let s = 0; s < 4; s++) {
    if (suitCounts[s] === 4 && (suitOf(hero[0]) === s || suitOf(hero[1]) === s)) return true;
  }
  return false;
}

/**
 * Detect straight draw type. Returns 0=none, 0.5=gutshot, 1.0=OESD.
 */
function detectStraightDrawIdx(hero: [number, number], board: number[]): number {
  const rankSet = new Set<number>();
  const heroRanks = new Set<number>();
  for (const c of [hero[0], hero[1]]) {
    const r = rankOf(c);
    rankSet.add(r);
    heroRanks.add(r);
  }
  for (const c of board) rankSet.add(rankOf(c));
  // Ace-low
  if (rankSet.has(12)) rankSet.add(-1);
  if (heroRanks.has(12)) heroRanks.add(-1);

  const ranks = [...rankSet].sort((a, b) => a - b);

  // Check for made straight (5 consecutive)
  for (let i = 0; i <= ranks.length - 5; i++) {
    if (ranks[i + 4] - ranks[i] === 4) return 0;
  }

  let bestDraw = 0;
  for (let low = -1; low <= 8; low++) {
    const high = low + 4;
    let count = 0;
    let hasHero = false;
    for (const r of ranks) {
      if (r >= low && r <= high) {
        count++;
        if (heroRanks.has(r)) hasHero = true;
      }
    }
    if (count === 4 && hasHero) {
      const missing: number[] = [];
      for (let r = low; r <= high; r++) {
        if (!rankSet.has(r)) missing.push(r);
      }
      if (missing.length === 1) {
        const m = missing[0];
        bestDraw = Math.max(bestDraw, m === low || m === high ? 1.0 : 0.5);
      }
    }
  }
  return bestDraw;
}

/**
 * V3 feature encoder for CFR training data.
 * Extends encodeCfrFeatures with 11 equity/draw/blocker features.
 * Returns a 65-dimensional vector.
 */
export function encodeCfrFeaturesV3(
  holeCards: [number, number],
  boardCards: number[],
  gameState: GameState,
  player: 0 | 1,
  historyKey: string,
): number[] {
  const features = encodeCfrFeatures(holeCards, boardCards, gameState, player, historyKey);

  // ── V3 features (indices 54-64) ──

  // [54] handStrength — equity vs random
  features.push(boardCards.length >= 3 ? computeHandStrengthIdx(holeCards, boardCards) : 0.5);

  // [55] flushDraw — 4 to flush, not yet made
  features.push(boardCards.length >= 3 && hasFlushDrawIdx(holeCards, boardCards) ? 1 : 0);

  // [56] straightDraw — 0=none, 0.5=gutshot, 1.0=OESD
  features.push(boardCards.length >= 3 ? detectStraightDrawIdx(holeCards, boardCards) : 0);

  // [57] overcards — hero ranks above all board ranks / 2
  let maxBoardRank = 0;
  for (const c of boardCards) maxBoardRank = Math.max(maxBoardRank, rankOf(c));
  let overCount = 0;
  if (boardCards.length > 0) {
    if (rankOf(holeCards[0]) > maxBoardRank) overCount++;
    if (rankOf(holeCards[1]) > maxBoardRank) overCount++;
  }
  features.push(overCount / 2);

  // [58] nutFlushBlocker — holds ace of dominant board suit
  const boardSuitCounts = [0, 0, 0, 0];
  for (const c of boardCards) boardSuitCounts[suitOf(c)]++;
  let bestBoardSuit = 0;
  let bestBoardSuitCount = 0;
  for (let s = 0; s < 4; s++) {
    if (boardSuitCounts[s] > bestBoardSuitCount) {
      bestBoardSuitCount = boardSuitCounts[s];
      bestBoardSuit = s;
    }
  }
  const hasNutBlock =
    bestBoardSuitCount >= 2 &&
    ((rankOf(holeCards[0]) === 12 && suitOf(holeCards[0]) === bestBoardSuit) ||
      (rankOf(holeCards[1]) === 12 && suitOf(holeCards[1]) === bestBoardSuit));
  features.push(hasNutBlock ? 1 : 0);

  // [59] pairBlocker — holds card matching highest board rank
  const hasPairBlock =
    boardCards.length > 0 &&
    (rankOf(holeCards[0]) === maxBoardRank || rankOf(holeCards[1]) === maxBoardRank);
  features.push(hasPairBlock ? 1 : 0);

  // [60] boardPaired — board has repeated rank
  const boardRanks = new Set(boardCards.map(rankOf));
  features.push(boardRanks.size < boardCards.length ? 1 : 0);

  // [61] boardFlushDraw — 3+ board cards same suit
  features.push(boardSuitCounts.some((n) => n >= 3) ? 1 : 0);

  // [62] boardConnected — 3+ board ranks within span of 5
  let boardConn = false;
  if (boardRanks.size >= 3) {
    const sorted = [...boardRanks].sort((a, b) => a - b);
    for (let i = 0; i <= sorted.length - 3; i++) {
      if (sorted[i + 2] - sorted[i] <= 4) {
        boardConn = true;
        break;
      }
    }
  }
  features.push(boardConn ? 1 : 0);

  // [63] handRank — made hand category / 10
  if (boardCards.length >= 3) {
    try {
      const RANK_CHARS = '23456789TJQKA';
      const SUIT_CHARS = 'cdhs';
      const toCard = (idx: number): string => RANK_CHARS[idx >> 2] + SUIT_CHARS[idx & 3];
      const allCards = [toCard(holeCards[0]), toCard(holeCards[1]), ...boardCards.map(toCard)];
      const eval_ = evaluateBestHand(allCards);
      features.push(eval_.rank / 10);
    } catch {
      features.push(0);
    }
  } else {
    features.push(0);
  }

  // [64] comboDrawPotential — flush draw AND straight draw
  const fd = features[55];
  const sd = features[56];
  features.push(fd > 0 && sd > 0 ? 1 : 0);

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
  const preflopRaises = 0;
  let raisesOnStreet = 0;
  let totalRaises = 0;
  const lastBetAmount = 0;
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
  selectionSeed = 0,
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
    buildTurnBuckets(
      oopRange,
      turnBoard,
      turnDead,
      bucketCount,
      oopFlopBuckets,
      turnCard,
      oopTurnMap,
    );
    buildTurnBuckets(ipRange, turnBoard, turnDead, bucketCount, ipFlopBuckets, turnCard, ipTurnMap);
  }

  // ── River bucket mapping (sampled) ──
  const oopRiverMap = new Map<
    string,
    Array<{ combo: [number, number]; turnCard: number; riverCard: number }>
  >();
  const ipRiverMap = new Map<
    string,
    Array<{ combo: [number, number]; turnCard: number; riverCard: number }>
  >();

  for (const turnCard of turnCards) {
    const turnDead = new Set([...deadCards, turnCard]);
    // Sample N river cards for this turn
    const riverCandidates: number[] = [];
    for (let c = 0; c < 52; c++) {
      if (!turnDead.has(c)) riverCandidates.push(c);
    }

    // Sample up to riverSamplesPerTurn river cards
    const riverCards = deterministicSampleN(
      riverCandidates,
      riverSamplesPerTurn,
      `${selectionSeed}|river|${flopCards.join(',')}|${turnCard}`,
    );

    for (const riverCard of riverCards) {
      const riverBoard = [...flopCards, turnCard, riverCard];
      const riverDead = new Set([...turnDead, riverCard]);

      buildRiverBuckets(
        oopRange,
        riverBoard,
        riverDead,
        bucketCount,
        oopFlopBuckets,
        turnCard,
        riverCard,
        oopRiverMap,
      );
      buildRiverBuckets(
        ipRange,
        riverBoard,
        riverDead,
        bucketCount,
        ipFlopBuckets,
        turnCard,
        riverCard,
        ipRiverMap,
      );
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

function fnv1a32(value: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let value = Math.imul(state ^ (state >>> 15), 1 | state);
    value = (value + Math.imul(value ^ (value >>> 7), 61 | value)) ^ value;
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

/** Stable partial Fisher-Yates sampling, independent of worker count/order. */
export function deterministicSampleN<T>(arr: T[], n: number, seedKey: string): T[] {
  if (arr.length <= n) return arr;
  const random = mulberry32(fnv1a32(seedKey));
  // Fisher-Yates partial shuffle
  const copy = [...arr];
  for (let i = 0; i < n; i++) {
    const j = i + Math.floor(random() * (copy.length - i));
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
  selectionSeed = 0,
  outputFormat: OutputFormat = 'fast-v2',
  outputSampleRate = 1,
  outputSampleRates?: Record<Street, number>,
  onBatch?: (samples: OutputSample[]) => void,
): { samples: OutputSample[]; count: number } {
  const startTime = Date.now();
  const { flopCards, boardId, bucketCount } = meta;

  // Step 1: Build bucket → combo reverse mapping
  const { oopMap, ipMap } = buildBucketComboMap(
    flopCards,
    oopRange,
    ipRange,
    bucketCount,
    riverSamplesPerTurn,
    selectionSeed,
  );

  const samples: OutputSample[] = [];
  let pending: OutputSample[] = [];
  let sampleCount = 0;
  const emit = (sample: OutputSample): void => {
    sampleCount++;
    if (!onBatch) {
      samples.push(sample);
      return;
    }
    pending.push(sample);
    if (pending.length >= 50_000) {
      onBatch(pending);
      pending = [];
    }
  };

  // Step 2: Process each info-set
  for (const [key, probs] of infoSets) {
    const parsed = parseInfoSetKey(key);
    const effectiveOutputSampleRate = outputSampleRates?.[parsed.street] ?? outputSampleRate;
    if (
      effectiveOutputSampleRate < 1 &&
      fnv1a32(`${selectionSeed}|output|${key}`) / 4294967296 >= effectiveOutputSampleRate
    ) {
      continue;
    }

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
    const combos = lookupCombos(bucketMap, parsed.street, parsed.bucketStr, flopCards);
    if (!combos || combos.length === 0) continue;

    // Sample N representative combos
    const sampled = deterministicSampleN(
      combos,
      samplesPerBucket,
      `${selectionSeed}|combo|${boardId}|${key}`,
    );

    for (const entry of sampled) {
      const holeCards = entry.combo;
      // Build the board for this street
      const boardCards = buildBoardForEntry(flopCards, parsed.street, entry);

      // Check for card conflicts
      if (boardCards.some((c) => c === holeCards[0] || c === holeCards[1])) continue;

      const sampleId =
        `flop${String(boardId).padStart(4, '0')}_${parsed.street[0]}` +
        `${parsed.player}_b${parsed.bucketStr}`;
      if (outputFormat === 'v55-compact') {
        const probabilitySum = probs.reduce((sum, value) => sum + value, 0);
        if (!(probabilitySum > 0) || !Number.isFinite(probabilitySum)) continue;
        const normalized = probs.map((value) => value / probabilitySum);
        const target = mapCfrProbsToV55Actions(parsed.historyKey, actions, normalized, config);
        const legalCounts = mapCfrProbsToV55Actions(
          parsed.historyKey,
          actions,
          actions.map(() => 1),
          config,
        );
        const trace = replayHistoryTrace(parsed.historyKey, config);
        emit({
          schema: 'cfr.v55.compact.v1',
          boardId,
          player: parsed.player,
          street: parsed.street,
          historyKey: parsed.historyKey,
          bucket: parsed.bucketStr,
          holeCards,
          boardCards,
          state: trace.state,
          events: trace.events,
          legalMask: legalCounts.map((value) => (value > 0 ? 1 : 0)),
          target,
          h: sampleId,
          s: parsed.street,
        });
      } else {
        // Encode features for the legacy fast-model trainer.
        const f = encodeCfrFeatures(
          holeCards,
          boardCards,
          gameState,
          parsed.player,
          parsed.historyKey,
        );
        const sample: TrainingSample = {
          f,
          l,
          h: sampleId,
          s: parsed.street,
        };
        if (sz) sample.sz = sz;
        emit(sample);
      }
    }
  }
  if (onBatch && pending.length > 0) onBatch(pending);

  const elapsed = Date.now() - startTime;
  console.log(`  Flop ${boardId}: ${sampleCount} samples in ${(elapsed / 1000).toFixed(1)}s`);

  return { samples, count: sampleCount };
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
      return combos.map((combo) => ({ combo }));
    }
    case 'TURN': {
      const entries = bucketMap.turn.get(bucketStr);
      if (!entries) return null;
      return entries.map((e) => ({ combo: e.combo, turnCard: e.turnCard }));
    }
    case 'RIVER': {
      const entries = bucketMap.river.get(bucketStr);
      if (!entries) return null;
      return entries.map((e) => ({ combo: e.combo, turnCard: e.turnCard, riverCard: e.riverCard }));
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
  const maxDev = Math.max(...probs.map((p) => Math.abs(p - uniform)));
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
  // Supports gzipped (.jsonl.gz, 200bb) and plain (.jsonl, legacy) outputs.
  // 200bb boards are ~1.5GB decompressed — too large for a single V8 string
  // (ERR_STRING_TOO_LONG), so parse line-by-line over the Buffer and only
  // stringify each (small) line.
  const raw = readFileSync(jsonlPath);
  const buf = jsonlPath.endsWith('.gz') ? gunzipSync(raw) : raw;
  const n = buf.length;
  let start = 0;
  const parseLine = (s: number, e: number): void => {
    if (e <= s) return;
    const trimmed = buf.toString('utf-8', s, e).trim();
    if (!trimmed) return;
    try {
      const entry = JSON.parse(trimmed);
      if (entry.key && entry.probs) map.set(entry.key, entry.probs);
    } catch {
      // skip malformed lines
    }
  };
  for (let i = 0; i < n; i++) {
    if (buf[i] === 0x0a) {
      parseLine(start, i);
      start = i + 1;
    }
  }
  parseLine(start, n);
  return map;
}

function discoverSolvedFlops(
  cfrDir: string,
): Array<{ boardId: number; metaPath: string; jsonlPath: string }> {
  const files = readdirSync(cfrDir).filter((f) => f.endsWith('.meta.json'));
  const result: Array<{ boardId: number; metaPath: string; jsonlPath: string }> = [];

  for (const metaFile of files) {
    // Prefer gzipped output (.jsonl.gz, 200bb); fall back to plain .jsonl (legacy).
    const gzPath = join(cfrDir, metaFile.replace('.meta.json', '.jsonl.gz'));
    const plainPath = join(cfrDir, metaFile.replace('.meta.json', '.jsonl'));
    const jsonlPath = existsSync(gzPath) ? gzPath : plainPath;
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

function validateSelectedFlopMetadata(
  flops: Array<{ boardId: number; metaPath: string }>,
  configName: TreeConfigName,
): { sourceConfigs: string[]; sourceStacks: string[] } {
  const sourceConfigs = new Set<string>();
  const sourceStacks = new Set<string>();
  const failures: string[] = [];

  for (const flop of flops) {
    let metadata: Record<string, unknown>;
    try {
      metadata = JSON.parse(readFileSync(flop.metaPath, 'utf-8')) as Record<string, unknown>;
    } catch (error) {
      failures.push(`board ${flop.boardId}: cannot parse ${flop.metaPath}: ${String(error)}`);
      continue;
    }
    const sourceConfig = String(metadata.config ?? '');
    const sourceStack = String(metadata.stack ?? '');
    if (sourceConfig) sourceConfigs.add(sourceConfig);
    if (sourceStack) sourceStacks.add(sourceStack);
    if (sourceConfig && sourceConfig !== configName) {
      failures.push(
        `board ${flop.boardId}: metadata config ${sourceConfig} != ` +
          `requested converter config ${configName}`,
      );
    }
    if (metadata.boardId !== undefined && Number(metadata.boardId) !== flop.boardId) {
      failures.push(`board ${flop.boardId}: metadata boardId=${String(metadata.boardId)}`);
    }
  }

  if (failures.length > 0) {
    throw new Error(
      'CFR source metadata/config mismatch; refusing to reconstruct states:\n' +
        failures.slice(0, 20).join('\n') +
        (failures.length > 20 ? `\n... ${failures.length - 20} more` : ''),
    );
  }
  return {
    sourceConfigs: [...sourceConfigs].sort(),
    sourceStacks: [...sourceStacks].sort(),
  };
}

function appendSampleBatch(outputPath: string, samples: OutputSample[]): void {
  const chunk = samples.map((sample) => JSON.stringify(sample)).join('\n') + '\n';
  appendFileSync(outputPath, chunk, 'utf-8');
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
  selectionSeed: number;
  outputFormat: OutputFormat;
  outputSampleRate: number;
  outputSampleRates: Record<Street, number>;
}

const IS_WORKER = process.argv.includes('--worker-mode');
const IS_MAIN_SCRIPT =
  process.argv[1] && resolve(process.argv[1]).replace(/\\/g, '/').includes('cfr-to-training-data');

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

      const outputPath = join(
        config.outputDir,
        `flop_${String(task.boardId).padStart(4, '0')}.jsonl`,
      );
      writeFileSync(outputPath, '', 'utf-8');
      const result = processFlop(
        meta,
        infoSets,
        treeConfig,
        oopCombos,
        ipCombos,
        config.samplesPerBucket,
        config.riverSamplesPerTurn,
        config.minProbDivergence,
        config.selectionSeed,
        config.outputFormat,
        config.outputSampleRate,
        config.outputSampleRates,
        (batch) => appendSampleBatch(outputPath, batch),
      );

      process.send!({ boardId: task.boardId, samples: result.count, ok: true });
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
  let skipFlops = 0;
  let maxFlops = Infinity;
  let selectionSeed = 0;
  let outputFormat: OutputFormat = 'fast-v2';
  let outputSampleRate = 1;
  const outputSampleRates: Record<Street, number> = {
    FLOP: 1,
    TURN: 1,
    RIVER: 1,
  };

  const parseOutputRate = (raw: string, flag: string): number => {
    const rate = Number.parseFloat(raw);
    if (!(rate > 0 && rate <= 1)) {
      throw new Error(`invalid ${flag}: ${rate}`);
    }
    return rate;
  };

  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--cfr-dir' && argv[i + 1]) cfrDir = argv[++i];
    if (argv[i] === '--output' && argv[i + 1]) outputDir = argv[++i];
    if (argv[i] === '--config' && argv[i + 1]) configName = argv[++i] as TreeConfigName;
    if (argv[i] === '--samples-per-bucket' && argv[i + 1])
      samplesPerBucket = parseInt(argv[++i], 10);
    if (argv[i] === '--workers' && argv[i + 1]) workers = parseInt(argv[++i], 10);
    if (argv[i] === '--river-samples' && argv[i + 1]) riverSamplesPerTurn = parseInt(argv[++i], 10);
    if (argv[i] === '--min-divergence' && argv[i + 1]) minProbDivergence = parseFloat(argv[++i]);
    if (argv[i] === '--skip-flops' && argv[i + 1]) skipFlops = parseInt(argv[++i], 10);
    if (argv[i] === '--max-flops' && argv[i + 1]) maxFlops = parseInt(argv[++i], 10);
    if (argv[i] === '--selection-seed' && argv[i + 1]) selectionSeed = parseInt(argv[++i], 10);
    if (argv[i] === '--output-format' && argv[i + 1]) {
      const value = argv[++i];
      if (value !== 'fast-v2' && value !== 'v55-compact') {
        throw new Error(`invalid --output-format: ${value}`);
      }
      outputFormat = value;
    }
    if (argv[i] === '--output-sample-rate' && argv[i + 1]) {
      outputSampleRate = parseOutputRate(argv[++i], '--output-sample-rate');
      outputSampleRates.FLOP = outputSampleRate;
      outputSampleRates.TURN = outputSampleRate;
      outputSampleRates.RIVER = outputSampleRate;
    }
    if (argv[i] === '--flop-output-sample-rate' && argv[i + 1]) {
      outputSampleRates.FLOP = parseOutputRate(argv[++i], '--flop-output-sample-rate');
    }
    if (argv[i] === '--turn-output-sample-rate' && argv[i + 1]) {
      outputSampleRates.TURN = parseOutputRate(argv[++i], '--turn-output-sample-rate');
    }
    if (argv[i] === '--river-output-sample-rate' && argv[i + 1]) {
      outputSampleRates.RIVER = parseOutputRate(argv[++i], '--river-output-sample-rate');
    }
  }

  if (!cfrDir) cfrDir = resolve(process.cwd(), 'data/cfr/pipeline_hu_srp_50bb');
  if (!outputDir) outputDir = resolve(process.cwd(), 'data/training/cfr_srp');

  return {
    cfrDir,
    outputDir,
    configName,
    samplesPerBucket,
    workers,
    riverSamplesPerTurn,
    minProbDivergence,
    skipFlops,
    maxFlops,
    selectionSeed,
    outputFormat,
    outputSampleRate,
    outputSampleRates,
  };
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

      child.on(
        'message',
        (msg: { boardId: number; samples: number; ok: boolean; error?: string }) => {
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
        },
      );

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

    const outputPath = join(
      config.outputDir,
      `flop_${String(task.boardId).padStart(4, '0')}.jsonl`,
    );
    writeFileSync(outputPath, '', 'utf-8');
    const result = processFlop(
      meta,
      infoSets,
      treeConfig,
      oopCombos,
      ipCombos,
      config.samplesPerBucket,
      config.riverSamplesPerTurn,
      config.minProbDivergence,
      config.selectionSeed,
      config.outputFormat,
      config.outputSampleRate,
      config.outputSampleRates,
      (batch) => appendSampleBatch(outputPath, batch),
    );

    totalSamples += result.count;
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
  console.log(`  Skip flops: ${config.skipFlops}`);
  console.log(`  Selection seed: ${config.selectionSeed}`);
  console.log(`  Output format: ${config.outputFormat}`);
  console.log(`  Output sample rate: ${config.outputSampleRate}`);
  console.log(
    `  Output rates by street: flop=${config.outputSampleRates.FLOP} ` +
      `turn=${config.outputSampleRates.TURN} river=${config.outputSampleRates.RIVER}`,
  );
  console.log();

  // Discover solved flops
  let flops = discoverSolvedFlops(config.cfrDir);
  if (flops.length === 0) {
    console.error('No solved flops found in:', config.cfrDir);
    process.exit(1);
  }
  const discoveredFlopCount = flops.length;
  if (config.skipFlops > 0 || config.maxFlops < flops.length) {
    flops = flops.slice(
      Math.max(0, config.skipFlops),
      Number.isFinite(config.maxFlops)
        ? Math.max(0, config.skipFlops) + config.maxFlops
        : undefined,
    );
    console.log(
      `Found ${discoveredFlopCount} solved flops, selecting ${flops.length} ` +
        `after skipping ${config.skipFlops}`,
    );
  } else {
    console.log(`Found ${flops.length} solved flops`);
  }
  if (flops.length === 0) {
    console.error('No solved flops remain after skip/limit selection');
    process.exit(1);
  }
  const sourceMetadata = validateSelectedFlopMetadata(flops, config.configName);
  console.log(
    `  Source metadata: configs=${sourceMetadata.sourceConfigs.join(',') || 'unknown'} ` +
      `stacks=${sourceMetadata.sourceStacks.join(',') || 'unknown'}`,
  );

  // Create output directory
  mkdirSync(config.outputDir, { recursive: true });

  const startTime = Date.now();

  // Build worker tasks
  const tasks: WorkerTask[] = flops.map((f) => ({
    metaPath: f.metaPath,
    jsonlPath: f.jsonlPath,
    boardId: f.boardId,
  }));

  let result: { totalSamples: number; processedFlops: number };

  if (config.workers > 1) {
    const chartsPath = resolve(process.cwd(), 'data/preflop_charts.json');
    result = await runWithWorkers(
      tasks,
      {
        configName: config.configName,
        samplesPerBucket: config.samplesPerBucket,
        riverSamplesPerTurn: config.riverSamplesPerTurn,
        minProbDivergence: config.minProbDivergence,
        outputDir: config.outputDir,
        chartsPath,
        selectionSeed: config.selectionSeed,
        outputFormat: config.outputFormat,
        outputSampleRate: config.outputSampleRate,
        outputSampleRates: config.outputSampleRates,
      },
      config.workers,
    );
  } else {
    result = await runSingleThreaded(tasks, config);
  }

  const elapsed = (Date.now() - startTime) / 1000;

  // Write manifest
  const manifest = {
    config: config.configName,
    sourceConfigs: sourceMetadata.sourceConfigs,
    sourceStacks: sourceMetadata.sourceStacks,
    flopIds: flops.map((f) => f.boardId),
    skipFlops: config.skipFlops,
    totalSamples: result.totalSamples,
    processedFlops: result.processedFlops,
    streets: ['FLOP', 'TURN', 'RIVER'],
    samplesPerBucket: config.samplesPerBucket,
    riverSamplesPerTurn: config.riverSamplesPerTurn,
    minProbDivergence: config.minProbDivergence,
    selectionSeed: config.selectionSeed,
    outputFormat: config.outputFormat,
    outputSampleRate: config.outputSampleRate,
    outputSampleRates: config.outputSampleRates,
    generatedAt: new Date().toISOString(),
  };
  writeFileSync(join(config.outputDir, 'manifest.json'), JSON.stringify(manifest, null, 2));

  console.log();
  console.log('════════════════════════════════════════════');
  console.log(
    `  Done! ${result.processedFlops} flops → ${result.totalSamples.toLocaleString()} training samples`,
  );
  console.log(`  Time: ${elapsed.toFixed(1)}s`);
  console.log(`  Output: ${config.outputDir}`);
  console.log('════════════════════════════════════════════');
}

if (!IS_WORKER && IS_MAIN_SCRIPT) {
  main().catch((err) => {
    console.error('Fatal error:', err);
    process.exit(1);
  });
}
