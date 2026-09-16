# Seed3 frozen two-endpoint external development calibration

Prospective fixed-budget study, registered before any new Slumbot request. This
continues the completed same-dose Seed3 replication and the existing one-family,
one-control research line. It adds zero training hands and is NOT the final
at-least100,000-hand qualification cohort. Both frozen final endpoints are tested,
not a selected earlier checkpoint or a selected winning seed.

## Question and compute decision

The completed Seed3 internal final moving-minus-static contrast is+1.2054bb/100,
nominal95% CI[-12.1648,14.5757]. Across the fixed Seed1/Seed3 endpoints, the
equal-seed final contrast is+8.0762, conditionalCI[-4.0531,20.2056]. Both arms have
negative later-slope point estimates in both seeds; the moving early gain did not
become a clearly increasing late edge. These are conditional fixed-anchor results,
not training-seed population confidence intervals or general stability evidence.

The earlier, separate Seed1 external80k test gave static -19.8721 and moving
-29.4744bb/100 over40k hands EACH, method contrast -9.6023,
raw95% CI[-32.2884,13.0838]. Neither a method winner nor external transfer was
resolved. The next decision is whether the second training seed reproduces external
direction/breadth sufficiently to inform further expensive training, rather than
automatically doubling both arms to16M or rejecting long-run learning for low dose.

## Exact policies and unchanged execution

Qualified training experiment:
`v6-phase-held-reference-seed3-replication-20260905`, completed and logger-audited.

- Static: `static_stage2/latest.pt`, iteration1773,8,392,377 cumulative local
  physical hands; SHA256
  `36aa1d935179570e76499a0a0c1c81ccd75384b0411b9c7d9cca56c9a2c14b69`.
- Moving256: `moving256_stage2/latest.pt`, iteration1769,8,390,981 hands; SHA256
  `da6d49c60eb73ceddb6a27ff8ff10de06b3306360f61dd49e49b82cd857f4b8c`.
- Twice-recovered training report: `recovery_20260905b/post_terminal_report.json`,
  SHA256 `820862d4e74af6999260b14e0c05a6ba213edffc9d907060cf60d140f802a6d5`.

These two arms share one Seed3 parent; they are not two independent training seeds.
The treatment includes initial reference rebasing plus held-reference cadence.
Two original Windows publication failures remain preserved. Retained new physical
hands are8,393,542; observed executions8,397,834 include4,292 unretained hands.
Recovered5,256 unpublished hands are already retained. Unknown extra worker tails
remain unknown. This study neither resumes training nor erases those limitations.

Use exactly the same frozen286-file Python poker runtime source as the completed
Seed1 external calibration:
`v6-static-seed1-4m-greedy-fresh20k-slumbot-20260904/prepared_runtime/scripts`.
Journaled-client SHA256:
`cea29a9217784b27168665dc01c981433832bb0d7352aefdfe7041f7c896429d`.
CPU inference, generic greedy execution (temperature0), physical-v6 legal actions
and `--observation-bridge legacy-v4`; bridge contract
`hunl_v6_physical_legacy_v4_observation_bridge_v1`. No solver/search, new action
rules, policy interpolation, temperature scan, model update or Slumbot-label training.

New local copies of the qualified pair executor/protocol retain the execution,
raw-counter, audit, statistics and scheduling structure. Changes are Seed3 endpoint
and source bindings, its two-interruption admission, new session IDs/policy seeds,
and additional known poker-process names in the no-overlap guard. Offline admission
also records source derivation and new binding tests. The source derivation checks
unchanged core functions/classes by AST; this is not a proof of every new guard.
Original Seed1 sources, records, models, sessions and results remain unchanged.

## Fixed fresh schedule and failure handling

Exactly32 distinct new sessions:16 per arm,2,500 completed hands each,40,000 per
model and80,000 total. Four waves each have four sessions per arm, at most eight
concurrent clients. Alternate arms within each session index; reverse initial arm
order on odd waves. Session indices are1..4,5..8,9..12,13..16 by wave.

- IDs: `v6_phase_reference_seed3_external_20260905_static_s01` through`s16`,
  and the corresponding`moving256` IDs.
- Static policy seeds:2026365101..2026365116.
- Moving policy seeds:2026365201..2026365216.

