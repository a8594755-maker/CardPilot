#pragma once

#include "types.h"
#include "flat_tree.h"
#include "array_store.h"
#include "terminal_cache.h"
#include "combo_mapping.h"
#include "nn_evaluator.h"
#include <vector>
#include <random>
#include <functional>
#include <memory>
#include <set>

namespace ez_cfr {

// Forward declarations for terminal EV functions
void computeShowdownEVCached(
    const TerminalCache& cache, StreetBufs& bufs,
    float pot, float s0, float s1,
    const float* oopReach, const float* ipReach,
    int traverser, float* outEV);

void computeFoldEVFast(
    const int32_t* comboCards, const int32_t* cardCombos,
    const int32_t* cardCombosLen, StreetBufs& bufs, uint32_t nc,
    float pot, float s0, float s1, int traverser, int folder,
    const float* oopReach, const float* ipReach, float* outEV);

// TerminalCache builder (declared in combo_mapping.cpp)
TerminalCache buildTerminalCache(const ValidCombos& combos,
                                 const int32_t* board, int boardLen);

// River subtree
struct RiverSubtree {
    int32_t riverCard;
    ComboMapping mapping;
    OwnedFlatTree tree;
    ArrayStore store;
    TerminalCache cache;
    uint32_t childNC;
};

// Turn subtree
struct TurnSubtree {
    int32_t turnCard;
    ComboMapping mapping;
    OwnedFlatTree tree;
    ArrayStore store;
    uint32_t childNC;
    ValidCombos turnCombos;   // for fold EV on turn
    std::vector<RiverSubtree> rivers;
    std::vector<int32_t> comboGlobalIds;  // [childNC] canonical 0..1325 index per turn combo
};

// Pre-allocated traversal context (one per street level)
struct TraversalCtx {
    uint32_t maxDepth;
    uint32_t maxActions;
    uint32_t nc;

    // All stored as flat vectors indexed by [depth * maxActions * nc + action * nc + combo]
    std::vector<float> nodeEV;         // [maxDepth * nc]
    std::vector<float> childOopReach;  // [maxDepth * nc]
    std::vector<float> childIpReach;   // [maxDepth * nc]
    std::vector<float> actionEVs;      // [maxDepth * maxActions * nc]
    std::vector<float> strategy;       // [maxDepth * maxActions * nc]
    std::vector<float> regretDeltas;   // [maxDepth * maxActions * nc]
    std::vector<float> stratWeights;   // [maxDepth * maxActions * nc]

    static TraversalCtx create(uint32_t numNodes, uint32_t maxActions, uint32_t nc) {
        TraversalCtx ctx;
        ctx.maxDepth = numNodes;
        ctx.maxActions = maxActions;
        ctx.nc = nc;
        ctx.nodeEV.resize(numNodes * nc, 0.0f);
        ctx.childOopReach.resize(numNodes * nc, 0.0f);
        ctx.childIpReach.resize(numNodes * nc, 0.0f);
        size_t actSize = (size_t)numNodes * maxActions * nc;
        ctx.actionEVs.resize(actSize, 0.0f);
        ctx.strategy.resize(actSize, 0.0f);
        ctx.regretDeltas.resize(actSize, 0.0f);
        ctx.stratWeights.resize(actSize, 0.0f);
        return ctx;
    }

    float* nodeEVAt(uint32_t depth) { return nodeEV.data() + depth * nc; }
    float* childOopAt(uint32_t depth) { return childOopReach.data() + depth * nc; }
    float* childIpAt(uint32_t depth) { return childIpReach.data() + depth * nc; }
    float* actionEVAt(uint32_t depth, uint32_t action) {
        return actionEVs.data() + (depth * maxActions + action) * nc;
    }
    float* strategyAt(uint32_t depth) { return strategy.data() + depth * maxActions * nc; }
    float* regretDeltaAt(uint32_t depth) { return regretDeltas.data() + depth * maxActions * nc; }
    float* stratWeightAt(uint32_t depth) { return stratWeights.data() + depth * maxActions * nc; }
};

// Main solver result
struct FullGameResult {
    uint32_t flopNC;
    uint32_t flopNumNodes;
    uint32_t flopTotalActions;
    // Pointers into solver-owned memory
    float* strategySums;
    float* regrets;
    uint32_t strategySumsLen;
    double elapsedMs;
    size_t memoryMB;
};

// Callback type for NN-based river value prediction
// Replaces exhaustive 48-river enumeration with a single neural network call.
// The callback receives raw C++ pointers (internally converted to uintptr_t at the Embind layer).
using RiverValueFn = std::function<void(
    const int32_t* board,              // [boardLen] flop board cards
    int boardLen,
    int32_t turnCard,                  // the turn card dealt
    float potOffset,                   // pot - startingPot at this terminal
    float startingPot,
    float effectiveStack,
    uint32_t turnNC,                   // number of valid turn combos
    const int32_t* comboGlobalIds,     // [turnNC] canonical 0..1325 index per combo
    const float* oopReach,             // [turnNC] OOP reach probabilities
    const float* ipReach,              // [turnNC] IP reach probabilities
    int traverser,                     // 0 (OOP) or 1 (IP)
    float* outEV                       // [turnNC] output: write CFV here
)>;

// The C++ CFR solver
class CfrSolver {
public:
    CfrSolver();
    ~CfrSolver();

