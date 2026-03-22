#pragma once

#include <cstdint>

namespace ez_cfr {

// Card encoding: index 0-51, rank = index >> 2 (0=2..12=A), suit = index & 3
// Returns numeric value where higher = stronger hand.
// Value encoding: handRank * 1e10 + r0 * 1e8 + r1 * 1e6 + r2 * 1e4 + r3 * 1e2 + r4

double evaluate5Fast(int c1, int c2, int c3, int c4, int c5);

// Evaluate best 5-card hand from hole cards + board (3-5 cards)
double evaluateHandBoard(int h0, int h1, const int* board, int boardLen);

} // namespace ez_cfr
