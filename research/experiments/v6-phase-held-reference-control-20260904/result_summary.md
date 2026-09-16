# Phase-held reference control: completed research review

Both preregistered endpoints completed. The interruption-aware independent raw
reaggregation passed after all controller, trainer and evaluation owners exited.
The experiment is complete; the long-term benchmark goal is not achieved.

## Strength evidence

All values below are internal greedy evaluation bb/100 differences, not Slumbot
win rates. Each stage uses 8,192 fresh common decks across four fixed anchors,
both seats. Repeated original-parent executions are joined and verified exactly,
not treated as extra independent observations.

| Comparison | Approximately 6.30M endpoint, nominal 95% CI | Approximately 8.40M endpoint, nominal 95% CI |
|---|---:|---:|
| Static reference minus original 4M | +2.26 [-3.85, 8.38] | -7.44 [-13.21, -1.67] |
| Phase-held reference minus original 4M | +12.74 [2.43, 23.05] | +7.51 [-12.47, 27.48] |
| Phase-held minus static, raw paired | +10.48 [-0.71, 21.67] | +14.95 [-5.29, 35.19] |

At the final endpoint the phase-held branch has positive point differences against
the original parent in three of four anchors and both seats. The static branch
has negative point differences in all four anchors and both seats. The direct
method contrast remains unresolved. The phase-held branch's later geometric slope
is -5.23 [-27.71, 17.24]; the static branch's is -9.70 [-18.11, -1.29]. These slopes
compare independent stage cohorts, not shared decks between stages.

Intervals are descriptive, conditional on these fixed anchors/checkpoints and
their sampling assumptions; they are not adjusted for multiple comparisons or
continuation selection and do not establish population-level generalization.
This is one training seed with matched initial state, not independent-seed
replication. The treatment changes initial reference rebasing as well as refresh
cadence; it is not an isolated causal test of cadence or a faithful NashPG/AlphaHoldem
paper reproduction. Low drift is not strength: final mean TV versus Standard10 is
0.01154 static and 0.03043 phase-held; greedy disagreement is 1.415% and 2.875%.

## Accounting and recovery

- Newly retained physical training executions: 8,394,971 across both branches.
- Transition-bearing hands: 7,311,247; no-decision hands: 1,082,438;
  retained worker-tail hands: 1,286. These sum to the retained physical count.
- Replay rows: 12,804,420, not new environment hands.
- Shared original parent: 4,197,976 local physical hands, counted once in the
  12,592,947 known local lineage-union total. This union is not one policy's dose.
- Final static lineage: 8,395,752; final phase-held lineage: 8,395,171.
  Pretrained Standard10 environment-hand exposure is not inferred.
- Internal evaluation: 131,072 physical executions, including intentional repeated
  parent controls; offline drift: 80,000 states; new Slumbot hands: zero.
- Training-attempt wall time is bounded by 17,095.62 to 18,031.74 seconds
  (4.75 to 5.01 hours), giving 465.57 to 491.06 retained physical hands/second.
  This is the full experiment's training time, not a claim about only the user's
  most recent three-hour window. Record wall time also includes evaluation/review.

The original static stage2 attempt was interrupted at iteration 1525 and physical
7,237,515. Its checkpoint, manifest, complete assignment evidence and raw logs
remain unchanged. A separate remainder restored model, optimizer/LR, replay and
saved random/assignment/reference state, adding only 1,158,237 retained physical
hands. Five durable attempt namespaces prevent deal-prefix reuse. Continuation is
statistical, not bitwise worker-RNG continuation. The interrupted attempt's
uncheckpointed crash suffix remains unknown/null, not zero or recovered credit.
Its missing normal termination evidence has not been fabricated.

Final checkpoint SHA256:

- Static: `41ff38496167424fa71373028e9291a0d8bd595315f7121d8fa303e6b15a3372`
- Phase-held: `b0ab97e76dd6d3603b5b6cde0b2fccaa1726fb8b825b23458f9f9f58dc36f932`

Authoritative independent report:
`recovery_20260905/post_terminal_report.json`, SHA256
`461a74b29504eb70d7156f61f2f3b693d4c6a6cb609ccc213a3bd28ade0a65c9`.
It binds raw evaluation/drift files, endpoint hashes, completed termination
receipts, prior-corpus disjointness and preserved interruption evidence.

## Resource decision

Do not automatically expand either branch to 16M or declare a winning model.
Follow the original protocol with a separately preregistered external development
comparison of BOTH frozen final endpoints, regardless of their internal ranking.
The prepared design is 40,000 fresh Slumbot hands per endpoint, 16 sessions per
endpoint in four balanced waves, fixed greedy/legacy-v4 execution, no score-based
early stopping, replacement or extension. Preparation passed 45 offline tests;
its synthetic rows are not poker hands. It is not yet an external launch or a
formal >=100k qualification experiment.

External alignment, interval width, seat/session consistency and cost determine
whether independent unaffected Seed3 replication and later geometric scale are
worth funding. An unresolved small pilot is not proof that a method can never
learn; a negative continuation curve is also not a reason to allocate paper-scale
compute automatically. A final benchmark cohort remains separate and untouched.
