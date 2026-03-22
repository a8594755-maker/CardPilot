#pragma once

#include <cstdint>
#include <cstring>

#ifdef __wasm_simd128__
#include <wasm_simd128.h>
#define EZ_SIMD 1
#else
#define EZ_SIMD 0
#endif

namespace ez_cfr {
namespace simd {

// ─── dst[i] = max(0, dst[i] + delta[i]) ───
// Used by: updateRegrets (CFR+ floor at 0)
inline void addMax0(float* dst, const float* delta, uint32_t len) {
#if EZ_SIMD
    v128_t zero = wasm_f32x4_const(0, 0, 0, 0);
    uint32_t i = 0;
    for (; i + 4 <= len; i += 4) {
        v128_t d = wasm_v128_load(dst + i);
        v128_t dd = wasm_v128_load(delta + i);
        v128_t sum = wasm_f32x4_add(d, dd);
        wasm_v128_store(dst + i, wasm_f32x4_max(sum, zero));
    }
    for (; i < len; i++) {
        float val = dst[i] + delta[i];
        dst[i] = val > 0.0f ? val : 0.0f;
    }
#else
    for (uint32_t i = 0; i < len; i++) {
        float val = dst[i] + delta[i];
        dst[i] = val > 0.0f ? val : 0.0f;
    }
#endif
}

// ─── dst[i] += src[i] ───
// Used by: addStrategyWeights, EV accumulation
inline void add(float* dst, const float* src, uint32_t len) {
#if EZ_SIMD
    uint32_t i = 0;
    for (; i + 4 <= len; i += 4) {
        v128_t d = wasm_v128_load(dst + i);
        v128_t s = wasm_v128_load(src + i);
        wasm_v128_store(dst + i, wasm_f32x4_add(d, s));
    }
    for (; i < len; i++) {
        dst[i] += src[i];
    }
#else
    for (uint32_t i = 0; i < len; i++) {
        dst[i] += src[i];
    }
#endif
}

// ─── dst[i] = a[i] * b[i] ───
// Used by: reach multiplication
inline void mul(float* dst, const float* a, const float* b, uint32_t len) {
#if EZ_SIMD
    uint32_t i = 0;
    for (; i + 4 <= len; i += 4) {
        v128_t va = wasm_v128_load(a + i);
        v128_t vb = wasm_v128_load(b + i);
        wasm_v128_store(dst + i, wasm_f32x4_mul(va, vb));
    }
    for (; i < len; i++) {
        dst[i] = a[i] * b[i];
    }
#else
    for (uint32_t i = 0; i < len; i++) {
        dst[i] = a[i] * b[i];
    }
#endif
}

// ─── dst[i] += a[i] * b[i] ───
// Used by: EV accumulation (strategy * actionEV)
inline void fma(float* dst, const float* a, const float* b, uint32_t len) {
#if EZ_SIMD
    uint32_t i = 0;
    for (; i + 4 <= len; i += 4) {
        v128_t d = wasm_v128_load(dst + i);
        v128_t va = wasm_v128_load(a + i);
        v128_t vb = wasm_v128_load(b + i);
        wasm_v128_store(dst + i, wasm_f32x4_add(d, wasm_f32x4_mul(va, vb)));
    }
    for (; i < len; i++) {
        dst[i] += a[i] * b[i];
    }
#else
    for (uint32_t i = 0; i < len; i++) {
        dst[i] += a[i] * b[i];
    }
#endif
}

// ─── dst[i] = a[i] - b[i] ───
// Used by: regret delta = actionEV - nodeEV
inline void sub(float* dst, const float* a, const float* b, uint32_t len) {
#if EZ_SIMD
    uint32_t i = 0;
    for (; i + 4 <= len; i += 4) {
        v128_t va = wasm_v128_load(a + i);
        v128_t vb = wasm_v128_load(b + i);
        wasm_v128_store(dst + i, wasm_f32x4_sub(va, vb));
    }
    for (; i < len; i++) {
        dst[i] = a[i] - b[i];
    }
#else
    for (uint32_t i = 0; i < len; i++) {
        dst[i] = a[i] - b[i];
    }
#endif
}

// ─── dst[i] = scale * a[i] * b[i] ───
// Used by: strategy weight = iterWeight * reach * strategy
inline void mulScale(float* dst, const float* a, const float* b, float scale, uint32_t len) {
#if EZ_SIMD
    v128_t vs = wasm_f32x4_splat(scale);
    uint32_t i = 0;
    for (; i + 4 <= len; i += 4) {
        v128_t va = wasm_v128_load(a + i);
        v128_t vb = wasm_v128_load(b + i);
        wasm_v128_store(dst + i, wasm_f32x4_mul(vs, wasm_f32x4_mul(va, vb)));
    }
    for (; i < len; i++) {
        dst[i] = scale * a[i] * b[i];
    }
#else
    for (uint32_t i = 0; i < len; i++) {
        dst[i] = scale * a[i] * b[i];
    }
#endif
}

// ─── dst[i] *= factor ───
// Used by: DCFR discount
inline void scale(float* dst, float factor, uint32_t len) {
#if EZ_SIMD
    v128_t vf = wasm_f32x4_splat(factor);
    uint32_t i = 0;
    for (; i + 4 <= len; i += 4) {
        v128_t d = wasm_v128_load(dst + i);
        wasm_v128_store(dst + i, wasm_f32x4_mul(d, vf));
    }
    for (; i < len; i++) {
        dst[i] *= factor;
    }
#else
    for (uint32_t i = 0; i < len; i++) {
        dst[i] *= factor;
    }
#endif
}

// ─── copy(dst, src, len) ───
inline void copy(float* dst, const float* src, uint32_t len) {
#if EZ_SIMD
    uint32_t i = 0;
    for (; i + 4 <= len; i += 4) {
        wasm_v128_store(dst + i, wasm_v128_load(src + i));
    }
    for (; i < len; i++) {
        dst[i] = src[i];
    }
#else
    std::memcpy(dst, src, len * sizeof(float));
#endif
}

// ─── Positive-regret matching for getCurrentStrategy (vanilla CFR) ───
// Uses max(0, regret) so that negative regrets (allowed in vanilla CFR) are
// excluded from the strategy. Regrets accumulated without floor (simd::add).
inline void positiveRegretMatch(const float* regrets, uint32_t base, uint32_t nc,
                                uint32_t numActions, float* out)
{
#if EZ_SIMD
    v128_t zero = wasm_f32x4_const(0, 0, 0, 0);
    float invUniform = 1.0f / numActions;
    v128_t vUniform = wasm_f32x4_splat(invUniform);

    uint32_t c = 0;
    for (; c + 4 <= nc; c += 4) {
        // Sum max(0, regret) across all actions
        v128_t sum = zero;
        for (uint32_t a = 0; a < numActions; a++) {
            v128_t r = wasm_v128_load(&regrets[base + a * nc + c]);
            sum = wasm_f32x4_add(sum, wasm_f32x4_max(r, zero));
        }
        v128_t mask = wasm_f32x4_gt(sum, zero);
        for (uint32_t a = 0; a < numActions; a++) {
            v128_t r = wasm_v128_load(&regrets[base + a * nc + c]);
            v128_t rpos = wasm_f32x4_max(r, zero);
            v128_t normalized = wasm_f32x4_div(rpos, sum);
            v128_t result = wasm_v128_bitselect(normalized, vUniform, mask);
            wasm_v128_store(&out[a * nc + c], result);
        }
    }
    for (; c < nc; c++) {
        float sum = 0.0f;
        for (uint32_t a = 0; a < numActions; a++) {
            float r = regrets[base + a * nc + c];
            if (r > 0.0f) sum += r;
        }
        float invUniformF = 1.0f / numActions;
        if (sum > 0.0f) {
            for (uint32_t a = 0; a < numActions; a++) {
                float r = regrets[base + a * nc + c];
                out[a * nc + c] = (r > 0.0f) ? r / sum : 0.0f;
            }
        } else {
            for (uint32_t a = 0; a < numActions; a++) {
                out[a * nc + c] = invUniformF;
            }
        }
    }
#else
    float invUniform = 1.0f / numActions;
    for (uint32_t c = 0; c < nc; c++) {
        float sum = 0.0f;
        for (uint32_t a = 0; a < numActions; a++) {
            float r = regrets[base + a * nc + c];
            if (r > 0.0f) sum += r;
        }
        if (sum > 0.0f) {
            for (uint32_t a = 0; a < numActions; a++) {
                float r = regrets[base + a * nc + c];
                out[a * nc + c] = (r > 0.0f) ? r / sum : 0.0f;
            }
        } else {
            for (uint32_t a = 0; a < numActions; a++) {
                out[a * nc + c] = invUniform;
            }
        }
    }
#endif
}

// ─── regretMatch: for getAverageStrategy (strategy sums are always >= 0) ───
// Memory layout: regrets[base + a * nc + c]
// Process 4 combos at a time: sum across actions, normalize
inline void regretMatch(const float* regrets, uint32_t base, uint32_t nc,
                        uint32_t numActions, float* out)
{
#if EZ_SIMD
    v128_t zero = wasm_f32x4_const(0, 0, 0, 0);
    float invUniform = 1.0f / numActions;
    v128_t vUniform = wasm_f32x4_splat(invUniform);

    uint32_t c = 0;
    for (; c + 4 <= nc; c += 4) {
        // Sum regrets across all actions for these 4 combos
        v128_t sum = zero;
        for (uint32_t a = 0; a < numActions; a++) {
            v128_t r = wasm_v128_load(&regrets[base + a * nc + c]);
            sum = wasm_f32x4_add(sum, r);
        }

        // Mask: which lanes have sum > 0?
        v128_t mask = wasm_f32x4_gt(sum, zero);

        // For lanes with sum > 0: normalized = regret / sum
        // For lanes with sum <= 0: uniform
        for (uint32_t a = 0; a < numActions; a++) {
            v128_t r = wasm_v128_load(&regrets[base + a * nc + c]);
            v128_t normalized = wasm_f32x4_div(r, sum); // inf where sum==0, masked out
            v128_t result = wasm_v128_bitselect(normalized, vUniform, mask);
            wasm_v128_store(&out[a * nc + c], result);
        }
    }

    // Tail
    for (; c < nc; c++) {
        float sum = 0.0f;
        for (uint32_t a = 0; a < numActions; a++) {
            sum += regrets[base + a * nc + c];
        }
        if (sum > 0.0f) {
            for (uint32_t a = 0; a < numActions; a++) {
                out[a * nc + c] = regrets[base + a * nc + c] / sum;
            }
        } else {
            for (uint32_t a = 0; a < numActions; a++) {
                out[a * nc + c] = invUniform;
            }
        }
    }
#else
    float invUniform = 1.0f / numActions;
    for (uint32_t c = 0; c < nc; c++) {
        float sum = 0.0f;
        for (uint32_t a = 0; a < numActions; a++) {
            sum += regrets[base + a * nc + c];
        }
        if (sum > 0.0f) {
            for (uint32_t a = 0; a < numActions; a++) {
                out[a * nc + c] = regrets[base + a * nc + c] / sum;
            }
        } else {
            for (uint32_t a = 0; a < numActions; a++) {
                out[a * nc + c] = invUniform;
            }
        }
    }
#endif
}

} // namespace simd
} // namespace ez_cfr
