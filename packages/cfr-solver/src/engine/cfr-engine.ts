// CFR+ with Chance-Sampled MCCFR (V2)
//
// Each iteration:
// 1. Sample a hand matchup (oopHand, ipHand) from preflop ranges (weighted by frequency)
// 2. Sample turn card + river card for the runout
// 3. Compute per-street hand buckets for each player (dynamic re-bucketing)
// 4. Traverse the action tree:
//    - At traverser's nodes: explore ALL actions (full traversal)
//    - At opponent's nodes: explore ALL actions weighted by strategy
// 5. Update regrets (CFR+: floor at 0) and accumulate strategy sums
//
// V2 improvements over V1:
// - Weighted sampling using preflop frequencies
// - Dynamic per-street bucketing (flop precomputed, turn/river recomputed per runout)
// - V2 info-set key format with per-street bucket IDs

import type { GameNode, ActionNode, Player, Street } from '../types.js';
import { InfoSetStore } from './info-set-store.js';
import { indexToCard } from '../abstraction/card-index.js';
import { evaluateBestHand, compareHands } from '@cardpilot/poker-evaluator';
import type { WeightedCombo } from '../integration/preflop-ranges.js';

// ---------- Public API ----------

export interface SolveParams {
  root: ActionNode;
  store: InfoSetStore;
  boardId: number;
  flopCards: [number, number, number]; // 3 card indices
  oopRange: WeightedCombo[];           // weighted combos in OOP range
  ipRange: WeightedCombo[];            // weighted combos in IP range
  iterations: number;
  bucketCount: number;                 // buckets per street (e.g. 50)
  onProgress?: (iter: number, elapsed: number, exploitEst: number) => void;
}

/**
 * Run MCCFR chance-sampling solver (V2).
 */
export function solveCFR(params: SolveParams): void {
  const {
    root, store, boardId, flopCards,
    oopRange, ipRange,
    iterations, bucketCount, onProgress,
  } = params;

  // Precompute flop equity buckets (these don't change across iterations)
  const deadFlop = new Set(flopCards as number[]);
  const flopBucketsOOP = computeEquityBuckets(oopRange, flopCards, bucketCount, deadFlop);
  const flopBucketsIP = computeEquityBuckets(ipRange, flopCards, bucketCount, deadFlop);

  // Precompute cumulative weight arrays for weighted sampling
  const oopCumWeights = buildCumulativeWeights(oopRange);
  const ipCumWeights = buildCumulativeWeights(ipRange);

  // Build remaining deck (exclude flop cards)
  const remainDeck: number[] = [];
  for (let c = 0; c < 52; c++) {
    if (!deadFlop.has(c)) remainDeck.push(c);
  }

  // Bucket cache for dynamic per-street bucketing
  // Key: `${comboKey}-${boardCards}`, Value: bucket number
  const turnBucketCache = new Map<string, number>();
  const riverBucketCache = new Map<string, number>();

  const startTime = Date.now();
  let rngState = Date.now() & 0x7fffffff;

  for (let iter = 0; iter < iterations; iter++) {
    // 1. Sample OOP hand (weighted by preflop frequency)
    rngState = nextRng(rngState);
    const oopIdx = weightedSample(oopCumWeights, rngState);
    const oopHand = oopRange[oopIdx].combo;

    // 2. Sample IP hand (must not conflict with OOP hand, weighted)
    rngState = nextRng(rngState);
    const ipIdx = weightedSampleFiltered(ipRange, ipCumWeights, oopHand, rngState);
    if (ipIdx < 0) continue;
    const ipHand = ipRange[ipIdx].combo;

    // 3. Sample turn + river cards (not conflicting with flop or hands)
    const usedCards = new Set([
      ...flopCards, oopHand[0], oopHand[1], ipHand[0], ipHand[1],
    ]);
    const available = remainDeck.filter(c => !usedCards.has(c));

    rngState = nextRng(rngState);
    const turnIdx = rngState % available.length;
    const turnCard = available[turnIdx];
    // Remove turn from available for river
    const availForRiver = available.filter((_, i) => i !== turnIdx);
    rngState = nextRng(rngState);
    const riverCard = availForRiver[rngState % availForRiver.length];

    // 4. Compute per-street buckets (V2: dynamic re-bucketing)
    const riverBoard: number[] = [...flopCards, turnCard, riverCard];

    // Flop: use precomputed buckets
    const oopFlopBucket = flopBucketsOOP.get(comboKey(oopHand));
    const ipFlopBucket = flopBucketsIP.get(comboKey(ipHand));
    if (oopFlopBucket === undefined || ipFlopBucket === undefined) continue;

    // Turn: 6-card evaluation with dynamic bucketing
    const turnBoard = [...flopCards, turnCard];
    const oopTurnBucket = computeSingleBucketCached(
      oopHand, turnBoard, oopRange, bucketCount, turnBucketCache,
    );
    const ipTurnBucket = computeSingleBucketCached(
      ipHand, turnBoard, ipRange, bucketCount, turnBucketCache,
    );

    // River: 7-card evaluation with dynamic bucketing
    const oopRiverBucket = computeSingleBucketCached(
      oopHand, riverBoard, oopRange, bucketCount, riverBucketCache,
    );
    const ipRiverBucket = computeSingleBucketCached(
      ipHand, riverBoard, ipRange, bucketCount, riverBucketCache,
    );

    const buckets: StreetBuckets = {
      FLOP: [oopFlopBucket, ipFlopBucket],
      TURN: [oopTurnBucket, ipTurnBucket],
      RIVER: [oopRiverBucket, ipRiverBucket],
    };

    // 5. Precompute showdown result for this matchup
    const showdownResult = computeShowdown(oopHand, ipHand, riverBoard);

    // 6. Traverse for each player as traverser
    cfrTraverse(root, store, boardId, buckets, showdownResult, 0, 1.0, 1.0);
    cfrTraverse(root, store, boardId, buckets, showdownResult, 1, 1.0, 1.0);

    if (onProgress && (iter + 1) % 5000 === 0) {
      onProgress(iter + 1, Date.now() - startTime, 0);
    }
  }
}

