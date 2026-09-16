# Deferred post-terminal review preparation

Prepared while the external controller is live. This directory is not imported by
the live runner or clients and does not modify frozen evaluation inputs. It adds
zero poker hands or model queries and does not inspect current rewards.

Actual offline commands completed:

`python -B -m pytest -q research/experiments/v6-phase-reference-greedy-paired-fresh80k-20260905/post_analysis/test_review_completed.py --junitxml=research/experiments/v6-phase-reference-greedy-paired-fresh80k-20260905/post_analysis/tests.xml`

Six tests passed. The integer-moment check uses exact integer sum/sum-of-squares;
historical comparisons use the fixed original4M and same-contract Standard10 raw
cohorts with their prior full-audit raw SHA and both samples' uncertainty.

`python -B research/experiments/v6-phase-reference-greedy-paired-fresh80k-20260905/post_analysis/review_completed.py --check-ready`

Readiness correctly returned false because exact controller PID53100, creation
time1788593822.190148, remained live. No outcomes were read.

After authoritative controller and child termination, run the same reviewer with
`--out` pointing to a NEW `post_terminal_review.json` in the experiment root.
Do not overwrite an existing report or interpret the helper's passed flag as a
winning-policy or final-goal claim. Inspect its underlying full audits and raw
statistics and make the resource decision separately.

The controller remains sole experiment-log writer while live. After it exits,
append these actual commands and attach source, tests, XML and resulting report
through experiment_log.py before finishing the SAME external record. Do not rerun
completed poker sessions. The runner's final artifact collection also sees this
directory, but does not execute this review or finish the experiment.
