// CFR+ with Chance-Sampled MCCFR
//
// Each iteration:
// 1. Sample a hand matchup (oopHand, ipHand) from preflop ranges
// 2. Sample turn card + river card for the runout
// 3. Compute per-street hand buckets for each player
// 4. Traverse the action tree:
//    - At traverser's nodes: explore ALL actions (full traversal)
//    - At opponent's nodes: explore ALL actions weighted by strategy
// 5. Update regrets (CFR+: floor at 0) and accumulate strategy sums
//
// This is "External Sampling" MCCFR where chance events (cards) are sampled
// but all player actions are fully explored.

import type { GameNode, ActionNode, Player, Street } from '../types.js';
import { InfoSetStore } from './info-set-store.js';
import { indexToCard } from '../abstraction/card-index.js';
import { evaluateBestHand, compareHands } from '@cardpilot/poker-evaluator';

// ---------- Public API ----------

export interface SolveParams {
  root: ActionNode;
  store: InfoSetStore;
  boardId: number;
  flopCards: [number, number, number]; // 3 card indices
  oopRange: Array<[number, number]>;   // list of (c1, c2) combos in OOP range
  ipRange: Array<[number, number]>;    // list of (c1, c2) combos in IP range
  iterations: number;
  bucketCount: number;                 // buckets per street (e.g. 50)
  onProgress?: (iter: number, elapsed: number, exploitEst: number) => void;
}

/**
 * Run MCCFR chance-sampling solver.
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

  // Build remaining deck (exclude flop cards)
  const remainDeck: number[] = [];
  for (let c = 0; c < 52; c++) {
    if (!deadFlop.has(c)) remainDeck.push(c);
  }

  const startTime = Date.now();
  let rngState = Date.now() & 0x7fffffff;

  for (let iter = 0; iter < iterations; iter++) {
    // 1. Sample OOP hand from range
    rngState = nextRng(rngState);
    const oopIdx = rngState % oopRange.length;
    const oopHand = oopRange[oopIdx];

    // 2. Sample IP hand (must not conflict with OOP hand)
    const ipValid = ipRange.filter(
      h => h[0] !== oopHand[0] && h[0] !== oopHand[1] &&
           h[1] !== oopHand[0] && h[1] !== oopHand[1]
    );
    if (ipValid.length === 0) continue;
    rngState = nextRng(rngState);
    const ipHand = ipValid[rngState % ipValid.length];

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

    // 4. Compute per-street buckets
    const riverBoard: number[] = [...flopCards, turnCard, riverCard];

    // Use precomputed flop buckets for all streets (static hand abstraction for V1)
    // This is a valid simplification: the hand's "bucket identity" stays constant.
    // The street is part of the info-set key, so different streets still have
    // different info sets even with the same bucket.
    const oopBucket = flopBucketsOOP.get(comboKey(oopHand))!;
    const ipBucket = flopBucketsIP.get(comboKey(ipHand))!;

    if (oopBucket === undefined || ipBucket === undefined) continue;

    const buckets: StreetBuckets = {
      FLOP: [oopBucket, ipBucket],
      TURN: [oopBucket, ipBucket],
      RIVER: [oopBucket, ipBucket],
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
  const bucket = buckets[act.street][player];
  const infoKey = `${streetChar(act.street)}|${boardId}|${player}|${act.historyKey}|${bucket}`;

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
 * Precompute equity-based buckets for a set of hands on the flop.
 * Uses hand rank as a proxy for equity (faster than Monte Carlo).
 */
function computeEquityBuckets(
  range: Array<[number, number]>,
  board: number[],
  numBuckets: number,
  deadCards: Set<number>,
): Map<string, number> {
  // Compute hand rank for each combo
  const ranked: Array<{ key: string; value: number }> = [];

  for (const combo of range) {
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

// ---------- Utilities ----------

function comboKey(combo: [number, number]): string {
  return combo[0] < combo[1] ? `${combo[0]},${combo[1]}` : `${combo[1]},${combo[0]}`;
}

function streetChar(street: Street): string {
  switch (street) {
    case 'FLOP': return 'F';
    case 'TURN': return 'T';
    case 'RIVER': return 'R';
  }
}

function nextRng(state: number): number {
  return (state * 1103515245 + 12345) & 0x7fffffff;
}
