# Four final full-representation policies: fixed 80k external development calibration

This protocol is fixed before any new Slumbot request. This is development, not
final qualification, policy training, or a claim that the long goal is achieved.

## Decision and frozen endpoints

The completed two-seed full-network learning-rate continuation added 4,207,129
physical training hands across four branches. It did not identify a replicated
LR winner; Seed3 half-rate's early advantage reversed with further training.
Current full-representation final endpoints have not received external calibration.
Prior internal/external ranking disagreement makes direct external measurement
more decision-relevant than another proxy-only diagnostic or automatic scale-up.
The aim is to measure large failures and direction, not guarantee power for small
LR differences at 20k hands/policy. Do not infer that inadequate power disproves
small gains or that these tests validate paper-scale learning.

Use only final stage2 checkpoints in
`v6-full-step-size-1m-continuation-20260905`, never its more encouraging stage1:

| Arm | Physical lineage hands | Checkpoint SHA256 |
|---|---:|---|
|seed1_full|10498234|8904f3b2e25baec5bc0bcb6556502c19b3fb213efdc9a32b16d55eee1284a3ef|
|seed1_half|10497544|669b331d23264136dd75bd923ed3e2fa0e2dd73e4e20485400cd795e59f7653f|
|seed3_full|10492141|f2249b0d19937ddadfc29fe5ba10cd7f07909d638dc0edeca89fae05b6f498e2|
|seed3_half|10492450|f64928d15ecc8620046615774ac9c74fc76d0b8a447f441bd07409d3c41c755a|

Bind completed training review SHA256
70c40a9cdc68b1c1052e8b1d938c9ee41103b57450c313e289f6a5014a69eeab.
Each lineage has approximately 2.1M hands under full-trainable scope; earlier
approximately 8.4M heads-only hands are not relabeled full-network training.

## Execution and fixed allocation

Reuse the qualified journaled client and whole Python runtime from
`v6-static-seed1-4m-greedy-fresh20k-slumbot-20260904/prepared_runtime/scripts`.
CPU, greedy, temperature zero, physical-v6 200bb action mapping, unchanged
legacy-v4 observation bridge. No benchmark-specific rules or Slumbot action labels.
`network_hybrid_h1.py` is byte-identical to the current learned-weight architecture.
Freeze all runtime/source/model hashes, Python/package environment and exact
commands before requests. No training source or earlier experiment is edited.

Exactly eight new sessions of 2,500 completed hands for EACH arm: 32 sessions and
80,000 total. Four waves, each eight concurrent clients maximum: two sessions/arm.
Arm order begins [seed1_full, seed1_half, seed3_full, seed3_half] and rotates left
one position each wave; repeat that order for the second within-wave quartet.
Every arm occupies each within-quartet launch position equally often.
Session indices 1..8 and IDs
`v6_full_step_size_external_20260906_{arm}_sXX` are fixed. Policy seeds use bases
2026401100, 2026401200, 2026403100, 2026403200 respectively plus session index.
Policy seeds do NOT seed the server's cards. Check all readable historical raw
initial IDs/seeds and audited token chains before launch. The schedule is explicit
in `pair_protocol.py` and frozen into `launch_spec.json` and `session_commands.json`.

All four arms complete regardless of intermediate rewards. Running monitoring
counts complete committed raw JSONL only; no interim score-based decisions.
No score-based stopping, extension, policy selection or automatic retries.
If a client, contract, frozen hash, evidence or capacity check fails: drain already
launched bounded sessions, prohibit later waves, preserve every journal/raw byte
and report the failure/uncertainty. No silent session replacement or reconnect.
Only one controller writes this experiment; ownership uses PID plus create time.

## Evidence and statistical analysis

Require exact raw counters, model hashes, terminal payout validation, per-decision
frozen-model replay, greedy/bridge legality, no pending request or partial/uncommitted
journal tail. Require per-arm independence checks and disjoint cross-arm/prior
token chains, plus cross-arm same-index visible seat/hero-hole stream checks.
These checks do not prove arbitrary independence of the remote server RNG.
Unreadable prior records and unknown historical tails remain explicitly not covered.

Primary family: FOUR absolute raw bb/100 means and TWO within-seed half-minus-full
contrasts. Compute bb/100 directly from terminal chips (100 chips/bb). Report raw
hand normal 95% intervals and independent-hand Welch contrast intervals; also
Bonferroni family-adjusted intervals over six primary quantities. Report eight-session
t7 means and Welch contrasts, and four balanced-wave contrast t3 sensitivities.
Not paired server deals. All seat/anchor/historical details remain descriptive.
Any cross-seed aggregate would be exploratory conditional on these two observed
lineages, never a training-seed population confidence interval. Do not combine
policies into one 80k/100k policy claim or turn development hands into blind credit.

Review only after all fixed samples and audits, with consistent evidence required
across seeds/sessions/seats before calling an advantage robust. Use external
direction, severity, uncertainty and agreement with internal curves to choose
further scale or one general-training mechanism control. No automatic LR winner,
new training or final-qualification launch is authorized by the controller.
Finish this same record after independent terminal review; all raw evidence stays.
