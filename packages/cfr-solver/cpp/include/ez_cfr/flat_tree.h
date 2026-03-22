#pragma once

#include "types.h"

namespace ez_cfr {

// Mirrors the TypeScript FlatTree structure.
// All arrays are pointers into externally-owned memory (WASM heap or malloc'd).
struct FlatTree {
    uint32_t numNodes;
    uint32_t numTerminals;
    uint32_t totalActions;

    // Per-action-node arrays (length = numNodes)
    const uint8_t*  nodePlayer;        // 0=OOP, 1=IP
    const uint8_t*  nodeNumActions;    // actions at this node
    const uint32_t* nodeActionOffset;  // offset into childNodeId
    const float*    nodePot;           // pot at this node
    const float*    nodeStacks;        // [numNodes * 2]

    // Edge arrays (length = totalActions)
    const int32_t*  childNodeId;       // >=0: action node, <0: terminal

    // Terminal arrays (length = numTerminals)
    const float*    terminalPot;
    const uint8_t*  terminalIsShowdown;
    const int8_t*   terminalFolder;
    const float*    terminalStacks;    // [numTerminals * 2]
};

// Mutable copy of a FlatTree that owns its memory.
// Used for cloning the inner tree template for each subtree.
struct OwnedFlatTree {
    uint32_t numNodes;
    uint32_t numTerminals;
    uint32_t totalActions;

    std::vector<uint8_t>  nodePlayer;
    std::vector<uint8_t>  nodeNumActions;
    std::vector<uint32_t> nodeActionOffset;
    std::vector<float>    nodePot;
    std::vector<float>    nodeStacks;
    std::vector<int32_t>  childNodeId;
    std::vector<float>    terminalPot;
    std::vector<uint8_t>  terminalIsShowdown;
    std::vector<int8_t>   terminalFolder;
    std::vector<float>    terminalStacks;

    // Get a read-only FlatTree view into this owned data
    FlatTree view() const {
        return FlatTree{
            numNodes, numTerminals, totalActions,
            nodePlayer.data(), nodeNumActions.data(),
            nodeActionOffset.data(), nodePot.data(), nodeStacks.data(),
            childNodeId.data(),
            terminalPot.data(), terminalIsShowdown.data(),
            terminalFolder.data(), terminalStacks.data(),
        };
    }

    // Clone from a FlatTree (deep copy). nodePot/nodeStacks may be nullptr.
    static OwnedFlatTree clone(const FlatTree& src) {
        OwnedFlatTree t;
        t.numNodes = src.numNodes;
        t.numTerminals = src.numTerminals;
        t.totalActions = src.totalActions;
        t.nodePlayer.assign(src.nodePlayer, src.nodePlayer + src.numNodes);
        t.nodeNumActions.assign(src.nodeNumActions, src.nodeNumActions + src.numNodes);
        t.nodeActionOffset.assign(src.nodeActionOffset, src.nodeActionOffset + src.numNodes);
        if (src.nodePot) {
            t.nodePot.assign(src.nodePot, src.nodePot + src.numNodes);
        } else {
            t.nodePot.resize(src.numNodes, 0.0f);
        }
        if (src.nodeStacks) {
            t.nodeStacks.assign(src.nodeStacks, src.nodeStacks + src.numNodes * 2);
        } else {
            t.nodeStacks.resize(src.numNodes * 2, 0.0f);
        }
        t.childNodeId.assign(src.childNodeId, src.childNodeId + src.totalActions);
        t.terminalPot.assign(src.terminalPot, src.terminalPot + src.numTerminals);
        t.terminalIsShowdown.assign(src.terminalIsShowdown, src.terminalIsShowdown + src.numTerminals);
        t.terminalFolder.assign(src.terminalFolder, src.terminalFolder + src.numTerminals);
        t.terminalStacks.assign(src.terminalStacks, src.terminalStacks + src.numTerminals * 2);
        return t;
    }
};

// Apply rake to showdown terminals (mutates terminalPot in place)
inline void applyRakeToTree(OwnedFlatTree& tree, float rakePercent, float rakeCap) {
    for (uint32_t ti = 0; ti < tree.numTerminals; ti++) {
        if (tree.terminalIsShowdown[ti]) {
            float pot = tree.terminalPot[ti];
            float rake = std::min(pot * rakePercent, rakeCap);
            tree.terminalPot[ti] = pot - rake;
        }
    }
}

} // namespace ez_cfr
