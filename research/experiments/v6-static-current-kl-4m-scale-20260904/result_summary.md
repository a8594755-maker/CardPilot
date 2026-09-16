# 4M milestone: completed measurement, uncertain strength gain

Written after all three frozen evaluations and drift cohorts completed, 2026-09-04 local time. This is a research conclusion, not a change to the preregistration or a Slumbot success claim.

## Actual work and accounting

| Seed | Final iteration | Cumulative physical executions | Cumulative transition-bearing hands | New physical executions since 2M |
|---|---:|---:|---:|---:|
| 1 | 882 | 4,197,976 | 3,632,466 | 2,100,620 |
| 2 | 890 | 4,195,304 | 3,666,391 | 2,095,518 |
| 3 | 880 | 4,194,908 | 3,624,053 | 2,095,248 |

The stage added 6,291,386 evidenced physical executions and 5,469,450 transition-bearing hands, with 1,328 new updates. It reused 9,658,592 replay rows; those are not new environment hands. The three lineages together have 12,588,188 physical executions, not one 12.6M-trained policy. Checkpoint-evidenced counts exclude any unknown crash suffix.

All 98,304 planned internal evaluation hands (24,576 complete paired-deck rows) and 60,000 offline drift states completed. There were zero new Slumbot hands. The runner reached terminal evidence-ready state at 2026-09-05T00:22:18.779001+00:00; its owner and children were subsequently confirmed absent in the OS. Experiment wall time includes training, interruptions, diagnosis, evaluation and analysis; it is not a trainer-throughput estimate.

## Strength evidence

Paired 4M-minus-2M changes against the unchanged four anchors, in bb/100:

| Frozen policies | Change | Paired 95% CI |
|---|---:|---:|
| Seed1 | +2.08997 | [-2.53295, +6.71288] |
| Seed2 | +3.69568 | [-3.37279, +10.76415] |
| Seed3 | -1.99805 | [-7.62051, +3.62442] |
| All three | +1.26253 | [-2.11955, +4.64462] |
| Fixed incident-unaffected Seed1/Seed3 subset | +0.04596 | [-3.59355, +3.68547] |

These intervals describe evaluation uncertainty conditional on these frozen policies and selected anchors, not a training-population confidence interval. Seed1 improves in point estimate against three anchors and both seats; Seed2 against all four and both seats. Seed3 has negative point estimates against all four anchors and one seat. None of the seed-level pooled intervals excludes zero. The incident-unaffected subset is essentially flat and uncertain, so the pooled positive direction is not clean replicated evidence for more training.

The Standard10-to-4M drift cohorts have mean TV 0.009416 / 0.009305 / 0.010373 and greedy disagreement 0.865% / 0.830% / 1.230% for seeds 1/2/3. The registered drift bounds and changed-parameter scopes pass. This establishes limited behavioral change on these states, not increased poker strength or universal capability preservation.

## Deviations retained, not erased

Seed2 has 575,831 evidenced repeated deterministic deal exposures during this stage. Its 2,095,518 executed hands cover 1,519,687 unique deterministic deal identities. Its execution count is valid as work performed but must not be called wholly fresh training coverage. Available optimizer/replay and assignment restoration does not imply bitwise worker RNG or rollout continuity. The outcome-blind amendment fixed the Seed1/Seed3 sensitivity subset before evaluation; that subset does not replace the intended three-seed replication.

The original training_audit.json remains unchanged and failed. Its pool-history completeness check incorrectly demanded all new candidates in a capped final history. The separate archive-window proof reconstructs all 664 new candidates through 27 checkpoint windows and 1,328 suffix assignments, including exact metadata, scores and surviving selections. The proof and independent inherited-bridge/mechanics checks qualify interpretation without rewriting the failed original audit or recovering lost freshness. The old pool score formula TEXT also misstates the value-loss coefficient: the actual frozen implementation and reconstructed scores use 0.5, not the coefficient 1 in that descriptive label. No historical metadata or learned weights were rewritten.

The original guard's stopped state is preserved. A separately qualified successor completed the original evaluation contracts. Raw evidence SHA checks, per-anchor deck uniqueness, prior-corpus disjointness, checkpoint identities, evaluation seeds and cross-seed checks pass. The scoped deviation-aware report preserves original failures, uses the declared OR broad-reversal interpretation and disallows automatic promotion.

## Resource decision

Complete this experiment as a finished measurement with a training deviation, not as a successful strength promotion. Retain the static-current-KL family as viable but unproven: this curve neither establishes a gain nor causally rejects long-horizon learning. Do not automatically launch unchanged three-seed 8M training.

First complete the already-staged managed-resume production integration and fixed-parent current-recipe GPU qualification in its existing experiment. Then use a fixed, non-best-score-selected Seed1 checkpoint for a separately preregistered external development calibration before a major further allocation. This prospective external choice is made after inspecting internal outcomes; it is not a claim of earlier preregistration or a final blind benchmark. Do not select Seed2 for its highest observed internal point estimate. Combine external calibration with realized compute cost to select one main continuation and at most one substantive control.

Authoritative numeric evidence: aggregate.json, deviation_aware_report.json, final_seed2_overlap.json, pool_history_window_audit.json, frozen_allseed_mechanics_inherited_bridge.json, the three terminal manifests/checkpoints and raw eval_seed*/common_deck_pairs.jsonl.gz files. The experiment logger retains exact execution commands and artifact hashes. Existing negative external evidence from the earlier integrated recipe is relevant caution but is not a measurement of these static-current-KL checkpoints.

## Explicit prose correction after GPU qualification

The first version mistakenly called the source drift comparison "2M-to-4M". The actual frozen drift command uses Standard10 as parent; the paragraph above now says "Standard10-to-4M". All numerical results, raw evidence, gates and decisions are unchanged. Before this correction the exact original summary (SHA256689c921068f2e40072e95bbd6c5887f61a55351980bdba46fd9b8b3b49eb9ebb) and completed experiment record (SHA256a19a998cfaf0c285e846e6df971bb2daaa1a2a48f14793282ffcd2c8ced8feac) were preserved as qualified_4m_result_summary.md and qualified_4m_experiment.json in the managed-resume experiment. The latter preserves the GPU handoff's original record input; GPU execution was already terminal before this append-only explanatory amendment.
