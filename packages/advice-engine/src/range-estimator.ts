// Range estimation and narrowing based on action history

import type { HandAction, Street, PlayerActionType } from "@cardpilot/shared-types";

export type HandRange = Map<string, number>; // hand -> weight (0-1)

export interface RangeEstimatorConfig {
  defaultOpeningRange: string[]; // Per position
  tightnessAdjustment: number;   // -1 (loose) to +1 (tight)
}

/**
 * Estimate opponent range based on action history
 */
export class RangeEstimator {
  private rangeCache = new Map<string, HandRange>();
  
  /**
   * Build initial preflop range based on position and action
   */
  buildPreflopRange(position: string, action: PlayerActionType, facing?: string): HandRange {
    const cacheKey = `preflop_${position}_${action}_${facing || "none"}`;
    
    if (this.rangeCache.has(cacheKey)) {
      return this.rangeCache.get(cacheKey)!;
    }
    
    let range = new Map<string, number>();
    
    if (action === "raise" && !facing) {
      // Opening raise range
      range = this.getOpeningRange(position);
    } else if (action === "raise" && facing) {
      // 3bet range
      range = this.get3BetRange(position, facing);
    } else if (action === "call" && facing) {
      // Calling range
      range = this.getCallingRange(position, facing);
    } else {
      // Default to tight range
      range = this.getDefaultTightRange();
    }
    
    this.rangeCache.set(cacheKey, range);
    return range;
  }
  
  /**
   * Narrow range based on postflop action
   */
  narrowRangePostflop(
    currentRange: HandRange,
    action: PlayerActionType,
    street: Street,
    board: string[],
    betSize?: number
  ): HandRange {
    const narrowed = new Map<string, number>();
    
    for (const [hand, weight] of currentRange) {
      if (weight < 0.01) continue;
      
      let newWeight = weight;
      
      // Adjust weight based on action type
      if (action === "raise" || action === "all_in") {
        // Aggressive action: favor strong hands and draws
        const isStrongHand = this.isLikelyStrongOnBoard(hand, board);
        const isDraw = this.isLikelyDraw(hand, board);
        
        if (isStrongHand) {
          newWeight *= 1.8;
        } else if (isDraw) {
          newWeight *= 1.2;
        } else {
          newWeight *= 0.3; // Bluffs still possible
        }
      } else if (action === "call") {
        // Calling: marginal hands, draws, slowplays
        const isStrongHand = this.isLikelyStrongOnBoard(hand, board);
        const isDraw = this.isLikelyDraw(hand, board);
        
        if (isStrongHand) {
          newWeight *= 0.8; // Some slowplay
        } else if (isDraw) {
          newWeight *= 1.5; // Draws call often
        } else {
          newWeight *= 1.0; // Medium strength
        }
      } else if (action === "check") {
        // Checking: weak hands, medium hands, some traps
        const isStrongHand = this.isLikelyStrongOnBoard(hand, board);
        
        if (isStrongHand) {
          newWeight *= 0.4; // Rare check-traps
        } else {
          newWeight *= 1.2; // Weak/medium hands
        }
      } else if (action === "fold") {
        // Folded hands have 0 weight
        newWeight = 0;
      }
      
      // Bet size adjustments (larger bets = polarized)
      if (betSize && betSize > 0.75 && action === "raise") {
        const isNutted = this.isLikelyNutted(hand, board);
        if (isNutted || !this.isLikelyStrongOnBoard(hand, board)) {
          newWeight *= 1.3; // Polarized: nuts or air
        } else {
          newWeight *= 0.6; // Less medium strength
        }
      }
      
      narrowed.set(hand, newWeight);
    }
    
    return this.normalizeRange(narrowed);
  }
  
