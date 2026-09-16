# Seed3 frozen external calibration: completed, no winning policy

Independent raw review passed. Exactly32 new2500-hand sessions completed:
16/static and16/moving256,40000 per frozen policy and80000 total. All37 tracked
children exited0 and the exact controller and child identities were terminal
before review.246789 decisions were fully replayed. Raw/journal SHA bindings,
per-arm session checks,cross-arm/prior token checks,visible-stream checks and
independent payout/statistical reaggregation passed.652 frozen input hashes were
rechecked. These checks do not prove arbitrary server-RNG/temporal independence.

## Current Seed3 results

All values below are bb/100. Raw hands are NOT common server deals. Nominal95%
intervals are supplemented by the preregistered Bonferroni-three adjustment and
session/wave sensitivity. Every session and all four waves are retained.

| Quantity | Point | Raw nominal95% CI | Session nominal95% CI |
|---|---:|---|---|
| Static | -25.68955 | [-40.38771,-10.99139] | [-37.00084,-14.37826] |
| Moving256 | -40.73755 | [-57.75896,-23.71614] | [-61.12048,-20.35462] |
| Moving minus static | -15.04800 | [-37.53714,7.44114] | [-37.64900,7.55300] |

Both absolute scores remain negative under adjusted raw and session intervals.
The method contrast remains unresolved: adjusted raw[-42.51732,12.42132],
adjusted session[-43.24569,13.14969]. All four balanced-wave contrasts have
negative points,[-37.3832,-1.8882,-15.0416,-5.8790],but their t3 interval is
[-40.30976,10.21376],adjusted[-53.59938,23.50338]. Both policies have only2/16
positive session points. No wave is discarded.

By physical seat0/1,the static points are-32.3100/-19.0691 and moving points
-36.9150/-44.5601. Corresponding method differences are-4.6050/-25.4910;
both seat-difference intervals include0. Each policy/seat has20000 hands and
each session contributes1250 per seat. Seat detail remains descriptive.

## Exploratory fixed-two-seed synthesis

The unchanged Seed1 raw80k evidence was reaggregated against its SHA-bound
completed review. Its two policies are distinct from the two Seed3 policies.
Equal0.5 seed weights describe these fixed lineages; they do NOT provide a
training-seed population interval or a new confirmatory alpha guarantee.
Seed1 outcomes informed the allocation of the current study.

| Quantity | Equal-seed point | Conditional raw95% CI | Conditional session95% CI |
|---|---:|---|---|
| Static | -22.780825 | [-33.27158,-12.29007] | [-33.21000,-12.35165] |
| Moving256 | -35.105975 | [-47.14959,-23.06236] | [-49.99968,-20.21227] |
| Moving minus static | -12.325150 | [-28.29702,3.64672] | [-30.14094,5.49064] |

Adjusted method intervals remain unresolved: raw[-31.83391,7.18361],session
[-34.29452,9.64422]. Balanced-wave conditional contrast sensitivity is much
wider: nominal[-45.57082,20.92052],adjusted[-60.31810,35.66780]. The adjusted
wave sensitivity for static absolute crosses0; do not claim every sensitivity
analysis resolves negative performance. No empirical-zero-variance promotion.

Both training seeds have negative external moving-minus-static points,whereas
their final internal points were positive. The completed two-seed internal
contrast was+8.0762 CI[-4.0531,20.2056]. This is repeated point-direction
misalignment,not proof of a statistically resolved causal method reversal.
Internal later-stage slopes also did not establish increasing gains. There is
no evidence here for a profitable frozen policy or automatic16M scaling of the
held-reference treatment. This does not reject all long-run self-play learning
because8M hands is small relative to paper scale.

## Accounting and cost

This experiment added0 training hands and80000 external development hands.
The separate Seed1 cohort is reused analysis,not new evaluation credit. All
160000 analyzed external hands belong to four different frozen policies.
Final qualification hands=0; the long goal remains unmet.

Authoritative execution wall time was5298.625seconds (88.3104minutes),including
the live fixed cohort and automated audits. The experiment lifetime also
includes preparation,post-terminal elapsed time and independent review; it is
not training time or a throughput measurement. The execution completed before
the independent report timestamp2026-09-05T17:16:45.953110+00:00. Preserve the
actual timestamps rather than assigning this intervening elapsed time to poker
execution. Prior Seed1 execution cost about50minutes and is not a guarantee.

## Resource decision and next bounded experiment

Do not launch a final100k qualification,extend these cohorts,select a lucky
midpoint,or automatically double the current two-arm reference study to16M.
Retain both arms and all raw evidence. The current static endpoints remain
controls,not proven improvements over Standard10; historical-11.4275 is not a
contemporaneous matched baseline.

Prioritize a matched representation-scope control under the CURRENT corrected
legacy-observation bridge,current-reference KL and replay regimen. The present
main family trains heads/critic while retaining a frozen feature extractor;
simply accumulating more of the same updates does not test feature learning.
This is a candidate bottleneck,NOT a demonstrated cause of external losses.

Relevant prior negatives must be retained: the corrected-v6 full-network265k
curve used sourceKL.01,small1024 minibatches and sampled native-v6 evaluation;
the older full-representation checkpoint used pre-repair semantics and its
corrected-greedy fresh5k result was-68.8218. Low-temperature training already had
its own65k followthrough; do not present it as untried. None of these establishes
that safely opening representation learning under the current regimen works.

Next,preregister the scope-transfer qualification and matched pilot before any
new model queries or hands. Use the two static8M parents without selecting one
winning seed. Verify named-parameter optimizer transfer,replay/counters/RNG and
fresh attempt identities. Explicitly distinguish new representation-parameter
optimizer initialization from preserved existing optimizer state; never silently
reset or mis-map Adam tensors. Freeze all other intended controls and determine
actual learning rates from restored optimizer state. The representation learner
is the main candidate and heads-only continuation its single major control.
Use geometric,multi-seed,heterogeneous/both-seat evidence to decide extension;
small pilots reject only demonstrated mechanism failures or broad collapse,
not long-run learning solely for an early negative absolute Slumbot score.
No Slumbot action labels,outcome imitation or benchmark-specific rules.

The independent report SHA256 is
`9493ac2ec242d6e619e846f9a70851861552d2a5347f5dc16cc73f06e6738036`.
