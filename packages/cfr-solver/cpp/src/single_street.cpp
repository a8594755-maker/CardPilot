// single_street.cpp — Standalone river-batch solver for NN training data mining.
//
// solveTurnRivers() takes a turn board + reaches + river tree template,
// builds all 48 river subtrees, solves each with CFR+, and returns
// averaged per-combo counterfactual values in canonical 1326-space.

#include "ez_cfr/cfr_engine.h"
#include <cstring>
#include <cmath>
#include <algorithm>

namespace ez_cfr {

void CfrSolver::solveTurnRivers(
    const int32_t* turnBoard, int turnBoardLen,
    const uint8_t* innerNodePlayer, const uint8_t* innerNodeNumActions,
    const uint32_t* innerNodeActionOffset, const int32_t* innerChildNodeId,
    const float* innerTerminalPot, const float* innerTerminalStacks,
    const uint8_t* innerTerminalIsShowdown, const int8_t* innerTerminalFolder,
    uint32_t innerNumNodes, uint32_t innerNumTerminals, uint32_t innerTotalActions,
    const float* oopReach1326, const float* ipReach1326,
    float potOffset, float startingPot, float effectiveStack,
    uint32_t iterations,
    float rakePercentage, float rakeCap)
{
    // Store config for traversal callbacks
    startingPot_ = startingPot;
    effectiveStack_ = effectiveStack;
    mccfr_ = false;

    // ── 1. Enumerate valid turn combos ──
    ValidCombos turnCombos = enumerateValidCombos(turnBoard, turnBoardLen);
    uint32_t turnNC = turnCombos.numCombos;

    // ── 2. Map 1326-space reaches → turn-local ──
    std::vector<float> oopReachLocal(turnNC), ipReachLocal(turnNC);
    // Also build global-id mapping for output
    std::vector<int32_t> comboGlobalIds(turnNC);
    for (uint32_t ci = 0; ci < turnNC; ci++) {
        int32_t c1 = turnCombos.comboCards[ci * 2];
        int32_t c2 = turnCombos.comboCards[ci * 2 + 1];
        int32_t hi = std::max(c1, c2);
        int32_t lo = std::min(c1, c2);
        int32_t gid = hi * (hi - 1) / 2 + lo;
        comboGlobalIds[ci] = gid;
        oopReachLocal[ci] = oopReach1326[gid];
        ipReachLocal[ci] = ipReach1326[gid];
    }

    // ── 3. Enumerate dealable river cards ──
    uint8_t dead[52] = {0};
    for (int i = 0; i < turnBoardLen; i++) dead[turnBoard[i]] = 1;
    std::vector<int32_t> riverCards;
    for (int c = 0; c < 52; c++) {
        if (!dead[c]) riverCards.push_back(c);
    }
    uint32_t numRivers = (uint32_t)riverCards.size();

    // ── 4. Build inner tree template ──
    FlatTree innerSrc{innerNumNodes, innerNumTerminals, innerTotalActions,
                      innerNodePlayer, innerNodeNumActions, innerNodeActionOffset,
                      nullptr, nullptr,
                      innerChildNodeId, innerTerminalPot, innerTerminalIsShowdown,
                      innerTerminalFolder, innerTerminalStacks};
    OwnedFlatTree innerTemplate = OwnedFlatTree::clone(innerSrc);

    // Compute max actions for traversal context
    uint32_t innerMaxActions = 0;
    for (uint32_t n = 0; n < innerNumNodes; n++) {
        innerMaxActions = std::max(innerMaxActions, (uint32_t)innerNodeNumActions[n]);
    }

    // ── 5. Build all river subtrees ──
    uint32_t localMaxRiverNC = 0;
    std::vector<RiverSubtree> rivers;
    rivers.reserve(numRivers);

    for (uint32_t ri = 0; ri < numRivers; ri++) {
        int32_t riverCard = riverCards[ri];

        ComboMapping mapping = buildComboMapping(
            turnCombos, turnBoard, turnBoardLen, riverCard);
        uint32_t riverNC = mapping.childNC;
        if (riverNC > localMaxRiverNC) localMaxRiverNC = riverNC;

        OwnedFlatTree riverTree = OwnedFlatTree::clone(innerTemplate.view());
        if (rakePercentage > 0.0f) {
            applyRakeToTree(riverTree, rakePercentage, rakeCap);
        }

        ArrayStore riverStore(innerNumNodes, innerTotalActions, riverNC,
                              riverTree.nodeNumActions.data());

        std::vector<int32_t> riverBoard(turnBoard, turnBoard + turnBoardLen);
        riverBoard.push_back(riverCard);

        TerminalCache cache = buildTerminalCache(
            mapping.childCombos, riverBoard.data(), (int)riverBoard.size());

        rivers.push_back(RiverSubtree{
            riverCard, std::move(mapping),
            std::move(riverTree), std::move(riverStore),
            std::move(cache), riverNC
        });
    }

    // ── 6. Initialize traversal infrastructure ──
    riverCtx_ = TraversalCtx::create(innerNumNodes, innerMaxActions, localMaxRiverNC);
    riverBufs_ = StreetBufs(localMaxRiverNC);

    // Reusable buffers for reach remapping and EV
    std::vector<float> riverOOP(localMaxRiverNC);
    std::vector<float> riverIP(localMaxRiverNC);
    std::vector<float> reachOOPBuf(localMaxRiverNC);
    std::vector<float> reachIPBuf(localMaxRiverNC);
    std::vector<float> resultEV(localMaxRiverNC);

    // Accumulate CFVs in turn-local space
    std::vector<float> cfvOOPLocal(turnNC, 0.0f);
    std::vector<float> cfvIPLocal(turnNC, 0.0f);
    std::vector<float> survivalCount(turnNC, 0.0f);

    // ── 7. Solve each river subtree ──
    for (uint32_t ri = 0; ri < numRivers; ri++) {
        RiverSubtree& rs = rivers[ri];
        uint32_t riverNC = rs.childNC;
        const auto& mapping = rs.mapping;

        // Remap reaches to river combo space
        for (uint32_t ci = 0; ci < riverNC; ci++) {
            riverOOP[ci] = oopReachLocal[mapping.childToParent[ci]];
            riverIP[ci] = ipReachLocal[mapping.childToParent[ci]];
        }

        // Count survival for ALL parent combos that map to this river
        for (uint32_t pi = 0; pi < turnNC; pi++) {
            if (mapping.parentToChild[pi] >= 0) {
                survivalCount[pi] += 1.0f;
            }
        }

        // Skip dead rivers
        bool oopAlive = false, ipAlive = false;
        for (uint32_t i = 0; i < riverNC; i++) {
            if (riverOOP[i] >= PRUNE_THRESHOLD) oopAlive = true;
            if (riverIP[i] >= PRUNE_THRESHOLD) ipAlive = true;
            if (oopAlive && ipAlive) break;
        }
        if (!oopAlive || !ipAlive) continue;

        // Run CFR+ iterations on this river subtree
        for (uint32_t iter = 0; iter < iterations; iter++) {
            uint32_t t = iter + 1;
            iterWeight_ = 1.0f; // DCFR uses unweighted iter, discount after

            // Traversal for OOP
            std::memcpy(reachOOPBuf.data(), riverOOP.data(), riverNC * sizeof(float));
            std::memcpy(reachIPBuf.data(), riverIP.data(), riverNC * sizeof(float));
            cfrTraverseRiver(rs, reachOOPBuf.data(), reachIPBuf.data(),
                             0, resultEV.data(), potOffset);

            // Traversal for IP
            std::memcpy(reachOOPBuf.data(), riverOOP.data(), riverNC * sizeof(float));
            std::memcpy(reachIPBuf.data(), riverIP.data(), riverNC * sizeof(float));
            cfrTraverseRiver(rs, reachOOPBuf.data(), reachIPBuf.data(),
                             1, resultEV.data(), potOffset);

            // DCFR discounting
            float factor = (float)(t * t) / (float)((t + 1) * (t + 1));
            rs.store.discountStrategySums(factor);
        }

        // ── Extract per-combo EV using average strategy ──
        // Do one final traversal with iterWeight=0 (no regret/strategy updates)
        // to get the game value under the converged strategy.
        // We use the last iteration's EV which closely approximates Nash EV.
        std::vector<float> finalEV_OOP(riverNC, 0.0f);
        std::vector<float> finalEV_IP(riverNC, 0.0f);

        // Final OOP traversal
        std::memcpy(reachOOPBuf.data(), riverOOP.data(), riverNC * sizeof(float));
        std::memcpy(reachIPBuf.data(), riverIP.data(), riverNC * sizeof(float));
        cfrTraverseRiver(rs, reachOOPBuf.data(), reachIPBuf.data(),
                         0, finalEV_OOP.data(), potOffset);

        // Final IP traversal
        std::memcpy(reachOOPBuf.data(), riverOOP.data(), riverNC * sizeof(float));
        std::memcpy(reachIPBuf.data(), riverIP.data(), riverNC * sizeof(float));
        cfrTraverseRiver(rs, reachOOPBuf.data(), reachIPBuf.data(),
                         1, finalEV_IP.data(), potOffset);

        // Remap river EVs → turn-local space and accumulate
        for (uint32_t ci = 0; ci < riverNC; ci++) {
            uint32_t pi = mapping.childToParent[ci];
            cfvOOPLocal[pi] += finalEV_OOP[ci];
            cfvIPLocal[pi] += finalEV_IP[ci];
        }
    }

    // ── 8. Average across surviving rivers ──
    for (uint32_t pi = 0; pi < turnNC; pi++) {
        if (survivalCount[pi] > 0.0f) {
            cfvOOPLocal[pi] /= survivalCount[pi];
            cfvIPLocal[pi] /= survivalCount[pi];
        }
    }

    // ── 9. Map turn-local CFVs → canonical 1326-space ──
    mineResultCfvOOP1326_.assign(1326, 0.0f);
    mineResultCfvIP1326_.assign(1326, 0.0f);

    for (uint32_t ci = 0; ci < turnNC; ci++) {
        int32_t gid = comboGlobalIds[ci];
        mineResultCfvOOP1326_[gid] = cfvOOPLocal[ci];
        mineResultCfvIP1326_[gid] = cfvIPLocal[ci];
    }
}

} // namespace ez_cfr
