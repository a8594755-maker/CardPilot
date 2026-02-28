import { type Card } from "./card-utils.js";
import { type HandEvaluation } from "./hand-rank.js";
/**
 * 從 7 張牌中找出最強的 5 張組合
 */
export declare function evaluateBestHand(cards: Card[]): HandEvaluation;
/**
 * 比較兩手牌的大小
 * @returns positive if hand1 wins, negative if hand2 wins, 0 if tie
 */
export declare function compareHands(hand1: HandEvaluation, hand2: HandEvaluation): number;
/**
 * 從多個玩家的牌中找出贏家
 */
export declare function findWinners(players: Array<{
    seat: number;
    cards: Card[];
}>): Array<{
    seat: number;
    evaluation: HandEvaluation;
}>;
