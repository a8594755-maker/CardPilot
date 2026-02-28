import { type Card } from "./card-utils.js";
export interface EquityResult {
    win: number;
    tie: number;
    lose: number;
    equity: number;
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
export declare function calculateEquity(params: {
    heroHand: [Card, Card];
    villainHands: Array<[Card, Card]>;
    board: Card[];
    simulations?: number;
}): EquityResult;
/**
 * Calculate hand strength (equity vs random hand)
 */
export declare function calculateHandStrength(heroHand: [Card, Card], board: Card[]): number;
/**
 * Calculate pot odds needed for a call to be profitable
 */
export declare function calculatePotOdds(potSize: number, toCall: number): number;
/**
 * Calculate expected value of a call given equity and pot odds
 */
export declare function calculateCallEV(params: {
    potSize: number;
    toCall: number;
    equity: number;
}): number;
/**
 * Calculate outs (cards that improve hand)
 */
export declare function calculateOuts(params: {
    heroHand: [Card, Card];
    board: Card[];
    targetHand: 'flush' | 'straight' | 'set' | 'two_pair' | 'pair';
}): number;
/**
 * Convert outs to equity approximation (Rule of 2 and 4)
 */
export declare function outsToEquity(outs: number, streets: 1 | 2): number;
