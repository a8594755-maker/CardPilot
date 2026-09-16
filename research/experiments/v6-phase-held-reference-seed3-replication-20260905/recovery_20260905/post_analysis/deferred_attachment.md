# Deferred same-record post-analysis attachment

This directory is outside the live recovery controller's frozen runtime. Its
qualification adds zero training hands, evaluation hands and model inference
calls. Do not change the live controller or run a competing experiment-log writer.

Executed once on 2026-09-05 at 09:58:24 UTC from `C:\Users\a8594\CardPilot`:

```powershell
python -B research/experiments/v6-phase-held-reference-seed3-replication-20260905/recovery_20260905/post_analysis/qualify_recovered_analysis.py
```

`qualification.json` records the exact nested commands, stdout, stderr, source
SHA256, test XML and 2.425-second wall time. All 32 tests passed with zero skips.
The real readiness check confirmed the recovery controller was live and did not
read/reaggregate outcome evidence. These are accounting and process-guard tests,
not new poker-strength evidence or a substitute for actual terminal reaggregation.

After the exact recovery owner and every tracked child are terminal:

1. Inspect the authoritative recovery phase. A missing terminal result, runtime
   boundary or error requires scoped review, not an automatic restart or finish.
2. Verify this qualification's artifact hashes and its actual test/command results.
   Preserve qualified source and all existing evidence; version any needed repair.
3. For complete or preregistered-collapse evidence only, run the new analyzer with
   an unused output path, normally `recovery_20260905/post_terminal_report.json`.
   It reconstructs the interrupted prefix, completed attempts and raw evaluation,
   then combines Seed1 and Seed3 with equal seed weights. The older normal-completion
   Seed3 reporter must not be used as this recovered experiment's final report.
4. Attach this directory's sources, qualification and XML, the final actual report
   and its actual command to the SAME Seed3 experiment record. Also attach any
   still-deferred original `post_analysis` qualification (17 tests) and missing
   nested I/O/preflight exact commands already preserved in their qualification
   artifacts. Do not attach a self-mutating `experiment.json` as an artifact.
5. Finish only after the actual terminal gates pass, with retained hands separate
   from the observed 4,292 uncheckpointed executions and unknown additional tails.
   Audit the finished record. Neither a passing audit nor an internal comparison
   establishes a profitable policy or authorizes an automatic formal Slumbot test.

No final report has been executed by this qualification. No new research family
or new Slumbot cohort was launched.
