#include "ez_cfr/cfr_engine.h"
#include <cstring>
#include <cmath>
#include <chrono>
#include <algorithm>
#include <cstdio>

namespace ez_cfr {

CfrSolver::CfrSolver() : rng_(42) {
#ifndef __EMSCRIPTEN__
    initNativeNNEvaluatorFromEnv();
#endif
}
CfrSolver::~CfrSolver() { destroy(); }

void CfrSolver::initNativeNNEvaluatorFromEnv() {
#ifdef __EMSCRIPTEN__
    nativeNNEvaluator_.reset();
#else
    nativeNNEvaluator_ = createNativeNNEvaluatorFromEnv();
    if (nativeNNEvaluator_ && nativeNNEvaluator_->isReady()) {
        std::printf("  [Native NN] Enabled backend=%s batch=%zu\n",
                    nativeNNEvaluator_->backend().c_str(),
                    nativeNNEvaluator_->maxBatchStates());
    } else if (nativeNNEvaluator_) {
        std::printf("  [Native NN] Evaluator created but not ready (%s)\n",
                    nativeNNEvaluator_->backend().c_str());
    }
#endif
}

void CfrSolver::flushNativeNNEvaluator() {
    if (nativeNNEvaluator_) {
        nativeNNEvaluator_->flush();
    }
}

void CfrSolver::setRiverValueFn(RiverValueFn fn) {
    riverValueFn_ = std::move(fn);
    useNNRiver_ = true;
}

void CfrSolver::clearRiverValueFn() {
    riverValueFn_ = nullptr;
    useNNRiver_ = false;
}

void CfrSolver::initFlop(
    const uint8_t* nodePlayer, const uint8_t* nodeNumActions,
    const uint32_t* nodeActionOffset, const int32_t* childNodeId,
    const float* terminalPot, const float* terminalStacks,
    const uint8_t* terminalIsShowdown, const int8_t* terminalFolder,
    uint32_t numNodes, uint32_t numTerminals, uint32_t totalActions,
    const int32_t* comboCards, uint32_t numCombos,
    const float* oopReach, const float* ipReach,
    float startingPot, float effectiveStack)
{
    // Build FlatTree from raw pointers
    FlatTree src{numNodes, numTerminals, totalActions,
                 nodePlayer, nodeNumActions, nodeActionOffset,
                 nullptr, nullptr, // nodePot, nodeStacks not needed for traversal
                 childNodeId, terminalPot, terminalIsShowdown,
                 terminalFolder, terminalStacks};
    flopTree_ = OwnedFlatTree::clone(src);

    flopNC_ = numCombos;
    startingPot_ = startingPot;
    effectiveStack_ = effectiveStack;

    // Build flop combos
    flopCombos_.numCombos = numCombos;
    flopCombos_.comboCards.assign(comboCards, comboCards + numCombos * 2);
    flopCombos_.cardCombos.resize(52 * MAX_COMBOS_PER_CARD, -1);
    flopCombos_.cardCombosLen.resize(52, 0);
    buildCardCombos(flopCombos_.comboCards.data(), numCombos,
                    flopCombos_.cardCombos.data(), flopCombos_.cardCombosLen.data());

    // Copy reaches
    flopOopReach_.assign(oopReach, oopReach + numCombos);
    flopIpReach_.assign(ipReach, ipReach + numCombos);

    // Create flop ArrayStore
    flopStore_ = ArrayStore(numNodes, totalActions, numCombos,
                            flopTree_.nodeNumActions.data());
}

void CfrSolver::buildSubtrees(
    const int32_t* boardCards, int boardLen,
    const uint8_t* innerNodePlayer, const uint8_t* innerNodeNumActions,
    const uint32_t* innerNodeActionOffset, const int32_t* innerChildNodeId,
    const float* innerTerminalPot, const float* innerTerminalStacks,
    const uint8_t* innerTerminalIsShowdown, const int8_t* innerTerminalFolder,
    uint32_t innerNumNodes, uint32_t innerNumTerminals, uint32_t innerTotalActions,
    float rakePercentage, float rakeCap,
    bool skipRiverSubtrees,
    std::function<void(const char*, float)> onProgress)
{
    board_.assign(boardCards, boardCards + boardLen);
    rakePercentage_ = std::max(0.0f, rakePercentage);
    rakeCap_ = std::max(0.0f, rakeCap);

    // Build inner tree template
    FlatTree innerSrc{innerNumNodes, innerNumTerminals, innerTotalActions,
                      innerNodePlayer, innerNodeNumActions, innerNodeActionOffset,
                      nullptr, nullptr,
                      innerChildNodeId, innerTerminalPot, innerTerminalIsShowdown,
                      innerTerminalFolder, innerTerminalStacks};
    OwnedFlatTree innerTemplate = OwnedFlatTree::clone(innerSrc);

    // Enumerate dealable turn cards
    uint8_t dead[52] = {0};
    for (int i = 0; i < boardLen; i++) dead[boardCards[i]] = 1;

    std::vector<int32_t> turnCards;
    for (int c = 0; c < 52; c++) {
        if (!dead[c]) turnCards.push_back(c);
    }
    uint32_t numTurns = (uint32_t)turnCards.size();

    maxTurnNC_ = 0;
    maxRiverNC_ = 0;
    size_t totalMemory = 0;
    uint32_t totalRivers = 0;

    turnSubtrees_.resize(numTurns);

    for (uint32_t ti = 0; ti < numTurns; ti++) {
        int32_t turnCard = turnCards[ti];

        // Build turn combo mapping
        ComboMapping turnMapping = buildComboMapping(flopCombos_, board_.data(), boardLen, turnCard);
        uint32_t turnNC = turnMapping.childNC;
        if (turnNC > maxTurnNC_) maxTurnNC_ = turnNC;

        // Clone inner tree for turn
        OwnedFlatTree turnTree = OwnedFlatTree::clone(innerTemplate.view());
        ArrayStore turnStore(innerNumNodes, innerTotalActions, turnNC,
                             turnTree.nodeNumActions.data());
        totalMemory += turnStore.estimateMemoryBytes();

        // Build comboGlobalIds: canonical 0..1325 index for each turn combo
        std::vector<int32_t> comboGlobalIds(turnNC);
        for (uint32_t ci = 0; ci < turnNC; ci++) {
            int32_t c1 = turnMapping.childCombos.comboCards[ci * 2];
            int32_t c2 = turnMapping.childCombos.comboCards[ci * 2 + 1];
            int32_t hi = std::max(c1, c2);
            int32_t lo = std::min(c1, c2);
            comboGlobalIds[ci] = hi * (hi - 1) / 2 + lo;
        }

        // Turn board
        std::vector<int32_t> turnBoard(board_.begin(), board_.end());
        turnBoard.push_back(turnCard);

        std::vector<RiverSubtree> rivers;

        if (!skipRiverSubtrees) {
            // Enumerate river cards
            uint8_t turnDead[52] = {0};
            for (auto c : turnBoard) turnDead[c] = 1;
            std::vector<int32_t> riverCards;
            for (int c = 0; c < 52; c++) {
                if (!turnDead[c]) riverCards.push_back(c);
            }

            rivers.reserve(riverCards.size());

            for (uint32_t ri = 0; ri < riverCards.size(); ri++) {
                int32_t riverCard = riverCards[ri];

                // Build river combo mapping
                ComboMapping riverMapping = buildComboMapping(
                    turnMapping.childCombos, turnBoard.data(), (int)turnBoard.size(), riverCard);
                uint32_t riverNC = riverMapping.childNC;
                if (riverNC > maxRiverNC_) maxRiverNC_ = riverNC;

                // Clone inner tree for river
                OwnedFlatTree riverTree = OwnedFlatTree::clone(innerTemplate.view());

                ArrayStore riverStore(innerNumNodes, innerTotalActions, riverNC,
                                      riverTree.nodeNumActions.data());
                totalMemory += riverStore.estimateMemoryBytes();

                // Build river board
                std::vector<int32_t> riverBoard(turnBoard.begin(), turnBoard.end());
                riverBoard.push_back(riverCard);

                // Build terminal cache
                TerminalCache cache = buildTerminalCache(
                    riverMapping.childCombos, riverBoard.data(), (int)riverBoard.size());

                rivers.push_back(RiverSubtree{
                    riverCard, std::move(riverMapping),
                    std::move(riverTree), std::move(riverStore),
                    std::move(cache), riverNC
                });
                totalRivers++;
            }
        }

        // Copy turnCombos BEFORE moving turnMapping (avoid use-after-move UB)
        ValidCombos turnCombosCopy = turnMapping.childCombos;

        turnSubtrees_[ti] = TurnSubtree{
            turnCard, std::move(turnMapping),
            std::move(turnTree), std::move(turnStore),
            turnNC, std::move(turnCombosCopy),
            std::move(rivers),
            std::move(comboGlobalIds)
        };

        if (onProgress && (ti + 1) % 5 == 0) {
            char msg[128];
            snprintf(msg, sizeof(msg), "Turn %u/%u built (%u rivers)",
                     ti + 1, numTurns, totalRivers);
            onProgress(msg, 5.0f + (float)(ti + 1) / numTurns * 20.0f);
        }
    }

    // Create traversal contexts
    uint32_t flopMaxActions = 0;
    for (uint32_t n = 0; n < flopTree_.numNodes; n++) {
        flopMaxActions = std::max(flopMaxActions, (uint32_t)flopTree_.nodeNumActions[n]);
    }
    uint32_t innerMaxActions = 0;
    for (uint32_t n = 0; n < innerNumNodes; n++) {
        innerMaxActions = std::max(innerMaxActions, (uint32_t)innerNodeNumActions[n]);
    }

    flopCtx_ = TraversalCtx::create(flopTree_.numNodes, flopMaxActions, flopNC_);
    turnCtx_ = TraversalCtx::create(innerNumNodes, innerMaxActions, maxTurnNC_);

    // Only allocate river context if we have river subtrees
    if (!skipRiverSubtrees && maxRiverNC_ > 0) {
        riverCtx_ = TraversalCtx::create(innerNumNodes, innerMaxActions, maxRiverNC_);
    }

    // Chance node buffers
    turnChanceOop_.resize(maxTurnNC_, 0.0f);
    turnChanceIp_.resize(maxTurnNC_, 0.0f);
    turnChanceEV_.resize(maxTurnNC_, 0.0f);

    if (!skipRiverSubtrees && maxRiverNC_ > 0) {
        riverChanceOop_.resize(maxRiverNC_, 0.0f);
        riverChanceIp_.resize(maxRiverNC_, 0.0f);
        riverChanceEV_.resize(maxRiverNC_, 0.0f);
    }

    // Street buffers
    flopBufs_ = StreetBufs(flopNC_);
    turnBufs_ = StreetBufs(maxTurnNC_);
    if (!skipRiverSubtrees && maxRiverNC_ > 0) {
        riverBufs_ = StreetBufs(maxRiverNC_);
    }

    if (onProgress) {
        size_t memMB = totalMemory / (1024 * 1024);
        char msg[128];
        snprintf(msg, sizeof(msg), "All subtrees built: %u turns, %u rivers, %zu MB",
                 numTurns, totalRivers, memMB);
        onProgress(msg, 25.0f);
    }
}

void CfrSolver::solve(uint32_t iterations, bool mccfr, uint32_t globalIterOffset,
                      std::function<void(const char*, float)> onProgress)
{
    mccfr_ = mccfr;
    bool useLinearWeighting = mccfr; // MCCFR uses linear, full-enum uses DCFR

    auto iterStart = std::chrono::steady_clock::now();
    std::vector<float> resultEV(flopNC_, 0.0f);
    std::vector<float> reachOopBuf(flopNC_);
    std::vector<float> reachIpBuf(flopNC_);

    for (uint32_t iter = 0; iter < iterations; iter++) {
        uint32_t t = iter + 1;
        uint32_t globalT = globalIterOffset + t;
        iterWeight_ = useLinearWeighting ? (float)globalT : 1.0f;

        // Traversal for player 0 (OOP)
        // Per-terminal sampling: each flop showdown terminal independently samples
        // a new turn card (sampledTurnIdx_=-1 triggers the rng fallback in
        // computeTurnChanceValue). This gives K independent gradient samples per
        // traversal (K = number of flop showdown terminals) vs 1 shared sample.
        if (mccfr_) sampledTurnIdx_ = -1;
        std::memcpy(reachOopBuf.data(), flopOopReach_.data(), flopNC_ * sizeof(float));
        std::memcpy(reachIpBuf.data(), flopIpReach_.data(), flopNC_ * sizeof(float));
        cfrTraverseFlop(reachOopBuf.data(), reachIpBuf.data(), 0, resultEV.data());

        // Traversal for player 1 (IP)
        if (mccfr_) sampledTurnIdx_ = -1;
        std::memcpy(reachOopBuf.data(), flopOopReach_.data(), flopNC_ * sizeof(float));
        std::memcpy(reachIpBuf.data(), flopIpReach_.data(), flopNC_ * sizeof(float));
        cfrTraverseFlop(reachOopBuf.data(), reachIpBuf.data(), 1, resultEV.data());

        // DCFR discounting (serial full-enum only)
        if (!useLinearWeighting) {
            float factor = (float)(t * t) / (float)((t + 1) * (t + 1));
            flopStore_.discountStrategySums(factor);
            for (auto& ts : turnSubtrees_) {
                ts.store.discountStrategySums(factor);
                for (auto& rs : ts.rivers) {
                    rs.store.discountStrategySums(factor);
                }
            }
        }

        if (onProgress && (iter + 1) % std::max(1u, iterations / 20) == 0) {
            auto now = std::chrono::steady_clock::now();
            double elapsed = std::chrono::duration<double>(now - iterStart).count();
            double iterPerSec = (iter + 1) / elapsed;
            float pct = 25.0f + (float)(iter + 1) / iterations * 75.0f;
            char msg[128];
            snprintf(msg, sizeof(msg), "Iter %u/%u (%.1fs, %.0f it/s)",
                     iter + 1, iterations, elapsed, iterPerSec);
            onProgress(msg, pct);
        }
    }

    flushNativeNNEvaluator();
}

float* CfrSolver::getStrategySumsPtr() {
    return flopStore_.strategySums.data();
}

uint32_t CfrSolver::getStrategySumsLen() {
    return (uint32_t)flopStore_.strategySums.size();
}

float* CfrSolver::getRegretsPtr() {
    return flopStore_.regrets.data();
}

void CfrSolver::destroy() {
    flushNativeNNEvaluator();
    nativeNNEvaluator_.reset();
    turnSubtrees_.clear();
    flopStore_ = ArrayStore();
    flopCombos_ = ValidCombos();
    flopOopReach_.clear();
    flopIpReach_.clear();
    clearRiverValueFn();
}

} // namespace ez_cfr
