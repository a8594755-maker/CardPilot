// street_solver.cpp — Per-street CFR+ solver for real-time resolving.
//
// StreetSolver handles a single-street tree (flop, turn, or river)
// with 3-way terminal dispatch:
//   1. Fold terminals (folder >= 0)      → computeFoldEVFast()
//   2. Showdown terminals (isShowdown=1) → computeShowdownEVCached()
//   3. Transition terminals (else)       → JS callback (value network)

#include "ez_cfr/cfr_engine.h"
#include "ez_cfr/simd_utils.h"
#include <cstring>
#include <cmath>
#include <algorithm>
#include <set>

namespace ez_cfr {

// ────────────────────────────────────────────────
// Construction / Destruction
// ────────────────────────────────────────────────

StreetSolver::StreetSolver() {}
StreetSolver::~StreetSolver() { destroy(); }

void StreetSolver::destroy() {
    nc_ = 0;
    useTransition_ = false;
    transitionFn_ = nullptr;
}

// ────────────────────────────────────────────────
// init — set up tree, combos, cache, store
// ────────────────────────────────────────────────

void StreetSolver::init(
    const uint8_t* nodePlayer, const uint8_t* nodeNumActions,
    const uint32_t* nodeActionOffset, const int32_t* childNodeId,
    const float* terminalPot, const float* terminalStacks,
    const uint8_t* terminalIsShowdown, const int8_t* terminalFolder,
    uint32_t numNodes, uint32_t numTerminals, uint32_t totalActions,
    const int32_t* boardCards, int boardLen,
    const int32_t* comboCards, uint32_t numCombos,
    const float* oopReach, const float* ipReach)
{
    nc_ = numCombos;

    // Clone the flat tree
    FlatTree srcTree{numNodes, numTerminals, totalActions,
                     nodePlayer, nodeNumActions, nodeActionOffset,
                     nullptr, nullptr,
                     childNodeId, terminalPot, terminalIsShowdown,
                     terminalFolder, terminalStacks};
    tree_ = OwnedFlatTree::clone(srcTree);

    // Build ValidCombos from the provided combo cards
    combos_.numCombos = numCombos;
    combos_.comboCards.assign(comboCards, comboCards + numCombos * 2);
    combos_.cardCombos.resize(52 * MAX_COMBOS_PER_CARD, -1);
    combos_.cardCombosLen.resize(52, 0);
    buildCardCombos(combos_.comboCards.data(), numCombos,
                    combos_.cardCombos.data(), combos_.cardCombosLen.data());

    // Build showdown cache (works for 3/4/5 card boards)
    bool hasShowdown = false;
    for (uint32_t t = 0; t < numTerminals; t++) {
        if (terminalIsShowdown[t]) { hasShowdown = true; break; }
    }
    if (hasShowdown) {
        cache_ = buildTerminalCache(combos_, boardCards, boardLen);
    }

    // Identify transition terminals: !showdown && folder == -1
    transitionTerminals_.clear();
    for (uint32_t t = 0; t < numTerminals; t++) {
        if (!terminalIsShowdown[t] && terminalFolder[t] == -1) {
            transitionTerminals_.insert(t);
        }
    }

    // Create store
    store_ = ArrayStore(numNodes, totalActions, numCombos, nodeNumActions);

    // Compute max actions for TraversalCtx
    uint32_t maxActions = 0;
    for (uint32_t n = 0; n < numNodes; n++) {
        maxActions = std::max(maxActions, (uint32_t)nodeNumActions[n]);
    }
    ctx_ = TraversalCtx::create(numNodes, maxActions, numCombos);
    bufs_ = StreetBufs(numCombos);

    // Store initial reaches
    oopInitReach_.assign(oopReach, oopReach + numCombos);
    ipInitReach_.assign(ipReach, ipReach + numCombos);
}

// ────────────────────────────────────────────────
// Transition callback management
// ────────────────────────────────────────────────

void StreetSolver::setTransitionFn(StreetTransitionFn fn) {
    transitionFn_ = std::move(fn);
    useTransition_ = true;
}

void StreetSolver::clearTransitionFn() {
    transitionFn_ = nullptr;
    useTransition_ = false;
}

// ────────────────────────────────────────────────
// streetTraverseNode — standalone traversal with 3-way terminal dispatch
// ────────────────────────────────────────────────

static bool isReachDeadLocal(const float* reach, uint32_t nc) {
    for (uint32_t c = 0; c < nc; c++) {
        if (reach[c] >= PRUNE_THRESHOLD) return false;
    }
    return true;
}

void StreetSolver::streetTraverseNode(
    int32_t nodeId, uint32_t depth,
    float* oopReach, float* ipReach, int traverser, float* outEV)
{
    FlatTree tree = tree_.view();
    uint32_t nc = nc_;

    // ── Terminal ──
    if (isTerminal(nodeId)) {
        int32_t ti = decodeTerminalId(nodeId);
        float pot = tree.terminalPot[ti];
        float s0 = tree.terminalStacks[ti * 2];
        float s1 = tree.terminalStacks[ti * 2 + 1];

        if (tree.terminalFolder[ti] >= 0) {
            // Fold terminal
            int folder = tree.terminalFolder[ti];
            computeFoldEVFast(
                combos_.comboCards.data(),
                combos_.cardCombos.data(),
                combos_.cardCombosLen.data(),
                bufs_, nc, pot, s0, s1, traverser, folder,
                oopReach, ipReach, outEV);
        } else if (tree.terminalIsShowdown[ti]) {
            // Showdown terminal (all-in)
            computeShowdownEVCached(cache_, bufs_, pot, s0, s1,
                                    oopReach, ipReach, traverser, outEV);
        } else if (useTransition_ && transitionTerminals_.count(ti)) {
            // Transition terminal — call JS callback
            transitionFn_((uint32_t)ti, nc, pot, s0, s1,
                          oopReach, ipReach, traverser, outEV);
        } else {
            // Transition terminal but no callback — zero EV
            std::memset(outEV, 0, nc * sizeof(float));
        }
        return;
    }

    // ── Pruning ──
    if (isReachDeadLocal(oopReach, nc) || isReachDeadLocal(ipReach, nc)) {
        std::memset(outEV, 0, nc * sizeof(float));
        return;
    }

    int player = tree.nodePlayer[nodeId];
    uint32_t numActions = tree.nodeNumActions[nodeId];
    uint32_t actionOffset = tree.nodeActionOffset[nodeId];

    // Get current strategy via regret matching
    float* strategy = ctx_.strategyAt(depth);
    store_.getCurrentStrategy(nodeId, numActions, strategy);

    // Local node EV accumulator
    float* nodeEV = ctx_.nodeEVAt(depth);
    std::memset(nodeEV, 0, nc * sizeof(float));

    for (uint32_t a = 0; a < numActions; a++) {
        int32_t childId = tree.childNodeId[actionOffset + a];

        // Build child reaches
        float* childOop = ctx_.childOopAt(depth);
        float* childIp = ctx_.childIpAt(depth);
        if (player == 0) {
            simd::mul(childOop, oopReach, &strategy[a * nc], nc);
            simd::copy(childIp, ipReach, nc);
        } else {
            simd::copy(childOop, oopReach, nc);
            simd::mul(childIp, ipReach, &strategy[a * nc], nc);
        }

        // Skip dead branches
        const float* actingReach = (player == 0) ? childOop : childIp;
        if (isReachDeadLocal(actingReach, nc)) {
            float* aev = ctx_.actionEVAt(depth, a);
            std::memset(aev, 0, nc * sizeof(float));
            continue;
        }

        // Recurse
        float* actionEV = ctx_.actionEVAt(depth, a);
        streetTraverseNode(childId, depth + 1, childOop, childIp, traverser, actionEV);

        // Accumulate node EV
        if (player == traverser) {
            simd::fma(nodeEV, &strategy[a * nc], actionEV, nc);
        } else {
            simd::add(nodeEV, actionEV, nc);
        }
    }

    // Update regrets and strategy sums
    if (player == traverser) {
        const float* playerReach = (traverser == 0) ? oopReach : ipReach;
        float* regretDeltas = ctx_.regretDeltaAt(depth);
        float* stratWeights = ctx_.stratWeightAt(depth);

        for (uint32_t a = 0; a < numActions; a++) {
            float* actionEV = ctx_.actionEVAt(depth, a);
            simd::sub(&regretDeltas[a * nc], actionEV, nodeEV, nc);
            simd::mulScale(&stratWeights[a * nc], playerReach, &strategy[a * nc], iterWeight_, nc);
        }

        store_.updateRegrets(nodeId, numActions, regretDeltas);
        store_.addStrategyWeights(nodeId, numActions, stratWeights);
    }

    // Copy result to output
    std::memcpy(outEV, nodeEV, nc * sizeof(float));
}

// ────────────────────────────────────────────────
// solve — run CFR+ iterations
// ────────────────────────────────────────────────

void StreetSolver::solve(uint32_t iterations) {
    std::vector<float> reachOOP(nc_), reachIP(nc_), resultEV(nc_);
    iterWeight_ = 1.0f;

    for (uint32_t iter = 0; iter < iterations; iter++) {
        // OOP traversal
        std::memcpy(reachOOP.data(), oopInitReach_.data(), nc_ * sizeof(float));
        std::memcpy(reachIP.data(), ipInitReach_.data(), nc_ * sizeof(float));
        streetTraverseNode(0, 0, reachOOP.data(), reachIP.data(), 0, resultEV.data());

        // IP traversal
        std::memcpy(reachOOP.data(), oopInitReach_.data(), nc_ * sizeof(float));
        std::memcpy(reachIP.data(), ipInitReach_.data(), nc_ * sizeof(float));
        streetTraverseNode(0, 0, reachOOP.data(), reachIP.data(), 1, resultEV.data());
    }
}

// ────────────────────────────────────────────────
// Result accessors
// ────────────────────────────────────────────────

float* StreetSolver::getStrategySumsPtr() {
    return store_.strategySums.data();
}

uint32_t StreetSolver::getStrategySumsLen() {
    return (uint32_t)store_.strategySums.size();
}

float* StreetSolver::getRegretsPtr() {
    return store_.regrets.data();
}

uint32_t StreetSolver::getRegretsLen() {
    return (uint32_t)store_.regrets.size();
}

uint32_t StreetSolver::getNC() const {
    return nc_;
}

} // namespace ez_cfr
