// Monte Carlo equity calculator for Texas Hold'em

import { createShuffledDeck, FULL_DECK, type Card, parseCard } from './card-utils.js';
import { evaluateBestHand, compareHands } from './evaluator.js';

export interface EquityResult {
  win: number; // Win probability (0-1)
  tie: number; // Tie probability (0-1)
  lose: number; // Lose probability (0-1)
  equity: number; // Overall equity: win + tie/2 (0-1)
  simulations: number;
}

export interface RangeEquity {
  heroHand: string;
  villainRange: string[];
  board: Card[];
  result: EquityResult;
}

/**
 * Calculate equity of hero hand vs villain hand(s) using Monte Carlo simulation
 */
export function calculateEquity(params: {
  heroHand: [Card, Card];
  villainHands: Array<[Card, Card]>;
  board: Card[];
  simulations?: number;
}): EquityResult {
  const { heroHand, villainHands, board, simulations = 10000 } = params;

  const deadCards = new Set([...heroHand, ...villainHands.flat(), ...board]);
  const cardsNeeded = 5 - board.length;

  if (cardsNeeded < 0) {
    throw new Error('Board cannot have more than 5 cards');
  }

  // Optimization: Filter available cards once, outside the loop
  const availableCards = FULL_DECK.filter((c) => !deadCards.has(c));

  // Need to ensure we have enough cards
  if (availableCards.length < cardsNeeded) {
    throw new Error('Not enough cards remaining in deck');
  }

  let wins = 0;
  let ties = 0;
  let losses = 0;

  for (let i = 0; i < simulations; i++) {
    // Optimization: Shuffle only the available cards
    // We only need 'cardsNeeded' random cards.
    // Fisher-Yates shuffle on a copy of availableCards is sufficient.
    const runout: Card[] = [];
    const deck = [...availableCards]; // Clone to avoid mutating the base set

    // Partial shuffle just enough to get the cards we need
    for (let j = 0; j < cardsNeeded; j++) {
      const idx = Math.floor(Math.random() * (deck.length - j));
      const picked = deck[idx];
      deck[idx] = deck[deck.length - 1 - j]; // Swap with end
      runout.push(picked);
    }

    const finalBoard = [...board, ...runout];

    const heroEval = evaluateBestHand([...heroHand, ...finalBoard]);

    let heroWins = true;
    let isTie = false;
    let isLoss = false;

    for (const villainHand of villainHands) {
      const villainEval = evaluateBestHand([...villainHand, ...finalBoard]);
      const cmp = compareHands(heroEval, villainEval);

      if (cmp < 0) {
        heroWins = false;
        isLoss = true;
        break;
      } else if (cmp === 0) {
        isTie = true;
      }
    }

    if (isLoss) losses++;
    else if (heroWins && !isTie) wins++;
    else if (isTie) ties++;
    else losses++;
  }

  const win = wins / simulations;
  const tie = ties / simulations;
  const lose = losses / simulations;
  const equity = win + tie / 2;

  return {
    win: round4(win),
    tie: round4(tie),
    lose: round4(lose),
    equity: round4(equity),
    simulations,
  };
}

/**
 * Calculate hand strength (equity vs random hand)
 */
export function calculateHandStrength(heroHand: [Card, Card], board: Card[]): number {
  const randomHands = generateRandomOpponentHands(heroHand, board, 100);
  const result = calculateEquity({
    heroHand,
    villainHands: randomHands,
    board,
    simulations: 1000,
  });
  return result.equity;
}

/**
 * Calculate pot odds needed for a call to be profitable
 */
export function calculatePotOdds(potSize: number, toCall: number): number {
  if (toCall === 0) return 0;
  return round4(toCall / (potSize + toCall));
}

/**
 * Calculate expected value of a call given equity and pot odds
 */
export function calculateCallEV(params: {
  potSize: number;
  toCall: number;
  equity: number;
}): number {
  const { potSize, toCall, equity } = params;
  const potOdds = calculatePotOdds(potSize, toCall);

  if (equity >= potOdds) {
    return round4((potSize + toCall) * equity - toCall);
  }
  return round4(-toCall * (1 - equity));
}

/**
 * Calculate outs (cards that improve hand)
 */
export function calculateOuts(params: {
  heroHand: [Card, Card];
  board: Card[];
  targetHand: 'flush' | 'straight' | 'set' | 'two_pair' | 'pair';
}): number {
  const { heroHand, board, targetHand } = params;

  // Simplified outs calculation
  const heroCards = heroHand.map(parseCard);
  const boardCards = board.map(parseCard);

  switch (targetHand) {
    case 'flush': {
      // Count flush draw outs
      const suits: Record<string, number> = {};
      for (const c of [...heroCards, ...boardCards]) {
        suits[c.suit] = (suits[c.suit] || 0) + 1;
      }
      const maxSuit = Math.max(...Object.values(suits));
      return maxSuit === 4 ? 9 : 0; // 9 outs for flush draw
    }

    case 'straight': {
      // Simplified: assume open-ended straight draw = 8 outs, gutshot = 4
      // This is a rough approximation
      return 8; // Conservative estimate
    }

    case 'set': {
      // Pair to set: 2 outs
      const isPair = heroCards[0].rank === heroCards[1].rank;
      return isPair ? 2 : 0;
    }

    case 'two_pair':
    case 'pair': {
      // Overcards to make pair: ~6 outs
      return 6;
    }

    default:
      return 0;
  }
}

/**
 * Convert outs to equity approximation (Rule of 2 and 4)
 */
export function outsToEquity(outs: number, streets: 1 | 2): number {
  if (streets === 1) {
    // One card to come: outs * 2%
    return round4(Math.min(outs * 0.02, 1));
  }
  // Two cards to come: outs * 4%
  return round4(Math.min(outs * 0.04, 1));
}

function generateRandomOpponentHands(
  heroHand: [Card, Card],
  board: Card[],
  count: number,
): Array<[Card, Card]> {
  const deadCards = new Set([...heroHand, ...board]);
  const availableCards = createShuffledDeck().filter((c) => !deadCards.has(c));

  const hands: Array<[Card, Card]> = [];
  for (let i = 0; i < Math.min(count, Math.floor(availableCards.length / 2)); i++) {
    hands.push([availableCards[i * 2], availableCards[i * 2 + 1]]);
  }
  return hands;
}

function round4(n: number): number {
  return Math.round(n * 10000) / 10000;
}
