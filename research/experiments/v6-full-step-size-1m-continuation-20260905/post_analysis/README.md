# Deferred post-analysis, not live-controller dependencies

Prepared while the unchanged registered training controller is running. This
directory is outside its top-level Python dependency snapshot. Do not edit any
frozen dependency or update its experiment logger concurrently.

The terminal reviewer must wait for the exact owner and every recorded job/worker
identity to be terminal. It verifies both full-network LR arms, actual parent
optimizer clocks and initial state, trace prefixes, physical/transition/replay
accounting, raw paired-deck rewards and CIs, both-seat/anchor safety rules, corpus
disjointness, stage boundaries and costs. It never launches poker hands or
declares strength. Pure helpers may later review already-closed stages separately;
main refuses a live owner.

Deferred exact command:

    python -B -m pytest -q -p no:cacheprovider research/experiments/v6-full-step-size-1m-continuation-20260905/post_analysis/test_review.py --junitxml=research/experiments/v6-full-step-size-1m-continuation-20260905/post_analysis/review_tests.xml

After terminal completion, and only after inspecting the boundary:

    python -B research/experiments/v6-full-step-size-1m-continuation-20260905/post_analysis/review.py

The researcher must append these actual commands, sources/tests/results and hashes
to the SAME experiment record through experiment_log.py after its owner exits.
No separate algorithmic experiment is created for this review preparation.

After both cells of one seed/stage are verified CLOSED, their descriptive
realized-dose comparison may run while other cells continue. This does not alter
allocation and is not an early strength gate. First such exact command:

    python -B research/experiments/v6-full-step-size-1m-continuation-20260905/post_analysis/closed_seed_dose.py --seed 1 --stage 1

Attach its source, actual commands and generated JSON to the same record when the
owner has exited. Until then do not create a competing logger writer.

The two-stage LR curve analysis reuses the prior qualified independent-deck
variance calculation. It reports half-minus-full changes, each endpoint's change
relative to its fixed parent, and absolute anchor changes, retaining both seeds,
seats and all anchors. These are exploratory nominal conditional comparisons,
not causal or seed-population evidence. It requires the complete terminal review;
no curve output is produced during live evaluation. Deferred commands:

    python -B -m pytest -q -p no:cacheprovider research/experiments/v6-full-step-size-1m-continuation-20260905/post_analysis/test_review.py research/experiments/v6-full-step-size-1m-continuation-20260905/post_analysis/test_curve_comparison.py --junitxml=research/experiments/v6-full-step-size-1m-continuation-20260905/post_analysis/curve_tests.xml

    python -B research/experiments/v6-full-step-size-1m-continuation-20260905/post_analysis/curve_comparison.py

Register only actually executed commands and outputs after owner exit. Keep the
original review_tests.xml; curve_tests.xml is a separate combined-test artifact.

The direct-gradient route observation is a CPU-only connectivity check on the two
already-closed stage1 full-rate checkpoints, not a new training method or an
allocation decision. It tests synthetic preflop/postflop routing and scalar-value
gradients without PPO updates or poker hands. Do not describe trainable scope as
proof that every objective can update the shared representation. Exact command:

    python -B research/experiments/v6-full-step-size-1m-continuation-20260905/post_analysis/gradient_routes.py

Register the actual command, source and gradient_route_observation.json after the
owner exits. Source-level detach is an existing contract, not automatically a bug;
the observation alone neither authorizes changing it mid-run nor proves it causes
any poker-strength result.

After stage1_analysis.json exists, the closed-stage reviewer can independently
recompute all four paired evaluations, reconstruct registered random.Random deck
streams, check the inventoried historical corpus and verify all eight stage1 jobs
are terminal. It does not re-inspect optimizer/replay tensors or change the live
controller's allocation. Run once, then attach source/command/output after owner
exit:

    python -B research/experiments/v6-full-step-size-1m-continuation-20260905/post_analysis/stage1_milestone.py

Terminal-only finishing preparation (not executed against the logger while live):

    python -B -m pytest -q -p no:cacheprovider research/experiments/v6-full-step-size-1m-continuation-20260905/post_analysis/test_review.py research/experiments/v6-full-step-size-1m-continuation-20260905/post_analysis/test_curve_comparison.py research/experiments/v6-full-step-size-1m-continuation-20260905/post_analysis/test_finish_record.py --junitxml=research/experiments/v6-full-step-size-1m-continuation-20260905/post_analysis/finish_preparation_tests.xml

    python -B research/experiments/v6-full-step-size-1m-continuation-20260905/post_analysis/finish_record.py --check-ready

After the complete two-stage terminal review and curve exist, write a substantive
research_decision.json bound to their SHA256 values and result_summary.md. Only
then run finish_record.py without --check-ready. It checks original owner and all
recorded job/worker identities, preserved evidence hashes, no external hand credit
and an explicit goal_achieved=false. It retrieves actual commands from outputs,
batches metadata additions within Windows argv limits, finishes this SAME record
and runs a scoped logger audit. It never selects a research direction itself.
Do not run it to close an incomplete/failed execution; such boundaries require a
separate failure/recovery review and preserve all existing evidence.
