# EXP-009 Phase 0 Teacher Data Audit - 2026-07-07

Scope: CPU-only inventory for the user-approved CFR warm-start validation branch. No trainer change, no BC dataset build, no GPU-heavy training, and no artifacts created under `models/alpha_holdem_v5_bc_bootstrap/`.

## Verdict

`CONDITIONAL_FEASIBLE_BUT_PHASE1_BLOCKED`.

There is no ready-to-train teacher dataset on disk that satisfies the EXP-009 hard guard: every BC sample must carry both a policy/action target and a value target. The only plausible path is the 200bb SRP raw CFR solve, but it currently exports policy only (`key`, `probs`). Before Phase 1 dataset build, a small CPU proof must demonstrate that a value target can be recovered/exported for sampled nodes from the 200bb solve. If that proof fails, EXP-009 should close without building a BC branch.

## Candidate Path A - 200bb SRP Raw CFR Solves

Path: `data/cfr/pipeline_v3_hu_srp_200bb/`

Inventory:
- 96 `*.jsonl.gz` strategy files and 96 `*.meta.json` files are present.
- Total artifact size is about 19.3 GB.
- Metadata reports `game=HU_NLHE_SRP`, `stack=200bb`, `config=pipeline_srp_v3_200bb`, `bucketCount=50`, `iterations=200000`.
- Board IDs present are 0 through 95.
- Meta total is about 2.598B info sets.
- Sample row schema is only `key` + `probs`, i.e. strategy probabilities over bucketed actions.

Feasibility:
- Right stack depth and relevant SRP coverage make this the best candidate.
- It is not currently Phase-1-ready because sampled rows do not contain exact AlphaHoldem v55 obs or value targets.
- Value-target path is conditional: repo has EV-extraction machinery in `packages/cfr-solver/src/vectorized/ev-extractor.ts`, but Phase 0 did not prove that existing compressed policy exports alone can reconstruct node EV/value targets for sampled AlphaHoldem rows.

Required before Phase 1:
- CPU-only proof on a tiny sample that maps a CFR row/node to AlphaHoldem v55 observation fields and emits a value target.
- Explicit failure mode if the existing policy-only export lacks enough state/store information to recover EV.
- Only QA-passed board artifacts should be eligible; this audit did not re-run full QA.

## Candidate Path B - V10 + Real-Time Resolver Teacher Bot

Path references:
- `apps/bot-client/src/realtime-resolver.ts`
- `models/vnet-v10-v3data.json`

Inventory:
- The resolver can return a `ResolvedStrategy` with raise/call/fold and per-action probabilities.
- Scenario selection is capped to `srp_50bb`, `srp_100bb`, `3bet_50bb`, and `3bet_100bb`; there is no 200bb scenario in the current production path.
- Current `ResolvedStrategy` does not expose node EV/value target.

Feasibility:
- Not Phase-1-ready.
- It would require new harness/code to run inside v55 AlphaHoldem env, expose resolver EV, and address the 200bb scenario gap.
- This is a possible future teacher path, but not a direct data path under the current Phase 0 evidence.

## Candidate Path C - Presampled 54-Dim Data

Path: `data/training/v3_srp_50bb_sampled/`

Inventory:
- 141 files, about 10.3 GB.
- Sample row schema: `f`, `h`, `l`, `s`, `sz`.
- `f` is 54-dimensional value-net feature format, with policy-like labels `l` and sizing `sz`.

Feasibility:
- Infeasible for EXP-009 BC bootstrap as-is.
- It is 50bb/value-net feature format, not AlphaHoldem v55 obs (`card_obs`, `action_obs`, `legal_mask`, history, exact cards).
- It has no value target field for the AlphaHoldem value head.

## Additional Existing AlphaHoldem-Obs Teacher Data

Path: `data/phase2/teacher_v3_5M.jsonl`

Inventory:
- Sample row has `card_obs`, `action_obs`, `extra_obs`, `legal_mask`, board/cards, and `teacher_action`.
- It does not include value-like fields (`ev`, `value`, `value_target`, `q_values`, etc.).

Feasibility:
- Useful only as a schema reference for AlphaHoldem-style obs.
- Not valid for EXP-009 training because it lacks value targets and uses the saturated heuristic_v3 teacher.

## Decision

Do not build Phase 1 yet.

EXP-009 remains useful, but the next permitted work item is a narrow CPU-only value-target feasibility proof for Candidate Path A. No BC branch directory, no BC model, and no GPU training should be started until that proof passes and the ledger is updated.

