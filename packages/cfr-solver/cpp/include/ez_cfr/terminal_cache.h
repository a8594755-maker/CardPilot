#pragma once

#include "types.h"
#include <vector>

namespace ez_cfr {

// O(n) showdown evaluation cache for a specific river board.
// Pre-sorted by hand value for prefix-sum computation.
struct TerminalCache {
    uint32_t nc;                        // num combos
    std::vector<int32_t> comboCards;    // [nc * 2]: flat c1, c2 pairs
    std::vector<double>  handValues;    // [nc]: pre-computed hand strength
    std::vector<int32_t> sortedIndices; // [nc]: indices sorted by handValue (ascending)
    std::vector<int32_t> rankStart;     // [nc]: first sorted index with same value as combo i
    std::vector<int32_t> rankEnd;       // [nc]: last sorted index with same value as combo i

    // Per-card combo lists for blocker exclusion
    // cardCombos[card * MAX_COMBOS_PER_CARD ... + cardCombosLen[card]]
    std::vector<int32_t> cardCombos;    // [52 * MAX_COMBOS_PER_CARD]
    std::vector<int32_t> cardCombosLen; // [52]
};

// Reusable scratch buffers for showdown/fold EV computation
struct StreetBufs {
    std::vector<double> prefixReach;    // [maxNC]
    std::vector<double> cardReach;      // [52]

    StreetBufs() : cardReach(52, 0.0) {}
    StreetBufs(uint32_t maxNC) : prefixReach(maxNC, 0.0), cardReach(52, 0.0) {}
};

} // namespace ez_cfr