Check these IDs/seeds against all readable prior initial journaled records, including
the completed Seed1 external32 sessions. Policy seeds do not control server cards.
Freeze the complete schedule, both SHA-bound models, full runtime, code, environment
metadata and this preregistration before any network request. Copy to exclusive
new output paths; never overwrite or reconnect a previous ambiguous session.

Both arms finish regardless of their running scores. No interim score inspection,
lucky5k screening, score-based early stop, extension, replacement session or
automatic retry. Any process/protocol/source/identity/count failure preserves all
raw evidence, lets already launched bounded clients drain, and prevents later
waves. An incomplete80k cohort remains incomplete. Recovery requires scoped review,
not silently truncating, discarding or repeating evidence.

## Evidence and statistical contract

Update evaluation_hands/slumbot_hands only from complete committed raw JSONL hands.
No fixtures, requests, decisions or replay samples count as benchmark hands. Fully
replay every decision and terminal payout under the frozen model/runtime/bridge.
Audit each model's16 sessions with the unchanged single-model auditor, then check
all32 token chains across arms and against readable prior raw initial tokens and
PASS combined-audit token chains. Preserve unreadable/unknown historical tails as
not covered. Retain within-arm/cross-arm visible-stream checks and all sessions.
These checks do not prove arbitrary server-RNG or temporal independence.

Three primary current-Seed3 quantities: static absolute bb/100, moving absolute
bb/100, moving-minus-static. Calculate from all raw terminal chips (100chips/bb).
Report nominal raw95% mean intervals, independent-hand Welch contrast, and
Bonferroni-three adjusted intervals. Also report16-session t/Welch and four balanced
wave contrast t3 sensitivity, with adjusted versions. Report each seat/session/wave;
seat detail is descriptive, with hand versus equal-session weighting explicit.
Preserve empirical-zero-variance warnings and never promote on them. Balanced
scheduling is NOT common server deals; do not use common-deck paired variance.

After complete current evidence, additionally reaggregate the preserved Seed1 raw
cohort and give equal0.5-weight Seed1/Seed3 method and absolute summaries, using
both cohorts' sampling uncertainty. These cross-seed results are exploratory,
conditional on the two frozen lineages: Seed1 results influenced this study's
allocation. Nominal and Bonferroni-three sensitivity intervals on the combined
three quantities are not new confirmatory alpha guarantees or training-seed
population intervals. Neither80k study may be pooled into one policy's final
qualification; the four endpoints are four different frozen policies.

Same-contract historical references are context, not contemporaneous randomized
controls. Historical Standard10 -11.4275 is not this study's matched baseline.
The completed Seed1 external review is SHA256
`0ca3eff30cd967690d6099f2e7a36e4095a822953b6a1236c32800c53dd54d05`.
All waves, including extreme losses, remain in the analysis.

The80k budget repeats the earlier design, not a variance-adaptive extension. The
observed Seed1 raw contrast half-width was about22.7bb/100 at40k/arm; this is not
adequate power for every small gain. Earlier execution cost was about50minutes,
excluding preparation/review. Actual runtime may differ and is not a stopping rule.
No paid compute is requested or authorized.

## Subsequent decision and ownership

No automatic winner declaration,16M scale, new algorithm family or formal100k
launch. Combine current external evidence, the preserved Seed1 external result,
two-seed internal geometry, opponent/seat breadth, capability preservation and
measured cost. Replicated positive relative direction without broad harm can justify
bounded larger training even when absolute scores remain negative. Replicated broad
regression can justify reallocation or a general mechanism diagnostic. Unresolved
evidence is neither success nor proof that insufficient-scale learning cannot work.
Do not derive action patches or training labels from winning/losing Slumbot hands.

First command, after registration:
`python -B research/experiments/v6-phase-reference-seed3-greedy-paired-fresh80k-20260905/prepare_launch.py`.
It performs offline source/admission/tests and writes exclusive preparation evidence,
with zero network requests and zero model inference. Launch separately through
`launch.ps1`, hidden and file-backed. The exact live controller alone owns this
record and frozen runtime until it and its tracked children terminate. Final
independent evidence review and experiment_log.py finish follow actual completion.
