// Postflop advice engine for flop, turn, and river decisions

import type { AdvicePayload, StrategyMix, HandAction } from "@cardpilot/shared-types";
import { 
  calculateEquity, 
  calculatePotOdds, 
  calculateCallEV,
  analyzeBoardTexture,
  classifyHandOnBoard,
  type Card,
  type BoardTexture
} from "@cardpilot/poker-evaluator";
import { RangeEstimator } from './range-estimator.js';

export interface PostflopContext {
  tableId: string;
  handId: string;
  seat: number;
  street: 'FLOP' | 'TURN' | 'RIVER';
  heroHand: [Card, Card];
  board: Card[];
  heroPosition: string;
  villainPosition: string;
  potSize: number;
  toCall: number;
  effectiveStack: number;
  aggressor: 'hero' | 'villain' | 'none';
  numVillains: number;
  actionHistory?: HandAction[];  // For range estimation
  betSizingCategory?: 'small' | 'medium' | 'large' | 'overbet' | 'all_in';
}

export interface PostflopAdvice extends AdvicePayload {
  equity: number;
  potOdds: number;
  callEV?: number;
  boardTexture: BoardTexture;
  handStrength: 'nutted' | 'strong' | 'medium' | 'weak' | 'bluff';
}

const rangeEstimator = new RangeEstimator();

const EXPLANATIONS: Record<string, string> = {
  // Betting rationale
  VALUE_BET: "Your hand is strong enough to bet for value against worse hands.",
  PROTECTION_BET: "Bet to protect your equity and deny opponents odds to draw.",
  BLUFF: "You have fold equity and can credibly represent a strong hand.",
  SEMI_BLUFF: "You have outs to improve plus fold equity - aggressive play is profitable.",
  THIN_VALUE: "Marginal value bet targeting specific worse hands that might call.",
  
  // Calling rationale
  DRAW_ODDS: "You have correct pot odds to call with your draw.",
  IMPLIED_ODDS: "Future betting rounds give you implied odds to continue.",
  SHOWDOWN_VALUE: "Your hand has showdown value - worth seeing another card.",
  POT_COMMITTED: "Stack-to-pot ratio makes folding unprofitable.",
  
  // Folding rationale
  NO_EQUITY: "Insufficient equity against opponent's likely range.",
  BAD_ODDS: "Pot odds don't justify calling with your draw.",
  DOMINATED: "Board texture favors opponent's range heavily.",
  REVERSE_IMPLIED: "Poor reverse implied odds - likely to lose more if you hit.",
  
  // Texture analysis
  WET_BOARD: "Coordinated board with many draws - proceed with caution.",
  DRY_BOARD: "Static board with few draws - value bets are more reliable.",
  PAIRED_BOARD: "Paired board reduces straight/flush possibilities.",
  MONOTONE: "Three cards of same suit - flush draws are very likely.",
  HIGH_CARD: "High-card heavy board favors aggressive ranges.",
  
  // Multiway
  MULTIWAY_CAUTION: "Multiple opponents - tighten ranges and avoid bluffing.",
  MULTIWAY_NUTTED: "In multiway pots, only bet/raise with very strong hands.",
  
  // Position
  IP_CONTROL: "In position - you can control pot size and apply pressure.",
  OOP_CAUTION: "Out of position - check-calling and pot control are key."
};

/**
 * Generate postflop advice based on board texture, equity, and game theory
 */
