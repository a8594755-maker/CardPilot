#include "ez_cfr/nn_evaluator.h"

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#ifdef EZ_CFR_ENABLE_ORT
#include <onnxruntime_cxx_api.h>

#if __has_include(<onnxruntime/core/providers/cuda/cuda_provider_factory.h>)
#include <onnxruntime/core/providers/cuda/cuda_provider_factory.h>
#define EZ_CFR_HAS_ORT_CUDA_PROVIDER 1
#elif __has_include(<cuda_provider_factory.h>)
#include <cuda_provider_factory.h>
#define EZ_CFR_HAS_ORT_CUDA_PROVIDER 1
#endif
#endif

namespace ez_cfr {

namespace {

constexpr int kMaxBoardCards = 5;
constexpr int kNumCombos = 1326;

struct PendingState {
    int boardLen = 0;
    std::array<int32_t, kMaxBoardCards> board{};
    int32_t turnCard = -1;
    float potOffset = 0.0f;
    float startingPot = 0.0f;
    float effectiveStack = 0.0f;
    uint32_t turnNC = 0;
    std::vector<int32_t> comboGlobalIds;
    std::vector<float> oopReach;
    std::vector<float> ipReach;
    int traverser = 0;
    float* outEV = nullptr;
};

size_t parseEnvUsize(const char* name, size_t fallback) {
    const char* raw = std::getenv(name);
    if (!raw || !raw[0]) return fallback;
    try {
        size_t parsed = static_cast<size_t>(std::stoull(raw));
        return parsed > 0 ? parsed : fallback;
    } catch (...) {
        return fallback;
    }
}

bool parseEnvBool(const char* name, bool fallback) {
    const char* raw = std::getenv(name);
    if (!raw || !raw[0]) return fallback;
    std::string v(raw);
    std::transform(v.begin(), v.end(), v.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    if (v == "1" || v == "true" || v == "yes" || v == "on") return true;
    if (v == "0" || v == "false" || v == "no" || v == "off") return false;
    return fallback;
}

float heuristicValue(int32_t gid, float oop, float ip, float potScale, int traverser) {
    const float sign = traverser == 0 ? 1.0f : -1.0f;
    const float prior = (static_cast<float>(gid % 13) / 12.0f) - 0.5f;
    const float reachDelta = oop - ip;
    return sign * potScale * (0.65f * prior + 0.35f * reachDelta);
}

void writeHeuristicEV(const PendingState& state) {
    if (!state.outEV) return;
    const float potScale = std::max(0.01f, state.startingPot + state.potOffset);
    for (uint32_t i = 0; i < state.turnNC; i++) {
        const int32_t gid = state.comboGlobalIds[i];
        state.outEV[i] = heuristicValue(
            gid,
            state.oopReach[i],
            state.ipReach[i],
            potScale,
            state.traverser
        );
    }
}

} // namespace

// Contract type detected from ONNX model metadata.
enum class ModelContract {
    kUnknown,
    kPerState4Input,   // legacy: 4 separate tensors [B,1326],[B,1326],[B,6],[B,5] → [B,1326]
    kPerCombo1Input,   // v3/v4 style: single flat [B,featureDim] → [B,1] per-combo model
};

struct NativeNNEvaluator::Impl {
    std::vector<PendingState> queue;
    ModelContract contract = ModelContract::kUnknown;
    int featureDim = 0;  // populated for kPerCombo1Input

#ifdef EZ_CFR_ENABLE_ORT
    Ort::Env env{ORT_LOGGING_LEVEL_WARNING, "ez_cfr_native_nn"};
    std::unique_ptr<Ort::Session> session;
    std::vector<std::string> inputNamesStorage;
    std::string outputNameStorage;
#endif
};

NativeNNEvaluator::NativeNNEvaluator(const NNEvaluatorConfig& config)
    : impl_(std::make_unique<Impl>())
{
    maxBatchStates_ = std::max<size_t>(1, config.maxBatchStates);
    impl_->queue.reserve(maxBatchStates_);

#ifdef EZ_CFR_ENABLE_ORT
    if (config.modelPath.empty()) {
        backend_ = "disabled:no-model";
        return;
    }

    try {
        auto shapeToString = [](const std::vector<int64_t>& shape) {
            std::ostringstream oss;
            oss << "[";
            for (size_t i = 0; i < shape.size(); i++) {
                if (i) oss << ",";
                oss << shape[i];
            }
            oss << "]";
            return oss.str();
        };
        auto is2dLastDim = [](const std::vector<int64_t>& shape, int64_t expectedLast) {
            return shape.size() == 2 && (shape[1] == expectedLast || shape[1] == -1);
        };

        Ort::SessionOptions opts;
        opts.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_EXTENDED);
        opts.SetIntraOpNumThreads(1);

        bool cudaEnabled = false;
#ifdef EZ_CFR_HAS_ORT_CUDA_PROVIDER
        if (config.preferCuda) {
            OrtCUDAProviderOptions cudaOptions{};
            cudaOptions.device_id = 0;
            if (OrtSessionOptionsAppendExecutionProvider_CUDA(opts, &cudaOptions) == nullptr) {
                cudaEnabled = true;
            }
        }
#endif

#ifdef _WIN32
        const std::wstring modelPathWide(config.modelPath.begin(), config.modelPath.end());
        impl_->session = std::make_unique<Ort::Session>(
            impl_->env,
            modelPathWide.c_str(),
            opts
        );
#else
        impl_->session = std::make_unique<Ort::Session>(
            impl_->env,
            config.modelPath.c_str(),
            opts
        );
#endif

        Ort::AllocatorWithDefaultOptions allocator;
        const size_t inputCount = impl_->session->GetInputCount();
        for (size_t i = 0; i < inputCount; i++) {
            auto name = impl_->session->GetInputNameAllocated(i, allocator);
            impl_->inputNamesStorage.emplace_back(name.get());
        }
        auto outName = impl_->session->GetOutputNameAllocated(0, allocator);
        impl_->outputNameStorage = outName.get();

        // Detect model contract from input/output shape.
        //
        // Contract A — per-state 4-input (legacy, if ever trained):
        //   input0: oopReach [B,1326]
        //   input1: ipReach  [B,1326]
        //   input2: meta     [B,6]
        //   input3: board    [B,5]
        //   output0: ev      [B,1326]
        //
        // Contract B — per-combo single-input (v3/v4/generic style):
        //   input0: features [B, featureDim]   (featureDim ≥ 1, typically 12)
        //   output0: ev      [B, 1]
        std::vector<std::vector<int64_t>> inShapes(inputCount);
        for (size_t i = 0; i < inputCount; i++) {
            auto tInfo = impl_->session->GetInputTypeInfo(i).GetTensorTypeAndShapeInfo();
            if (tInfo.GetElementType() != ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT) {
                ready_ = false;
                backend_ = "ort-contract-mismatch:input-not-float";
                return;
            }
            inShapes[i] = tInfo.GetShape();
        }
        auto outInfo = impl_->session->GetOutputTypeInfo(0).GetTensorTypeAndShapeInfo();
        const auto outShape = outInfo.GetShape();
        if (outInfo.GetElementType() != ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT) {
            ready_ = false;
            backend_ = "ort-contract-mismatch:output-not-float";
            return;
        }

        if (inputCount == 1 && inShapes[0].size() == 2 && outShape.size() == 2) {
            // Contract B: per-combo single-input model.
            // input shape: [batch, featureDim], output shape: [batch, 1]
            const int64_t fd = inShapes[0][1];
            const int64_t od = outShape[1];
            if (fd < 1 || (od != 1 && od != -1)) {
                ready_ = false;
                backend_ =
                    std::string("ort-contract-mismatch:percombo-shape:in=")
                    + shapeToString(inShapes[0]) + ",out=" + shapeToString(outShape);
                return;
            }
            impl_->contract = ModelContract::kPerCombo1Input;
            impl_->featureDim = static_cast<int>(fd > 0 ? fd : 12);
            ready_ = true;
            backend_ = std::string(cudaEnabled ? "ort-cuda" : "ort-cpu")
                + "-percombo-" + std::to_string(impl_->featureDim) + "d";
        } else if (inputCount >= 4) {
            // Contract A: per-state 4-input model.
            const bool contractOk =
                is2dLastDim(inShapes[0], kNumCombos) &&
                is2dLastDim(inShapes[1], kNumCombos) &&
                is2dLastDim(inShapes[2], 6) &&
                is2dLastDim(inShapes[3], kMaxBoardCards) &&
                is2dLastDim(outShape, kNumCombos);

            if (!contractOk) {
                ready_ = false;
                backend_ =
                    std::string("ort-contract-mismatch:in0=") + shapeToString(inShapes[0]) +
                    ",in1=" + shapeToString(inShapes[1]) +
                    ",in2=" + shapeToString(inShapes[2]) +
                    ",in3=" + shapeToString(inShapes[3]) +
                    ",out=" + shapeToString(outShape);
                return;
            }
            impl_->contract = ModelContract::kPerState4Input;
            ready_ = true;
            backend_ = cudaEnabled ? "ort-cuda" : "ort-cpu";
        } else {
            ready_ = false;
            backend_ =
                std::string("ort-contract-mismatch:unsupported:inputs=")
                + std::to_string(inputCount)
                + ",in0=" + shapeToString(inShapes[0])
                + ",out=" + shapeToString(outShape);
            return;
        }

    } catch (const std::exception& ex) {
        ready_ = false;
        backend_ = std::string("ort-init-error:") + ex.what();
    }
#else
    (void)config;
    backend_ = "disabled:no-ort";
#endif
}

NativeNNEvaluator::~NativeNNEvaluator() = default;

size_t NativeNNEvaluator::pending() const {
    return impl_ ? impl_->queue.size() : 0;
}

void NativeNNEvaluator::enqueue(const NNEvalState& state) {
    if (!impl_) return;
    if (!state.outEV || state.turnNC == 0 || !state.comboGlobalIds || !state.oopReach || !state.ipReach) {
        return;
    }

    PendingState pending;
    pending.boardLen = std::max(0, std::min(state.boardLen, kMaxBoardCards));
    if (state.board && pending.boardLen > 0) {
        std::memcpy(pending.board.data(), state.board, pending.boardLen * sizeof(int32_t));
    }
    pending.turnCard = state.turnCard;
    pending.potOffset = state.potOffset;
    pending.startingPot = state.startingPot;
    pending.effectiveStack = state.effectiveStack;
    pending.turnNC = state.turnNC;
    pending.traverser = state.traverser;
    pending.outEV = state.outEV;

    pending.comboGlobalIds.assign(state.comboGlobalIds, state.comboGlobalIds + state.turnNC);
    pending.oopReach.assign(state.oopReach, state.oopReach + state.turnNC);
    pending.ipReach.assign(state.ipReach, state.ipReach + state.turnNC);

    impl_->queue.push_back(std::move(pending));
}

#ifdef EZ_CFR_ENABLE_ORT
namespace {
// Build a per-combo feature vector for a single-input model.
//
// Layout (12 features — matches featureDim for v3/v4/generic models):
//
//  [0]  combo global ID, normalised to [0,1]
//  [1]  low-card slot within ID (gid % 52) / 51
//  [2]  high-card slot within ID (gid / 52) / 24   (hi ≤ 24 for valid combos)
//  [3]  OOP reach probability   [0,1]
//  [4]  IP  reach probability   [0,1]
//  [5]  reach balance  0.5 + 0.5*(oop-ip)          [0,1]
//  [6]  starting pot / 400
//  [7]  pot offset / 400  (accumulated pot change)
//  [8]  effective stack / 800
//  [9]  board card 0 / 51  (or 0 if absent)
//  [10] board card 1 / 51
//  [11] board card 2 / 51
//
// If featureDim > 12 the remaining slots are zeroed.
// If featureDim < 12 only the first featureDim features are written.
inline void buildPerComboFeature(
    float* feat,
    int featureDim,
    int32_t gid,
    float oopReach,
    float ipReach,
    const PendingState& st)
{
    std::fill(feat, feat + featureDim, 0.0f);
    auto set = [&](int idx, float v) { if (idx < featureDim) feat[idx] = v; };
    set(0,  static_cast<float>(gid) / 1325.0f);
    set(1,  static_cast<float>(gid % 52) / 51.0f);
    set(2,  static_cast<float>(gid / 52) / 24.0f);
    set(3,  oopReach);
    set(4,  ipReach);
    set(5,  0.5f + 0.5f * (oopReach - ipReach));
    set(6,  std::min(st.startingPot, 400.0f) / 400.0f);
    set(7,  std::min(std::max(0.0f, st.potOffset), 400.0f) / 400.0f);
    set(8,  std::min(st.effectiveStack, 800.0f) / 800.0f);
    set(9,  (st.boardLen > 0) ? static_cast<float>(st.board[0]) / 51.0f : 0.0f);
    set(10, (st.boardLen > 1) ? static_cast<float>(st.board[1]) / 51.0f : 0.0f);
    set(11, (st.boardLen > 2) ? static_cast<float>(st.board[2]) / 51.0f : 0.0f);
}
} // namespace
#endif // EZ_CFR_ENABLE_ORT

bool NativeNNEvaluator::flushInternal(bool allowHeuristicFallback) {
    if (!impl_ || impl_->queue.empty()) return true;

#ifdef EZ_CFR_ENABLE_ORT
    if (ready_ && impl_->session) {
        try {
            // ── Contract B: per-combo single-input [N, featureDim] → [N, 1] ──────
            if (impl_->contract == ModelContract::kPerCombo1Input) {
                const int fd = impl_->featureDim;

                // Count total combos across all queued states.
                size_t totalCombos = 0;
                for (const PendingState& st : impl_->queue)
                    totalCombos += st.turnNC;

                std::vector<float> inData(totalCombos * fd, 0.0f);
                // Track which (state, local-idx) each batch row belongs to.
                // We only need the state index and local i to write outEV later.
                struct ComboRef { size_t stIdx; uint32_t localIdx; };
                std::vector<ComboRef> refs;
                refs.reserve(totalCombos);

                size_t row = 0;
                for (size_t s = 0; s < impl_->queue.size(); s++) {
                    const PendingState& st = impl_->queue[s];
                    for (uint32_t i = 0; i < st.turnNC; i++) {
                        buildPerComboFeature(
                            &inData[row * fd], fd,
                            st.comboGlobalIds[i],
                            st.oopReach[i], st.ipReach[i], st);
                        refs.push_back({s, i});
                        row++;
                    }
                }

                Ort::MemoryInfo memInfo = Ort::MemoryInfo::CreateCpu(
                    OrtArenaAllocator, OrtMemTypeDefault);
                const std::array<int64_t, 2> inShape{
                    static_cast<int64_t>(totalCombos),
                    static_cast<int64_t>(fd),
                };
                Ort::Value inTensor = Ort::Value::CreateTensor<float>(
                    memInfo, inData.data(), inData.size(),
                    inShape.data(), inShape.size());

                const char* inputName  = impl_->inputNamesStorage[0].c_str();
                const char* outputName = impl_->outputNameStorage.c_str();
                auto outputs = impl_->session->Run(
                    Ort::RunOptions{nullptr},
                    &inputName, &inTensor, 1,
                    &outputName, 1);

                if (outputs.empty())
                    throw std::runtime_error("ORT returned no outputs (percombo path)");

                const float* outData = outputs[0].GetTensorMutableData<float>();
                const size_t outCount = outputs[0].GetTensorTypeAndShapeInfo().GetElementCount();

                for (size_t k = 0; k < refs.size(); k++) {
                    const ComboRef& ref = refs[k];
                    const PendingState& st = impl_->queue[ref.stIdx];
                    if (!st.outEV) continue;

                    const float rawEv = (k < outCount) ? outData[k] : 0.0f;
                    // Scale to pot-relative magnitude and apply traverser sign.
                    const float potScale = std::max(0.01f, st.startingPot + st.potOffset);
                    const float sign = st.traverser == 0 ? 1.0f : -1.0f;
                    st.outEV[ref.localIdx] = sign * potScale * rawEv;
                }

                impl_->queue.clear();
                return true;
            }

            // ── Contract A: per-state 4-input ────────────────────────────────────
            const size_t batch = impl_->queue.size();
            std::vector<float> oopTensor(batch * kNumCombos, 0.0f);
            std::vector<float> ipTensor(batch * kNumCombos, 0.0f);
            std::vector<float> metaTensor(batch * 6, 0.0f);
            std::vector<float> boardTensor(batch * kMaxBoardCards, -1.0f);

            for (size_t b = 0; b < batch; b++) {
                const PendingState& st = impl_->queue[b];
                const size_t base = b * kNumCombos;

                for (uint32_t i = 0; i < st.turnNC; i++) {
                    const int32_t gid = st.comboGlobalIds[i];
                    if (gid < 0 || gid >= kNumCombos) continue;
                    oopTensor[base + static_cast<size_t>(gid)] = st.oopReach[i];
                    ipTensor[base + static_cast<size_t>(gid)] = st.ipReach[i];
                }

                metaTensor[b * 6 + 0] = st.potOffset;
                metaTensor[b * 6 + 1] = st.startingPot;
                metaTensor[b * 6 + 2] = st.effectiveStack;
                metaTensor[b * 6 + 3] = static_cast<float>(st.turnCard);
                metaTensor[b * 6 + 4] = static_cast<float>(st.traverser);
                metaTensor[b * 6 + 5] = static_cast<float>(st.turnNC);

                for (int i = 0; i < st.boardLen; i++) {
                    boardTensor[b * kMaxBoardCards + i] = static_cast<float>(st.board[i]);
                }
            }

            Ort::MemoryInfo memInfo = Ort::MemoryInfo::CreateCpu(
                OrtArenaAllocator,
                OrtMemTypeDefault
            );

            const std::array<int64_t, 2> reachShape{
                static_cast<int64_t>(batch),
                static_cast<int64_t>(kNumCombos),
            };
            const std::array<int64_t, 2> metaShape{
                static_cast<int64_t>(batch),
                6,
            };
            const std::array<int64_t, 2> boardShape{
                static_cast<int64_t>(batch),
                static_cast<int64_t>(kMaxBoardCards),
            };

            const size_t inputCount = impl_->inputNamesStorage.size();
            std::vector<const char*> inputNames;
            std::vector<Ort::Value> inputValues;
            inputNames.reserve(inputCount);
            inputValues.reserve(inputCount);

            for (size_t i = 0; i < inputCount; i++) {
                inputNames.push_back(impl_->inputNamesStorage[i].c_str());

                if (i == 0) {
                    inputValues.emplace_back(Ort::Value::CreateTensor<float>(
                        memInfo,
                        oopTensor.data(),
                        oopTensor.size(),
                        reachShape.data(),
                        reachShape.size()
                    ));
                } else if (i == 1) {
                    inputValues.emplace_back(Ort::Value::CreateTensor<float>(
                        memInfo,
                        ipTensor.data(),
                        ipTensor.size(),
                        reachShape.data(),
                        reachShape.size()
                    ));
                } else if (i == 2) {
                    inputValues.emplace_back(Ort::Value::CreateTensor<float>(
                        memInfo,
                        metaTensor.data(),
                        metaTensor.size(),
                        metaShape.data(),
                        metaShape.size()
                    ));
                } else {
                    inputValues.emplace_back(Ort::Value::CreateTensor<float>(
                        memInfo,
                        boardTensor.data(),
                        boardTensor.size(),
                        boardShape.data(),
                        boardShape.size()
                    ));
                }
            }

            const char* outputName = impl_->outputNameStorage.c_str();
            auto outputs = impl_->session->Run(
                Ort::RunOptions{nullptr},
                inputNames.data(),
                inputValues.data(),
                inputValues.size(),
                &outputName,
                1
            );

            if (outputs.empty()) {
                throw std::runtime_error("ORT returned no outputs");
            }

            float* outputData = outputs[0].GetTensorMutableData<float>();
            auto outInfo = outputs[0].GetTensorTypeAndShapeInfo();
            const auto outShape = outInfo.GetShape();
            const size_t outElemCount = outInfo.GetElementCount();
            const size_t rowStride = (outShape.size() >= 2)
                ? static_cast<size_t>(outShape.back())
                : (batch > 0 ? (outElemCount / batch) : 0);

            for (size_t b = 0; b < batch; b++) {
                const PendingState& st = impl_->queue[b];
                if (!st.outEV) continue;

                for (uint32_t i = 0; i < st.turnNC; i++) {
                    const int32_t gid = st.comboGlobalIds[i];
                    float value = 0.0f;
                    if (rowStride == kNumCombos && gid >= 0 && gid < static_cast<int32_t>(rowStride)) {
                        value = outputData[b * rowStride + static_cast<size_t>(gid)];
                    } else if (rowStride >= st.turnNC) {
                        value = outputData[b * rowStride + i];
                    } else {
                        value = heuristicValue(
                            gid,
                            st.oopReach[i],
                            st.ipReach[i],
                            std::max(0.01f, st.startingPot + st.potOffset),
                            st.traverser
                        );
                    }
                    st.outEV[i] = value;
                }
            }

            impl_->queue.clear();
            return true;
        } catch (const std::exception& ex) {
            ready_ = false;
            backend_ = std::string("ort-runtime-error:") + ex.what();
        }
    }
#endif

    if (!allowHeuristicFallback) {
        impl_->queue.clear();
        return false;
    }

    // Fallback: deterministic heuristic evaluator.
    for (const PendingState& st : impl_->queue) {
        writeHeuristicEV(st);
    }
    impl_->queue.clear();
    return false;
}

void NativeNNEvaluator::flush() {
    (void)flushInternal(true);
}

bool NativeNNEvaluator::evaluate(const NNEvalState& state) {
    if (!ready_) return false;
    enqueue(state);
    // For CFR traversal, ORT failure should trigger exact fallback at call site,
    // not heuristic substitution.
    return flushInternal(false);
}

std::unique_ptr<NativeNNEvaluator> createNativeNNEvaluatorFromEnv() {
    const char* modelPath = std::getenv("EZ_GTO_ORT_MODEL");
    if (!modelPath || !modelPath[0]) {
        return nullptr;
    }

    NNEvaluatorConfig cfg;
    cfg.modelPath = modelPath;
    cfg.maxBatchStates = parseEnvUsize("EZ_GTO_ORT_BATCH", 1024);
    cfg.preferCuda = parseEnvBool("EZ_GTO_ORT_PREFER_CUDA", true);
    return std::make_unique<NativeNNEvaluator>(cfg);
}

} // namespace ez_cfr
