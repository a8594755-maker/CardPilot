#include "ez_cfr/cfr_engine.h"
#include "ez_cfr/simd_utils.h"
#include <cstring>
#include <cmath>
#include <algorithm>

namespace ez_cfr {

static bool isReachDead(const float* reach, uint32_t nc) {
    for (uint32_t c = 0; c < nc; c++) {
        if (reach[c] >= PRUNE_THRESHOLD) return false;
    }
    return true;
}

void CfrSolver::cfrTraverseNode(
    const FlatTree& tree, ArrayStore& store, uint32_t nc,
    float* oopReach, float* ipReach, int traverser,
    int32_t nodeId, uint32_t depth, TraversalCtx& ctx,
    std::function<void(float, float, float, float*, float*, int, float*)> onShowdown,
    std::function<void(float, float, float, float*, float*, int, int, float*)> onFold,
    float* outEV,
    float potOffset)
{
    // ── Terminal ──
    if (isTerminal(nodeId)) {
        int32_t ti = decodeTerminalId(nodeId);
        float pot = tree.terminalPot[ti] + potOffset;
        float s0 = tree.terminalStacks[ti * 2] - potOffset / 2.0f;
        float s1 = tree.terminalStacks[ti * 2 + 1] - potOffset / 2.0f;

        // Virtual Tree Clipping: clamp negative stacks → 0.
        // When actual stacks < template stacks, s_actual = s_template - potOffset/2 < 0.
        // These phantom chips were never in the actual game, so SUBTRACT them from the pot.
        // (sign: s < 0, so pot += s subtracts the excess, pot += (-s) would ADD — wrong)
        if (s0 < 0.0f) { pot += s0; s0 = 0.0f; }
        if (s1 < 0.0f) { pot += s1; s1 = 0.0f; }

        if (tree.terminalIsShowdown[ti]) {
            // Showdown terminals are street transitions (flop→turn, turn→river) OR
            // the final river showdown. Rake must NOT be applied here because:
            // 1. For flop/turn transitions: we're not at the final hand yet; rake will
            //    be applied once at the river level (in cfrTraverseRiver's onShowdown).
            // 2. For river terminals: rake is applied by the caller (cfrTraverseRiver).
            // Applying rake here would cause it to be taken multiple times.
            onShowdown(pot, s0, s1, oopReach, ipReach, traverser, outEV);
        } else {
            // Fold terminals: apply rake once (this IS the final terminal for this hand).
            if (rakePercentage_ > 0.0f && pot > 0.0f) {
                const float rake = std::min(pot * rakePercentage_, rakeCap_);
                pot = std::max(0.0f, pot - rake);
            }
            int folder = tree.terminalFolder[ti];
            onFold(pot, s0, s1, oopReach, ipReach, traverser, folder, outEV);
        }
        return;
    }

    // ── Pruning ──
    if (isReachDead(oopReach, nc) || isReachDead(ipReach, nc)) {
        std::memset(outEV, 0, nc * sizeof(float));
        return;
    }

    int player = tree.nodePlayer[nodeId];
    uint32_t numActions = tree.nodeNumActions[nodeId];
    uint32_t actionOffset = tree.nodeActionOffset[nodeId];

    // Get current strategy via regret matching (SIMD)
    float* strategy = ctx.strategyAt(depth);
    store.getCurrentStrategy(nodeId, numActions, strategy);

    // Local node EV accumulator
    float* nodeEV = ctx.nodeEVAt(depth);
    std::memset(nodeEV, 0, nc * sizeof(float));

    for (uint32_t a = 0; a < numActions; a++) {
        int32_t childId = tree.childNodeId[actionOffset + a];

        // Build child reaches (SIMD)
        float* childOop = ctx.childOopAt(depth);
        float* childIp = ctx.childIpAt(depth);
        if (player == 0) {
            simd::mul(childOop, oopReach, &strategy[a * nc], nc);
            simd::copy(childIp, ipReach, nc);
        } else {
            simd::copy(childOop, oopReach, nc);
            simd::mul(childIp, ipReach, &strategy[a * nc], nc);
        }

        // Skip dead branches
        const float* actingReach = (player == 0) ? childOop : childIp;
        if (isReachDead(actingReach, nc)) {
            float* aev = ctx.actionEVAt(depth, a);
            std::memset(aev, 0, nc * sizeof(float));
            continue;
        }

        // Recurse
        float* actionEV = ctx.actionEVAt(depth, a);
        cfrTraverseNode(tree, store, nc, childOop, childIp, traverser,
                        childId, depth + 1, ctx, onShowdown, onFold,
                        actionEV, potOffset);

        // Accumulate node EV (SIMD)
        if (player == traverser) {
            simd::fma(nodeEV, &strategy[a * nc], actionEV, nc);
        } else {
            simd::add(nodeEV, actionEV, nc);
        }
    }

    // Update regrets and strategy sums (SIMD)
    if (player == traverser) {
        const float* playerReach = (traverser == 0) ? oopReach : ipReach;
        float* regretDeltas = ctx.regretDeltaAt(depth);
        float* stratWeights = ctx.stratWeightAt(depth);

        for (uint32_t a = 0; a < numActions; a++) {
            float* actionEV = ctx.actionEVAt(depth, a);
            simd::sub(&regretDeltas[a * nc], actionEV, nodeEV, nc);
            simd::mulScale(&stratWeights[a * nc], playerReach, &strategy[a * nc], iterWeight_, nc);
        }

        store.updateRegrets(nodeId, numActions, regretDeltas);
        store.addStrategyWeights(nodeId, numActions, stratWeights);
    }

    // Copy result to output
    std::memcpy(outEV, nodeEV, nc * sizeof(float));
}

// ─── Street-Level Traversals ───

void CfrSolver::cfrTraverseFlop(
    float* oopReach, float* ipReach, int traverser, float* outEV)
{
    FlatTree flopView = flopTree_.view();
    uint32_t nc = flopNC_;

    auto onShowdown = [&](float pot, float s0, float s1,
                          float* oR, float* iR, int trav, float* out) {
        float turnPotOffset = pot - startingPot_;
        computeTurnChanceValue(oR, iR, trav, out, turnPotOffset, startingPot_);
    };

    auto onFold = [&](float pot, float s0, float s1,
                      float* oR, float* iR, int trav, int folder, float* out) {
        computeFoldEVFast(
            flopCombos_.comboCards.data(),
            flopCombos_.cardCombos.data(),
            flopCombos_.cardCombosLen.data(),
            flopBufs_, nc, pot, s0, s1, trav, folder, oR, iR, out);
    };

    cfrTraverseNode(flopView, flopStore_, nc, oopReach, ipReach, traverser,
                    0, 0, flopCtx_, onShowdown, onFold, outEV);
}

void CfrSolver::cfrTraverseTurn(
    TurnSubtree& ts,
    float* oopReach, float* ipReach, int traverser,
    float* outEV, float potOffset, float startingPot)
{
    // Store turn context for NN river value callback
    currentTurnCard_ = ts.turnCard;
    currentComboGlobalIds_ = ts.comboGlobalIds.data();

    FlatTree turnView = ts.tree.view();
    uint32_t nc = ts.childNC;

    ArrayStore& store = ts.store;

    auto onShowdown = [&](float pot, float s0, float s1,
                          float* oR, float* iR, int trav, float* out) {
        float riverPotOffset = pot - startingPot;
        computeRiverChanceValue(ts.rivers, nc, oR, iR, trav, out, riverPotOffset);
    };

    auto onFold = [&](float pot, float s0, float s1,
                      float* oR, float* iR, int trav, int folder, float* out) {
        computeFoldEVFast(
            ts.turnCombos.comboCards.data(),
            ts.turnCombos.cardCombos.data(),
            ts.turnCombos.cardCombosLen.data(),
            turnBufs_, nc, pot, s0, s1, trav, folder, oR, iR, out);
    };

    cfrTraverseNode(turnView, store, nc, oopReach, ipReach, traverser,
                    0, 0, turnCtx_, onShowdown, onFold, outEV, potOffset);
}

void CfrSolver::cfrTraverseRiver(
    RiverSubtree& rs,
    float* oopReach, float* ipReach, int traverser,
    float* outEV, float potOffset)
{
    FlatTree riverView = rs.tree.view();
    uint32_t nc = rs.childNC;

    auto onShowdown = [&](float pot, float s0, float s1,
                          float* oR, float* iR, int trav, float* out) {
        // River is the final street: apply rake exactly once here.
        if (rakePercentage_ > 0.0f && pot > 0.0f) {
            const float rake = std::min(pot * rakePercentage_, rakeCap_);
            pot = std::max(0.0f, pot - rake);
        }
        computeShowdownEVCached(rs.cache, riverBufs_, pot, s0, s1, oR, iR, trav, out);
    };

    auto onFold = [&](float pot, float s0, float s1,
                      float* oR, float* iR, int trav, int folder, float* out) {
        computeFoldEVFast(
            rs.cache.comboCards.data(),
            rs.cache.cardCombos.data(),
            rs.cache.cardCombosLen.data(),
            riverBufs_, nc, pot, s0, s1, trav, folder, oR, iR, out);
    };

    cfrTraverseNode(riverView, rs.store, nc, oopReach, ipReach, traverser,
                    0, 0, riverCtx_, onShowdown, onFold, outEV, potOffset);
}

} // namespace ez_cfr