// ---------- Internal ----------

type StreetBuckets = Record<Street, [number, number]>;

function cfrTraverse(
  node: GameNode,
  store: InfoSetStore,
  boardId: number,
  buckets: StreetBuckets,
  showdownResult: number, // +1 OOP wins, -1 IP wins, 0 tie
  traverser: Player,
  oopReach: number,
  ipReach: number,
): number {
  if (node.type === 'terminal') {
    return terminalValue(node, showdownResult, traverser);
  }

  const act = node;
  const player = act.player;
  const numActions = act.actions.length;
  const infoKey = buildInfoKey(act.street, boardId, player, act.historyKey, buckets);

  const strategy = store.getCurrentStrategy(infoKey, numActions);
  const actionValues = new Float32Array(numActions);
  let nodeValue = 0;

  for (let a = 0; a < numActions; a++) {
    const child = act.children.get(act.actions[a])!;

    const newOopReach = player === 0 ? oopReach * strategy[a] : oopReach;
    const newIpReach = player === 1 ? ipReach * strategy[a] : ipReach;

    actionValues[a] = cfrTraverse(
      child, store, boardId, buckets, showdownResult,
      traverser, newOopReach, newIpReach,
    );
    nodeValue += strategy[a] * actionValues[a];
  }

  // Update regrets and strategy sums only for traverser's info sets
  if (player === traverser) {
    const opponentReach = player === 0 ? ipReach : oopReach;
    const playerReach = player === 0 ? oopReach : ipReach;

    for (let a = 0; a < numActions; a++) {
      // CFR+ regret update: floor at 0
      const regret = actionValues[a] - nodeValue;
      store.updateRegret(infoKey, a, opponentReach * regret, numActions);
      // Accumulate strategy weight
      store.addStrategyWeight(infoKey, a, playerReach * strategy[a], numActions);
    }
  }

  return nodeValue;
}

