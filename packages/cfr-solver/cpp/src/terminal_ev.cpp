#include "ez_cfr/terminal_cache.h"
#include "ez_cfr/types.h"

namespace ez_cfr {

// O(n) showdown EV with prefix sums + blocker exclusion
void computeShowdownEVCached(
    const TerminalCache& cache,
    StreetBufs& bufs,
    float pot,
    float s0, float s1,
    const float* oopReach,
    const float* ipReach,
    int traverser,
    float* outEV)
{
    const uint32_t nc = cache.nc;
    const float startTotal = (s0 + s1 + pot) / 2.0f;
    const float tStack = (traverser == 0) ? s0 : s1;
    const float winPayoff  = tStack + pot - startTotal;
    const float losePayoff = tStack - startTotal;
    const float tiePayoff  = tStack + pot / 2.0f - startTotal;
    const float* oppReach  = (traverser == 0) ? ipReach : oopReach;

    // Step 1: Prefix sums of opponent reach in sorted order
    double totalOppReach = 0.0;
    for (uint32_t k = 0; k < nc; k++) {
        int idx = cache.sortedIndices[k];
        totalOppReach += oppReach[idx];
        bufs.prefixReach[k] = totalOppReach;
    }

    // Step 2: Per-combo EV with blocker exclusion
    for (uint32_t i = 0; i < nc; i++) {
        int c1 = cache.comboCards[i * 2];
        int c2 = cache.comboCards[i * 2 + 1];
        int rs = cache.rankStart[i];
        int re = cache.rankEnd[i];

        double totalWin = (rs > 0) ? bufs.prefixReach[rs - 1] : 0.0;
        double totalTie = bufs.prefixReach[re] - totalWin;
        double totalLose = totalOppReach - bufs.prefixReach[re];

        // Exclude blocked combos (share a card with i)
        double blockedWin = 0.0, blockedTie = 0.0, blockedLose = 0.0;
        double myVal = cache.handValues[i];

        // Combos sharing card c1
        int len1 = cache.cardCombosLen[c1];
        for (int k = 0; k < len1; k++) {
            int j = cache.cardCombos[c1 * MAX_COMBOS_PER_CARD + k];
            float oppR = oppReach[j];
            if (oppR == 0.0f) continue;
            double val = cache.handValues[j];
            if (val < myVal) blockedWin += oppR;
            else if (val == myVal) blockedTie += oppR;
            else blockedLose += oppR;
        }

        // Combos sharing card c2
        int len2 = cache.cardCombosLen[c2];
        for (int k = 0; k < len2; k++) {
            int j = cache.cardCombos[c2 * MAX_COMBOS_PER_CARD + k];
            if (j == (int)i) continue; // avoid double-counting self
            float oppR = oppReach[j];
            if (oppR == 0.0f) continue;
            double val = cache.handValues[j];
            if (val < myVal) blockedWin += oppR;
            else if (val == myVal) blockedTie += oppR;
            else blockedLose += oppR;
        }

        outEV[i] = (float)((totalWin - blockedWin) * winPayoff
                          + (totalTie - blockedTie) * tiePayoff
                          + (totalLose - blockedLose) * losePayoff);
    }
}

// O(n) fold EV with card-reach approach
void computeFoldEVFast(
    const int32_t* comboCards,   // [nc * 2]
    const int32_t* cardCombos,   // [52 * MAX_COMBOS_PER_CARD]
    const int32_t* cardCombosLen,// [52]
    StreetBufs& bufs,
    uint32_t nc,
    float pot,
    float s0, float s1,
    int traverser,
    int folder,
    const float* oopReach,
    const float* ipReach,
    float* outEV)
{
    const float startTotal = (s0 + s1 + pot) / 2.0f;
    const float tStack = (traverser == 0) ? s0 : s1;
    const float payoff = (traverser == folder)
        ? (tStack - startTotal)
        : (tStack + pot - startTotal);
    const float* oppReach = (traverser == 0) ? ipReach : oopReach;

    double totalOppReach = 0.0;
    for (uint32_t i = 0; i < nc; i++) totalOppReach += oppReach[i];

    // Per-card reach
    bufs.cardReach.assign(52, 0.0);
    for (int card = 0; card < 52; card++) {
        int len = cardCombosLen[card];
        double sum = 0.0;
        for (int k = 0; k < len; k++) {
            sum += oppReach[cardCombos[card * MAX_COMBOS_PER_CARD + k]];
        }
        bufs.cardReach[card] = sum;
    }

    // Per-combo fold EV
    for (uint32_t i = 0; i < nc; i++) {
        int c1 = comboCards[i * 2];
        int c2 = comboCards[i * 2 + 1];
        double blocked = bufs.cardReach[c1] + bufs.cardReach[c2] - oppReach[i];
        outEV[i] = payoff * (float)(totalOppReach - blocked);
    }
}

} // namespace ez_cfr
