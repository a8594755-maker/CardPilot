# Frozen qualification: sample-size and cost planning

Planning memo written while the already preregistered phase-held-reference
control trains. This is not a new training experiment, a formal test
preregistration, a candidate selection, or authorization to start Slumbot.
It changes no active protocol, frozen source, checkpoint, or experiment record.
Attach it to the next relevant calibration/qualification record when that record
is opened; do not introduce a competing writer to the active controller's log.

## Evidence used

The completed original static Seed1 4M development cohort has 20,000 hands,
raw mean -41.3116 bb/100, and per-hand standard deviation
15.917620778970303 bb. Its raw hand-normal interval is
[-63.37229688260496, -19.25090311739504]; the equal-session t7 sensitivity
interval is [-68.7037, -13.9195]. These remain negative, not qualification evidence.

Source: `research/experiments/v6-static-seed1-4m-greedy-fresh20k-slumbot-20260904/raw_ci.json`,
SHA256 `023a2e21ed675e02077e226b2092906a13e24a671b05387d60281e4be806fe63`.
The same directory's `completed_analysis.json` SHA256 is
`2f911af7f27b5e806d0f3bef243141c25e435c5bf76613d35da3cdd964193687`.
Its result summary reports 776.25 seconds for the 20k execution with original
replay/evidence collection, excluding later researcher interpretation.

## Conditional normal-approximation calculation

For planning only, suppose a different frozen candidate has the same per-hand
variance and independent stationary rewards. Let `s = 100 * 15.917620778970303`,
`z = NormalDist().inv_cdf(.975)`, and `SE(n) = s / sqrt(n)` in bb/100.
Then the approximate probability that a two-sided 95% lower bound exceeds zero,
under a hypothetical positive true edge `mu`, is
`1 - NormalDist().cdf(z - mu / SE(n))`.
The approximate 80%-power sample requirement is
`ceil(((z + NormalDist().inv_cdf(.8)) * s / mu) ** 2)`.

At 100,000 hands, SE is 5.0335936592369785 bb/100 and the 95% halfwidth is
9.865662284913657 bb/100. Thus a 100k sample mean merely above zero generally
does not meet the requested positive-lower-bound criterion.

| Hypothetical true edge | Power at 100k | Approximate n for 80% power | Budget rounded to 20k cohorts and >=100k |
|---|---:|---:|---:|
| +5 bb/100 | 16.69% | 795,471 | 800,000 |
| +10 bb/100 | 51.06% | 198,868 | 200,000 |
| +20 bb/100 | 97.80% | 49,717 | 100,000 |

The table is **not an estimate of any current candidate's edge**. A negative
model does not become positive by collecting more hands. At the observed 20k
execution cost, simple linear planning gives about 65 minutes for 100k,
129 minutes for 200k, and 8.6 hours for 800k, before additional preparation or
analysis. These are conditional extrapolations, not reservations or guarantees
of future API throughput, stability, variance, or statistical power.

## Consequences for the next allocation decision

1. Continue the current phase-held-reference experiment unchanged. Its two
   geometric stages and paired internal gates come before any new final test.
   The current negative 4M endpoint remains ineligible for an automatic 100k run.
2. After a valid stage2 completion, preregister the planned external development
   comparison of both fixed endpoints regardless of their internal ranking.
   Do not relabel those development hands as final blind qualification.
3. Select a final sample size using separately held-out development evidence,
   plausible edge and the selected policy's reward/session variance. Freeze that
   sample size, complete execution contract, cohort identities, inference code,
   and failure/stop rules before the first formal hand. The user's 100k is a
   minimum, not a statistically sufficient universal target.
4. Use multiple independently initialized session cohorts. Examine both seats
   and session/cohort sensitivity; an absence of repeated visible prefixes is
   not proof of arbitrary independence. Hand-normal power above does not include
   serial correlation, clustered variance, nonstationarity, candidate-selection
   uncertainty, or the extra cost of more conservative valid intervals.
5. Do not extend a fixed final test after seeing a near miss or repeatedly try
   frozen candidates until one happens to cross zero. Before formal qualification,
   specify how repeated qualification attempts or sequential looks will be
   handled. Report any multiplicity and retain failures; do not imply that an
   unbounded search for a passing ordinary 95% interval has 95% overall coverage.

No new environment hands, offline model queries, external hands, or paid compute
were used for this arithmetic memo. Stronger learned weights, independent
generalization evidence, and the complete frozen-policy benchmark remain unproven.