  /**
   * Apply multiway adjustments (tighten ranges)
   */
  adjustForMultiway(range: HandRange, numOpponents: number): HandRange {
    if (numOpponents <= 1) return range;
    
    const adjusted = new Map<string, number>();
    const tighteningFactor = 1 - (numOpponents - 1) * 0.15;
    
    for (const [hand, weight] of range) {
      const isPremium = this.isPremiumHand(hand);
      const newWeight = isPremium 
        ? weight * Math.max(0.8, tighteningFactor + 0.2)
        : weight * Math.max(0.3, tighteningFactor);
      
      adjusted.set(hand, newWeight);
    }
    
    return this.normalizeRange(adjusted);
  }
  
  /**
   * Convert range to array of weighted hands for Monte Carlo
   */
  sampleHandsFromRange(range: HandRange, sampleSize: number): Array<[string, string]> {
    const hands: Array<[string, string]> = [];
    const normalized = this.normalizeRange(range);
    
    const entries = Array.from(normalized.entries())
      .filter(([_, w]) => w > 0.01)
      .sort((a, b) => b[1] - a[1]);
    
    // Weighted sampling
    for (let i = 0; i < sampleSize && i < entries.length; i++) {
      const [hand, _] = entries[i];
      const combos = this.handToCombos(hand);
      if (combos.length > 0) {
        const randomCombo = combos[Math.floor(Math.random() * combos.length)];
        hands.push(randomCombo);
      }
    }
    
    return hands;
  }
  
  // ===== Position-based opening ranges =====
  
  private getOpeningRange(position: string): HandRange {
    const range = new Map<string, number>();
    const allHands = this.getAllHands();
    
    const openingFrequencies: Record<string, number> = {
      "UTG": 0.14,
      "MP": 0.18,
      "HJ": 0.22,
      "CO": 0.28,
      "BTN": 0.45,
      "SB": 0.38,
      "BB": 0.00
    };
    
    const freq = openingFrequencies[position] || 0.20;
    const sortedHands = this.sortHandsByStrength(allHands);
    const cutoff = Math.floor(sortedHands.length * freq);
    
    for (let i = 0; i < sortedHands.length; i++) {
      const hand = sortedHands[i];
      if (i < cutoff) {
        range.set(hand, 1.0);
      } else if (i < cutoff + 20) {
        // Mixed region
        range.set(hand, (cutoff + 20 - i) / 20);
      } else {
        range.set(hand, 0.0);
      }
    }
    
    return range;
  }
  
  private get3BetRange(position: string, facing: string): HandRange {
    const range = new Map<string, number>();
    const allHands = this.getAllHands();
    const sortedHands = this.sortHandsByStrength(allHands);
    
    // 3bet is polarized: premium + some bluffs
    const premiumCutoff = Math.floor(sortedHands.length * 0.08);
    const bluffStart = Math.floor(sortedHands.length * 0.75);
    
    for (let i = 0; i < sortedHands.length; i++) {
      const hand = sortedHands[i];
      
      if (i < premiumCutoff) {
        range.set(hand, 0.9); // Premium value
      } else if (i >= bluffStart && i < bluffStart + 15) {
        range.set(hand, 0.4); // Polarized bluffs
      } else {
        range.set(hand, 0.0);
      }
    }
    
    return range;
  }
  
  private getCallingRange(position: string, facing: string): HandRange {
    const range = new Map<string, number>();
    const allHands = this.getAllHands();
    const sortedHands = this.sortHandsByStrength(allHands);
    
    // Calling range: medium strength, speculative hands
    const startCutoff = Math.floor(sortedHands.length * 0.10);
    const endCutoff = Math.floor(sortedHands.length * 0.45);
    
    for (let i = 0; i < sortedHands.length; i++) {
      const hand = sortedHands[i];
      
      if (i >= startCutoff && i < endCutoff) {
        const suited = hand.endsWith("s");
        const weight = suited ? 0.85 : 0.65;
        range.set(hand, weight);
      } else {
        range.set(hand, 0.0);
      }
    }
    
    return range;
  }
  
