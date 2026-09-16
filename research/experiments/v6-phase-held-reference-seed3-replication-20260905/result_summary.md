# Seed3 same-dose replication: completed independent review

Both preregistered stages and both arms completed. Static ends at iteration1773,
8,392,377 cumulative local physical hands; phase-held moving256 ends at
iteration1769, 8,390,981 hands. These include the shared qualified4M parent, not
Standard10's unknown pretraining dose. The original and both recovery controllers,
all14 tracked jobs and their observed descendants are terminal. Both original
failed jobs remain exit1; all completed training/evaluation jobs are exit0.

The twice-recovered independent report reloaded actual parent/initial/final states,
checked optimizer/replay/main-RNG/pool/reference preservation, raw prefixes and
attempt receipts, and reaggregated both evaluation stages and both training seeds.
Its506 input hashes and cross-seed deck-disjointness checks passed. This is not a
blanket certification of older unexamined training boundaries or arbitrary RNG
independence. No completed work, checkpoint, failure evidence or outcomes were
discarded or silently rewritten. No new Slumbot hands were used in this experiment.

## Training and recovery accounting

- New retained physical training hands, both arms:8,393,542.
- Observed physical executions:8,397,834, including4,292 completed but unretained
  executions from the first interruption. Unknown extra worker tails remain null.
- Retained transition hands:7,354,144; observed transition hands:7,358,267.
- Retained no-decision hands:1,037,871; retained worker-tail hands:1,527.
- Replay rows:12,917,918, not additional environment hands.
- The second interruption's5,256 unpublished physical hands were recovered from
  the durable candidate; they are ALREADY included in retained counts, not added
  again. Original published and pending files remain unchanged.
- Six distinct attempt namespaces; main-state-exact remainder/stage2 recovery,
  but explicitly statistical rather than bitwise uninterrupted worker continuation.
- Shared parent4,194,908 counted once gives12,588,450 known retained local lineage
  union hands, not the dose of any one policy.
- Internal evaluation:131,072 physical executions, including the declared repeated
  parent controls; offline drift samples:80,000; Slumbot hands:0.
- Sum of all six actual training-attempt wall times:11,956.0912seconds
  (3.3211hours), including the failed attempts. Retained throughput:702.0306
  physical hands/second. This excludes preparation, evaluation and review;
  experiment wall time is recorded separately by the logger.

Windows publication failed twice. The failure-time file holder is unknown; the
later empty Restart Manager listing does not establish the original cause.
The second recovery used the qualified same-payload45-second I/O grace wrapper,
without changing training hyperparameters, seeds, targets or optimizer state.
Its successful completion does not prove permanent freedom from publication locks.

## Seed3 strength evidence

Internal nominal95% intervals below are paired-deck sampling intervals conditional
on these frozen endpoints and four anchors, not training-seed population intervals.

| Comparison | Stage1 (~6.294M), bb/100 [95% CI] | Stage2 (~8.39M), bb/100 [95% CI] |
|---|---:|---:|
| Static minus its original4M parent | +1.9196 [-2.6452,6.4843] | -0.1282 [-4.9947,4.7384] |
| Moving256 minus its original4M parent | +5.6305 [-4.4873,15.7483] | +1.0773 [-12.4143,14.5689] |
| Moving256 minus static | +3.7109 [-6.8216,14.2435] | +1.2054 [-12.1648,14.5757] |

At stage2, each arm has positive parent-relative point estimates on2/4 anchors,
and neither improves in both seats by point estimate. No predeclared broad-collapse
gate fired. Differences of disjoint-cohort parent-relative gains from stage1 to2
are static -2.0477 [-8.7201,4.6246] and moving -4.5532 [-21.4172,12.3107]. These
are descriptive cohort contrasts, not a direct same-deck6M-versus8M experiment.

Final Standard10-state drift remains modest for static (meanTV0.011240,
greedy disagreement1.335%) and larger for moving (0.029954,2.990%). Neither drift
nor a green integrity test is a strength metric. The copied raw-stage ci_scope text
says Seed1; the actual Seed3 parent SHA and evaluator seeds were verified, and the
independent report clarifies the label without changing frozen stage summaries.

## Equal-seed synthesis and allocation decision

The preserved Seed1 report was hash-verified and its raw data reaggregated together
with Seed3. Each seed has weight0.5. Only two training seeds are available and both
share pretrained initialization. These nominal conditional intervals are NOT
population-level reproducibility, multiplicity-adjusted claims or proof of stability.

| Parent-relative comparison | Stage1 equal-seed bb/100 [95% CI] | Stage2 equal-seed bb/100 [95% CI] |
|---|---:|---:|
| Static | +2.0911 [-1.7236,5.9059] | -3.7842 [-7.5595,-0.0089] |
| Moving256 | +9.1858 [1.9626,16.4090] | +4.2921 [-7.7595,16.3436] |
| Moving256 minus static | +7.0947 [-0.5896,14.7789] | +8.0762 [-4.0531,20.2056] |

Both seeds have negative later-slope point estimates for both arms. Equal-seed late
slopes are static -5.8753 [-11.2424,-0.5082] and moving -4.8937 [-18.9442,9.1567].
The borderline negative static endpoint interval and exploratory slopes do not
establish universal failure. The moving early signal did not become a clearly
increasing late edge, and neither method's superiority is established.

The prior, separate Seed1 external comparison remains static -19.8721 and moving
-29.4744bb/100 over40k fresh hands EACH. Its moving-minus-static difference is
-9.6023 with raw95% CI[-32.2884,13.0838]; external translation is unresolved. Do
not pool different policies into formal100k qualification, use historical
Standard10 -11.4275 as a matched current baseline, or promote a favorable tiny pilot.

Decision: complete this valid replication, preserve both families and do not
automatically allocate16M training or formal final qualification. The next priority
is a separately preregistered, fixed-budget Seed3 external matched-arm development
calibration of BOTH exact8.39M endpoints. Reuse the qualified balanced-wave fresh80k
design (40k per arm), with new sessions/evidence and no interim selection, replacement
or extension. Qualify the necessary endpoint/seed/session bindings first; do not
rerun the completed Seed1 cohort. This tests external translation across a second
training seed before a materially more expensive scale decision. It is not a
profitable-policy claim or an instruction to discard a method for insufficient scale.

## Frozen artifacts

- Static endpoint SHA256:
  36aa1d935179570e76499a0a0c1c81ccd75384b0411b9c7d9cca56c9a2c14b69.
- Moving256 endpoint SHA256:
  da6d49c60eb73ceddb6a27ff8ff10de06b3306360f61dd49e49b82cd857f4b8c.
- Independent report:`recovery_20260905b/post_terminal_report.json`, SHA256
  820862d4e74af6999260b14e0c05a6ba213edffc9d907060cf60d140f802a6d5.
- The original17-test, first-recovery32-test and second-recovery28-test post-analysis
  qualifications are preserved. The first two complete-report entry points are
  superseded for this twice-interrupted run; their qualified pure helpers were reused.

Goal achieved:false. No positive frozen-policy final blind benchmark exists yet.
