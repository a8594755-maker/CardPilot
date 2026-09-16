# No replicated learning-rate winner; calibrate external performance before more training

The complete fixed-dose study and independent terminal review passed. This is
completion of the registered experiment, not achievement of the long Slumbot goal.
Original controller PID50836 and every recorded job/worker identity are terminal.

## Execution and evidence

- New physical environment executions: **4,207,129**, summed across four branches.
- Transition-bearing hands: **3,713,245**; no-decision hands: **491,903**;
  residual worker tail: **1,981**. These partitions sum to the physical count.
- Replay rows: **6,408,656**, not additional environment hands.
- Largest individual endpoint counter: **10,498,234**, not the sum of branches.
  Each full-trainable lineage now has approximately2.1M physical hands under that
  scope. Earlier approximately8.4M heads-only hands are not relabeled full training.
- Internal evaluation executions: **262,144**, on **32,768 unique common decks**.
  Intentional shared decks and repeated-parent payouts within seed/stage are not
  independent extra samples. All8 raw files were reaggregated and SHA-bound.
- The inventoried prior corpus contained641,026 raw rows; none overlapped the new
  evaluation decks. This is not a claim to have inventoried every historical corpus.
- Eight distinct new managed training namespaces;112 recorded child identities
  checked terminal across16 jobs. Model, optimizer, replay, counters, main RNG,
  prefixes and input hashes passed the terminal review. Per-parameter Adam clocks
  advanced without resets or new state IDs. Worker restarts remain explicitly
  statistical continuation, not bitwise rollout-RNG replay.
- Slumbot development hands: **0**. Final qualification hands: **0**.

Review SHA256: `70c40a9cdc68b1c1052e8b1d938c9ee41103b57450c313e289f6a5014a69eeab`.
Curve SHA256: `08d29fe83213ec0518b748e84d8af1e13598ec5a59370e69dead4ec6a32d0ade`.
The independent review took90.266 seconds and required the actual owner to exit.

## Strength and learning curves

All intervals below are exploratory nominal conditional paired-deck95% intervals,
in bb/100. They are not training-seed population intervals, multiplicity-adjusted
confirmatory claims or Slumbot results. Parent is each seed's SAME original
full-network endpoint from the preceding representation pilot, not its stage1
continuation checkpoint. Both arms have full trainable parameter scope.

| Final contrast | Seed1 | Seed3 |
|---|---|---|
| Original LR minus parent | -2.3225 [-21.2414,16.5964] | -9.5087 [-26.0964,7.0790] |
| Half LR minus parent | +6.2853 [-8.7477,21.3183] | -20.4172 [-38.1250,-2.7095] |
| Half LR minus original LR | +8.6078 [-10.2918,27.5074] | -10.9086 [-28.8387,7.0216] |
| Original LR absolute vs anchors | -5.5719 [-23.0057,11.8619] | +5.0823 [-10.6670,20.8316] |
| Half LR absolute vs anchors | +3.0359 [-13.2319,19.3037] | -5.8263 [-20.6946,9.0420] |

| Stage2-minus-stage1 change in parent-relative score | Seed1 | Seed3 |
|---|---|---|
| Original LR | +0.4403 [-26.7535,27.6341] | -19.8979 [-42.5222,2.7263] |
| Half LR | +12.0563 [-10.9174,35.0299] | -43.6969 [-67.0911,-20.3027] |

The initially encouraging Seed3 half-rate result (+23.2797 versus parent atstage1)
did not survive further training. Its later decline appears on all four anchors
and both seats as point estimates; the nominal change intervals exclude zero for
Standard10, legacy_iter16 and seat0. This is a material adverse within-lineage
curve, not merely failure to exceed0 on a small Slumbot sample. Seed1 does not
replicate that decline, so do not turn it into a universal causal claim.

Final half-rate parent-relative seat deltas were+5.3423/+7.2283 for Seed1, both
intervals crossing zero, and-33.2319/-7.6025 for Seed3; only Seed3 seat0 excludes
zero. Final Standard10 parent deltas were-3.1250/-24.7803 for the original rate
and+7.7393/-21.0205 for half rate across Seed1/Seed3, all nominal intervals crossing
zero. Stable preservation across seeds/opponents/seats has not been established.
Absolute seat returns are not themselves a regression test; use relative changes.

