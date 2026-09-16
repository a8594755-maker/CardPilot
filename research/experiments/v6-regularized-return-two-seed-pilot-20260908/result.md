# Fixed regularized-return pilot result

All four arms completed65536 new physical hands,262144 executions on131072
unique planned decks. Matched arms deliberately share decks. Retained86 Adam
states advanced32 updates per arm; old replay/pool remain inactive in unchanged
hash-bound parents.242240 hands generated715001 hero decision rows.128 optimizer
updates total. Independent raw/accounting/Adam checks passed both stages.

Both frozen sampled eight-anchor evaluations completed49152 executions each,
98304 total on16384 distinct evaluation decks. Ordered raw/hash checks passed.
No Slumbot hands. Known anchors share ancestry; not unseen-family generalization.

Paired treatment minus control, bb/100, conditional unadjusted95% intervals:

| New hands per arm | Seed1 | Seed3 |
| --- | --- | --- |
| 16384 | +5.61 [-12.49,23.70] | +7.24 [-5.05,19.52] |
| 65536 | +71.67 [5.42,137.92] | +69.83 [26.80,112.86] |

The final comparison is positive in both seeds, stronger than the initial-dose
point estimates. Independent stage decks mean this is not a paired estimate of
the change in slope, and nominal intervals do not adjust all exploratory panels.

Final treatment versus own parent:Seed1+72.37 [1.28,143.47],Seed3+19.34
[-34.99,73.66]. Control versus parent:Seed1+0.71 [-55.59,57.00],Seed3-50.50
[-100.70,-0.29]. Thus Seed3 treatment advantage partly reflects control decline;
replicated improvement beyond both parents remains unconfirmed.

Treatment-control preservation:Seed1+103.78 [11.35,196.21],Seed3+72.37
[8.28,136.45]; transfer:Seed1+39.56 [-55.38,134.49],Seed3+67.29 [9.85,124.74].
Seat0/1 points:Seed1+167.19/-23.85,Seed3+51.28/+88.38. Seed1 seat asymmetry
and wide intervals prevent a broad-strength claim. No endpoint promotion or
benchmark success is warranted from these results alone.

Training controller wall time424.259+1410.160=1834.419 seconds. Sum of update
transaction times1534.221 seconds; remainder includes initialization and source/
raw/checkpoint verification. Evaluation wall743.849+729.107=1472.956 seconds.
These costs exclude preliminary implementation fixtures and analysis time.

Decision: retain this sole positive candidate and exact endpoints. Next priority
is independent frozen endpoint confirmation versus BOTH matched controls and own
parents, with predeclared heterogeneous held-out-family coverage and external
development calibration where execution evidence supports it. Do not retune eta
on the same cohorts, automatically promote the better seed, or jump to paper scale.
If the signal survives, extend geometric learning and opponent breadth; fixed
Standard10-only learning is a mechanism pilot, not a general self-play solution.
This is a regularized trajectory-return PPO variant, NOT full RNaD/DeepNash.
