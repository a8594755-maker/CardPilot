// Board texture analysis for postflop decisions

import { type Card, parseCard, RANKS } from './card-utils.js';

export interface BoardTexture {
  // Structure
  isPaired: boolean;
  isTwoPair: boolean;
  isTrips: boolean;
  isMonotone: boolean; // All same suit
  isTwoTone: boolean; // Two suits dominate
  isRainbow: boolean; // All different suits

  // Connectivity
  hasFlushDraw: boolean;
  hasStraightPossible: boolean;
  straightDraws: number; // 0, 1, 2+ straight draw combos

  // Card heights
  highCard: string;
  highCardValue: number;
  wetness: number; // 0-1 scale: how coordinated/dangerous

  // Categorization
  category: 'dry' | 'semi-wet' | 'wet' | 'very-wet';
}

/**
 * Analyze board texture for strategic decisions
 */
export function analyzeBoardTexture(board: Card[]): BoardTexture {
  if (board.length < 3) {
    throw new Error('Need at least 3 cards (flop) to analyze texture');
  }

  const cards = board.slice(0, 5).map(parseCard);

  // Rank analysis
  const rankCounts: Record<string, number> = {};
  for (const c of cards) {
    rankCounts[c.rank] = (rankCounts[c.rank] || 0) + 1;
  }

  const counts = Object.values(rankCounts).sort((a, b) => b - a);
  const isPaired = counts[0] >= 2;
  const isTwoPair = counts[0] >= 2 && counts[1] >= 2;
  const isTrips = counts[0] >= 3;

  // Suit analysis
  const suitCounts: Record<string, number> = {};
  for (const c of cards) {
    suitCounts[c.suit] = (suitCounts[c.suit] || 0) + 1;
  }

  const suitValues = Object.values(suitCounts).sort((a, b) => b - a);
  const isMonotone = suitValues[0] === 3 || suitValues[0] === 4 || suitValues[0] === 5;
  const isTwoTone = suitValues[0] >= 2 && suitValues[1] >= 1;
  const isRainbow = suitValues[0] === 1;
  const hasFlushDraw = suitValues[0] >= 3;

  // Connectivity analysis
  const rankValues = cards.map((c) => c.rankValue).sort((a, b) => b - a);
  const gaps = [];
  for (let i = 0; i < rankValues.length - 1; i++) {
    gaps.push(rankValues[i] - rankValues[i + 1]);
  }

  const maxGap = Math.max(...gaps);
  const hasStraightPossible = maxGap <= 4;

  // Count straight draws (simplified)
  let straightDraws = 0;
  if (gaps.some((g) => g === 1)) straightDraws += 2; // Connected cards
  if (gaps.some((g) => g === 2)) straightDraws += 1; // One-gap

  // High card
  const highCardValue = rankValues[0];
  const highCard = RANKS[highCardValue];

  // Wetness score (0-1)
  let wetness = 0;
  if (hasFlushDraw) wetness += 0.25;
  if (straightDraws >= 2) wetness += 0.3;
  else if (straightDraws === 1) wetness += 0.15;
  if (isPaired) wetness += 0.15;
  if (maxGap <= 2) wetness += 0.2; // Very connected
  if (highCardValue <= 3) wetness -= 0.1; // High cards = less draws
  wetness = Math.max(0, Math.min(1, wetness));

  // Categorization
  let category: BoardTexture['category'];
  if (wetness < 0.25) category = 'dry';
  else if (wetness < 0.5) category = 'semi-wet';
  else if (wetness < 0.75) category = 'wet';
  else category = 'very-wet';

  return {
    isPaired,
    isTwoPair,
    isTrips,
    isMonotone,
    isTwoTone,
    isRainbow,
    hasFlushDraw,
    hasStraightPossible,
    straightDraws,
    highCard,
    highCardValue,
    wetness: round2(wetness),
    category,
  };
}

/**
 * Classify hand type on board
 */
export function classifyHandOnBoard(
  heroHand: [Card, Card],
  board: Card[],
): {
  type: 'made_hand' | 'draw' | 'air';
  strength: 'strong' | 'medium' | 'weak';
  description: string;
} {
  const hero = heroHand.map(parseCard);
  const boardCards = board.map(parseCard);

  // Check for pairs
  const heroPair = hero[0].rank === hero[1].rank;
  const boardRanks = new Set(boardCards.map((c) => c.rank));
  const hasPairOnBoard = hero.some((c) => boardRanks.has(c.rank));

  // Check for flush draw
  const boardSuits: Record<string, number> = {};
  for (const c of boardCards) {
    boardSuits[c.suit] = (boardSuits[c.suit] || 0) + 1;
  }

  const hasFlushDraw = hero.some((c) => (boardSuits[c.suit] || 0) >= 2);

  // Simple classification
  if (heroPair && !boardRanks.has(hero[0].rank)) {
    return {
      type: 'made_hand',
      strength: hero[0].rankValue <= 5 ? 'strong' : 'medium',
      description: 'Pocket pair',
    };
  }

  if (hasPairOnBoard) {
    const pairRank = hero.find((c) => boardRanks.has(c.rank))!.rankValue;
    return {
      type: 'made_hand',
      strength: pairRank <= 3 ? 'strong' : pairRank <= 7 ? 'medium' : 'weak',
      description: 'Top pair / pair',
    };
  }

  if (hasFlushDraw) {
    return {
      type: 'draw',
      strength: 'medium',
      description: 'Flush draw',
    };
  }

  return {
    type: 'air',
    strength: 'weak',
    description: 'No pair',
  };
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}