The registered severe broad-collapse gate is false in both seeds and stages.
That was a safety threshold for the fixed allocation, not a successful-learning
threshold. The evaluator's older generic promote/reject labels are NOT this
study's preregistered allocation rule.

## Realized update dose and cost

| Stage2 observation | S1 original | S1 half | S3 original | S3 half |
|---|---:|---:|---:|---:|
| Physical hands added |787438|787269|787653|786633|
| Per-parameter Adam steps added (all86) |638|678|614|670|
| PPO KL early-stop iterations |82/165|6/170|91/169|10/168|
| Mean approximate PPO KL |0.008129|0.004138|0.009212|0.004477|
| Mean current-to-reference KL |0.059219|0.058066|0.053351|0.042932|
| Training subprocess seconds |1455.085|2046.234|2495.492|2637.665|

Actual Adam LRs remained approximately1e-4 and5e-5; the CLI's nominal3e-4 was not
the restored LR. Lower PPO KL/fewer early stops are real mechanism observations,
not evidence of improved poker. Half rate received6.3%/9.1% more actual optimizer
steps in Seed1/Seed3; nominal LR alone is not the realized update dose.

Training subprocess time:12,379.552 seconds (206.326minutes), approximately339.845
physical hands/second across all8 cells. Evaluation subprocess time:7,664.695
seconds (127.745minutes); stage1 alone85.672minutes andstage2 42.073minutes.
All job time:20,044.247 seconds; controller time:20,823.198 seconds. The large
between-job throughput variation is not an isolated hardware or LR benchmark.
Do not attribute it to a specific application, batching cost or causal LR effect
without a controlled profile. No other applications were closed or altered.

The zero-hand gradient-route observation confirms an existing contract:
preflop actor logits and critic_v2 values use detached shared features. All86
trainable tensors does not mean all streets/losses train the representation.
Postflop updates may indirectly alter preflop outputs; the preflop head itself
still learns. The probe used synthetic inputs, not poker causal counterfactuals;
it neither proves why the curve declined nor justifies silently removing detach.

## Research decision

No LR winner, automatic larger training, paper-scale allocation or final100k
qualification is justified by this study. Do not select the lucky Seed3 stage1
checkpoint or ignore its adverse later result. Preserve every checkpoint and row.
This is insufficient/adverse internal scaling evidence at the tested regimen,
not proof that full-representation learning can never succeed with more scale or
a different valid training design.

The next highest-information allocation is one prospectively fixed **80k external
development calibration**,20k fresh Slumbot hands for EACH of the four unchanged
final checkpoints below, regardless of running scores. Current full-representation
endpoints have not received external calibration, and earlier internal/external
rankings disagreed. Direct measurement is preferable to automatically allocating
more millions of training hands or declaring the family dead from this proxy.
The budget primarily detects large failures and calibrates direction;20k/policy
does not promise power for small LR differences. Freeze the complete execution
contract/schedule/statistics before requests and retain session/seat sensitivity.
Do not pool four policies into one100k claim or recycle development hands as blind
qualification. Reuse qualified journaled execution/audits; no new training, action
patches or Slumbot-label supervision in that experiment.

| Frozen final policy | Checkpoint SHA256 |
|---|---|
| Seed1 original LR |8904f3b2e25baec5bc0bcb6556502c19b3fb213efdc9a32b16d55eee1284a3ef|
| Seed1 half LR |669b331d23264136dd75bd923ed3e2fa0e2dd73e4e20485400cd795e59f7653f|
| Seed3 original LR |f2249b0d19937ddadfc29fe5ba10cd7f07909d638dc0edeca89fae05b6f498e2|
| Seed3 half LR |f64928d15ecc8620046615774ac9c74fc76d0b8a447f441bd07409d3c41c755a|

After external evidence review, decide between continued scale and a bounded
single-change general training control. Preflop actor-to-body connectivity is a
candidate mechanism, not an adopted fix. No new external experiment has been
launched merely by writing this decision. Deferred post-analysis sources, actual
commands and artifacts are attached by finish_record.py only after owner exit.
