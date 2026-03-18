// Hand ranking constants

export enum HandRank {
  ROYAL_FLUSH = 10,
  STRAIGHT_FLUSH = 9,
  FOUR_OF_A_KIND = 8,
  FULL_HOUSE = 7,
  FLUSH = 6,
  STRAIGHT = 5,
  THREE_OF_A_KIND = 4,
  TWO_PAIR = 3,
  ONE_PAIR = 2,
  HIGH_CARD = 1,
}

export const HAND_RANK_NAMES: Record<HandRank, string> = {
  [HandRank.ROYAL_FLUSH]: 'Royal Flush',
  [HandRank.STRAIGHT_FLUSH]: 'Straight Flush',
  [HandRank.FOUR_OF_A_KIND]: 'Four of a Kind',
  [HandRank.FULL_HOUSE]: 'Full House',
  [HandRank.FLUSH]: 'Flush',
  [HandRank.STRAIGHT]: 'Straight',
  [HandRank.THREE_OF_A_KIND]: 'Three of a Kind',
  [HandRank.TWO_PAIR]: 'Two Pair',
  [HandRank.ONE_PAIR]: 'One Pair',
  [HandRank.HIGH_CARD]: 'High Card',
};

export interface HandEvaluation {
  rank: HandRank;
  rankName: string;
  value: number; // For comparison
  cards: string[]; // The 5 cards forming the hand
  kickers: string[]; // Remaining cards for tie-breaking
}
