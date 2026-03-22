#include "ez_cfr/cfr_engine.h"
#include <cstring>
#include <cmath>
#include <algorithm>

namespace ez_cfr {

void CfrSolver::solveRiverBatch(
    const int32_t* turnBoard, int turnBoardLen,
    const int32_t* turnComboCards, uint32_t turnNC,
    const float* oopReach, const float* ipReach,
    const uint8_t* innerNodePlayer, const uint8_t* innerNodeNumActions,
    const uint32_t* innerNodeActionOffset, const int32_t* innerChildNodeId,
    const float* innerTerminalPot, const float* innerTerminalStacks,
    const uint8_t* innerTerminalIsShowdown, const int8_t* innerTerminalFolder,
    uint32_t innerNumNodes, uint32_t innerNumTerminals, uint32_t innerTotalActions,
    uint32_t iterations,
    float rakePercentage, float rakeCap,
    float potOffset,
    float* outCfvOOP, float* outCfvIP)
{
    // Set solver state for full enumeration
    mccfr_ = false;
    iterWeight_ = 1.0f;

    // Build inner tree template
    FlatTree innerSrc{innerNumNodes, innerNumTerminals, innerTotalActions,
                      innerNodePlayer, innerNodeNumActions, innerNodeActionOffset,
                      nullptr, nullptr,
                      innerChildNodeId, innerTerminalPot, innerTerminalIsShowdown,
                      innerTerminalFolder, innerTerminalStacks};
    OwnedFlatTree innerTemplate = OwnedFlatTree::clone(innerSrc);

    // Build turn ValidCombos
    ValidCombos turnCombos;
    turnCombos.numCombos = turnNC;
    turnCombos.comboCards.assign(turnComboCards, turnComboCards + turnNC * 2);
    turnCombos.cardCombos.resize(52 * MAX_COMBOS_PER_CARD, -1);
    turnCombos.cardCombosLen.resize(52, 0);
    buildCardCombos(turnCombos.comboCards.data(), turnNC,
                    turnCombos.cardCombos.data(), turnCombos.cardCombosLen.data());

    // Enumerate dealable river cards
    uint8_t dead[52] = {0};
    for (int i = 0; i < turnBoardLen; i++) dead[turnBoard[i]] = 1;
    std::vector<int32_t> riverCards;
    for (int c = 0; c < 52; c++) {
        if (!dead[c]) riverCards.push_back(c);
    }
    uint32_t numRivers = (uint32_t)riverCards.size();

    // Initialize output
    std::memset(outCfvOOP, 0, turnNC * sizeof(float));
    std::memset(outCfvIP, 0, turnNC * sizeof(float));
    std::vector<float> survivalCount(turnNC, 0.0f);

    // Find inner tree max actions for traversal context sizing
    uint32_t innerMaxActions = 0;
    for (uint32_t n = 0; n < innerNumNodes; n++) {
        innerMaxActions = std::max(innerMaxActions, (uint32_t)innerNodeNumActions[n]);
    }

    // Conservative upper bound for river NC: C(47,2) = 1081
    const uint32_t maxRNC = 1081;

    // Allocate traversal buffers (reused across all rivers)
    riverCtx_ = TraversalCtx::create(innerNumNodes, innerMaxActions, maxRNC);
    riverBufs_ = StreetBufs(maxRNC);

    std::vector<float> chanceOop(maxRNC);
    std::vector<float> chanceIp(maxRNC);
    std::vector<float> oopEV(maxRNC);
    std::vector<float> ipEV(maxRNC);
    std::vector<float> oopR(maxRNC);
    std::vector<float> ipR(maxRNC);

    // Process each river card
    for (uint32_t ri = 0; ri < numRivers; ri++) {
        int32_t riverCard = riverCards[ri];

        // Build river combo mapping
        ComboMapping mapping = buildComboMapping(turnCombos, turnBoard, turnBoardLen, riverCard);
        uint32_t riverNC = mapping.childNC;

        // Remap reaches from turn to river combo space
        for (uint32_t ci = 0; ci < riverNC; ci++) {
            chanceOop[ci] = oopReach[mapping.childToParent[ci]];
            chanceIp[ci] = ipReach[mapping.childToParent[ci]];
        }

        // Check for dead reaches
        bool oopAlive = false, ipAlive = false;
        for (uint32_t ci = 0; ci < riverNC; ci++) {
            if (chanceOop[ci] >= PRUNE_THRESHOLD) oopAlive = true;
            if (chanceIp[ci] >= PRUNE_THRESHOLD) ipAlive = true;
            if (oopAlive && ipAlive) break;
        }

        if (!oopAlive || !ipAlive) {
            // Count survival but skip solving
            for (uint32_t ci = 0; ci < riverNC; ci++) {
                survivalCount[mapping.childToParent[ci]] += 1.0f;
            }
            continue;
        }

        // Clone tree for this river
        OwnedFlatTree riverTree = OwnedFlatTree::clone(innerTemplate.view());
        if (rakePercentage > 0.0f) applyRakeToTree(riverTree, rakePercentage, rakeCap);

        // Create ArrayStore for this river
        ArrayStore riverStore(innerNumNodes, innerTotalActions, riverNC,
                              riverTree.nodeNumActions.data());

        // Build river board
        std::vector<int32_t> riverBoard(turnBoard, turnBoard + turnBoardLen);
        riverBoard.push_back(riverCard);

        // Build terminal cache (hand eval + sorted indices for O(n) showdown)
        TerminalCache cache = buildTerminalCache(
            mapping.childCombos, riverBoard.data(), (int)riverBoard.size());

        // Build RiverSubtree
        RiverSubtree rs{
            riverCard, std::move(mapping),
            std::move(riverTree), std::move(riverStore),
            std::move(cache), riverNC
        };

        // Run CFR iterations
        for (uint32_t iter = 0; iter < iterations; iter++) {
            uint32_t t = iter + 1;
            iterWeight_ = 1.0f;

            // OOP traversal
            std::copy_n(chanceOop.data(), riverNC, oopR.data());
            std::copy_n(chanceIp.data(), riverNC, ipR.data());
            cfrTraverseRiver(rs, oopR.data(), ipR.data(), 0, oopEV.data(), potOffset);

            // IP traversal
            std::copy_n(chanceOop.data(), riverNC, oopR.data());
            std::copy_n(chanceIp.data(), riverNC, ipR.data());
            cfrTraverseRiver(rs, oopR.data(), ipR.data(), 1, ipEV.data(), potOffset);

            // DCFR discounting
            float factor = (float)(t * t) / (float)((t + 1) * (t + 1));
            rs.store.discountStrategySums(factor);
        }

        // Accumulate last-iteration EVs back to turn combo space
        for (uint32_t ci = 0; ci < rs.childNC; ci++) {
            int32_t pi = rs.mapping.childToParent[ci];
            outCfvOOP[pi] += oopEV[ci];
            outCfvIP[pi] += ipEV[ci];
            survivalCount[pi] += 1.0f;
        }
    }

    // Average across surviving rivers
    for (uint32_t pi = 0; pi < turnNC; pi++) {
        if (survivalCount[pi] > 0.0f) {
            outCfvOOP[pi] /= survivalCount[pi];
            outCfvIP[pi] /= survivalCount[pi];
        }
    }
}

} // namespace ez_cfr
