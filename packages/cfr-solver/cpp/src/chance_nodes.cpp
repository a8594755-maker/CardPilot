#include "ez_cfr/cfr_engine.h"
#include <cstring>

namespace ez_cfr {

static bool isReachDead(const float* reach, uint32_t nc) {
    for (uint32_t c = 0; c < nc; c++) {
        if (reach[c] >= PRUNE_THRESHOLD) return false;
    }
    return true;
}

void CfrSolver::computeTurnChanceValue(
    float* oopReach, float* ipReach, int traverser,
    float* outEV, float potOffset, float startingPot)
{
    uint32_t flopNC = flopNC_;
    uint32_t numTurns = (uint32_t)turnSubtrees_.size();
    std::memset(outEV, 0, flopNC * sizeof(float));

    if (mccfr_) {
        // MCCFR: use the tree-wide pre-sampled turn card index so that all
        // showdown terminals in the same traverser pass see the same turn card.
        // This reduces regret variance compared to per-terminal independent sampling.
        uint32_t ti = (sampledTurnIdx_ >= 0)
            ? (uint32_t)sampledTurnIdx_ % numTurns
            : rng_() % numTurns;
        TurnSubtree& ts = turnSubtrees_[ti];
        uint32_t turnNC = ts.childNC;
        const auto& mapping = ts.mapping;

        // Per-terminal river sampling: each turn showdown terminal independently
        // samples a new river card (sampledRiverIdx_=-1 triggers the rng fallback).
        uint32_t numRivers = (uint32_t)ts.rivers.size();
        sampledRiverIdx_ = -1;

        // Remap reaches from flop → turn
        for (uint32_t ci = 0; ci < turnNC; ci++) {
            turnChanceOop_[ci] = oopReach[mapping.childToParent[ci]];
            turnChanceIp_[ci] = ipReach[mapping.childToParent[ci]];
        }

        cfrTraverseTurn(ts, turnChanceOop_.data(), turnChanceIp_.data(),
                        traverser, turnChanceEV_.data(), potOffset, startingPot);

        // Direct assignment (unbiased estimator)
        for (uint32_t ci = 0; ci < turnNC; ci++) {
            outEV[mapping.childToParent[ci]] = turnChanceEV_[ci];
        }
        return;
    }

    // Full enumeration: iterate all turn cards
    for (uint32_t ti = 0; ti < numTurns; ti++) {
        TurnSubtree& ts = turnSubtrees_[ti];
        uint32_t turnNC = ts.childNC;
        const auto& mapping = ts.mapping;

        // Remap reaches
        for (uint32_t ci = 0; ci < turnNC; ci++) {
            turnChanceOop_[ci] = oopReach[mapping.childToParent[ci]];
            turnChanceIp_[ci] = ipReach[mapping.childToParent[ci]];
        }

        // Skip dead turns
        if (isReachDead(turnChanceOop_.data(), turnNC) ||
            isReachDead(turnChanceIp_.data(), turnNC)) {
            continue;
        }

        cfrTraverseTurn(ts, turnChanceOop_.data(), turnChanceIp_.data(),
                        traverser, turnChanceEV_.data(), potOffset, startingPot);

        // Accumulate EV
        for (uint32_t ci = 0; ci < turnNC; ci++) {
            outEV[mapping.childToParent[ci]] += turnChanceEV_[ci];
        }
    }

    // Average across turn cards
    float invNumTurns = 1.0f / (float)numTurns;
    for (uint32_t c = 0; c < flopNC; c++) {
        outEV[c] *= invNumTurns;
    }
}

void CfrSolver::computeRiverChanceValue(
    std::vector<RiverSubtree>& rivers, uint32_t turnNC,
    float* oopReach, float* ipReach, int traverser,
    float* outEV, float potOffset)
{
    // ── Native ORT evaluator (non-WASM) ──
    if (nativeNNEvaluator_ && nativeNNEvaluator_->isReady()) {
        NNEvalState state;
        state.board = board_.data();
        state.boardLen = static_cast<int>(board_.size());
        state.turnCard = currentTurnCard_;
        state.potOffset = potOffset;
        state.startingPot = startingPot_;
        state.effectiveStack = effectiveStack_;
        state.turnNC = turnNC;
        state.comboGlobalIds = currentComboGlobalIds_;
        state.oopReach = oopReach;
        state.ipReach = ipReach;
        state.traverser = traverser;
        state.outEV = outEV;
        if (nativeNNEvaluator_->evaluate(state)) {
            return;
        }
    }

    // ── NN Mode: delegate to external callback ──
    if (useNNRiver_ && riverValueFn_) {
        riverValueFn_(
            board_.data(), (int)board_.size(),
            currentTurnCard_,
            potOffset, startingPot_, effectiveStack_,
            turnNC,
            currentComboGlobalIds_,
            oopReach, ipReach,
            traverser, outEV
        );
        return;
    }

    // ── Standard Mode: enumerate all river cards ──
    uint32_t numRivers = (uint32_t)rivers.size();
    std::memset(outEV, 0, turnNC * sizeof(float));

    if (mccfr_) {
        // MCCFR: use the tree-wide pre-sampled river card index so that all
        // turn showdown terminals in the same turn traversal see the same river card.
        uint32_t ri = (sampledRiverIdx_ >= 0)
            ? (uint32_t)sampledRiverIdx_ % numRivers
            : rng_() % numRivers;
        RiverSubtree& rs = rivers[ri];
        uint32_t riverNC = rs.childNC;
        const auto& mapping = rs.mapping;

        for (uint32_t ci = 0; ci < riverNC; ci++) {
            riverChanceOop_[ci] = oopReach[mapping.childToParent[ci]];
            riverChanceIp_[ci] = ipReach[mapping.childToParent[ci]];
        }

        cfrTraverseRiver(rs, riverChanceOop_.data(), riverChanceIp_.data(),
                         traverser, riverChanceEV_.data(), potOffset);

        for (uint32_t ci = 0; ci < riverNC; ci++) {
            outEV[mapping.childToParent[ci]] = riverChanceEV_[ci];
        }
        return;
    }

    // Full enumeration
    for (uint32_t ri = 0; ri < numRivers; ri++) {
        RiverSubtree& rs = rivers[ri];
        uint32_t riverNC = rs.childNC;
        const auto& mapping = rs.mapping;

        for (uint32_t ci = 0; ci < riverNC; ci++) {
            riverChanceOop_[ci] = oopReach[mapping.childToParent[ci]];
            riverChanceIp_[ci] = ipReach[mapping.childToParent[ci]];
        }

        if (isReachDead(riverChanceOop_.data(), riverNC) ||
            isReachDead(riverChanceIp_.data(), riverNC)) {
            continue;
        }

        cfrTraverseRiver(rs, riverChanceOop_.data(), riverChanceIp_.data(),
                         traverser, riverChanceEV_.data(), potOffset);

        for (uint32_t ci = 0; ci < riverNC; ci++) {
            outEV[mapping.childToParent[ci]] += riverChanceEV_[ci];
        }
    }

    // Average across river cards
    float invNumRivers = 1.0f / (float)numRivers;
    for (uint32_t c = 0; c < turnNC; c++) {
        outEV[c] *= invNumRivers;
    }
}

} // namespace ez_cfr
