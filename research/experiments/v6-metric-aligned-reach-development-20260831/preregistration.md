# Metric-aligned reach-target development fit

Parent v6-reach-target-gap-decomposition-r3-20260831 independently found
training-row epoch08 TV0.17784, no>0.03 generalization or history-truncation flag,
and a CE/hero-TV objective conflict. This is a development-set algorithm
selection record, not a confirmatory evaluation or strength test.

Reuse exact phase2 reservoir observations/IDs, reach targets and initializer.
No environment or Slumbot hands. Derive each retained row's acting seat from the
complete preserved native trace, exactly once. Fixed arms, each NEW Adam1e-4,
batch1024, clip1, eight epochs/2048 steps, identical permutation seed2026102501,
same80 trainable policy/shared and6 frozen value tensors:
1 unweighted_tv: mean per-row probability TV.
2 balanced_tv: TV weighted so each represented (hand,acting-seat) group has
  equal total reservoir weight.
3 balanced_ce: target cross-entropy with the same hand-seat weights.
No auxiliary loss, epoch rescue or extra arm.

The parent's exact8192-hand cohort is explicitly reused as a development set.
Evaluate only epoch08 of all three arms on its saved reach targets. Primary
development statistic is per-hand hero meanTV; select the lowest mean, fixed
tie order balanced_tv, unweighted_tv, balanced_ce. A selection is promising iff
it improves parent epoch08 heroTV by at least0.01 and selected mean<=0.19.
This is outcome-dependent development selection, so its CI is descriptive and
cannot admit strength testing. Preserve all three endpoints.

If promising, separately preregister an untouched new native cohort and evaluate
only this frozen selected endpoint versus the frozen parent endpoint. If not,
prioritize full-history/sequence representation before further loss tuning.
Account optimizer rows per arm, model queries, reused hands and0new hands.

