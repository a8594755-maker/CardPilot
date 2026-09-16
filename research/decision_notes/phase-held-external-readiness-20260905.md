# Next external comparison: readiness and cost review

Prepared while the same phase-held-reference experiment's static remainder is
running. Zero new Slumbot hands and no new experiment started. This is a planning
memo, not a frozen-model preregistration or an authorization to interrupt training.
Attach this memo and the recovery final-analysis preparation to the current record
after its controller relinquishes logger ownership.

## What is reusable, and what is not

The original static4M external run completed eight fresh2500 sessions using CPU,
generic greedy mode, the legacy-v4 observation bridge and journaled physical-v6
execution. Reuse that exact poker execution/evidence contract. Its local wrapper
`v6-static-seed1-4m-greedy-fresh20k-slumbot-20260904/run_pilot.py` has SHA256
`0243cbeaf7efae78b4b8910787eb4bd311659cc5c9308e10c5a1018a00a2e0c5`;
its frozen `prepared_runtime/scripts/alpha_holdem/play_slumbot_v6_journaled.py`
has SHA256`cea29a9217784b27168665dc01c981433832bb0d7352aefdfe7041f7c896429d`.
Freeze and verify every imported runtime dependency, not just this entry point.

The prior two-wave runner
`v6-selfplay-transfer-fresh40k-slumbot-20260831/run_transfer.py`, SHA256
`1ada25d980a064db708aa6d6d6603e69be9f3243123f875d80acb76268811cf4`,
provides a useful balanced schedule: four sessions of each arm in a wave, eight
concurrent jobs maximum, reverse arm launch order in the next wave. Do NOT run it
unchanged: its old sessions are sampledT1, it binds unrelated historical models,
and its statistics select a positive-point pilot for possible100k. All three are
wrong for the present comparison. Reuse scheduling/evidence ideas, not those
model bindings, execution defaults or promotion rule. Preserve old source files.

## Preferred fixed development budget, conditional on valid current completion

Prefer40,000 fresh hands per final endpoint (80,000 total):16 sessions per arm,
2500 hands/session, four balanced waves of eight jobs. Both endpoints must be
tested regardless of internal rank. Keep generic greedy execution fixed, CPU
inference and the same observation/action bridge. Freeze the actual completed
endpoint hashes and full runtime before the first network request. No intermediate
score inspection, replacement session, optional extension or5k admission screen.
Draft unused seed ranges2026345101..2026345116(static) and
2026345201..2026345216(moving256) had no match in the inspected experiment records,
protocols and decision notes; recheck uniqueness at preregistration. Client seeds
do not control server cards and do not prove independent server RNG.

Reason for the budget: the old4M raw standard deviation was15.917620779bb/hand.
Assuming independent equal-variance hands and equal arm sizes, the two-arm95%
contrast half-width is about31.20bb/100 at20k/arm and22.06 at40k/arm; the latter
also gives16 session means per arm for a less sparse cluster sensitivity check.
These are planning assumptions, not predicted variance or a claim of adequate
power for a10bb/100 improvement. At the old20k wall cost776.25seconds with eight
concurrent sessions,80k is roughly52minutes if throughput remains similar, not
a guaranteed ETA. This is a bounded external calibration before more multi-hour
training, not a test that can certify every plausible incremental gain.

The main contrast is moving256 minus static. Also report each raw mean/CI,
session-level Welch or t intervals, balanced-wave contrasts, both seats and
historical same-contract4M/Standard10 comparisons with both sources' uncertainty.
Temporal/session sensitivity is essential; these are not common-deck paired
Slumbot hands. A small positive point estimate or a wide interval crossing zero
does not establish superiority or mechanism failure. Negative absolute scores
alone do not close a long-horizon family. Use the learning curve and the magnitude,
breadth and uncertainty of external changes to decide clean Seed3 replication or
reallocation. No automatic winner promotion or final benchmark launch.

## Evidence prerequisites

Require current recovery controller and all workers terminal, both original stage2
internal evaluations complete, interruption-aware report passed and the same
training experiment correctly finished. Preserve the unknown crash suffix as
unknown. Final endpoint copies must match the audited SHA; do not substitute
an archive chosen from the new internal scores.

Before external execution, log a separate prospective development experiment with
exact fixed sample size, seeds/session IDs, wave order, hashes, runtime and failure
rules. Test greedy-bridge command construction, complete scheduling/counts,
cross-arm/prior token disjointness, no-network preflight, source preservation and
statistics. Retain and replay every decision/terminal hand/journal. Reuse audited
transport; no Slumbot action-label training or opponent-specific action patches.

Final>=100k frozen-policy qualification remains a separate untouched cohort with
its own prospective sample size/stopping rule. Do not pool development hands into
it or repeatedly extend a final cohort until its interval turns positive.

## Deferred current-record preparation receipts

Already executed, zero new poker hands:

`python -B -m pytest -q research/experiments/v6-phase-held-reference-control-20260904/recovery_20260905/test_final_analysis.py --junitxml=research/experiments/v6-phase-held-reference-control-20260904/recovery_20260905/final_analysis_tests.xml`

Eight tests passed. `final_analysis.py --check-ready` correctly refused final
analysis because the exact recovery owner was live. The original post-terminal
summarizer is intentionally not used unchanged: it assumes four normally finished
stage directories and numeric-zero crash suffixes. The new wrapper preserves the
original statistical functions while counting the interrupted prefix exactly once
and bounding its unknown wall time. Full raw reaggregation has not yet executed.
