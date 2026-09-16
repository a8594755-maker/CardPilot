# Descriptive decomposition of the completed corrected-v6 source baseline

This is posthoc analysis of the already finished fixed20k cohort, not another
performance test. Source aggregate(-82.8164bb/100) is already known. No new
training, policy queries, simulated deals, API requests or evaluation hands.
Reused raw records=20000; excluded16probe hands remain excluded. The active
physical1m trainer, runtime snapshots, seeds and matrix plan are unchanged.

Before reading group outcomes, fix exhaustive partitions: hero seat, terminal
kind(hero fold/opponent fold/showdown), final board-card count, seat x terminal
kind, and absolute payoff chip bands0,1..100,101..500,501..2000,2001..5000,
5001..10000,10001..20000. For each report count, total chips, conditional mean
bb/100 and additive contribution to the full cohort bb/100. Each partition must
sum exactly to original total hands/chips. Report each of8session contributions.
Terminal categories and payoff bands are endogenous: no causal interpretation,
conditional significance tests, strategy ranking or optimal-action claim.

Describe saved model decisions by seat/street: actual nine-slot counts, sum of
logged probabilities, selected calls/checks/folds/raises, and sample entropy.
No model replay is needed here: the baseline already has a full model/journal
audit. Validate hashes against that audit and independent reviewed report, and
verify raw accounting again. Counts are decision-weighted, not independent hands.

Purpose: identify which general policy/value diagnostics merit investigation
AFTER the fixed learning curve. Do not fit on Slumbot data, invent opponent-
specific rules or use posthoc subsets as qualification evidence. Snapshot this
analysis source and all input hashes, protect active76source/copy pairs, run
arithmetic/schema tests, log exact commands, and finish a separate zero-new-hand
record. Preserve all completed baseline and active training artifacts.
