# Deferred post-terminal research review

These post-analysis files are separate from the running controller's frozen input
contract. They do not modify its sources, model files, session evidence or logger.
Offline qualification uses synthetic fixtures and reads only exact owner/child
status, not current outcomes. Logging of these commands/artifacts is deferred until
the exact controller owner exits. No Slumbot requests or training are added.

Commands (run from C:\Users\a8594\CardPilot):

```powershell
python -B research/experiments/v6-full-step-size-two-seed-external-fresh80k-20260906/post_analysis/qualify_review.py
python -B research/experiments/v6-full-step-size-two-seed-external-fresh80k-20260906/post_analysis/review_completed.py --check-ready
python -B research/experiments/v6-full-step-size-two-seed-external-fresh80k-20260906/post_analysis/review_completed.py --out research/experiments/v6-full-step-size-two-seed-external-fresh80k-20260906/post_terminal_review.json
```

Run the first command once. Run the final command only after `--check-ready` is
true and no previous report exists. Actual raw/journal SHA and payout reaggregation
must agree with the controller's complete per-decision model replay audits, four
absolute scores, two within-seed contrasts, seats and cross-session checks.
The independent review requires all 41 jobs, all exact identities terminal, all
32 registered client commands and four completed waves. It is not just a check of
the saved PASS labels. Historical policies are not added to the current cohort.

After the independent review, analyze the evidence and write a research decision
bound to its SHA, then finish the same experiment record. Do not automatically
select a model, scale training, reuse these hands for final qualification, or
compute/report current rewards before the terminal gate.

Finisher preparation uses `qualify_finish.py`, then `finish_review.py` only after
the reviewed result and substantive `research_decision.json` are SHA-bound. The
decision must supply `post_terminal_review_sha256`, `result_summary_sha256`,
`goal_achieved: false`, and `summary`, `conclusion`, `decision`, `next_step` strings.
No outcome-dependent decision is filled in while execution is live.

The initial nine finisher unit tests did not cover logger CLI compatibility. A
read-only `experiment_log.py audit --help` check showed that audit uses `--since`
and `--out-json`, not `--id` and `--out`. Before any finisher execution or logger
mutation, the unexecuted finisher was corrected and an actual-parser regression
added. Original source snapshots are preserved in `finish_v1_sources`; original
`finish_qualification.json`/`finish_tests.xml` remain evidence of that limited
qualification, now superseded by `finish_qualification_v2.json`/`finish_tests_v2.xml`.
The original source hashes match the preserved snapshots, not the revised paths.
This correction changes no controller/model/session input and adds no poker hands.

## One-shot owner-exit followthrough

`terminal_followthrough.py` is a prerequisite chain bound to current owner PID11988
with create_time1788668926.081722. It waits for that exact identity to exit, admits
only the complete fixed80k/41-job terminal state, then invokes the qualified
independent raw review once. It never requests poker hands, trains, chooses policy
winners, writes the experiment logger, or restarts a failed execution. No other
caller should run `review_completed.py --out` while this followthrough is live.
Its own PID/create_time, exact command, child command/identity, final report hash
and outcome-independent status are in `followthrough_execution.json`.

The initial eight offline tests qualified a version that propagated temporary
observation errors; before launch this was strengthened to re-poll the same owner
and record transient read/permission errors without interpreting them as exit.
Additional tests cover that behavior and failed-owner refusal. Original qualified
sources are retained in `followthrough_v1_sources` with original qualification/XML;
the active binding is `followthrough_qualification_v2.json`/`followthrough_tests_v2.xml`.
This is observer-error recovery, not a retry of any Slumbot session or experiment.

After both controller and followthrough have actually exited, log the exact
commands from both generations of finisher/followthrough qualification, their
pytest argv and `followthrough_execution.json`; these records were deliberately
deferred to avoid a competing live writer. Then read the generated independent
review, write the hash-bound research decision/summary and use the qualified
finisher. Merely waiting for an owner or seeing a PASS test is not goal success.
