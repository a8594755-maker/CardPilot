# V5 EXP-005 Quarantine Goal Overlay

Checked at `2026-07-10 14:47 EDT`.

## Authority and reason

This overlay records a fail-closed correction to the EXP-005 launch state. It must
be read with `docs/V5_CURRENT_GOAL.md`, the append-only Ops log, and
`reports/v5_exp005_prelaunch_design_audit_20260710.md/json`.

EXP-005 cut over at `14:29 EDT` after the pre-launch audit had already returned
`BLOCKED_PRELAUNCH_DESIGN_CONTRACT`. The launch therefore collected treatment data
before the exact MEAS-001 pre identity, executable judgment thresholds, matched
baseline, and runtime group provenance were locked. Later edits cannot make those
criteria prospective. The current window is operational pilot evidence only and is
not a valid confirmatory EXP-005 judgment window.

## Current exact state

- Pilot run:
  `v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_exp005_pergroup5_r1_20260710`.
- Candidate PID `30224` is alive, health `PASS`, stderr empty.
- Manifest confirms the intended single behavior change:
  `opponent_assignment=per-group`, `opponent_groups=5`; retained EXP-002/003/004
  flags match the registration.
- Gate31500 passed at checkpoint `31500 / 517,633,535`; the pilot has accumulated
  about `1.64M` treatment hands from frozen gate31400 / `515,989,661`.
- Gate31500's 200-hand internal verdict is `REGRESSION_RISK_INTERNAL`, but it is
  local smoke evidence and is not the reason for quarantine or rollback.
- Frozen clean pre-treatment checkpoint:
  `v5_exp005_cutover_gate31400_checkpoint.pt`, SHA256
  `bcbb46bd01d62fcdea602269b7047323315d4e9bbcf447ea0323e289fde11a8e`.

## Immediate operational goal

1. Mark the current EXP-005 run `PILOT_QUARANTINED_NO_METHOD_JUDGMENT`. Preserve its
   manifest, logs, checkpoints, watcher artifacts, and exact gate31500 evidence; do
   not delete or reinterpret them.
2. Do not launch MEAS-001, Slumbot promotion20k, formal100k, or any second behavior
   change from this pilot lineage.
3. At the exact gate31500 boundary, execute the registered rollback path from the
   frozen gate31400 checkpoint with `opponent_assignment=per-iteration` and all
   other flags unchanged. Record the stop/resume identities and canonical watcher
   rearm append-only.
4. Preserve the original EXP-005 registration and pre-launch audit. Create a new
   immutable confirmatory design-lock artifact before any clean EXP-005 relaunch;
   do not silently edit thresholds after treatment data have been observed.
5. The confirmatory design lock must freeze:
   - exact formulas, numeric thresholds, CI/margin rules, and terminal behavior;
   - gate31400 as the MEAS-001 pre checkpoint (gate30700 remains external Slumbot
     reference only);
   - matched baseline-window identities/hashes;
   - runtime group provenance and invariant-failure reporting;
   - sequential-evidence wording, or an explicitly authorized same-start control
     branch if causal attribution is required.
6. Add reporting-only runtime provenance and pass focused deterministic/resume/
   multi-env tests plus the full V5 regression suite.
7. Only after items 4-6 pass may a clean confirmatory EXP-005 run restart from the
   frozen gate31400 checkpoint with exactly the same single behavior change and a
   newly recorded run identity. The fixed hand window begins only at that clean
   launch.

## Claim and experiment discipline

- The pilot may validate code execution and throughput, but cannot support EXP-005
  adoption, rejection, non-inferiority, or a V4/L5/L6 claim.
- EXP-006A, action-prior decay, callguard/selector changes, pool changes, and V6 work
  remain excluded.
- The gate30700 promotion remains the latest official evidence: `20,400` hands,
  `-153.300 bb/100`, 95% CI `[-187.695, -118.905]`, L0, non-strong.
- A clean negative or reverted experiment is a valid research result. Retrofitting
  criteria after launch is not.

