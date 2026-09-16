# Offline two-arm external transfer protocol readiness

Registered during the immutable v6-selfplay75-transfer-pilot-r4-20260831 training.
Do not modify that experiment, its trainer, copied source, configurations or data.
This independent CPU-only protocol test generates zero environment, evaluation,
Slumbot or validation hands; no model queries or external connections. Synthetic
integer arrays are arithmetic fixtures, not poker observations or learning data.

Qualify reusable schedule, statistics and cross-arm audit checks for the already
registered later20k/arm test. It cannot launch gameplay. Candidate-specific
parity and reviewed training evidence/final hashes remain mandatory later.

Fixed proposed cohort: control25/selfplay75, eight2500-hand sessions per arm,
two sequential waves of eight clients, each wave four sessions per arm.
Wave0 alternates control25/selfplay75; wave1 reverses arm-first order. All clients
within a wave must exit before the next wave begins. No replacement session or
score-based stop. An infrastructure failure preserves launched prefixes and
invalidates the full paired-cohort strength claim; do not rescue the survivor.
Fresh policy seeds2026100701..08 for control25 and2026100801..08 for selfplay75;
IDs v6_selfplay_transfer_20260831_{arm}_s01..08. These are reservations, not
already executed sessions. The eventual live record must freeze the schedule,
model identities and client runtime before the first request.

Each arm: mean chips equals bb/100 for100chips/bb; ordinary raw-hand normal95%CI
and eight-session t7 95%CI. Between-arm contrast selfplay75 minus control25:
unpaired Welch t CI using20000raw chip values per arm and separately eight
session means per arm. Never pair unrelated Slumbot hands by index or seed.
Report ordinary95% and Bonferroni family3 simultaneous95% intervals for the two
arm means and single between-arm contrast (each raw/session analysis separately).
Two balanced waves mitigate launch-order drift but do not prove independent
server RNG or eliminate shared temporal dependence. Session CIs assume
independent session clusters; state that limitation explicitly.

Use independently coded Welch arithmetic verified against the official SciPy
ttest_ind(equal_var=False).confidence_interval implementation, including uneven
variance and session offsets. References:
https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_ind.html
https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.t.html
Record installed SciPy version; do not imply the online documentation version
is the local runtime version. Zero observed variance is explicitly flagged and
no100k success can be inferred from any fixture or pilot.

Both full cohorts and all evidence checks must pass before computing a paired
report. Preserve full per-model journal/terminal/frozen-action replay audits.
Additionally require all16session IDs/seeds and token chains disjoint across
arms and previously used corrected-v6 sessions. A matching token, missing arm,
partial cohort, bad replay count or swapped checkpoint fails closed.

Allocation follows the parent preregistration: if a valid arm point is positive,
it may receive a separately logged fresh100k qualification. If both are positive,
choose the larger point, exact tie control25. This is a compute allocation, not
proof of superiority/significance. No pilot/internal/old sample pooling. No
internal score input is accepted. Actual Goal remains100k fresh hands for ONE
frozen learned policy with positive bb/100 AND95% lower bound above zero.

python research/experiments/v6-paired-transfer-protocol-readiness-20260831/run_readiness.py

Capture own files and logger with dirty patch/hashes. Test schedule identities,
both-wave balance, chip conversion, fixed budgets, malformed inputs, unpaired
variance, independent arithmetic, cross-arm/prior-token collision, missing replay
evidence and deterministic positive-point allocation. Assert no network calls.
Before and after, verify all76active original/copy pairs and frozen anchors.
Finish this zero-hand record only if all tests and protection checks pass.
