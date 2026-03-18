#include "ez_cfr/nn_evaluator.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <vector>

int main() {
    std::printf("EZ-CFR native runtime bootstrap\n");

    auto evaluator = ez_cfr::createNativeNNEvaluatorFromEnv();
    if (!evaluator) {
        std::printf(
            "Native NN evaluator disabled (set EZ_GTO_ORT_MODEL to enable ORT path)\n"
        );
        return 0;
    }

    std::printf("Evaluator backend: %s\n", evaluator->backend().c_str());

    // Synthetic smoke request for runtime validation.
    std::array<int32_t, 3> board{40, 42, 18};
    std::vector<int32_t> gids(16);
    std::vector<float> oopReach(16, 0.01f);
    std::vector<float> ipReach(16, 0.01f);
    std::vector<float> outEV(16, 0.0f);
    for (int i = 0; i < 16; i++) gids[i] = i * 3;

    ez_cfr::NNEvalState state;
    state.board = board.data();
    state.boardLen = static_cast<int>(board.size());
    state.turnCard = 7;
    state.potOffset = 12.5f;
    state.startingPot = 40.0f;
    state.effectiveStack = 100.0f;
    state.turnNC = static_cast<uint32_t>(gids.size());
    state.comboGlobalIds = gids.data();
    state.oopReach = oopReach.data();
    state.ipReach = ipReach.data();
    state.traverser = 0;
    state.outEV = outEV.data();

    const bool ortOk = evaluator->evaluate(state);

    float maxAbs = 0.0f;
    for (float v : outEV) maxAbs = std::max(maxAbs, std::abs(v));
    std::printf("Smoke inference done. ortOk=%d max|EV|=%.6f\n", ortOk ? 1 : 0, maxAbs);
    return 0;
}
