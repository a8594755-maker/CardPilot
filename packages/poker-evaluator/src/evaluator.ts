// Simple 5-card poker evaluator
// For Texas Hold'em, we evaluate the best 5-card hand from 7 cards

import { RANKS, type Card, parseCard } from './card-utils.js';
import { HandRank, HAND_RANK_NAMES, type HandEvaluation } from './hand-rank.js';

/**
 * 從 7 張牌中找出最強的 5 張組合
 */
export function evaluateBestHand(cards: Card[]): HandEvaluation {
  if (cards.length < 5) {
    throw new Error('Need at least 5 cards to evaluate');
  }

  // Generate all 5-card combinations
  const combinations = generateCombinations(cards, 5);

  let bestEval: HandEvaluation | null = null;

  for (const combo of combinations) {
    const eval_ = evaluate5CardHand(combo);
    if (!bestEval || compareHands(eval_, bestEval) > 0) {
      bestEval = eval_;
    }
  }

  return bestEval!;
}

/**
 * 比較兩手牌的大小
 * @returns positive if hand1 wins, negative if hand2 wins, 0 if tie
 */
export function compareHands(hand1: HandEvaluation, hand2: HandEvaluation): number {
  if (hand1.rank !== hand2.rank) {
    return hand1.rank - hand2.rank;
  }
  return hand1.value - hand2.value;
}

/**
 * 從多個玩家的牌中找出贏家
 */
export function findWinners(
  players: Array<{ seat: number; cards: Card[] }>,
): Array<{ seat: number; evaluation: HandEvaluation }> {
  const evaluations = players.map((p) => ({
    seat: p.seat,
    evaluation: evaluateBestHand(p.cards),
  }));

  let bestEval = evaluations[0].evaluation;

  for (const ev of evaluations) {
    if (compareHands(ev.evaluation, bestEval) > 0) {
      bestEval = ev.evaluation;
    }
  }

  return evaluations.filter((ev) => compareHands(ev.evaluation, bestEval) === 0);
}

function evaluate5CardHand(cards: Card[]): HandEvaluation {
  const parsed = cards.map(parseCard);

  // Sort by rank value (descending)
  parsed.sort((a, b) => b.rankValue - a.rankValue);

  const isFlushHand = isFlush(parsed);
  const isStraightHand = isStraight(parsed);

  // Royal Flush / Straight Flush
  if (isFlushHand && isStraightHand.isStraight) {
    const rank = isStraightHand.highCard === 'A' ? HandRank.ROYAL_FLUSH : HandRank.STRAIGHT_FLUSH;
    return {
      rank,
      rankName: HAND_RANK_NAMES[rank],
      value: calculateValue(rank, [isStraightHand.highCard]),
      cards: cards,
      kickers: [],
    };
  }

  // Four of a Kind
  const quads = findOfAKind(parsed, 4);
  if (quads) {
    const kicker = parsed.find((c) => c.rank !== quads.rank)!;
    return {
      rank: HandRank.FOUR_OF_A_KIND,
      rankName: HAND_RANK_NAMES[HandRank.FOUR_OF_A_KIND],
      value: calculateValue(HandRank.FOUR_OF_A_KIND, [quads.rank, kicker.rank]),
      cards: cards,
      kickers: [kicker.rank],
    };
  }

  // Full House
  const trips = findOfAKind(parsed, 3);
  if (trips) {
    const pair = findOfAKind(
      parsed.filter((c) => c.rank !== trips.rank),
      2,
    );
    if (pair) {
      return {
        rank: HandRank.FULL_HOUSE,
        rankName: HAND_RANK_NAMES[HandRank.FULL_HOUSE],
        value: calculateValue(HandRank.FULL_HOUSE, [trips.rank, pair.rank]),
        cards: cards,
        kickers: [],
      };
    }
  }

  // Flush
  if (isFlushHand) {
    const ranks = parsed.map((c) => c.rank);
    return {
      rank: HandRank.FLUSH,
      rankName: HAND_RANK_NAMES[HandRank.FLUSH],
      value: calculateValue(HandRank.FLUSH, ranks),
      cards: cards,
      kickers: [],
    };
  }

  // Straight
  if (isStraightHand.isStraight) {
    return {
      rank: HandRank.STRAIGHT,
      rankName: HAND_RANK_NAMES[HandRank.STRAIGHT],
      value: calculateValue(HandRank.STRAIGHT, [isStraightHand.highCard]),
      cards: cards,
      kickers: [],
    };
  }

  // Three of a Kind
  if (trips) {
    const kickers = parsed
      .filter((c) => c.rank !== trips.rank)
      .slice(0, 2)
      .map((c) => c.rank);
    return {
      rank: HandRank.THREE_OF_A_KIND,
      rankName: HAND_RANK_NAMES[HandRank.THREE_OF_A_KIND],
      value: calculateValue(HandRank.THREE_OF_A_KIND, [trips.rank, ...kickers]),
      cards: cards,
      kickers,
    };
  }

  // Two Pair
  const pair1 = findOfAKind(parsed, 2);
  if (pair1) {
    const pair2 = findOfAKind(
      parsed.filter((c) => c.rank !== pair1.rank),
      2,
    );
    if (pair2) {
      const kicker = parsed.find((c) => c.rank !== pair1.rank && c.rank !== pair2.rank)!;
      const highPair = pair1.rankValue < pair2.rankValue ? pair1 : pair2;
      const lowPair = pair1.rankValue < pair2.rankValue ? pair2 : pair1;
      return {
        rank: HandRank.TWO_PAIR,
        rankName: HAND_RANK_NAMES[HandRank.TWO_PAIR],
        value: calculateValue(HandRank.TWO_PAIR, [highPair.rank, lowPair.rank, kicker.rank]),
        cards: cards,
        kickers: [kicker.rank],
      };
    }

    // One Pair
    const kickers = parsed
      .filter((c) => c.rank !== pair1.rank)
      .slice(0, 3)
      .map((c) => c.rank);
    return {
      rank: HandRank.ONE_PAIR,
      rankName: HAND_RANK_NAMES[HandRank.ONE_PAIR],
      value: calculateValue(HandRank.ONE_PAIR, [pair1.rank, ...kickers]),
      cards: cards,
      kickers,
    };
  }

  // High Card
  const ranks = parsed.map((c) => c.rank);
  return {
    rank: HandRank.HIGH_CARD,
    rankName: HAND_RANK_NAMES[HandRank.HIGH_CARD],
    value: calculateValue(HandRank.HIGH_CARD, ranks),
    cards: cards,
    kickers: ranks.slice(1),
  };
}

