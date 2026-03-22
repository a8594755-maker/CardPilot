#ifdef __EMSCRIPTEN__
#include <emscripten/bind.h>
#include <emscripten/val.h>
#endif

#include "ez_cfr/cfr_engine.h"
#include <cstdio>

using namespace ez_cfr;

// Wrapper class that accepts uintptr_t (WASM heap pointers from JS)
class CfrSolverBinding {
public:
    CfrSolverBinding() {}

    void initFlop(
        uintptr_t nodePlayer, uintptr_t nodeNumActions,
        uintptr_t nodeActionOffset, uintptr_t childNodeId,
        uintptr_t terminalPot, uintptr_t terminalStacks,
        uintptr_t terminalIsShowdown, uintptr_t terminalFolder,
        uint32_t numNodes, uint32_t numTerminals, uint32_t totalActions,
        uintptr_t comboCards, uint32_t numCombos,
        uintptr_t oopReach, uintptr_t ipReach,
        float startingPot, float effectiveStack)
    {
        solver_.initFlop(
            reinterpret_cast<const uint8_t*>(nodePlayer),
            reinterpret_cast<const uint8_t*>(nodeNumActions),
            reinterpret_cast<const uint32_t*>(nodeActionOffset),
            reinterpret_cast<const int32_t*>(childNodeId),
            reinterpret_cast<const float*>(terminalPot),
            reinterpret_cast<const float*>(terminalStacks),
            reinterpret_cast<const uint8_t*>(terminalIsShowdown),
            reinterpret_cast<const int8_t*>(terminalFolder),
            numNodes, numTerminals, totalActions,
            reinterpret_cast<const int32_t*>(comboCards), numCombos,
            reinterpret_cast<const float*>(oopReach),
            reinterpret_cast<const float*>(ipReach),
            startingPot, effectiveStack
        );
    }

    void buildSubtrees(
        uintptr_t boardCards, int boardLen,
        uintptr_t innerNodePlayer, uintptr_t innerNodeNumActions,
        uintptr_t innerNodeActionOffset, uintptr_t innerChildNodeId,
        uintptr_t innerTerminalPot, uintptr_t innerTerminalStacks,
        uintptr_t innerTerminalIsShowdown, uintptr_t innerTerminalFolder,
        uint32_t innerNumNodes, uint32_t innerNumTerminals, uint32_t innerTotalActions,
        float rakePercentage, float rakeCap,
        bool skipRiverSubtrees)
    {
        solver_.buildSubtrees(
            reinterpret_cast<const int32_t*>(boardCards), boardLen,
            reinterpret_cast<const uint8_t*>(innerNodePlayer),
            reinterpret_cast<const uint8_t*>(innerNodeNumActions),
            reinterpret_cast<const uint32_t*>(innerNodeActionOffset),
            reinterpret_cast<const int32_t*>(innerChildNodeId),
            reinterpret_cast<const float*>(innerTerminalPot),
            reinterpret_cast<const float*>(innerTerminalStacks),
            reinterpret_cast<const uint8_t*>(innerTerminalIsShowdown),
            reinterpret_cast<const int8_t*>(innerTerminalFolder),
            innerNumNodes, innerNumTerminals, innerTotalActions,
            rakePercentage, rakeCap,
            skipRiverSubtrees,
            [](const char* msg, float pct) {
                printf("  [C++] %s (%.0f%%)\n", msg, pct);
            }
        );
    }

    void solve(uint32_t iterations, bool mccfr, uint32_t globalIterOffset) {
        solver_.solve(iterations, mccfr, globalIterOffset,
            [](const char* msg, float pct) {
                printf("  [C++] %s (%.0f%%)\n", msg, pct);
            }
        );
    }

#ifdef __EMSCRIPTEN__
    void enableNNRiverValue(emscripten::val callback) {
        // Store the JS callback and wrap it as a C++ RiverValueFn.
        // The callback receives WASM heap pointers which JS reads via HEAPF32/HEAP32 views.
        nnCallback_ = callback;
        solver_.setRiverValueFn(
            [this](const int32_t* board, int boardLen, int32_t turnCard,
                   float potOffset, float startingPot, float effectiveStack,
                   uint32_t turnNC, const int32_t* comboGlobalIds,
                   const float* oopReach, const float* ipReach,
                   int traverser, float* outEV) {
                nnCallback_(
                    (unsigned)reinterpret_cast<uintptr_t>(board),
                    boardLen,
                    (int)turnCard,
                    potOffset, startingPot, effectiveStack,
                    (unsigned)turnNC,
                    (unsigned)reinterpret_cast<uintptr_t>(comboGlobalIds),
                    (unsigned)reinterpret_cast<uintptr_t>(oopReach),
                    (unsigned)reinterpret_cast<uintptr_t>(ipReach),
                    traverser,
                    (unsigned)reinterpret_cast<uintptr_t>(outEV)
                );
            }
        );
    }

    void disableNNRiverValue() {
        solver_.clearRiverValueFn();
        nnCallback_ = emscripten::val::null();
    }
#endif