export function getPostflopAdvice(context: PostflopContext): PostflopAdvice {
  const { heroHand, board, potSize, toCall, street, numVillains, actionHistory } = context;
  
  // Analyze board
  const boardTexture = analyzeBoardTexture(board);
  const handClass = classifyHandOnBoard(heroHand, board);
  
  // Estimate villain range from action history
  const villainRange = estimateVillainRange(context);
  const villainHands = rangeEstimator.sampleHandsFromRange(villainRange, 50);
  
  // Calculate equity (Monte Carlo simulation)
  const equityResult = calculateEquity({
    heroHand,
    villainHands: villainHands.length > 0 ? villainHands : generateVillainRange(context),
    board,
    simulations: street === 'RIVER' ? 1000 : 5000
  });
  
  const equity = equityResult.equity;
  const potOdds = calculatePotOdds(potSize, toCall);
  
  // Determine hand strength category
  const handStrength = categorizeHandStrength(equity, boardTexture, handClass);
  
  // Apply multiway adjustments
  const adjustedEquity = numVillains > 1 ? equity * (1 - (numVillains - 1) * 0.12) : equity;
  
  // Generate strategy mix
  const mix = generatePostflopMix({
    context,
    equity: adjustedEquity,
    potOdds,
    boardTexture,
    handStrength,
    handClass
  });
  
  // Determine tags and explanation
  const tags = generateTags(context, equity, potOdds, boardTexture, handClass, mix);
  const explanation = tags.map(t => EXPLANATIONS[t] || t).join(" ");
  
  // Pick recommended action
  const rand = hashToUnitInterval(`${context.tableId}|${context.handId}|${context.seat}|${street}`);
  const recommended = pickByMix(mix, rand);
  
  const callEV = toCall > 0 ? calculateCallEV({ potSize, toCall, equity }) : undefined;
  
  return {
    tableId: context.tableId,
    handId: context.handId,
    seat: context.seat,
    spotKey: `${street}_${context.heroPosition}_vs_${context.villainPosition}`,
    heroHand: `${heroHand[0]}${heroHand[1]}`,
    mix,
    tags,
    explanation,
    recommended,
    randomSeed: Math.round(rand * 100) / 100,
    equity: round4(equity),
    potOdds: round4(potOdds),
    callEV,
    boardTexture,
    handStrength
  };
}

function generatePostflopMix(params: {
  context: PostflopContext;
  equity: number;
  potOdds: number;
  boardTexture: BoardTexture;
  handStrength: string;
  handClass: ReturnType<typeof classifyHandOnBoard>;
}): StrategyMix {
  const { context, equity, potOdds, boardTexture, handStrength } = params;
  const { toCall, aggressor, street, heroPosition, numVillains } = context;
  
  const isIP = ['BTN', 'CO'].includes(heroPosition);
  const isMultiway = numVillains > 1;
  
  // Facing a bet
  if (toCall > 0) {
    return generateDefenseMix(equity, potOdds, handStrength, boardTexture, isIP, isMultiway);
  }
  
  // Checked to us (IP) or first to act
  if (aggressor === 'none' || aggressor === 'villain') {
    return generateAggressiveMix(equity, handStrength, boardTexture, isIP, street, isMultiway);
  }
  
  // Default cautious mix
  return { raise: 0.1, call: 0.3, fold: 0.6 };
}

function generateDefenseMix(
  equity: number,
  potOdds: number,
  handStrength: string,
  texture: BoardTexture,
  isIP: boolean,
  isMultiway: boolean
): StrategyMix {
  // Multiway: tighten defense significantly
  if (isMultiway) {
    if (handStrength === 'nutted' || handStrength === 'strong') {
      return normalizeMix({ raise: 0.70, call: 0.30, fold: 0 });
    }
    if (handStrength === 'medium' && equity > potOdds + 0.1) {
      return normalizeMix({ raise: 0.10, call: 0.70, fold: 0.20 });
    }
    // Fold more in multiway with weak hands
    return normalizeMix({ raise: 0, call: 0.20, fold: 0.80 });
  }
  // Strong hands: raise for value
  if (handStrength === 'nutted' || handStrength === 'strong') {
    const raiseFreq = handStrength === 'nutted' ? 0.85 : 0.65;
    return normalizeMix({ 
      raise: raiseFreq, 
      call: 1 - raiseFreq, 
      fold: 0 
    });
  }
  
  // Medium strength: mix of call/raise
  if (handStrength === 'medium') {
    if (equity > potOdds + 0.15) {
      // Good equity - can call or raise
      return normalizeMix({ 
        raise: 0.25, 
        call: 0.70, 
        fold: 0.05 
      });
    }
    // Marginal equity
    return normalizeMix({ 
      raise: 0.10, 
      call: 0.55, 
      fold: 0.35 
    });
  }
  
  // Weak/draws: check pot odds
  if (equity >= potOdds) {
    // Correct odds to call
    const bluffRaiseFreq = texture.wetness > 0.6 ? 0.15 : 0.08;
    return normalizeMix({ 
      raise: bluffRaiseFreq, 
      call: 0.80 - bluffRaiseFreq, 
      fold: 0.20 
    });
  }
  
  // No equity + bad odds = mostly fold
  return normalizeMix({ 
    raise: 0.05, 
    call: 0.15, 
    fold: 0.80 
  });
}