    // Set/clear NN river value callback
    void setRiverValueFn(RiverValueFn fn);
    void clearRiverValueFn();

    // Initialize/flush native ORT evaluator (non-WASM path).
    void initNativeNNEvaluatorFromEnv();
    void flushNativeNNEvaluator();

    // Initialize flop tree from TS-provided flat arrays
    void initFlop(
        const uint8_t* nodePlayer, const uint8_t* nodeNumActions,
        const uint32_t* nodeActionOffset, const int32_t* childNodeId,
        const float* terminalPot, const float* terminalStacks,
        const uint8_t* terminalIsShowdown, const int8_t* terminalFolder,
        uint32_t numNodes, uint32_t numTerminals, uint32_t totalActions,
        const int32_t* comboCards, uint32_t numCombos,
        const float* oopReach, const float* ipReach,
        float startingPot, float effectiveStack
    );

    // Build inner tree template + all turn/river subtrees
    void buildSubtrees(
        const int32_t* boardCards, int boardLen,
        // Inner tree template
        const uint8_t* innerNodePlayer, const uint8_t* innerNodeNumActions,
        const uint32_t* innerNodeActionOffset, const int32_t* innerChildNodeId,
        const float* innerTerminalPot, const float* innerTerminalStacks,
        const uint8_t* innerTerminalIsShowdown, const int8_t* innerTerminalFolder,
        uint32_t innerNumNodes, uint32_t innerNumTerminals, uint32_t innerTotalActions,
        // Config
        float rakePercentage, float rakeCap,
        // When true, skip building river subtrees (NN mode — saves ~635MB)
        bool skipRiverSubtrees = false,
        // Progress callback (optional, nullptr to skip)
        std::function<void(const char*, float)> onProgress = nullptr
    );

    // Run CFR iterations
    void solve(uint32_t iterations, bool mccfr, uint32_t globalIterOffset,
               std::function<void(const char*, float)> onProgress = nullptr);

    // Result extraction
    float* getStrategySumsPtr();
    uint32_t getStrategySumsLen();
    float* getRegretsPtr();
    uint32_t getFlopNC() const { return flopNC_; }

    // Solve all 48 river subtrees for a given turn board in batch.
    // Used by the mining pipeline for ground-truth CFV generation.
    // Outputs averaged CFVs in turn-local combo space.
    void solveRiverBatch(
        const int32_t* turnBoard, int turnBoardLen,
        const int32_t* turnComboCards, uint32_t turnNC,
        const float* oopReach, const float* ipReach,
        // River tree template
        const uint8_t* innerNodePlayer, const uint8_t* innerNodeNumActions,
        const uint32_t* innerNodeActionOffset, const int32_t* innerChildNodeId,
        const float* innerTerminalPot, const float* innerTerminalStacks,
        const uint8_t* innerTerminalIsShowdown, const int8_t* innerTerminalFolder,
        uint32_t innerNumNodes, uint32_t innerNumTerminals, uint32_t innerTotalActions,
        uint32_t iterations,
        float rakePercentage, float rakeCap,
        float potOffset,
        // Output: write averaged CFVs here [turnNC] each
        float* outCfvOOP, float* outCfvIP
    );

    void destroy();

    // Set RNG seed (for parallel workers with distinct seeds)
    void setSeed(uint32_t seed) { rng_ = std::mt19937(seed); }

    // ─── Mining: solve all 48 river subtrees for a given turn state ───
    // Returns averaged per-combo CFVs in 1326-space for both players.
    void solveTurnRivers(
        const int32_t* turnBoard, int turnBoardLen,
        // Inner (river) tree template
        const uint8_t* innerNodePlayer, const uint8_t* innerNodeNumActions,
        const uint32_t* innerNodeActionOffset, const int32_t* innerChildNodeId,
        const float* innerTerminalPot, const float* innerTerminalStacks,
        const uint8_t* innerTerminalIsShowdown, const int8_t* innerTerminalFolder,
        uint32_t innerNumNodes, uint32_t innerNumTerminals, uint32_t innerTotalActions,
        // Reaches in canonical 1326-space
        const float* oopReach1326, const float* ipReach1326,
        // Config
        float potOffset, float startingPot, float effectiveStack,
        uint32_t iterations,
        float rakePercentage, float rakeCap
    );

    // Result accessors for solveTurnRivers
    float* getMineResultOOPPtr() { return mineResultCfvOOP1326_.data(); }
    float* getMineResultIPPtr() { return mineResultCfvIP1326_.data(); }

private:
    // Mining result buffers (1326 floats each)
    std::vector<float> mineResultCfvOOP1326_;
    std::vector<float> mineResultCfvIP1326_;

    // Flop data
    OwnedFlatTree flopTree_;
    ArrayStore flopStore_;
    ValidCombos flopCombos_;
    uint32_t flopNC_ = 0;
    std::vector<float> flopOopReach_;
    std::vector<float> flopIpReach_;
    float startingPot_ = 0.0f;
    float effectiveStack_ = 0.0f;

