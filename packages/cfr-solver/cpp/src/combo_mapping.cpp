#include "ez_cfr/combo_mapping.h"
#include "ez_cfr/hand_eval.h"
#include "ez_cfr/terminal_cache.h"
#include <cstring>
#include <algorithm>
#include <numeric>

namespace ez_cfr {

// comboIndex: maps (c1, c2) with c1 < c2 to a unique index 0..1325
static int comboIndex(int c1, int c2) {
    // Triangular index: c1 * (103 - c1) / 2 + c2 - c1 - 1
    return c1 * (103 - c1) / 2 + c2 - c1 - 1;
}

ValidCombos enumerateValidCombos(const int32_t* board, int boardLen) {
    uint8_t dead[52] = {0};
    for (int i = 0; i < boardLen; i++) dead[board[i]] = 1;

    ValidCombos vc;
    std::vector<int> ids;

    for (int c1 = 0; c1 < 52; c1++) {
        if (dead[c1]) continue;
        for (int c2 = c1 + 1; c2 < 52; c2++) {
            if (dead[c2]) continue;
            vc.comboCards.push_back(c1);
            vc.comboCards.push_back(c2);
            ids.push_back(comboIndex(c1, c2));
        }
    }

    vc.numCombos = (uint32_t)(ids.size());

    // Build globalToLocal mapping
    std::vector<int16_t> globalToLocal(1326, -1);
    for (uint32_t i = 0; i < vc.numCombos; i++) {
        globalToLocal[ids[i]] = (int16_t)i;
    }

    // Build cardCombos (per-card combo index lists)
    vc.cardCombos.resize(52 * MAX_COMBOS_PER_CARD, -1);
    vc.cardCombosLen.resize(52, 0);
    for (uint32_t i = 0; i < vc.numCombos; i++) {
        int c1 = vc.comboCards[i * 2];
        int c2 = vc.comboCards[i * 2 + 1];
        int len1 = vc.cardCombosLen[c1];
        int len2 = vc.cardCombosLen[c2];
        if (len1 < MAX_COMBOS_PER_CARD) {
            vc.cardCombos[c1 * MAX_COMBOS_PER_CARD + len1] = (int32_t)i;
            vc.cardCombosLen[c1] = len1 + 1;
        }
        if (len2 < MAX_COMBOS_PER_CARD) {
            vc.cardCombos[c2 * MAX_COMBOS_PER_CARD + len2] = (int32_t)i;
            vc.cardCombosLen[c2] = len2 + 1;
        }
    }

    return vc;
}

void buildCardCombos(const int32_t* comboCards, uint32_t nc,
                     int32_t* cardCombos, int32_t* cardCombosLen) {
    std::memset(cardCombosLen, 0, 52 * sizeof(int32_t));
    for (uint32_t i = 0; i < nc; i++) {
        int c1 = comboCards[i * 2];
        int c2 = comboCards[i * 2 + 1];
        int len1 = cardCombosLen[c1];
        int len2 = cardCombosLen[c2];
        if (len1 < MAX_COMBOS_PER_CARD) {
            cardCombos[c1 * MAX_COMBOS_PER_CARD + len1] = (int32_t)i;
            cardCombosLen[c1] = len1 + 1;
        }
        if (len2 < MAX_COMBOS_PER_CARD) {
            cardCombos[c2 * MAX_COMBOS_PER_CARD + len2] = (int32_t)i;
            cardCombosLen[c2] = len2 + 1;
        }
    }
}

ComboMapping buildComboMapping(const ValidCombos& parentCombos,
                               const int32_t* parentBoard, int parentBoardLen,
                               int32_t newCard) {
    // Build child board
    std::vector<int32_t> childBoard(parentBoard, parentBoard + parentBoardLen);
    childBoard.push_back(newCard);

    // Enumerate child combos
    ValidCombos childCombos = enumerateValidCombos(childBoard.data(), (int)childBoard.size());
    uint32_t childNC = childCombos.numCombos;
    uint32_t parentNC = parentCombos.numCombos;

    // Build globalToLocal for child
    std::vector<int16_t> childGlobalToLocal(1326, -1);
    for (uint32_t i = 0; i < childNC; i++) {
        int c1 = childCombos.comboCards[i * 2];
        int c2 = childCombos.comboCards[i * 2 + 1];
        childGlobalToLocal[comboIndex(c1, c2)] = (int16_t)i;
    }

    // Build parent comboIds (globalIndex for each parent combo)
    std::vector<int> parentComboIds(parentNC);
    for (uint32_t i = 0; i < parentNC; i++) {
        int c1 = parentCombos.comboCards[i * 2];
        int c2 = parentCombos.comboCards[i * 2 + 1];
        parentComboIds[i] = comboIndex(c1, c2);
    }

    ComboMapping mapping;
    mapping.childNC = childNC;
    mapping.parentNC = parentNC;
    mapping.childToParent.resize(childNC, -1);
    mapping.parentToChild.resize(parentNC, -1);

    for (uint32_t pi = 0; pi < parentNC; pi++) {
        int c1 = parentCombos.comboCards[pi * 2];
        int c2 = parentCombos.comboCards[pi * 2 + 1];
        if (c1 == newCard || c2 == newCard) continue;

        int globalId = parentComboIds[pi];
        int16_t childIdx = childGlobalToLocal[globalId];
        if (childIdx >= 0) {
            mapping.parentToChild[pi] = childIdx;
            mapping.childToParent[childIdx] = pi;
        }
    }

    mapping.childCombos = std::move(childCombos);
    return mapping;
}

// Build terminal cache for a specific river board
TerminalCache buildTerminalCache(const ValidCombos& combos,
                                 const int32_t* board, int boardLen) {
    uint32_t nc = combos.numCombos;
    TerminalCache cache;
    cache.nc = nc;
    cache.comboCards = combos.comboCards;

    // Evaluate hand values
    cache.handValues.resize(nc);
    for (uint32_t i = 0; i < nc; i++) {
        int h0 = combos.comboCards[i * 2];
        int h1 = combos.comboCards[i * 2 + 1];
        cache.handValues[i] = evaluateHandBoard(h0, h1, board, boardLen);
    }

    // Sort indices by hand value (ascending)
    cache.sortedIndices.resize(nc);
    std::iota(cache.sortedIndices.begin(), cache.sortedIndices.end(), 0);
    std::sort(cache.sortedIndices.begin(), cache.sortedIndices.end(),
              [&](int a, int b) { return cache.handValues[a] < cache.handValues[b]; });

    // Build rankStart / rankEnd
    cache.rankStart.resize(nc);
    cache.rankEnd.resize(nc);
    int start = 0;
    while (start < (int)nc) {
        int end = start;
        double val = cache.handValues[cache.sortedIndices[start]];
        while (end < (int)nc && cache.handValues[cache.sortedIndices[end]] == val) end++;
        for (int k = start; k < end; k++) {
            cache.rankStart[cache.sortedIndices[k]] = start;
            cache.rankEnd[cache.sortedIndices[k]] = end - 1;
        }
        start = end;
    }

    // Build cardCombos
    cache.cardCombos.resize(52 * MAX_COMBOS_PER_CARD, -1);
    cache.cardCombosLen.resize(52, 0);
    for (uint32_t i = 0; i < nc; i++) {
        int c1 = combos.comboCards[i * 2];
        int c2 = combos.comboCards[i * 2 + 1];
        int len1 = cache.cardCombosLen[c1];
        int len2 = cache.cardCombosLen[c2];
        if (len1 < MAX_COMBOS_PER_CARD) {
            cache.cardCombos[c1 * MAX_COMBOS_PER_CARD + len1] = (int32_t)i;
            cache.cardCombosLen[c1] = len1 + 1;
        }
        if (len2 < MAX_COMBOS_PER_CARD) {
            cache.cardCombos[c2 * MAX_COMBOS_PER_CARD + len2] = (int32_t)i;
            cache.cardCombosLen[c2] = len2 + 1;
        }
    }

    return cache;
}

} // namespace ez_cfr