  private getDefaultTightRange(): HandRange {
    const range = new Map<string, number>();
    const premium = ["AA", "KK", "QQ", "JJ", "TT", "AKs", "AQs", "AKo"];
    
    for (const hand of premium) {
      range.set(hand, 1.0);
    }
    
    return range;
  }
  
  // ===== Helper methods =====
  
  private getAllHands(): string[] {
    const ranks = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"];
    const hands: string[] = [];
    
    for (let i = 0; i < ranks.length; i++) {
      for (let j = i; j < ranks.length; j++) {
        if (i === j) {
          hands.push(`${ranks[i]}${ranks[j]}`);
        } else {
          hands.push(`${ranks[i]}${ranks[j]}s`);
          hands.push(`${ranks[i]}${ranks[j]}o`);
        }
      }
    }
    
    return hands;
  }
  
  private sortHandsByStrength(hands: string[]): string[] {
    return hands.sort((a, b) => this.handStrength(b) - this.handStrength(a));
  }
  
  private handStrength(hand: string): number {
    const ranks = "AKQJT98765432";
    const r1 = ranks.indexOf(hand[0]);
    const r2 = ranks.indexOf(hand[1]);
    const pair = hand[0] === hand[1];
    const suited = hand.endsWith("s");
    
    let strength = 0;
    if (pair) strength += 50 - r1 * 3;
    else {
      strength += (12 - r1) * 2 + (12 - r2);
      if (suited) strength += 4;
    }
    
    return strength;
  }
  
  private isPremiumHand(hand: string): boolean {
    const premium = ["AA", "KK", "QQ", "JJ", "AKs", "AKo"];
    return premium.includes(hand);
  }
  
  private isLikelyStrongOnBoard(hand: string, board: string[]): boolean {
    // Simplified: check for pairs with board
    if (hand[0] === hand[1]) return true; // Pocket pair
    const boardRanks = new Set(board.map(c => c[0]));
    return boardRanks.has(hand[0]) || boardRanks.has(hand[1]);
  }
  
  private isLikelyDraw(hand: string, board: string[]): boolean {
    const suited = hand.endsWith("s");
    if (!suited) return false;
    
    const boardSuits: Record<string, number> = {};
    for (const card of board) {
      boardSuits[card[1]] = (boardSuits[card[1]] || 0) + 1;
    }
    
    return Math.max(...Object.values(boardSuits)) >= 2;
  }
  
  private isLikelyNutted(hand: string, board: string[]): boolean {
    // Simplified: AA/KK/top pair
    return hand === "AA" || hand === "KK";
  }
  
  private normalizeRange(range: HandRange): HandRange {
    const total = Array.from(range.values()).reduce((sum, w) => sum + w, 0);
    if (total < 0.01) return range;
    
    const normalized = new Map<string, number>();
    for (const [hand, weight] of range) {
      normalized.set(hand, weight / total);
    }
    return normalized;
  }
  
  private handToCombos(hand: string): Array<[string, string]> {
    const suits = ["s", "h", "d", "c"];
    const combos: Array<[string, string]> = [];
    
    if (hand.length === 2) {
      // Pair
      for (let i = 0; i < suits.length; i++) {
        for (let j = i + 1; j < suits.length; j++) {
          combos.push([`${hand[0]}${suits[i]}`, `${hand[1]}${suits[j]}`]);
        }
      }
    } else if (hand.endsWith("s")) {
      // Suited
      for (const suit of suits) {
        combos.push([`${hand[0]}${suit}`, `${hand[1]}${suit}`]);
      }
    } else {
      // Offsuit
      for (let i = 0; i < suits.length; i++) {
        for (let j = 0; j < suits.length; j++) {
          if (i !== j) {
            combos.push([`${hand[0]}${suits[i]}`, `${hand[1]}${suits[j]}`]);
          }
        }
      }
    }
    
    return combos;
  }
}