    // Board
    std::vector<int32_t> board_;

    // Turn/River subtrees
    std::vector<TurnSubtree> turnSubtrees_;
    uint32_t maxTurnNC_ = 0;
    uint32_t maxRiverNC_ = 0;

    // Traversal contexts (one per street)
    TraversalCtx flopCtx_;
    TraversalCtx turnCtx_;
    TraversalCtx riverCtx_;

    // Chance node buffers
    std::vector<float> turnChanceOop_, turnChanceIp_, turnChanceEV_;
    std::vector<float> riverChanceOop_, riverChanceIp_, riverChanceEV_;

    // Street-level reusable buffers
    StreetBufs flopBufs_, turnBufs_, riverBufs_;

    // MCCFR state
    bool mccfr_ = false;
    float iterWeight_ = 1.0f;
    std::mt19937 rng_;
    // Tree-wide chance sampling: pre-sampled indices valid for one traverser pass.
    // All showdown terminals in the same pass use the same turn card, and all
    // turn showdown terminals use the same river card, reducing regret variance.
    int32_t sampledTurnIdx_ = -1;
    int32_t sampledRiverIdx_ = -1;

    // NN river value callback state
    bool useNNRiver_ = false;
    RiverValueFn riverValueFn_;
    int32_t currentTurnCard_ = -1;
    const int32_t* currentComboGlobalIds_ = nullptr;
    std::unique_ptr<NativeNNEvaluator> nativeNNEvaluator_;
    float rakePercentage_ = 0.0f;
    float rakeCap_ = 0.0f;

    // Internal traversal functions
    void cfrTraverseNode(
        const FlatTree& tree, ArrayStore& store, uint32_t nc,
        float* oopReach, float* ipReach, int traverser,
        int32_t nodeId, uint32_t depth, TraversalCtx& ctx,
        // Callbacks
        std::function<void(float pot, float s0, float s1,
                          float* oR, float* iR, int trav, float* out)> onShowdown,
        std::function<void(float pot, float s0, float s1,
                          float* oR, float* iR, int trav, int folder, float* out)> onFold,
        float* outEV,
        float potOffset = 0.0f
    );

    void cfrTraverseFlop(
        float* oopReach, float* ipReach, int traverser, float* outEV);

    void cfrTraverseTurn(
        TurnSubtree& ts,
        float* oopReach, float* ipReach, int traverser,
        float* outEV, float potOffset, float startingPot);

    void cfrTraverseRiver(
        RiverSubtree& rs,
        float* oopReach, float* ipReach, int traverser,
        float* outEV, float potOffset);

    void computeTurnChanceValue(
        float* oopReach, float* ipReach, int traverser,
        float* outEV, float potOffset, float startingPot);

    void computeRiverChanceValue(
        std::vector<RiverSubtree>& rivers, uint32_t turnNC,
        float* oopReach, float* ipReach, int traverser,
        float* outEV, float potOffset);
};

// ═══════════════════════════════════════════════
// StreetSolver — per-street CFR+ for real-time resolving
// ═══════════════════════════════════════════════

// Callback for transition terminals (street boundary → next street).
// Invoked during traversal to get EV from a value network or sub-solve.
// Args: terminalId, numCombos, pot, stack0, stack1, oopReach, ipReach, traverser, outEV
using StreetTransitionFn = std::function<void(
    uint32_t ti, uint32_t nc, float pot, float s0, float s1,
    const float* oopReach, const float* ipReach, int traverser, float* outEV)>;

class StreetSolver {
public:
    StreetSolver();
    ~StreetSolver();

    void init(
        const uint8_t* nodePlayer, const uint8_t* nodeNumActions,
        const uint32_t* nodeActionOffset, const int32_t* childNodeId,
        const float* terminalPot, const float* terminalStacks,
        const uint8_t* terminalIsShowdown, const int8_t* terminalFolder,
        uint32_t numNodes, uint32_t numTerminals, uint32_t totalActions,
        const int32_t* boardCards, int boardLen,
        const int32_t* comboCards, uint32_t numCombos,
        const float* oopReach, const float* ipReach
    );

    void setTransitionFn(StreetTransitionFn fn);
    void clearTransitionFn();

    void solve(uint32_t iterations);

    float* getStrategySumsPtr();
    uint32_t getStrategySumsLen();
    float* getRegretsPtr();
    uint32_t getRegretsLen();
    uint32_t getNC() const;

    void destroy();

private:
    OwnedFlatTree tree_;
    ArrayStore store_;
    ValidCombos combos_;
    TerminalCache cache_;
    uint32_t nc_ = 0;
    TraversalCtx ctx_;
    StreetBufs bufs_;
    float iterWeight_ = 1.0f;
    std::vector<float> oopInitReach_, ipInitReach_;
    std::set<uint32_t> transitionTerminals_;
    bool useTransition_ = false;
    StreetTransitionFn transitionFn_;

    void streetTraverseNode(
        int32_t nodeId, uint32_t depth,
        float* oopReach, float* ipReach, int traverser, float* outEV);
};

} // namespace ez_cfr
