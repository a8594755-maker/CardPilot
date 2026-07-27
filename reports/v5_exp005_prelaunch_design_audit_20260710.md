# EXP-005 Pre-Launch Design Audit

Checked at `2026-07-10 14:22 EDT`.

## Verdict

`BLOCKED_PRELAUNCH_DESIGN_CONTRACT`

EXP-005 is the selected single behavior hypothesis and its `per-group`
implementation has passed offline validation, but cutover is not yet scientifically
judgment-ready. The live trainer remains PID `48476` on the old `per-iteration`
assignment. Gate31400 PASS alone does not authorize cutover.

This audit does not reject EXP-005 and does not select EXP-006A. It requires a
prospective append-only design lock before any EXP-005 behavior data are collected.

## Evidence already settled

- Gate30700 official greedy-direct promotion20k is complete and audited:
  `20,400` hands, `-153.300 bb/100`, 95% CI `[-187.695, -118.905]`, L0,
  `promotion_20k_strong=false`.
- The full 500M loss review supports distribution lurch as the leading mechanism.
- The frozen EXP-006A direct-signal gate did not pass; EXP-005 remains the only
  selected next behavior experiment.
- EXP-005 implementation validation passed focused `5/5`, offline multi-env smoke,
  and full V5 regression `153/153` without touching the live trainer.

## Blocking design defects

1. **MEAS-001 pre identity is not yet exact.** MEAS-001 requires the exact
   pre-change cutover checkpoint. Gate30700 is the official external Slumbot anchor,
   not a valid substitute for a later EXP-005 cutover checkpoint. The cutover
   iteration/hands/hash fields are still null.
2. **Judgment thresholds are not fully numeric.** Phrases such as `materially
   worsen`, `improve by more than noise`, and `at minimum non-inferior` are not
   executable verdict rules. The exact formulas, margins, CI operation, and tie/
   missing-data behavior must be frozen before launch.
3. **The baseline window is not yet identity-bound.** The exact pre-cutover 20M
   window, its gate list, log hash, effective-h/s baseline, warning metrics, value-
   loss metric, and any secondary internal diagnostics must be frozen when the
   cutover source is selected.
4. **Runtime group provenance is absent.** `build_group_opponent_assignments()`
   returns group metadata, but the live training path currently discards it. The
   experiment contract requires per-iteration or lossless aggregate evidence for
   group sizes, self-play worker count/fraction, group-to-opponent IDs, distinct pool
   opponents, reshuffle behavior, and invariant failures.
5. **Causal language must match the design.** MEAS-001 provides a high-precision
   paired comparison of pre/post policies. Without a parallel unchanged-control
   continuation from the same checkpoint, it does not by itself separate the
   EXP-005 treatment effect from ordinary learning over the fixed hand window.
   Sequential evidence must be labeled accordingly; a parallel branch is the gold
   standard if compute is authorized.
6. **Signal hierarchy must be preserved.** The 200-hand scripted internal probe is
   smoke/localization evidence and may not become the primary adoption gate. MEAS-001
   is primary method evidence; stability counters are mechanism checks; official
   greedy-direct Slumbot remains the external calibration and claim path.

## Required resolution before cutover

1. Append an immutable pre-launch EXP-005 design-lock artifact that preserves the
   same single variable and fixed hand window while making every verdict formula and
   margin executable. Preserve the earlier registration; do not silently rewrite it.
2. Add reporting-only runtime provenance for group assignment and validate it with
   invariant, deterministic-seed, resume, multi-env, and full V5 regression tests.
3. At the first exact PASS gate after items 1-2 pass, freeze/hash that checkpoint as
   both the EXP-005 rollback source and MEAS-001 pre checkpoint. Gate30700 remains
   only the official external reference.
4. Freeze the matched pre-cutover baseline window and all source hashes before
   launching the continuation.
5. Rearm watchers and launch exactly one continuation with
   `--opponent-assignment per-group --opponent-groups 5`; all other behavior flags
   remain unchanged.

Until all five items are satisfied, the correct state is `WAITING/BLOCKED`, not
`READY_TO_CUTOVER`.

