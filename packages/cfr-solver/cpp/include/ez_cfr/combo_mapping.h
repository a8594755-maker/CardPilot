#pragma once

#include "types.h"
#include <vector>

namespace ez_cfr {

// Valid combos for a specific board
struct ValidCombos {
    std::vector<int32_t> comboCards;  // [nc * 2]: flat c1, c2 pairs
    uint32_t numCombos;

    // Per-card combo lists (for fast O(n) fold/showdown eval)
    std::vector<int32_t> cardCombos;     // [52 * MAX_COMBOS_PER_CARD]
    std::vector<int32_t> cardCombosLen;  // [52]
};

// Mapping between parent and child combos across street transitions
struct ComboMapping {
    uint32_t childNC;
    uint32_t parentNC;
    std::vector<int32_t> childToParent;   // [childNC]: child idx -> parent idx
    std::vector<int32_t> parentToChild;   // [parentNC]: parent idx -> child idx (-1 if blocked)
    ValidCombos childCombos;              // child street combos
};

// Enumerate all valid 2-card combos for a board
ValidCombos enumerateValidCombos(const int32_t* board, int boardLen);

// Build card-to-combo index for O(n) blocker exclusion
void buildCardCombos(const int32_t* comboCards, uint32_t nc,
                     int32_t* cardCombos, int32_t* cardCombosLen);

// Build combo mapping from parent to child after dealing a new card
ComboMapping buildComboMapping(const ValidCombos& parentCombos,
                               const int32_t* parentBoard, int parentBoardLen,
                               int32_t newCard);

} // namespace ez_cfr
