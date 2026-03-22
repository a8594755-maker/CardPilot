#include "ez_cfr/hand_eval.h"
#include <cstdint>
#include <algorithm>

namespace ez_cfr {

// Value encoding multipliers
static constexpr double HAND_MUL = 10000000000.0;
static constexpr double R0 = 100000000.0;
static constexpr double R1 = 1000000.0;
static constexpr double R2 = 10000.0;
static constexpr double R3 = 100.0;
static constexpr double R4 = 1.0;

// Hand rank constants
static constexpr int ROYAL_FLUSH     = 10;
static constexpr int STRAIGHT_FLUSH  = 9;
static constexpr int FOUR_OF_A_KIND  = 8;
static constexpr int FULL_HOUSE      = 7;
static constexpr int FLUSH_RANK      = 6;
static constexpr int STRAIGHT_RANK   = 5;
static constexpr int THREE_OF_A_KIND = 4;
static constexpr int TWO_PAIR        = 3;
static constexpr int ONE_PAIR        = 2;
static constexpr int HIGH_CARD       = 1;

// Extract 5 ranks from bitmask in descending order and encode as value
static double ranksFromBitsValue(int bits) {
    double value = 0.0;
    int pos = 0;
    for (int r = 12; r >= 0 && pos < 5; r--) {
        if (bits & (1 << r)) {
            switch (pos) {
                case 0: value += r * R0; break;
                case 1: value += r * R1; break;
                case 2: value += r * R2; break;
                case 3: value += r * R3; break;
                case 4: value += r * R4; break;
            }
            pos++;
        }
    }
    return value;
}

double evaluate5Fast(int c1, int c2, int c3, int c4, int c5) {
    // Extract ranks and suits
    int r1 = c1 >> 2, s1 = c1 & 3;
    int r2 = c2 >> 2, s2 = c2 & 3;
    int r3 = c3 >> 2, s3 = c3 & 3;
    int r4 = c4 >> 2, s4 = c4 & 3;
    int r5 = c5 >> 2, s5 = c5 & 3;

    // Flush check
    bool isFlush = (s1 == s2 && s2 == s3 && s3 == s4 && s4 == s5);

    // Rank bitmask for straight detection
    int rankBits = (1 << r1) | (1 << r2) | (1 << r3) | (1 << r4) | (1 << r5);

    // Popcount — number of unique ranks
    int uniqueCount = 0;
    int tmp = rankBits;
    while (tmp) { uniqueCount++; tmp &= tmp - 1; }

    // Straight detection
    int straightHigh = -1;
    if (uniqueCount == 5) {
        // Wheel: A-2-3-4-5
        if ((rankBits & 0x100F) == 0x100F) {
            straightHigh = 3;
        } else {
            for (int hi = 12; hi >= 4; hi--) {
                int mask = 0x1F << (hi - 4);
                if ((rankBits & mask) == mask) {
                    straightHigh = hi;
                    break;
                }
            }
        }
    }

    // Straight Flush / Royal Flush
    if (isFlush && straightHigh >= 0) {
        int handRank = (straightHigh == 12) ? ROYAL_FLUSH : STRAIGHT_FLUSH;
        return handRank * HAND_MUL + straightHigh * R0;
    }

    // Build rank histogram
    uint8_t rc[13] = {0};
    rc[r1]++; rc[r2]++; rc[r3]++; rc[r4]++; rc[r5]++;

    // Classify hand
    int quads = -1, trips = -1, pair1 = -1, pair2 = -1;
    for (int r = 12; r >= 0; r--) {
        int cnt = rc[r];
        if (cnt == 4) quads = r;
        else if (cnt == 3) trips = r;
        else if (cnt == 2) {
            if (pair1 < 0) pair1 = r; else pair2 = r;
        }
    }

    // Four of a Kind
    if (quads >= 0) {
        int kicker = 0;
        for (int r = 12; r >= 0; r--) {
            if (rc[r] > 0 && r != quads) { kicker = r; break; }
        }
        return FOUR_OF_A_KIND * HAND_MUL + quads * R0 + kicker * R1;
    }

    // Full House
    if (trips >= 0 && pair1 >= 0) {
        return FULL_HOUSE * HAND_MUL + trips * R0 + pair1 * R1;
    }

    // Flush
    if (isFlush) {
        return FLUSH_RANK * HAND_MUL + ranksFromBitsValue(rankBits);
    }

    // Straight
    if (straightHigh >= 0) {
        return STRAIGHT_RANK * HAND_MUL + straightHigh * R0;
    }

    // Three of a Kind
    if (trips >= 0) {
        int k1 = -1, k2 = -1;
        for (int r = 12; r >= 0; r--) {
            if (rc[r] == 1) {
                if (k1 < 0) k1 = r; else if (k2 < 0) { k2 = r; break; }
            }
        }
        return THREE_OF_A_KIND * HAND_MUL + trips * R0 + k1 * R1 + k2 * R2;
    }

    // Two Pair
    if (pair1 >= 0 && pair2 >= 0) {
        int kicker = 0;
        for (int r = 12; r >= 0; r--) {
            if (rc[r] == 1) { kicker = r; break; }
        }
        return TWO_PAIR * HAND_MUL + pair1 * R0 + pair2 * R1 + kicker * R2;
    }

    // One Pair
    if (pair1 >= 0) {
        int k1 = -1, k2 = -1, k3 = -1;
        for (int r = 12; r >= 0; r--) {
            if (rc[r] == 1) {
                if (k1 < 0) k1 = r;
                else if (k2 < 0) k2 = r;
                else if (k3 < 0) { k3 = r; break; }
            }
        }
        return ONE_PAIR * HAND_MUL + pair1 * R0 + k1 * R1 + k2 * R2 + k3 * R3;
    }

    // High Card
    return HIGH_CARD * HAND_MUL + ranksFromBitsValue(rankBits);
}

double evaluateHandBoard(int h0, int h1, const int* board, int boardLen) {
    if (boardLen == 3) {
        return evaluate5Fast(h0, h1, board[0], board[1], board[2]);
    }

    if (boardLen == 4) {
        int b0 = board[0], b1 = board[1], b2 = board[2], b3 = board[3];
        double best = evaluate5Fast(h0, h1, b0, b1, b2);
        double v;
        v = evaluate5Fast(h0, h1, b0, b1, b3); if (v > best) best = v;
        v = evaluate5Fast(h0, h1, b0, b2, b3); if (v > best) best = v;
        v = evaluate5Fast(h0, h1, b1, b2, b3); if (v > best) best = v;
        v = evaluate5Fast(h0, b0, b1, b2, b3); if (v > best) best = v;
        v = evaluate5Fast(h1, b0, b1, b2, b3); if (v > best) best = v;
        return best;
    }

    if (boardLen == 5) {
        int cards[7] = {h0, h1, board[0], board[1], board[2], board[3], board[4]};
        double best = 0.0;
        for (int i = 0; i < 3; i++)
            for (int j = i+1; j < 4; j++)
                for (int k = j+1; k < 5; k++)
                    for (int l = k+1; l < 6; l++)
                        for (int m = l+1; m < 7; m++) {
                            double v = evaluate5Fast(cards[i], cards[j], cards[k], cards[l], cards[m]);
                            if (v > best) best = v;
                        }
        return best;
    }

    return 0.0;
}

} // namespace ez_cfr
