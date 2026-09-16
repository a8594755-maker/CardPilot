# Method-selection evidence ledger (in progress)

No new environment or evaluation hands. No method selected for production yet.

## Retained neural-regret evidence

Read the analysis.md files from v6-deep-cfr-iterative-pilot,
v6-deep-cfr-exploration-average-strategy-control, v6-deep-cfr-fresh-reinit-control,
v6-deep-cfr-traversal-k-scale-control, v6-deep-cfr-paper-loss-control, and
v6-deep-cfr-snapshot-vs-standard10 (all dated 20260901).

- The early iterative report called sequential player updates an algorithmic
  confound. The later exploration report explicitly retracts the claim that this
  ordering is inherently incorrect. Do not revive synchronization as a new fix.
- Fresh reinitialization improved the bounded simple-anchor mean, but did not
  establish broad learned-policy strength. K2/K4/K8 root coverage was very small;
  K8 increased samples without proportional optimizer dose. These are confounded
  small-scale allocation results, not long-run convergence tests.
- The paper-loss control used 48 total roots and 512 update steps. Its worse
  simple-anchor score is evidence against that bounded bundle, not a test of a
  full-scale faithful implementation.
- The frozen surrogate snapshot policy lost to Standard10 at -473.51 bb/100,
  paired CI [-702.72, -244.30], over 8192 hands. This is strong negative evidence
  about that particular trained policy. Do not send it to Slumbot or describe
  occasional simple-anchor wins as generalization.
- Current code confirms paper-loss control explicitly uses fresh reinit, masked
  MSE and iteration/max_iteration weights. physical_v6_cfr.py stores iteration+1,
  so the suspected zero-weight first iteration is NOT present. The legacy
  ReservoirBuffer.sample_batch uses a bounded t^1.5/(t^1.5+1) surrogate despite
  its linear-weighting docstring; the paper-loss function bypasses that sampler.
  This known distinction is not a newly discovered cause of current PPO failure.

Primary reference located: Brown et al., Deep Counterfactual Regret Minimization,
https://proceedings.mlr.press/v97/brown19b/brown19b.pdf . Before implementing a new
regret variant, verify the relevant full algorithm and estimator assumptions.

## Remaining selection work

### Fictitious-response contract checked

Read response-phase2 and average-phase2 preregistration.md and result_summary.md.
The response is a fresh 86-tensor PPO run against one frozen average, not DQN-NFSP:
new Adam, 2,099,237 actual hands, no source KL, no replay/dynamic pool. The learned
average fits three whole-hand teachers in equal thirds; 262,144 data hands and
8 supervised epochs. The implementation explicitly disclaims perfect recall and
exact best response. Do not relabel it as a complete NFSP test.

The response's +2383.68 bb/100 final-minus-initial gain against its training
average coexists with negative final-minus-initial means on four of five known
anchors. Three negative anchors retain entirely negative family25 intervals.
The average-stage positive cross-entropy fit is not a strategic improvement test.
The index's phase2 external result is -182.1045 bb/100; its raw external review
has not yet been reopened in this selection audit. This route is a concrete
warning that exploiting a training average plus accurate imitation does not
establish a generally improving policy. It does not falsify all fictitious play.

Current follow-up candidate under inspection is value/advantage learning rather
than another pool or averaging change: inspect the existing public-critic route
and prior privileged-critic negative controls before choosing a separate public
critic or alternative update objective. No causal critic diagnosis yet; finite
loss or noncancelled actor gradient alone cannot establish useful advantage SNR.

The index also contains a completed fictitious-response/average-policy lineage
with poor phase2 external results. Read its actual contract before proposing NFSP
or policy averaging as novel. Current sampled PPO versus greedy evaluation is a
real contract distinction, not yet a causal diagnosis. Do not perform another
execution sweep merely because it is easy. Select at most one major control by
expected information about scalable general learning, with explicit mechanism,
cost, resume contract and multi-seed/seat evaluation.
