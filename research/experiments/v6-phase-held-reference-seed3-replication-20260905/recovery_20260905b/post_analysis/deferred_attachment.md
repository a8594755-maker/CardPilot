# Deferred second-recovery final analysis

Executed once at 2026-09-05 11:19:18 UTC from `C:\Users\a8594\CardPilot`:

```powershell
python -B research/experiments/v6-phase-held-reference-seed3-replication-20260905/recovery_20260905b/post_analysis/qualify_final_analysis.py
```

The immutable `qualification.json` records 28 passing synthetic/accounting/process
guard tests, no failures/errors/skips, exact nested commands, XML and source hashes.
The earlier32-test qualification was hash-verified and reused, not rerun. The real
readiness call found the exact controller live and did not read/reaggregate outcomes.
No training hands, evaluation hands or model inference calls were added.

Only after the current recovery controller and every tracked descendant exit:

1. Inspect the authoritative terminal phase and verify qualification source hashes.
   Missing/error/below-target results require scoped review, not automatic restart.
2. For complete or preregistered-collapse evidence, log and execute the new
   `analyze_twice_recovered.py` with an unused output, normally
   `recovery_20260905b/post_terminal_report.json`. This is the relevant final report;
   neither the original normal-completion reporter nor the first-recovery
   one-interruption reporter applies unchanged. Preserve those earlier sources/tests.
3. Attach this directory's Python sources, qualification, XML and actual final report
   and command to the SAME Seed3 experiment record. Attach any still-deferred
   original17-test and first-recovery32-test analysis qualifications. Their paths:
   `../post_analysis` under the original experiment, and
   `recovery_20260905/post_analysis`, respectively.
4. Add any missing actual nested I/O/preflight commands from preserved qualification
   artifacts. Do not attach the self-mutating experiment.json as a hashed artifact.
5. Finish only after actual raw evidence and state checks pass. The original static
   failed attempt, completed static remainder, failed moving attempt with recoverable
   candidate, and all new remainder/stage2 attempts are distinct. Include each actual
   attempt wall time once. The first4,292 unretained executions are separate; the
   recovered5,256 are already within retained hands and must not be added again.
   Unknown additional worker tails remain null for both failures.
6. Audit the finished record. Interpret equal-seed raw-evidence synthesis with only
   two training seeds and unconfirmed Seed1 external translation; do not imply a
   profitable policy or automatically launch formal Slumbot qualification/16M scale.

The current controller alone owns logger writes and its frozen runtime. This
post-analysis directory is not part of the live imported/frozen runtime. No final
report was generated or poker outcome inspected by this qualification.