function generateAggressiveMix(
  equity: number,
  handStrength: string,
  texture: BoardTexture,
  isIP: boolean,
  street: string,
  isMultiway: boolean
): StrategyMix {
  // Multiway: bet less frequently, focus on value
  if (isMultiway) {
    if (handStrength === 'nutted' || handStrength === 'strong') {
      return normalizeMix({ raise: 0.85, call: 0.15, fold: 0 });
    }
    if (handStrength === 'medium') {
      return normalizeMix({ raise: 0.40, call: 0.60, fold: 0 });
    }
    // Rarely bluff multiway
    return normalizeMix({ raise: 0.05, call: 0.95, fold: 0 });
  }
  const positionBonus = isIP ? 0.15 : 0;
  
  // Nutted hands: bet big/always
  if (handStrength === 'nutted') {
    return normalizeMix({ 
      raise: 0.95, 
      call: 0.05, 
      fold: 0 
    });
  }
  
  // Strong hands: bet frequently
  if (handStrength === 'strong') {
    return normalizeMix({ 
      raise: 0.75 + positionBonus, 
      call: 0.25 - positionBonus, 
      fold: 0 
    });
  }
  
  // Medium: mix of bet/check
  if (handStrength === 'medium') {
    const betFreq = texture.category === 'dry' ? 0.60 : 0.45;
    return normalizeMix({ 
      raise: betFreq + positionBonus, 
      call: 1 - betFreq - positionBonus, 
      fold: 0 
    });
  }
  
  // Weak: bluff occasionally, mostly check
  if (handStrength === 'weak') {
    const bluffFreq = isIP && texture.wetness > 0.5 ? 0.30 : 0.15;
    return normalizeMix({ 
      raise: bluffFreq, 
      call: 1 - bluffFreq, 
      fold: 0 
    });
  }
  
  // Bluff candidate: aggressive on wet boards
  const bluffFreq = texture.wetness > 0.6 ? 0.50 : 0.25;
  return normalizeMix({ 
    raise: bluffFreq, 
    call: 1 - bluffFreq, 
    fold: 0 
  });
}

function categorizeHandStrength(
  equity: number,
  texture: BoardTexture,
  handClass: ReturnType<typeof classifyHandOnBoard>
): 'nutted' | 'strong' | 'medium' | 'weak' | 'bluff' {
  if (equity >= 0.85) return 'nutted';
  if (equity >= 0.65) return 'strong';
  if (equity >= 0.45) return 'medium';
  if (equity >= 0.25) return 'weak';
  return 'bluff';
}

function estimateVillainRange(context: PostflopContext) {
  const { villainPosition, actionHistory, board, street, numVillains } = context;
  
  if (!actionHistory || actionHistory.length === 0) {
    return rangeEstimator.buildPreflopRange(villainPosition, "raise");
  }
  
  // Start with preflop range
  const preflopAction = actionHistory.find(a => a.street === "PREFLOP");
  let range = preflopAction 
    ? rangeEstimator.buildPreflopRange(villainPosition, preflopAction.type)
    : rangeEstimator.buildPreflopRange(villainPosition, "raise");
  
  // Narrow based on postflop actions
  const postflopActions = actionHistory.filter(a => 
    a.street === street || (street === "TURN" && a.street === "FLOP") || (street === "RIVER" && ["FLOP", "TURN"].includes(a.street))
  );
  
  for (const action of postflopActions) {
    const betSize = action.amount && context.potSize > 0 ? action.amount / context.potSize : undefined;
    range = rangeEstimator.narrowRangePostflop(range, action.type, action.street, board, betSize);
  }
  
  // Multiway adjustment
  if (numVillains > 1) {
    range = rangeEstimator.adjustForMultiway(range, numVillains);
  }
  
  return range;
}

