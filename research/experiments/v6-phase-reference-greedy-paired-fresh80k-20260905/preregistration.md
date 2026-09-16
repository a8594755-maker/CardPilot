# Frozen two-endpoint external development comparison

Prospective fixed-budget development experiment. No Slumbot hands in this record
have been executed at registration. It follows the completed
`v6-phase-held-reference-control-20260904` protocol, which required testing BOTH
final endpoints regardless of their internal rank. No new training is authorized
by this experiment. This is not the final >=100,000-hand qualification cohort.

## Question and frozen policies

Does the internally positive but uncertain phase-held-reference-minus-static
contrast transfer to external 200bb heads-up no-limit Hold'em play? Both endpoints
descend from the same original Seed1 4,197,976-hand parent. They are not independent
training seeds, and this test does not isolate reference refresh cadence from the
treatment's initial reference rebasing.

- Static: local lineage 8,395,752 physical hands, source
  `v6-phase-held-reference-control-20260904/recovery_20260905/static_stage2_remainder/latest.pt`,
  SHA256 `41ff38496167424fa71373028e9291a0d8bd595315f7121d8fa303e6b15a3372`.
- Moving256: local lineage 8,395,171 physical hands, source
  `v6-phase-held-reference-control-20260904/moving256_stage2/latest.pt`,
  SHA256 `b0ab97e76dd6d3603b5b6cde0b2fccaa1726fb8b825b23458f9f9f58dc36f932`.

The completed interruption-aware training report SHA256 is
`461a74b29504eb70d7156f61f2f3b693d4c6a6cb609ccc213a3bd28ade0a65c9`.
The unknown original crash suffix remains unknown, not zero or inferred training
credit. This experiment never resumes, changes or selects another checkpoint.

Use the exact full Python poker runtime snapshot from
`v6-static-seed1-4m-greedy-fresh20k-slumbot-20260904/prepared_runtime/scripts`.
The journaled client SHA256 is
`cea29a9217784b27168665dc01c981433832bb0d7352aefdfe7041f7c896429d`.
Bind every Python dependency in that snapshot, all execution/test source, this
document and both endpoints in `launch_spec.json` before any network request.
Copy runtime and models to this experiment without overwriting anything. Record
installed Python/package versions in `environment.json` before launch.

Execution is CPU inference, generic greedy policy (temperature zero), physical-v6
legality/action mapping with `--observation-bridge legacy-v4`. The bridge contract
is `hunl_v6_physical_legacy_v4_observation_bridge_v1`. No search, Slumbot-specific
action override, temperature sweep, policy selection or Slumbot-label training.

## Fixed schedule and stopping

Exactly 40,000 completed fresh hands per model: 16 distinct sessions per arm,
2,500 hands per session; 80,000 total. Four waves each contain four sessions from
each arm, maximum eight concurrent clients. Within each wave alternate arms for
each session index; reverse initial arm order on odd waves. Wave zero uses indices
1..4, then 5..8, 9..12 and 13..16. Both arms complete regardless of running scores.

Session IDs are `v6_phase_reference_external_20260905_static_s01` through `s16`,
and the corresponding `moving256` IDs. Static policy seeds are 2026345101..5116;
moving seeds are 2026345201..5216. The serialized complete schedule must equal the
prequalified `pair_protocol.schedule()` output. Check prior raw session IDs and
seeds before launch. Client seeds do not determine Slumbot cards.

No interim score inspection, lucky 5k screening, optional extension, early
score-based stopping, replacement session or automatic retry. A protocol,
identity, source, count or process failure preserves all evidence, allows already
launched bounded clients to drain and prevents later waves. An incomplete cohort
is incomplete; it is not relabeled a valid smaller experiment. Do not restart this
runner or reconnect an ambiguous prior session. Any recovery requires separate
evidence-based review without discarding or duplicating prior raw hands.

## Evidence and statistics

Incrementally update evaluation_hands and slumbot_hands from complete committed
raw JSONL records. Do not count fixtures, requests, decisions or internal training
as external hands. Full replay must verify every decision, greedy action,
observation bridge, terminal payout, successful/attempted counter and model SHA.
Audit each model's 16 sessions separately with the frozen single-model auditor;
retain its invariant. Then check all 32 token chains across arms and against
readable prior raw initial tokens and valid prior combined-audit token chains.
Record unreadable/unknown historical tails explicitly as not covered. Check
within-arm and cross-arm visible shared-stream evidence. These empirical checks
cannot prove arbitrary server-RNG or temporal independence.

Three primary quantities: static absolute bb/100, moving absolute bb/100 and
moving-minus-static. Compute raw means from all terminal chips (100 chips/bb),
raw normal mean intervals and an independent-hand Welch contrast. Report nominal
95% intervals plus Bonferroni-three adjusted intervals. Also report 16-session
t/Welch intervals and four balanced-wave contrast t3 sensitivity, with adjusted
versions. The word paired in this experiment's ID refers to balanced scheduling,
not common server deals. Do not use a common-deck paired variance estimator.

Report each seat, session and wave; seat detail is descriptive and not part of
the three-quantity family. Session and wave sensitivity do not establish arbitrary
dependence-robust coverage. Unequal seat counts and hand-versus-session weighting
are explicit. Preserve empirical-zero-variance warnings and do not promote on them.
Historical same-contract original4M and Standard10 comparisons use both sources'
uncertainty and are temporally confounded context, not randomized contemporaneous
controls. Historical Standard10 -11.4275 is not a matched current baseline.

The sample size was chosen before these outcomes: the historical4M variance gives
an approximate raw contrast half-width of22bb/100 at40k/arm versus31 at20k/arm.
Actual variance may differ; this test is not adequately powered for every10bb/100
gain. At historical throughput the rough80k wall cost is52minutes, not an ETA or
an excuse to truncate a slow cohort. No paid compute is requested or authorized.

## Decision after completed evidence review

No automatic winning-policy declaration, 16M training, Seed3 replication or final
100k launch. Review the external contrast and its uncertainty alongside the
two-stage internal curve, seat/session/wave breadth, drift and measured cost.
Directional external agreement without broad harm can justify independent
unaffected Seed3 replication even if absolute scores remain negative. Clear
replicated external reversal warrants reallocation or a bounded general mechanism
diagnostic. An unresolved interval is insufficient evidence, not a proof that
long-run learning cannot work. Do not train on winning/losing Slumbot actions or
patch their labels. Final qualification requires a separately frozen policy and
prospectively fixed fresh cohort; these80k development hands never count toward it.

The exact initial offline command is:
`python -B research/experiments/v6-phase-reference-greedy-paired-fresh80k-20260905/prepare_launch.py`.
It creates only exclusive preparation manifests and verifies admission. Launch
occurs separately through `launch.ps1`, whose hidden file-backed process survives
an observer returning. The controller owns this record until its exact PID and
creation time are terminal. Do not create a competing logger writer while live.
