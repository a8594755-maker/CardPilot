#pragma once

#include <cstdint>
#include <cstring>
#include <cmath>
#include <algorithm>
#include <vector>
#include <random>

namespace ez_cfr {

// Constants matching TypeScript solver
constexpr float PRUNE_THRESHOLD = 1e-8f;
constexpr int MAX_COMBOS_PER_CARD = 64;
constexpr int MAX_CARDS = 52;
constexpr int MAX_DEPTH = 128;   // conservative upper bound for tree depth
constexpr int MAX_ACTIONS = 8;   // max actions per node (fold/check/call + raises)

// Terminal node encoding (matches flat-tree.ts)
inline bool isTerminal(int32_t nodeId) { return nodeId < 0; }
inline int32_t decodeTerminalId(int32_t nodeId) { return -(nodeId + 1); }

} // namespace ez_cfr
