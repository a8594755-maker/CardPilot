export declare const RANKS: string[];
export declare const SUITS: string[];
export type Card = string;
export interface CardDetails {
    rank: string;
    suit: string;
    rankValue: number;
}
export declare function parseCard(card: Card): CardDetails;
export declare function formatCard(rank: string, suit: string): Card;
export declare function isSuited(cards: [Card, Card]): boolean;
export declare function isPair(cards: [Card, Card]): boolean;
/**
 * 正規化手牌表示
 * "AhKh" -> "AKs"
 * "AhKd" -> "AKo"
 * "AhAd" -> "AA"
 */
export declare function normalizeHand(cards: [Card, Card]): string;
/**
 * 生成一副洗牌後的牌組
 */
export declare function createShuffledDeck(seed?: string): Card[];
/**
 * 將牌轉換為 pokersolver 格式
 */
export declare function toSolverCard(card: Card): string;
export declare function toSolverCards(cards: Card[]): string[];
