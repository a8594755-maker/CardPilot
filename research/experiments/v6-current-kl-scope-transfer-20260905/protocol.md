# Current-regimen heads-to-full scope transfer qualification

Prospective bounded mechanism experiment. The completed Seed3 external80k record
and its two-seed synthesis do not support automatic16M reference-family scaling.
Test the prerequisite for a matched representation-learning control: opening the
existing feature extractor without resetting or positionally mis-mapping any
existing trained parameter's Adam state. This is NOT a strength experiment.

## Fixed source policies

Use both static8M endpoints,not a selected winning seed:

- Seed1: `v6-phase-held-reference-control-20260904/recovery_20260905/static_stage2_remainder/latest.pt`,
  SHA256 `41ff38496167424fa71373028e9291a0d8bd595315f7121d8fa303e6b15a3372`.
- Seed3: `v6-phase-held-reference-seed3-replication-20260905/static_stage2/latest.pt`,
  SHA256 `36aa1d935179570e76499a0a0c1c81ccd75384b0411b9c7d9cca56c9a2c14b69`.
- Current production trainer SHA256
  `1b4d23abfa3e0a9c675126fd7183d37b134a2a13253563e990e144cc01a90f8b`.

These parents retain earlier interruption/freshness limitations. This experiment
does not erase them or create new training-hand credit. Preserve every original
checkpoint,trace,optimizer,replay,reference,pool and RNG artifact unchanged.

## Scope and invariants

First inspect actual checkpoint metadata and ordered model parameter names under
the exact current network source. Bind source/runtime versions and all inputs.
Confirm the actual all-policy-heads/public-critic parameter order from the
SHA-bound producer,not from guessed parameter IDs or tensor shape alone.

Implement an isolated,explicit single-group Adam transfer on derived copies:
preserve existing parameter states by verified name; retain all group
hyperparameters and the effective learning rate; add previously frozen parameter
IDs with NO invented Adam moments/steps. Their optimizer state initializes only
on their first gradient. This is a scope expansion,not an exact unchanged-scope
resume and not a reset of existing Adam state.

Models,replay entries/RNG/cumulative rows,physical/transition counters,pool,
assignment origin,reference state and main RNG must remain recursively equal.
Only the optimizer ID mapping,all-policy-heads-only scope declaration and an
explicit transfer-provenance field may differ in a derived checkpoint. Write
exclusive new paths and verify after serialization; never replace the parents.

Qualification uses synthetic finite gradient fixtures on disposable model copies.
For identical supplied head gradients,the preserved head parameters and Adam
states must update identically to the heads-only control,while new representation
parameters obtain new states/updates. Verify failure on malformed,ambiguous,
duplicate,missing,shape-incompatible or nonfinite optimizer inputs and attempted
output overwrite. Save source hashes,exact commands and test evidence.

Budget: zero environment training hands,zero evaluation/Slumbot hands. Model
initialization and synthetic tensors/gradients are allowed,not poker strength
queries. No simulator workers,network requests or Slumbot labels. Production
trainer/network remain unchanged during this isolated qualification. No new
policy architecture,temperature,opponent distribution or learning-rate sweep.

## Decision

Passing permits a separately preregistered actual training-scope pilot,not automatic
16M/final100k or a claim that representations are the cause of external losses.
Its main candidate will learn representations and its single major comparator
will continue heads-only. Before production,verify actual trainer scope/load
compatibility and effective learning rates,and require fresh managed attempt
namespaces plus actual initial-state audit. Preserve existing Adam/replay/counters
and RNG; new representation states are explicitly new. Geometric,multi-seed,
heterogeneous and both-seat evidence governs later dose allocation. Do not reject
long-run learning just because a small pilot is not yet positive on Slumbot.

Prior negatives remain relevant: corrected-v6 full-network265k used sourceKL.01
and older native/sampled evaluation; old pre-repair full-network weights failed
corrected-greedy transfer; T0.5 already lost its smoke advantage at matched65k.
This experiment does not relabel any of those as success or repeat them.

First exact command after registration:
`python -B research/experiments/v6-current-kl-scope-transfer-20260905/inspect_parents.py`.

Register,start/update/finish through `research/experiment_log.py`. Capture later
source/test changes before executing them. This first inspection does not create
derived checkpoints or perform synthetic gradient updates.