function terminalValue(
  node: GameNode & { type: 'terminal' },
  showdownResult: number,
  traverser: Player,
): number {
  // Correct payoff: each player started with startTotal chips (stack + preflop investment).
  // startTotal = (stacks[0] + stacks[1] + pot) / 2  (money is conserved)
  const startTotal = (node.playerStacks[0] + node.playerStacks[1] + node.pot) / 2;
  const traverserStack = node.playerStacks[traverser];

  if (!node.showdown) {
    // Fold — lastToAct is the folder
    const folder = node.lastToAct;
    if (folder === traverser) {
      // Traverser folded → loses their investment
      return traverserStack - startTotal;
    } else {
      // Opponent folded → traverser wins the pot
      return traverserStack + node.pot - startTotal;
    }
  }

  // Showdown
  // showdownResult: +1 = OOP wins, -1 = IP wins, 0 = tie
  const oopWins = showdownResult > 0;
  const ipWins = showdownResult < 0;
  const isTie = showdownResult === 0;

  if (isTie) {
    // Both get back half the pot
    return traverserStack + node.pot / 2 - startTotal;
  }

  const traverserWins = (traverser === 0 && oopWins) || (traverser === 1 && ipWins);
  if (traverserWins) {
    return traverserStack + node.pot - startTotal;
  } else {
    return traverserStack - startTotal;
  }
}

// ---------- Showdown evaluation ----------

function computeShowdown(
  oopHand: [number, number],
  ipHand: [number, number],
  board: number[],
): number {
  const oopCards = [...oopHand.map(indexToCard), ...board.map(indexToCard)];
  const ipCards = [...ipHand.map(indexToCard), ...board.map(indexToCard)];

  const oopEval = evaluateBestHand(oopCards);
  const ipEval = evaluateBestHand(ipCards);
  const cmp = compareHands(oopEval, ipEval);

  if (cmp > 0) return 1;   // OOP wins
  if (cmp < 0) return -1;  // IP wins
  return 0;                 // tie
}

// ---------- Bucketing ----------

/**
 * Precompute equity-based buckets for a set of hands on a board.
 * Uses hand rank as a proxy for equity (faster than Monte Carlo).
 */
export function computeEquityBuckets(
  range: WeightedCombo[],
  board: number[],
  numBuckets: number,
  deadCards: Set<number>,
): Map<string, number> {
  // Compute hand rank for each combo
  const ranked: Array<{ key: string; value: number }> = [];

  for (const { combo } of range) {
    if (deadCards.has(combo[0]) || deadCards.has(combo[1])) continue;
    const cards = [...combo.map(indexToCard), ...board.map(indexToCard)];
    const eval_ = evaluateBestHand(cards);
    ranked.push({ key: comboKey(combo), value: eval_.value });
  }

  // Sort by hand strength and assign to equal-sized buckets
  ranked.sort((a, b) => a.value - b.value);

  const result = new Map<string, number>();
  const bucketSize = Math.max(1, Math.ceil(ranked.length / numBuckets));

  for (let i = 0; i < ranked.length; i++) {
    const bucket = Math.min(Math.floor(i / bucketSize), numBuckets - 1);
    result.set(ranked[i].key, bucket);
  }

  return result;
}

/**
 * Compute the bucket for a single hand on a given board relative to its range.
 * Uses percentile rank within the range's hand strength distribution.
 */
function computeSingleBucket(
  hand: [number, number],
  board: number[],
  range: WeightedCombo[],
  numBuckets: number,
): number {
  const handCards = [...hand.map(indexToCard), ...board.map(indexToCard)];
  const handEval = evaluateBestHand(handCards);
  const handValue = handEval.value;

  let weaker = 0;
  let total = 0;

  for (const { combo, weight } of range) {
    // Skip the same hand and card conflicts
    if (combo[0] === hand[0] && combo[1] === hand[1]) continue;
    if (combo[0] === hand[0] || combo[0] === hand[1] ||
        combo[1] === hand[0] || combo[1] === hand[1]) continue;
    // Skip board card conflicts
    let boardConflict = false;
    for (const bc of board) {
      if (combo[0] === bc || combo[1] === bc) { boardConflict = true; break; }
    }
    if (boardConflict) continue;

    const comboCards = [...combo.map(indexToCard), ...board.map(indexToCard)];
    const comboEval = evaluateBestHand(comboCards);
    total += weight;
    if (comboEval.value < handValue) weaker += weight;
    else if (comboEval.value === handValue) weaker += weight * 0.5;
  }

  if (total === 0) return Math.floor(numBuckets / 2);
  const percentile = weaker / total;
  return Math.min(numBuckets - 1, Math.floor(percentile * numBuckets));
}