    void solveRiverBatch(
        uintptr_t turnBoard, int turnBoardLen,
        uintptr_t turnComboCards, uint32_t turnNC,
        uintptr_t oopReach, uintptr_t ipReach,
        uintptr_t innerNodePlayer, uintptr_t innerNodeNumActions,
        uintptr_t innerNodeActionOffset, uintptr_t innerChildNodeId,
        uintptr_t innerTerminalPot, uintptr_t innerTerminalStacks,
        uintptr_t innerTerminalIsShowdown, uintptr_t innerTerminalFolder,
        uint32_t innerNumNodes, uint32_t innerNumTerminals, uint32_t innerTotalActions,
        uint32_t iterations,
        float rakePercentage, float rakeCap,
        float potOffset,
        uintptr_t outCfvOOP, uintptr_t outCfvIP)
    {
        solver_.solveRiverBatch(
            reinterpret_cast<const int32_t*>(turnBoard), turnBoardLen,
            reinterpret_cast<const int32_t*>(turnComboCards), turnNC,
            reinterpret_cast<const float*>(oopReach),
            reinterpret_cast<const float*>(ipReach),
            reinterpret_cast<const uint8_t*>(innerNodePlayer),
            reinterpret_cast<const uint8_t*>(innerNodeNumActions),
            reinterpret_cast<const uint32_t*>(innerNodeActionOffset),
            reinterpret_cast<const int32_t*>(innerChildNodeId),
            reinterpret_cast<const float*>(innerTerminalPot),
            reinterpret_cast<const float*>(innerTerminalStacks),
            reinterpret_cast<const uint8_t*>(innerTerminalIsShowdown),
            reinterpret_cast<const int8_t*>(innerTerminalFolder),
            innerNumNodes, innerNumTerminals, innerTotalActions,
            iterations, rakePercentage, rakeCap, potOffset,
            reinterpret_cast<float*>(outCfvOOP),
            reinterpret_cast<float*>(outCfvIP)
        );
    }

    void setSeed(uint32_t seed) {
        solver_.setSeed(seed);
    }

    void solveTurnRivers(
        uintptr_t turnBoard, int turnBoardLen,
        uintptr_t nodePlayer, uintptr_t nodeNumActions,
        uintptr_t nodeActionOffset, uintptr_t childNodeId,
        uintptr_t terminalPot, uintptr_t terminalStacks,
        uintptr_t terminalIsShowdown, uintptr_t terminalFolder,
        uint32_t numNodes, uint32_t numTerminals, uint32_t totalActions,
        uintptr_t oopReach1326, uintptr_t ipReach1326,
        float potOffset, float startingPot, float effectiveStack,
        uint32_t iterations,
        float rakePercentage, float rakeCap)
    {
        solver_.solveTurnRivers(
            reinterpret_cast<const int32_t*>(turnBoard), turnBoardLen,
            reinterpret_cast<const uint8_t*>(nodePlayer),
            reinterpret_cast<const uint8_t*>(nodeNumActions),
            reinterpret_cast<const uint32_t*>(nodeActionOffset),
            reinterpret_cast<const int32_t*>(childNodeId),
            reinterpret_cast<const float*>(terminalPot),
            reinterpret_cast<const float*>(terminalStacks),
            reinterpret_cast<const uint8_t*>(terminalIsShowdown),
            reinterpret_cast<const int8_t*>(terminalFolder),
            numNodes, numTerminals, totalActions,
            reinterpret_cast<const float*>(oopReach1326),
            reinterpret_cast<const float*>(ipReach1326),
            potOffset, startingPot, effectiveStack,
            iterations, rakePercentage, rakeCap
        );
    }

    uintptr_t getMineResultOOPPtr() {
        return reinterpret_cast<uintptr_t>(solver_.getMineResultOOPPtr());
    }

    uintptr_t getMineResultIPPtr() {
        return reinterpret_cast<uintptr_t>(solver_.getMineResultIPPtr());
    }

    uintptr_t getStrategySumsPtr() {
        return reinterpret_cast<uintptr_t>(solver_.getStrategySumsPtr());
    }

    uint32_t getStrategySumsLen() {
        return solver_.getStrategySumsLen();
    }

    uintptr_t getRegretsPtr() {
        return reinterpret_cast<uintptr_t>(solver_.getRegretsPtr());
    }

    uint32_t getFlopNC() {
        return solver_.getFlopNC();
    }

    void destroy() {
        solver_.destroy();
    }

private:
    CfrSolver solver_;
#ifdef __EMSCRIPTEN__
    emscripten::val nnCallback_ = emscripten::val::null();
#endif
};

// ═══════════════════════════════════════════════
// StreetSolverBinding — per-street WASM API
// ═══════════════════════════════════════════════

class StreetSolverBinding {
public:
    StreetSolverBinding() {}

