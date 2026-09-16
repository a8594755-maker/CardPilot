# Deferred outcome-gated review preparation

Prepared during the live fixed80k external evaluation. These files are not
imported by the runner or clients; no frozen execution inputs were modified.
The controller remains the only experiment-log writer until exact owner exit.

Actual completed command:

`python -B research/experiments/v6-phase-reference-seed3-greedy-paired-fresh80k-20260905/post_analysis/qualify_review.py`

The exclusive `qualification.json` records exact outer `sys.orig_argv`, exact
nested pytest argv, elapsed time, stdout/stderr, source hashes and XML hash.
All26 tests passed, with zero network requests, model queries or new hands.
Readiness correctly rejected execution while the exact controller remained live;
no current rewards were inspected. Do not rerun this exclusive qualification.

After the controller AND all37 tracked children are terminal with successful
receipts, execute once:

`python -B research/experiments/v6-phase-reference-seed3-greedy-paired-fresh80k-20260905/post_analysis/review_completed.py --out research/experiments/v6-phase-reference-seed3-greedy-paired-fresh80k-20260905/post_terminal_review.json`

The reviewer fails closed before outcome access unless the fixed cohort is
complete. It checks frozen inputs, reconstructs current raw statistics through
two parsers and integer moments, rechecks every raw/journal digest against full
decision replay, verifies current cross-arm/prior tokens and independence audits,
and reaggregates the unchanged Seed1 evidence for the preregistered equal-weight
two-lineage synthesis. It issues no poker requests or new model inference.

Combined intervals concern evaluation sampling conditional on these two trained
lineages, not a training-seed population. Prior Seed1 results informed allocation,
so adjusted combined intervals remain exploratory sensitivity, not fresh
confirmatory guarantees. Four distinct models never become one policy's formal
100k cohort. Zero empirical variance is flagged and must not justify promotion.

After sole-owner exit, attach sources, qualification and the new report and append
the actual commands via `experiment_log.py`. Independently inspect receipts and
results, record the research decision, then finish this SAME experiment. Never
restart sessions or discard extreme waves. A successful evidence report is not a
winning-model claim and does not automatically authorize16M or a final test.
