# Stage1 complete: heterogeneous improvement, no LR winner selected

Independent review completed2026-09-06T00:43:13UTC. Source artifact:
stage1_independent_review.json SHA256
eec8ade92d66e0f31113e32ab3fad2a0962d672e02a6d1ec610003479e1e90e6.
Attach this note and the actually executed reviewer command/source/output to the
same experiment record after its live controller exits. This is a milestone,
not experiment completion or achievement of the long Slumbot goal.

## What was completed and independently checked

All four training cells and all four evaluation jobs are cleanly terminal.
The131072 evaluation executions represent16384 distinct common decks, not131072
independent samples. Both LR arms share decks and repeated-parent payouts within
seed. The reviewer regenerated every registered deck from random.Random seeds,
recomputed paired returns and CIs, and found no overlap with641026 rows in the
inventoried prior evaluation corpus. This is not a claim of an inventory covering
every historical poker corpus. Model/source/raw hashes and recorded process
identities were checked; full optimizer/replay/initial-state tensor reinspection
remains part of the later terminal review.

Controller-verified new physical training hands total1058136 across four branches:
940617 transition-bearing hands,116382 no-decision hands and1137 residual worker
tail hands. Replay1638740 rows is not additional environment-hand credit. No
Slumbot or final-qualification hands were generated.

## Strength results

Nominal conditional paired-deck95% intervals in bb/100; no seed-population or
multiplicity-adjusted superiority claim. Parent is each seed's SAME frozen
full-network endpoint from the previous representation pilot.

| Contrast | Seed1 | Seed3 |
|---|---|---|
| Original LR minus parent | -2.763 [-22.297,16.771] | +10.389 [-4.996,25.774] |
| Half LR minus parent | -5.771 [-23.143,11.601] | +23.280 [7.992,38.568] |
| Half LR minus original LR | -3.008 [-18.926,12.910] | +12.890 [-3.262,29.043] |

Seed3 half-rate has positive parent-relative point estimates on all four anchors
and both seats. Its seat0 gain is+29.683 [6.311,53.055], seat1+16.876
[-5.191,38.944]. Its Standard10 parent-relative gain is+46.558 [16.918,76.197].
Its absolute pooled internal score is+18.485 [4.412,32.559], but this is NOT a
Slumbot result. Half-versus-full Seed3 Standard10 gain is+29.932 [6.025,53.838].
These local positives must not be selected while ignoring the other seed/buckets.

Seed1 does not reproduce half-rate improvement: half-versus-full point estimates
are negative on both seats and three of four anchors, with all those intervals
crossing zero. Both seeds' pooled LR contrasts cross zero. Reduced PPO update KL
and fewer early stops therefore have not yet established a replicated poker
advantage. The evidence supports neither declaring half-rate the winner nor
mechanistically rejecting it after this short continuation.

## Decision and cost

The preregistered severe broad-collapse gate is false in BOTH seeds. Continue
the already registered stage2 physical dose, without changing LR, architectures,
seeds, execution mode or choosing a lucky endpoint. This is not new authority for
16M/paper-scale training or blind Slumbot qualification. The generic evaluator's
legacy public-opponent promote/decision labels are not this study's stopping rule.

Actual stage1 training subprocess time3745.076s (62.418min); evaluation subprocess
time5140.318s (85.672min). Evaluation now costs more wall time than training at this
short dose. Keep the complete preregistered evaluation; use measured costs and
the documented throughput uncertainty for later resource decisions.

The controller started Seed3 original-rate stage2 from the unchanged stage1 SHA
bb7841a2ea4be1cc6aa1c9d1fefa8c3f3dda960400d1b37e0d63e4f4681e1688,
physical9704488/iteration2049, targeting10489640. Its live record reports a passed
actual initial model/optimizer/replay/counter/mainRNG/pool audit at actual LR1e-4.
Fresh managed worker namespaces still mean statistical continuation, not bitwise
worker replay. No earlier hands or optimizer states were reset.

The separate gradient-route observation further limits interpretation: all86
parameter tensors are trainable, but the separate preflop head and critic_v2
detach their shared representation input. Neither this architecture observation
nor the cost observations changed the current fixed-dose allocation. Final
research choice must consider both complete stage2 seed curves, both seats,
anchor breadth, Standard10 preservation, earlier internal/external misranking
and actual resource cost.
