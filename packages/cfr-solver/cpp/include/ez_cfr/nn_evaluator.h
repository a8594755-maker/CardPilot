#pragma once

#include <array>
#include <cstdint>
#include <cstddef>
#include <memory>
#include <string>
#include <vector>

namespace ez_cfr {

struct NNEvalState {
    const int32_t* board = nullptr;          // flop board ptr
    int boardLen = 0;                        // usually 3
    int32_t turnCard = -1;                   // dealt turn card
    float potOffset = 0.0f;
    float startingPot = 0.0f;
    float effectiveStack = 0.0f;
    uint32_t turnNC = 0;                     // local combo count
    const int32_t* comboGlobalIds = nullptr; // [turnNC], canonical 0..1325
    const float* oopReach = nullptr;         // [turnNC]
    const float* ipReach = nullptr;          // [turnNC]
    int traverser = 0;                       // 0/1
    float* outEV = nullptr;                  // [turnNC]
};

struct NNEvaluatorConfig {
    std::string modelPath;
    size_t maxBatchStates = 1024;
    bool preferCuda = true;
};

// Native ORT-based evaluator. Keeps a queue of turn states and executes batched
// inference when flushed.
class NativeNNEvaluator {
public:
    explicit NativeNNEvaluator(const NNEvaluatorConfig& config);
    ~NativeNNEvaluator();

    bool isReady() const { return ready_; }
    const std::string& backend() const { return backend_; }
    size_t maxBatchStates() const { return maxBatchStates_; }
    size_t pending() const;

    // Enqueue one state (input data is copied internally).
    void enqueue(const NNEvalState& state);

    // Flush queued states in one batch. Writes EVs to each state's outEV.
    // Uses heuristic fallback only when ORT is unavailable.
    void flush();

    // Convenience for synchronous call sites that need output immediately.
    // Returns true only when ORT successfully produced outputs.
    // Returns false when caller should use exact fallback path.
    bool evaluate(const NNEvalState& state);

private:
    bool flushInternal(bool allowHeuristicFallback);

    struct Impl;
    std::unique_ptr<Impl> impl_;
    bool ready_ = false;
    std::string backend_ = "disabled";
    size_t maxBatchStates_ = 1024;
};

// Factory: reads env vars and returns nullptr if model path is missing.
// Env:
//   EZ_GTO_ORT_MODEL        required
//   EZ_GTO_ORT_BATCH        optional, default 1024
//   EZ_GTO_ORT_PREFER_CUDA  optional, default 1
std::unique_ptr<NativeNNEvaluator> createNativeNNEvaluatorFromEnv();

} // namespace ez_cfr
