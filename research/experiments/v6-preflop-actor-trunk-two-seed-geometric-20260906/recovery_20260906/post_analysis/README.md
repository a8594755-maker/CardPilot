# Recovery-aware terminal review preparation

The recovery controller owns the live experiment logger and frozen sources.
This subdirectory is outside its frozen input scope; do not edit any prior source
or record while it is live. The earlier prepared root post_analysis/review.py and
curve_comparison.py do not handle this interruption and must not be executed as
if the original controller had finished normally.

recovery_chain.py supplies endpoint mapping, conflict-rejecting evidence hashes,
partial-plus-remainder accounting and optimizer clocks, bounded interrupted-job
timing, and terminal admission. It rejects either live owner before reading
endpoint outcomes. Only the source-bound, audited original connected attempt may
lack a normal termination receipt; every completed/new job requires its own
clean receipt and dead observed worker identities. The exception never invents
an exit code, unknown worker hand count or exact wall time.

The recovery-aware driver and curve entry point are now implemented and qualified:
qualification.json records41 passing tests, unchanged core/statistical AST checks,
positive and negative terminal-admission fixtures, source/XML hashes and exact
commands. This is preparatory infrastructure, not an executed final review or a
strength result. No actual current endpoint outcomes were read by qualification.

Only after BOTH original and recovery controller identities and all recorded jobs
are terminal, verify qualification.json and its input hashes, then run ONCE:

    python -B research/experiments/v6-preflop-actor-trunk-two-seed-geometric-20260906/recovery_20260906/post_analysis/review_recovered.py

The report is recovery_20260906/post_terminal_review.json. It recomputes original
raw statistics and parent comparisons, combines the interrupted and remainder
states for logical Seed1-connected-stage1 health/dose, then audits stage2 from
that exact recovered endpoint. It preserves null exit code/unknown worker tail
and bounded interrupted runtime. If another failure or safe boundary interrupts
the pipeline, do failure-specific review instead of forcing this successful-run
reviewer. Never rerun the original root reviewer to bypass these guards.

Only if TWO stages completed and the recovered report passed, run ONCE:

    python -B research/experiments/v6-preflop-actor-trunk-two-seed-geometric-20260906/recovery_20260906/post_analysis/curve_recovered.py

Output is recovery_20260906/post_analysis/curve_comparison.json. The original
qualified summarize/independent-stage math is reused; stage1 severe-stop results
must not invoke the two-stage curve. No automatic promotion, new family, enlarged
training allocation or external/final test follows these scripts.

All commands, test receipts and artifacts here are deferred for attachment to the
SAME experiment after the exact recovery owner exits. Also attach the actual
launcher command once at terminal logging:

    powershell -NoProfile -ExecutionPolicy Bypass -File research/experiments/v6-preflop-actor-trunk-two-seed-geometric-20260906/recovery_20260906/launch.ps1

No new poker hands, model selection, training recipe or final-test allocation is
authorized by this preparation. Do not rerun completed qualification suites just
to wait for training.
