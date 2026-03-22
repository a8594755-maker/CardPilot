#pragma once

#include "types.h"
#include "simd_utils.h"
#include <vector>

namespace ez_cfr {

// CFR+ regret and strategy store.
// Memory layout: for node n with action a and combo c:
//   regrets[nodeOffset[n] + a * numCombos + c]
//   strategySums[nodeOffset[n] + a * numCombos + c]
class ArrayStore {
public:
    uint32_t numCombos;
    uint32_t totalActions;
    uint32_t numNodes;
    std::vector<uint32_t> nodeOffset;
    std::vector<float> regrets;
    std::vector<float> strategySums;

    ArrayStore() : numCombos(0), totalActions(0), numNodes(0) {}

    ArrayStore(uint32_t numNodes, uint32_t totalActions, uint32_t numCombos,
               const uint8_t* nodeNumActions)
        : numCombos(numCombos), totalActions(totalActions), numNodes(numNodes)
    {
        nodeOffset.resize(numNodes);
        uint32_t off = 0;
        for (uint32_t n = 0; n < numNodes; n++) {
            nodeOffset[n] = off;
            off += nodeNumActions[n] * numCombos;
        }
        regrets.resize(off, 0.0f);
        strategySums.resize(off, 0.0f);
    }

    // Regret matching: compute current strategy from regrets (SIMD)
    void getCurrentStrategy(uint32_t nodeId, uint32_t numActions, float* out) const {
        simd::regretMatch(regrets.data(), nodeOffset[nodeId], numCombos, numActions, out);
    }

    // CFR+ regret update: accumulate delta then floor at 0.
    void updateRegrets(uint32_t nodeId, uint32_t numActions, const float* deltas) {
        const uint32_t base = nodeOffset[nodeId];
        const uint32_t nc = numCombos;
        for (uint32_t a = 0; a < numActions; a++) {
            simd::addMax0(&regrets[base + a * nc], &deltas[a * nc], nc);
        }
    }

    // Accumulate weighted strategy (SIMD)
    void addStrategyWeights(uint32_t nodeId, uint32_t numActions, const float* weights) {
        const uint32_t base = nodeOffset[nodeId];
        const uint32_t nc = numCombos;
        for (uint32_t a = 0; a < numActions; a++) {
            simd::add(&strategySums[base + a * nc], &weights[a * nc], nc);
        }
    }

    // Get average strategy (for result extraction, SIMD)
    void getAverageStrategy(uint32_t nodeId, uint32_t numActions, float* out) const {
        simd::regretMatch(strategySums.data(), nodeOffset[nodeId], numCombos, numActions, out);
    }

    // DCFR discount: multiply all strategy sums by factor (SIMD)
    void discountStrategySums(float factor) {
        simd::scale(strategySums.data(), factor, (uint32_t)strategySums.size());
    }

    size_t estimateMemoryBytes() const {
        return regrets.size() * sizeof(float) + strategySums.size() * sizeof(float)
             + nodeOffset.size() * sizeof(uint32_t);
    }
};

} // namespace ez_cfr
