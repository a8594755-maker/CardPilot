# EXP-009 Value-Target Proof - 2026-07-07

Scope: CPU-only follow-up to the EXP-009 Phase 0 teacher-data audit. Candidate A only: `data/cfr/pipeline_v3_hu_srp_200bb/`. No trainer change, no BC branch, no GPU work, and no files under `models/alpha_holdem_v5_bc_bootstrap/`.

## Verdict

`FAILED_PHASE1_NO_GO`.

The surviving 200bb SRP CFR artifacts cannot currently provide the required BC value target. They export bucketed average policy rows only, not node EV/value targets, not raw regret/strategy-sum stores, and not AlphaHoldem v55 observations. Under the EXP-009 registration rule, Phase 1 dataset build must not start and EXP-009 should close for the current artifact set.

This does not prove that CFR warm-starting is conceptually bad. It only says the available 200bb artifacts are not sufficient for the pre-registered BC bootstrap branch without a new value-export/re-solve experiment.

## Evidence

Artifact inventory:
- `data/cfr/pipeline_v3_hu_srp_200bb/` contains 96 `*.jsonl.gz`, 96 `*.meta.json`, and one `parallel-solver.log`.
- Solved boards are 0-95 only; boards 96+ are absent.
- Total size is about 18.0 GiB.
- Metadata sum is 2,598,059,281 info sets.
- Sample rows contain only `key` and `probs`, e.g. `{"key":"R|0|0|xx/xx/x2|39-44-34","probs":[...]}`.

Code path audit:
- `packages/cfr-solver/src/storage/json-export.ts` exports each info set as exactly `{ key, probs }`, where `probs` is rounded from `entry.averageStrategy`.
- `packages/cfr-solver/src/engine/info-set-store.ts` keeps regrets and strategy sums in memory, but `entries()` yields only `key`, `numActions`, and `averageStrategy` for export.
- `packages/cfr-solver/src/orchestration/solve-worker.ts` creates a fresh `InfoSetStore`, runs `solveCFR`, then calls `exportToJSONL` and `exportMeta`. It does not persist the store, regrets, strategy sums, reach data, sampled runouts, or value/action-value records.
- `packages/cfr-solver/src/scripts/solve-v3-parallel.ts` gzips each board's raw JSONL and deletes the uncompressed file; the raw file has the same policy-only JSONL schema.
- `packages/cfr-solver/src/vectorized/ev-extractor.ts` can extract EV only from a solved `FlatTree` plus `ArrayStore`, but the 200bb run used the legacy Map-based path and did not persist an `ArrayStore`.
- `packages/cfr-solver/src/scripts/cfr-to-training-data.ts` converts CFR rows to 54-dim policy training records (`f`, `l`, `sz`, `h`, `s`). Its sample schema has no value target and is not AlphaHoldem v55 obs.

## Blocking Reasons

1. Value target missing: no `ev`, `value`, `value_target`, `q_values`, node EV, or action EV field exists in the exported rows.
2. Raw solver state missing: the persisted artifacts do not include regret sums, strategy sums, reach probabilities, or sampled chance/runout traces needed by the existing EV extractor path.
3. Observation mismatch: Candidate A rows are bucketed SRP abstraction keys, not AlphaHoldem v55 `card_obs`, `action_obs`, `extra_obs`, and `legal_mask`.
4. Coverage mismatch: only 96 solved flops are present, not the full 1,911 isomorphic flop set.

## Decision

Do not build EXP-009 Phase 1 from the current 200bb CFR artifacts.

Status recommendation: `CLOSED_PHASE1_NO_GO_VALUE_TARGET_UNAVAILABLE`.

Allowed future work would require a separate registration, such as:
- a new CFR value-export/re-solve path that writes policy plus node/action EV in the same abstraction, or
- a 200bb resolver-teacher path that emits AlphaHoldem v55 obs, action distribution, and EV directly.

Main V5 from-zero trainer was untouched.
