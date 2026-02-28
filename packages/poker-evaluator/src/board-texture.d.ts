import { type Card } from "./card-utils.js";
export interface BoardTexture {
    isPaired: boolean;
    isTwoPair: boolean;
    isTrips: boolean;
    isMonotone: boolean;
    isTwoTone: boolean;
    isRainbow: boolean;
    hasFlushDraw: boolean;
    hasStraightPossible: boolean;
    straightDraws: number;
    highCard: string;
    highCardValue: number;
    wetness: number;
    category: 'dry' | 'semi-wet' | 'wet' | 'very-wet';
}
/**
 * Analyze board texture for strategic decisions
 */
export declare function analyzeBoardTexture(board: Card[]): BoardTexture;
/**
 * Classify hand type on board
 */
export declare function classifyHandOnBoard(heroHand: [Card, Card], board: Card[]): {
    type: 'made_hand' | 'draw' | 'air';
    strength: 'strong' | 'medium' | 'weak';
    description: string;
};
