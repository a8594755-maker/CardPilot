// Hand ranking constants
export var HandRank;
(function (HandRank) {
    HandRank[HandRank["ROYAL_FLUSH"] = 10] = "ROYAL_FLUSH";
    HandRank[HandRank["STRAIGHT_FLUSH"] = 9] = "STRAIGHT_FLUSH";
    HandRank[HandRank["FOUR_OF_A_KIND"] = 8] = "FOUR_OF_A_KIND";
    HandRank[HandRank["FULL_HOUSE"] = 7] = "FULL_HOUSE";
    HandRank[HandRank["FLUSH"] = 6] = "FLUSH";
    HandRank[HandRank["STRAIGHT"] = 5] = "STRAIGHT";
    HandRank[HandRank["THREE_OF_A_KIND"] = 4] = "THREE_OF_A_KIND";
    HandRank[HandRank["TWO_PAIR"] = 3] = "TWO_PAIR";
    HandRank[HandRank["ONE_PAIR"] = 2] = "ONE_PAIR";
    HandRank[HandRank["HIGH_CARD"] = 1] = "HIGH_CARD";
})(HandRank || (HandRank = {}));
export const HAND_RANK_NAMES = {
    [HandRank.ROYAL_FLUSH]: 'Royal Flush',
    [HandRank.STRAIGHT_FLUSH]: 'Straight Flush',
    [HandRank.FOUR_OF_A_KIND]: 'Four of a Kind',
    [HandRank.FULL_HOUSE]: 'Full House',
    [HandRank.FLUSH]: 'Flush',
    [HandRank.STRAIGHT]: 'Straight',
    [HandRank.THREE_OF_A_KIND]: 'Three of a Kind',
    [HandRank.TWO_PAIR]: 'Two Pair',
    [HandRank.ONE_PAIR]: 'One Pair',
    [HandRank.HIGH_CARD]: 'High Card'
};
