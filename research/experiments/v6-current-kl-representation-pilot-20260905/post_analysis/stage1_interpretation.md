# Stage1 milestone interpretation (not a protocol amendment)

Written after stage1 closed, while the original controller was executing the
preregistered Seed3 full stage2. No live source, checkpoint, input contract,
training configuration, evaluation schedule or experiment logger was changed.

Independent closed-stage reconstruction:
`python -B research/experiments/v6-current-kl-representation-pilot-20260905/post_analysis/stage1_milestone.py`

The resulting `stage1_milestone.json` SHA256 is
`471b8bd0f4502670300d39717d34bbbde81e33d7d41a2cfd2485472e5413b5f9`.
It verifies terminal identities, input/raw hashes, every paired payout and
full/heads deck and repeated-parent joins, and independently reproduces the
controller's means, intervals and preregistered broad-collapse Boolean.
Prior-corpus disjointness remains the controller's stage1 check until the already
prepared terminal review independently scans that inventory. This milestone
generated zero poker hands or updated weights. Attach it and its exact command
when the current controller relinquishes sole logger ownership.

## Strength evidence

Full minus heads, conditional paired-deck nominal 95% intervals, bb/100:

| Fixed training seed | Pooled difference | 95% interval |
|---|---:|---:|
| 1 | -0.206665 | [-13.347414, 12.934084] |
| 3 | -20.834839 | [-36.124942, -5.544736] |

Seed3's four anchor point differences are all negative; its seat0 interval is
negative, while seat1 crosses zero. These are negative signals, not a successful
strength gate. The severe preregistered broad-collapse condition is nevertheless
false in both seeds: it required at least three anchor upper bounds below -25
AND both seat upper bounds below zero. Stage2 follows that prior rule; continuing
is not retrospective evidence of improvement. Do not pool the two fixed training
seeds into a claim about the population of training seeds, and do not treat these
internal results as a Slumbot or final-qualification result.

## Actual update dose and a bounded hypothesis

| Run | Completed iterations | KL-stop iterations | Adam step increments per trained parameter |
|---|---:|---:|---:|
| Seed1 heads | 57 | 0 | 228 |
| Seed1 full | 55 | 37 | 196 |
| Seed3 heads | 55 | 0 | 220 |
| Seed3 full | 56 | 35 | 188 |

Both full arms updated all86 parameter tensors, including76 representation
states newly initialized by Adam. Both heads arms retained10 optimizer states.
Recorded epoch counts are not optimizer-step counts. Full-arm mean approximate
PPO KL was about0.0128/0.0132; heads means about0.000059/0.000072. Static-reference
mean KL was about0.0367 for full versus0.0010/0.0011 for heads. These are
descriptive realized-dose differences, not measures of poker strength or a causal
attribution of the negative results. Full training was not inert or starved of
all updates. Same nominal Adam LR across scopes did not imply the same policy
movement. A representation-specific step-size control is a possible subsequent
hypothesis only if terminal learning curves warrant it; it is not started here.
The older different-contract full-network negative remains relevant and is not
erased by this possibility. No Slumbot action labels or hand-specific patches.

## Compute and next decision

Stage1 executed1,056,429 new physical training hands and919,633 transition-bearing
hands, summed across four branches, not one policy's cumulative counter.
Training subprocess time was1,931.93s (32.20min), about547 physical hands/s.
Internal evaluation took2,321.39s (38.69min) for131,072 actual executions with
16,384 unique matched decks. Intentional repeated parent executions are not
independent extra statistical samples. Audit wall time for this reconstruction
was10.75s, concurrent with training.

Finish the unchanged fixed stage2 dose (1,048,576 cumulative additional physical
hands per arm/seed relative to the original8M parents), then examine both seeds'
slopes, anchor/seat breadth, Standard10 capability and realized update dose.
Do not auto-extend beyond stage2, select a lucky checkpoint, or start final blind
Slumbot qualification on the basis of this internal pilot. The known earlier
internal/external ranking misalignment constrains any subsequent scale decision.
