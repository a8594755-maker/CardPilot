# Outcome-blind launch observations

The previous fixed80k external experiment was finished through its same-record
finisher, with a passing metadata audit and attachment audit (one record, zero
warnings). No completed poker/test/review work was rerun for that closure.

This continuation passed23 changed-binding tests and a four-actual-checkpoint
preflight, freezing905 inputs. Controller PID29304/create1788713773.5332272 was
launched once. First trainer PID32528/create1788713781.24981 was observed live.
The first initial_resume_gate.json passed actual retained model, optimizer,
replay, pool, counters and main RNG equality and a new namespace
bbc7eede7eb3487b82d581d7f5166cc5. This is statistical worker continuation, not
bitwise worker/in-flight equivalence. The first two completed metrics reached
physical11,556,569 from11,547,070, at least9,499 new physical executions.

A read-only audit command passed a PowerShell-deserialized created_at property
to --since without explicitly preserving its ISO representation. The observed
scope was348 historical records with238 warnings, NOT a one-record prelaunch
zero-warning result. The following logger update succeeded in that same shell
invocation, so the shell's final exit code did not represent the earlier audit.
No historical warning was fixed, waived or erased. A separate read-only command
with the explicit ISO bound returned one experiment and zero warnings:

    python research/experiment_log.py audit --since "2026-09-06T16:55:06+00:00" --fail-on-warning

The qualification, training schedule, seeds, commands and real resume evidence
were unaffected. No process was restarted and no poker hands were repeated.
Use explicit ISO strings or a Python subprocess argument list for future audit
bounds, and avoid combining a failing audit with a later command that hides its
exit status. This note is post-launch documentation outside the frozen runtime;
attach it and the corrected audit command after the exact controller owner exits,
without creating a competing logger writer while training is live.
