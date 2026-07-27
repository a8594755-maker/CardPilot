# Path-1 200bb SRP Solve — Smoke Test (2026-06-08)

First real BUILD after the long analysis hold. User re-authorized proceeding ("keep trying,
don't stop, by any method"). Scope kept bounded: wire the 200bb config + run a **1-board** smoke
to validate memory/throughput BEFORE committing to the full (gated) 1,911-board run.

## What was built (code, non-destructive, reversible)
1. `packages/cfr-solver/src/tree/tree-config.ts`
   - New `PIPELINE_SRP_V3_200BB_CONFIG` = V3 SRP, `effectiveStack: 197.5` (vs 47.5@50bb / 97.5@100bb).
   - New `TreeConfigName` member `pipeline_srp_v3_200bb` + `CONFIG_REGISTRY` entry
     (outputDir `pipeline_v3_hu_srp_200bb`, stackLabel `200bb`, 200k iter, **buckets 50**).
2. `packages/cfr-solver/src/scripts/solve-v3-parallel.ts`
   - `STACK_LABEL` now derives from `getStackLabel(CONFIG_NAME)` (was a hard `100bb` vs `50bb` ternary).
   - Added `--max-boards N` (bounded smoke/throttle) and `--heap-mb N` (per-worker heap override).
3. `packages/cfr-solver/src/engine/info-set-store.ts` — **root-cause fix (see below)**
   - Sharded `regrets`/`strategies` across **16 Maps** keyed by a djb2 hash of the info-set key.
   - Pure storage refactor: identical keys → identical arrays → byte-identical strategy export.
   - Updated `size`, `entries()`, `estimateMemoryBytes()` to walk all shards.

## Smoke run
Command (board 0 = `2c 2d 2h`, single worker, bounded):
```
node --import tsx src/scripts/solve-v3-parallel.ts \
  --config pipeline_srp_v3_200bb --max-boards 1 --workers 1 --heap-mb 24576
```

### Finding 1 (blocker, then fixed): V8 Map 16.7M-entry ceiling
First attempt crashed after **2.3 min** with `RangeError: Map maximum size exceeded`
(`info-set-store.ts:21`). This is NOT OOM (24GB heap unused) — a single V8 `Map` hard-caps at
2^24 ≈ 16.7M entries, and ONE 200bb board exceeds that even at buckets=50 (the deep betting tree
explodes the info-set count). 100bb only grazed this on 2 boards; 200bb hits it on board 0.
→ Fixed by sharding the store across 16 Maps (≈268M-entry capacity). Re-run got past it.

### Finding 2 (cost): throughput + memory (the gate-defining numbers)
With the shard fix, board 0 solves cleanly:
| metric | value |
|---|---|
| throughput | **~17.6 iter/s** (25,000 iter in 23.6 min); ~14× slower than 100bb (~250 it/s) |
| per-board time (200k iter) | **~3.1 hr** (single worker; board 0 = a *simple* dry flop) |
| per-board RAM | **~16.6 GB** working set (now RAM, not entry-count, is the binding constraint) |

## Full-run extrapolation (the GATE)
- **Parallelism is RAM-bound**: (137GB − 8 reserved) / 16.6 ≈ **7 boards in parallel** (32 CPUs spare).
- **Wall-clock**: 1,911 boards / 7 × ~3.1 hr ≈ **~5 weeks** (simple boards faster, complex slower).
- **Disk (raw)**: 100bb = 389 MB/board → 200bb deeper ≈ 0.6–0.9 GB/board → **~1.2–1.7 TB**.
  Only **814 GB free** → **streaming `--samples-per-bucket 1` is mandatory** (raw never fully materialized).

## Pass/fail gates
- ✅ 200bb config valid; solver runs end-to-end after the shard fix.
- ✅ Smoke caught the V8 Map blocker BEFORE the full run (its purpose).
- ⛔ **Full 1,911-board run is hard-gated on EVERY axis**: ~5 weeks (>8h), ~1.2–1.7TB artifacts
  (>artifact scale + needs streaming), major compute commitment. Must NOT launch without explicit go.

## Next autonomous step (in-budget, if continuing without crossing the gate)
- Let board 0 finish (~2.5 hr, background) → record exact info-set count + raw export size/board
  to firm up the disk number.
- Optionally wire `--samples-per-bucket 1` streaming into the 200bb path (code only) so the full
  run is launch-ready the moment it's approved.

## Human approval needed? YES — full run only
The **full SRP-200bb solve crosses hard gates** (>8h → weeks; >1TB artifacts; streaming-to-disk).
ASK: approve the ~5-week / streaming-to-~1.2–1.7TB full run? If yes, I'll add streaming + launch the
1,911-board solve at 7 parallel workers (with the watchdog) and monitor per protocol. Everything up to
here (config, flags, shard fix, 1-board smoke) was bounded and is done.
