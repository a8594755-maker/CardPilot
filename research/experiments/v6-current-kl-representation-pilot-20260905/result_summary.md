# Current-regimen full-representation pilot: completed, strength unresolved

The same preregistered two-seed, two-scope study completed both fixed stages.
All original and final weights, source bindings, initial-state transfers, optimizer
clocks, replay/counters, pool reconstruction and raw common-deck evidence passed
the independent terminal review. Its SHA256 is
`0cb118d8232db5094e2f68a7ee03993ae5e28231f0f947126e0d9a2704b60971`.
This completes the experiment, not the long Slumbot goal.

## Actual work and cost

- New physical training hands:4,198,360 across four branches, not one policy.
- Transition-bearing hands:3,666,365; no-decision hands:530,002; residual worker
  tail hands:1,993. These sum to the physical count. Replay:6,402,035 rows, not
  additional environment hands.
- Largest single final lineage counter:9,445,556. Full representation was newly
  trainable for about1.05M physical hands per full branch; the earlier8M heads-only
  history is not relabeled as full-representation training.
- Internal evaluation:262,144 executions,32,768 unique common decks across both
  stages/seeds. Paired full/heads and repeated-parent executions are intentional.
- Slumbot hands and final-qualification hands:0.
- Training subprocess time:6,632.50s (110.54min),632.998 physical hands/s. All job
  time:11,077.14s (184.62min); controller wall:11,657.63s (194.29min). Record
  lifetime also includes preparation and review; it is not execution time.
- Eight distinct managed attempt namespaces;112 observed child identities and
  all recorded job/owner identities terminal.575,490 prior inventoried raw rows
  checked for overlap. This does not establish independence from every historical
  corpus. All eight endpoints retained initial opponent IDs0,1,2.

## Strength evidence

Nominal conditional paired-deck95% intervals, bb/100. These are not training-seed
population intervals or external strength estimates.

| Contrast | Seed1 | Seed3 |
|---|---|---|
| Stage1 full minus heads | -0.207 [-13.347,12.934] | -20.835 [-36.125,-5.545] |
| Stage2 full minus heads | +1.316 [-16.835,19.467] | -5.313 [-20.582,9.956] |
| Stage2 full minus original8M parent | +4.438 [-13.202,22.077] | +0.323 [-13.414,14.061] |
| Stage2 heads minus original8M parent | +3.122 [-1.498,7.742] | +5.637 [-3.598,14.872] |
| Stage2 full minus heads, seat0 | +29.049 [0.165,57.934] | +0.879 [-20.781,22.539] |
| Stage2 full minus heads, seat1 | -26.417 [-50.789,-2.046] | -11.505 [-30.875,7.864] |

Full-versus-parent Standard10 point differences are+2.319/+14.221, but both
intervals cross zero; do not claim demonstrated noninferiority. Full-minus-heads
has only2/4 and1/4 positive anchor point differences. The seat1 warning repeats
in direction, not as two independently decisive failures. No robust broad
advantage or basis for final blind Slumbot testing is established.

The separate fresh-cohort geometric changes matter too. Full-versus-parent
stage2-minus-stage1 is+9.055 CI[-13.221,31.331] and+21.061 CI[0.370,41.752].
Full-minus-heads changes are+1.523 CI[-20.886,23.931] and+15.522
CI[-6.087,37.130]. Both full branches recovered in pooled point estimate; this
is not a mechanistic rejection of representation learning or proof that scale
cannot work. These post-analysis intervals are exploratory and nominal, not
linear forecasts. The preregistered severe broad-collapse gate was false.

## Mechanism and research decision

The scope transfer genuinely worked. Full-stage2 existing86 Adam states advanced
588/650 steps; no states were reset or newly invented. Full-stage2 KL-stop
iterations were101/164 (Seed3) and88/169 (Seed1), versus zero in the heads arms.
Mean approximate update KL was0.00986/0.00832 for full, versus about0.00007 for
heads. Mean Standard10-reference KL was about0.046 versus0.001. PPO KL stops are
an intended safeguard, not an error; these differences motivate a step-size
hypothesis but do not prove a cause for the seat imbalance.

Keep one full-network learning family. Next qualify a0.5x actual-Adam-LR control
from BOTH current full endpoints, retaining the original full-rate continuation
as the main comparison. Deliberately change only the optimizer group LR in an
auditable derived checkpoint; preserve all weights, moment tensors, state clocks,
replay, counters, main RNG and pool history. No restart from Standard10 or the8M
parent. Require initial-state audit, source-bound trainer and fresh managed worker
namespaces. This is statistical worker continuation, not bitwise worker replay.

After qualification, preregister a bounded two-seed same-dose continuation:
first+262,144 physical hands per arm/seed, then cumulative+1,048,576 relative to
the present full endpoints if mechanical and preregistered safety checks permit.
This takes the unchanged main learner to roughly2.1M representation-training
hands rather than abandoning it at1M. The lower-rate full learner is the sole
major comparator; preserve the current heads endpoints without training a third
family. Keep all other settings, including reference KL, league, batch size and
execution contract, fixed. Report realized optimizer steps and policy KL rather
than assume half LR means half realized update dose. Assess new paired-deck
anchor/seat gains before larger scale or external development spend.

Retain earlier internal/external ranking misalignment and all older full-network,
sampled and low-temperature negatives. Training samples at T1 while this study
evaluates greedy; that fact alone is not a new successful method. Do not repeat a
temperature scan or add Slumbot-specific rules/labels. No automatic16M, paper-scale
allocation or final Slumbot qualification follows from this pilot.