function generateTags(
  context: PostflopContext,
  equity: number,
  potOdds: number,
  texture: BoardTexture,
  handClass: ReturnType<typeof classifyHandOnBoard>,
  mix: StrategyMix
): string[] {
  const tags: string[] = [];
  const { heroPosition, toCall, street, numVillains } = context;
  const isIP = ['BTN', 'CO'].includes(heroPosition);
  const isMultiway = numVillains > 1;
  
  // Position tags
  if (isIP) tags.push('IP_CONTROL');
  else tags.push('OOP_CAUTION');
  
  // Multiway tags
  if (isMultiway) {
    tags.push('MULTIWAY_CAUTION');
    if (mix.raise > 0.6) tags.push('MULTIWAY_NUTTED');
  }
  
  // Board texture tags
  if (texture.wetness >= 0.7) tags.push('WET_BOARD');
  else if (texture.wetness <= 0.3) tags.push('DRY_BOARD');
  if (texture.isPaired) tags.push('PAIRED_BOARD');
  if (texture.isMonotone) tags.push('MONOTONE');
  if (texture.highCardValue <= 3) tags.push('HIGH_CARD');
  
  // Action tags based on recommended strategy
  if (mix.raise > 0.5) {
    if (equity >= 0.55) tags.push('VALUE_BET');
    else if (handClass.type === 'draw') tags.push('SEMI_BLUFF');
    else tags.push('BLUFF');
  }
  
  if (mix.call > 0.5 && toCall > 0) {
    if (equity >= potOdds) tags.push('DRAW_ODDS');
    else if (street !== 'RIVER') tags.push('IMPLIED_ODDS');
    else if (handClass.type === 'made_hand') tags.push('SHOWDOWN_VALUE');
  }
  
  if (mix.fold > 0.5) {
    if (equity < 0.15) tags.push('NO_EQUITY');
    else if (equity < potOdds) tags.push('BAD_ODDS');
    else tags.push('DOMINATED');
  }
  
  return tags;
}

function generateVillainRange(context: PostflopContext): Array<[Card, Card]> {
  // Simplified: generate random opponent hands (not in hero hand or board)
  // In production, this should be based on opponent range estimation
  const deadCards = new Set([...context.heroHand, ...context.board]);
  const deck: Card[] = [];
  
  const ranks = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2'];
  const suits = ['s', 'h', 'd', 'c'];
  
  for (const r of ranks) {
    for (const s of suits) {
      const card = `${r}${s}` as Card;
      if (!deadCards.has(card)) deck.push(card);
    }
  }
  
  // Generate sample hands (simplified)
  const sampleSize = Math.min(50, Math.floor(deck.length / 2));
  const hands: Array<[Card, Card]> = [];
  
  for (let i = 0; i < sampleSize && i * 2 + 1 < deck.length; i++) {
    hands.push([deck[i * 2], deck[i * 2 + 1]]);
  }
  
  return hands;
}

function pickByMix(mix: StrategyMix, r: number): 'raise' | 'call' | 'fold' {
  const normalized = normalizeMix(mix);
  if (r < normalized.raise) return 'raise';
  if (r < normalized.raise + normalized.call) return 'call';
  return 'fold';
}

function normalizeMix(mix: StrategyMix): StrategyMix {
  const sum = mix.raise + mix.call + mix.fold;
  if (sum < 0.0001) return { raise: 0, call: 0, fold: 1 };
  return {
    raise: round4(mix.raise / sum),
    call: round4(mix.call / sum),
    fold: round4(mix.fold / sum)
  };
}

function hashToUnitInterval(seed: string): number {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  const unsigned = h >>> 0;
  return unsigned / 0x100000000;
}

function round4(n: number): number {
  return Math.round(n * 10000) / 10000;
}