    void init(
        uintptr_t nodePlayer, uintptr_t nodeNumActions,
        uintptr_t nodeActionOffset, uintptr_t childNodeId,
        uintptr_t terminalPot, uintptr_t terminalStacks,
        uintptr_t terminalIsShowdown, uintptr_t terminalFolder,
        uint32_t numNodes, uint32_t numTerminals, uint32_t totalActions,
        uintptr_t boardCards, int boardLen,
        uintptr_t comboCards, uint32_t numCombos,
        uintptr_t oopReach, uintptr_t ipReach)
    {
        solver_.init(
            reinterpret_cast<const uint8_t*>(nodePlayer),
            reinterpret_cast<const uint8_t*>(nodeNumActions),
            reinterpret_cast<const uint32_t*>(nodeActionOffset),
            reinterpret_cast<const int32_t*>(childNodeId),
            reinterpret_cast<const float*>(terminalPot),
            reinterpret_cast<const float*>(terminalStacks),
            reinterpret_cast<const uint8_t*>(terminalIsShowdown),
            reinterpret_cast<const int8_t*>(terminalFolder),
            numNodes, numTerminals, totalActions,
            reinterpret_cast<const int32_t*>(boardCards), boardLen,
            reinterpret_cast<const int32_t*>(comboCards), numCombos,
            reinterpret_cast<const float*>(oopReach),
            reinterpret_cast<const float*>(ipReach)
        );
    }

    void solve(uint32_t iterations) {
        solver_.solve(iterations);
    }

#ifdef __EMSCRIPTEN__
    void enableTransitionCallback(emscripten::val callback) {
        transitionCallback_ = callback;
        solver_.setTransitionFn(
            [this](uint32_t ti, uint32_t nc, float pot, float s0, float s1,
                   const float* oopReach, const float* ipReach,
                   int traverser, float* outEV) {
                transitionCallback_(
                    (unsigned)ti,
                    (unsigned)nc,
                    pot, s0, s1,
                    (unsigned)reinterpret_cast<uintptr_t>(oopReach),
                    (unsigned)reinterpret_cast<uintptr_t>(ipReach),
                    traverser,
                    (unsigned)reinterpret_cast<uintptr_t>(outEV)
                );
            }
        );
    }

    void disableTransitionCallback() {
        solver_.clearTransitionFn();
        transitionCallback_ = emscripten::val::null();
    }
#endif

    uintptr_t getStrategySumsPtr() {
        return reinterpret_cast<uintptr_t>(solver_.getStrategySumsPtr());
    }

    uint32_t getStrategySumsLen() {
        return solver_.getStrategySumsLen();
    }

    uintptr_t getRegretsPtr() {
        return reinterpret_cast<uintptr_t>(solver_.getRegretsPtr());
    }

    uint32_t getRegretsLen() {
        return solver_.getRegretsLen();
    }

    uint32_t getNC() {
        return solver_.getNC();
    }

    void destroy() {
        solver_.destroy();
    }

private:
    StreetSolver solver_;
#ifdef __EMSCRIPTEN__
    emscripten::val transitionCallback_ = emscripten::val::null();
#endif
};

#ifdef __EMSCRIPTEN__
EMSCRIPTEN_BINDINGS(cfr_module) {
    emscripten::class_<CfrSolverBinding>("CfrSolver")
        .constructor<>()
        .function("initFlop", &CfrSolverBinding::initFlop)
        .function("buildSubtrees", &CfrSolverBinding::buildSubtrees)
        .function("solve", &CfrSolverBinding::solve)
        .function("getStrategySumsPtr", &CfrSolverBinding::getStrategySumsPtr)
        .function("getStrategySumsLen", &CfrSolverBinding::getStrategySumsLen)
        .function("getRegretsPtr", &CfrSolverBinding::getRegretsPtr)
        .function("getFlopNC", &CfrSolverBinding::getFlopNC)
        .function("setSeed", &CfrSolverBinding::setSeed)
        .function("enableNNRiverValue", &CfrSolverBinding::enableNNRiverValue)
        .function("disableNNRiverValue", &CfrSolverBinding::disableNNRiverValue)
        .function("solveTurnRivers", &CfrSolverBinding::solveTurnRivers)
        .function("getMineResultOOPPtr", &CfrSolverBinding::getMineResultOOPPtr)
        .function("getMineResultIPPtr", &CfrSolverBinding::getMineResultIPPtr)
        .function("destroy", &CfrSolverBinding::destroy);

    emscripten::class_<StreetSolverBinding>("StreetSolver")
        .constructor<>()
        .function("init", &StreetSolverBinding::init)
        .function("solve", &StreetSolverBinding::solve)
        .function("enableTransitionCallback", &StreetSolverBinding::enableTransitionCallback)
        .function("disableTransitionCallback", &StreetSolverBinding::disableTransitionCallback)
        .function("getStrategySumsPtr", &StreetSolverBinding::getStrategySumsPtr)
        .function("getStrategySumsLen", &StreetSolverBinding::getStrategySumsLen)
        .function("getRegretsPtr", &StreetSolverBinding::getRegretsPtr)
        .function("getRegretsLen", &StreetSolverBinding::getRegretsLen)
        .function("getNC", &StreetSolverBinding::getNC)
        .function("destroy", &StreetSolverBinding::destroy);
}
#endif