function isFlush(cards: ReturnType<typeof parseCard>[]): boolean {
  const suits: Record<string, number> = {};
  for (const c of cards) {
    suits[c.suit] = (suits[c.suit] || 0) + 1;
    if (suits[c.suit] >= 5) return true;
  }
  return false;
}

function isStraight(
  cards: ReturnType<typeof parseCard>[],
): { isStraight: true; highCard: string } | { isStraight: false } {
  const uniqueRanks = [...new Set(cards.map((c) => c.rankValue))];

  // Check for A-5-4-3-2 straight (wheel)
  if (
    uniqueRanks.includes(0) &&
    uniqueRanks.includes(9) &&
    uniqueRanks.includes(10) &&
    uniqueRanks.includes(11) &&
    uniqueRanks.includes(12)
  ) {
    return { isStraight: true, highCard: '5' };
  }

  // Check regular straights
  for (let i = 0; i <= uniqueRanks.length - 5; i++) {
    if (uniqueRanks[i] - uniqueRanks[i + 4] === 4) {
      return { isStraight: true, highCard: RANKS[uniqueRanks[i + 4]] };
    }
  }

  return { isStraight: false };
}

function findOfAKind(
  cards: ReturnType<typeof parseCard>[],
  count: number,
): { rank: string; rankValue: number } | null {
  const counts: Record<string, number> = {};

  for (const c of cards) {
    counts[c.rank] = (counts[c.rank] || 0) + 1;
    if (counts[c.rank] === count) {
      return { rank: c.rank, rankValue: c.rankValue };
    }
  }

  return null;
}

function calculateValue(rank: HandRank, ranks: string[]): number {
  let value = rank * 10000000000;

  for (let i = 0; i < ranks.length; i++) {
    const rankValue = 12 - RANKS.indexOf(ranks[i]); // A=12, K=11, ..., 2=0
    value += rankValue * Math.pow(100, 4 - i);
  }

  return value;
}

/**
 * Evaluate hand + board from card indices (0-51).
 * index = rank * 4 + suit, rank: 0=2..12=A, suit: 0=c,1=d,2=h,3=s
 * Returns a numeric value suitable for comparing hand strength.
 */
export function evaluateHandBoard(h0: number, h1: number, board: number[]): number {
  const RANK_CHARS = '23456789TJQKA';
  const SUIT_CHARS = 'cdhs';
  const toCard = (idx: number): Card => RANK_CHARS[idx >> 2] + SUIT_CHARS[idx & 3];
  const cards = [toCard(h0), toCard(h1), ...board.map(toCard)];
  return evaluateBestHand(cards).value;
}

function generateCombinations<T>(arr: T[], k: number): T[][] {
  if (k === 0) return [[]];
  if (arr.length < k) return [];

  const result: T[][] = [];

  function backtrack(start: number, current: T[]) {
    if (current.length === k) {
      result.push([...current]);
      return;
    }

    for (let i = start; i < arr.length; i++) {
      current.push(arr[i]);
      backtrack(i + 1, current);
      current.pop();
    }
  }

  backtrack(0, []);
  return result;
}