/**
 * Cached version of computeSingleBucket to avoid redundant evaluations
 * across iterations sharing the same turn/river cards.
 */
function computeSingleBucketCached(
  hand: [number, number],
  board: number[],
  range: WeightedCombo[],
  numBuckets: number,
  cache: Map<string, number>,
): number {
  const cacheKey = `${comboKey(hand)}-${board.join(',')}`;
  const cached = cache.get(cacheKey);
  if (cached !== undefined) return cached;
  const bucket = computeSingleBucket(hand, board, range, numBuckets);
  cache.set(cacheKey, bucket);
  return bucket;
}

// ---------- Info-set key ----------

/**
 * Build info-set key in V2 format with per-street bucket IDs.
 * - Flop:  F|{boardId}|{player}|{history}|{flopBucket}
 * - Turn:  T|{boardId}|{player}|{history}|{flopBucket}-{turnBucket}
 * - River: R|{boardId}|{player}|{history}|{flopBucket}-{turnBucket}-{riverBucket}
 */
export function buildInfoKey(
  street: Street,
  boardId: number,
  player: Player,
  historyKey: string,
  buckets: StreetBuckets,
): string {
  const flopB = buckets.FLOP[player];
  switch (street) {
    case 'FLOP':
      return `F|${boardId}|${player}|${historyKey}|${flopB}`;
    case 'TURN':
      return `T|${boardId}|${player}|${historyKey}|${flopB}-${buckets.TURN[player]}`;
    case 'RIVER':
      return `R|${boardId}|${player}|${historyKey}|${flopB}-${buckets.TURN[player]}-${buckets.RIVER[player]}`;
  }
}

// ---------- Weighted sampling ----------

/**
 * Build cumulative weight array for efficient weighted sampling.
 */
function buildCumulativeWeights(range: WeightedCombo[]): Float32Array {
  const cum = new Float32Array(range.length);
  let sum = 0;
  for (let i = 0; i < range.length; i++) {
    sum += range[i].weight;
    cum[i] = sum;
  }
  return cum;
}

/**
 * Weighted random selection using cumulative weights and binary search.
 */
function weightedSample(cumWeights: Float32Array, rngState: number): number {
  const total = cumWeights[cumWeights.length - 1];
  const r = (rngState / 0x7fffffff) * total;
  // Binary search for the first index where cumWeight >= r
  let lo = 0;
  let hi = cumWeights.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (cumWeights[mid] < r) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/**
 * Weighted sample from IP range, skipping combos that conflict with the OOP hand.
 * Returns the index into the original ipRange, or -1 if no valid combo.
 */
function weightedSampleFiltered(
  ipRange: WeightedCombo[],
  _ipCumWeights: Float32Array,
  oopHand: [number, number],
  rngState: number,
): number {
  // Build filtered indices + cumulative weights on the fly
  // This is called once per iteration, and the filter set changes each time
  let cumWeight = 0;
  const validIndices: number[] = [];
  const validCumWeights: number[] = [];

  for (let i = 0; i < ipRange.length; i++) {
    const h = ipRange[i].combo;
    if (h[0] === oopHand[0] || h[0] === oopHand[1] ||
        h[1] === oopHand[0] || h[1] === oopHand[1]) continue;
    cumWeight += ipRange[i].weight;
    validIndices.push(i);
    validCumWeights.push(cumWeight);
  }

  if (validIndices.length === 0) return -1;

  const r = (rngState / 0x7fffffff) * cumWeight;
  let lo = 0;
  let hi = validIndices.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (validCumWeights[mid] < r) lo = mid + 1;
    else hi = mid;
  }
  return validIndices[lo];
}

// ---------- Utilities ----------

export function comboKey(combo: [number, number]): string {
  return combo[0] < combo[1] ? `${combo[0]},${combo[1]}` : `${combo[1]},${combo[0]}`;
}

export function streetChar(street: Street): string {
  switch (street) {
    case 'FLOP': return 'F';
    case 'TURN': return 'T';
    case 'RIVER': return 'R';
  }
}

function nextRng(state: number): number {
  return (state * 1103515245 + 12345) & 0x7fffffff;
}
