# Post-terminal analysis preparation

This subdirectory is not imported by the active controller or trainer. Preparation
does not modify their frozen dependencies, evaluation budget, stopping rule or
current experiment record. The main entry point refuses analysis while the exact
controller PID/creation-time identity remains live.

The script rechecks frozen inputs and logged artifact hashes, recomputes each
completed stage from its raw pairs/drift evidence, and derives stage2-minus-stage1
descriptive changes with independent-cohort variance addition. It does not claim
these are new direct paired matches or training-seed replication. Intervals are
not adjusted for multiplicity or the stage1 continuation gate; external blind
qualification remains separate.

It also distinguishes per-arm lineage counts from the union of local executed
history, counting the shared original4M parent only once in that union. Replay
rows remain separate from physical hands.

Preparation commands (record their execution/results in the same experiment after
the controller relinquishes logger ownership):

```powershell
python -m pytest -q research/experiments/v6-phase-held-reference-control-20260904/post_analysis/test_geometric_summary.py --junitxml=research/experiments/v6-phase-held-reference-control-20260904/post_analysis/tests.xml
python -m py_compile research/experiments/v6-phase-held-reference-control-20260904/post_analysis/summarize_geometric_control.py
python research/experiments/v6-phase-held-reference-control-20260904/post_analysis/summarize_geometric_control.py --check-ready
```

Run only after the controller and owned children are terminal, without rerunning
any training/evaluation:

```powershell
python research/experiments/v6-phase-held-reference-control-20260904/post_analysis/summarize_geometric_control.py --out research/experiments/v6-phase-held-reference-control-20260904/post_terminal_report.json
```

Then attach the source, tests, exact commands, report and the planning memo
`research/decision_notes/frozen-qualification-power-planning-20260905.md` to the
same experiment record before final researcher interpretation/finish. Also append
the actual launch command `python -u research/experiments/v6-phase-held-reference-control-20260904/run_control.py`:
the controller's self-reported `sys.argv` command omits interpreter `-u`; preserve
that original entry rather than silently changing historical command evidence.

No final Slumbot test, new research branch, or automatic promotion is authorized
by this postprocessor.

## Failure-handling scope clarification

The frozen controller SHA256
`a36c48530524d1caf63d7971e85c7fd0865e32b4f15356e7eda47dd5fba9231f`
does not guarantee immediate interruption of active work. In `execute`, exceptions
from the queue/log/observer block are collected around lines328-332, and exceptions
from `tick` are collected around lines339-342. The current child is drained to
natural exit or its configured runtime limit; the final evidence check then
prevents a subsequent job from launching. This is a narrower guarantee than
"stop the current training immediately on every error".

Other exceptions can escape those blocks. The outer `BaseException` handler
records/raises an error, but is not a tested universal graceful-child-shutdown
mechanism. A dead controller or an error/lock file alone is therefore insufficient
to infer that its trainer/workers have exited; inspect actual process identities.

The current28 controller tests cover command/evidence/pairing/accounting logic,
not end-to-end injected failures through every branch of this subprocess loop.
The8 post-analysis tests likewise do not establish that missing guarantee. No
such failure has been observed in the current run as of this clarification; do
not interrupt or hot-patch its frozen runtime solely to broaden these claims.

After the owner and all owned work are terminal, review and test exception scope
and drain/stop behavior before reusing this controller as a general launcher.
Include callback, logger/source-check and out-of-handler failures, explicit
child-exit evidence and a safe completed-update stop path where needed. Record
the clarification and any resulting bounded infrastructure experiment explicitly;
preserve this run's original source, evidence and actually executed behavior.

## Stage1 milestone and stage2 initial-boundary review

`review_stage1_resume.py` is a separate read-only review of closed stage1 evidence
and the immutable stage2 initial save. Unlike the full post-terminal summarizer,
it can run while stage2 training continues: it never reads the live stage2
`latest.pt`, launches model play, or changes the owner record/runtime.

```powershell
python research/experiments/v6-phase-held-reference-control-20260904/post_analysis/review_stage1_resume.py --out research/experiments/v6-phase-held-reference-control-20260904/post_analysis/stage1_resume_review.json
```

Attach this exact command, source and generated review to this same experiment
after the controller relinquishes logger ownership. The review adds zero hands
and zero offline policy queries. It reaggregates all8192 paired decks and the
preregistered AND collapse rule, and checks actual initial optimizer/replay,
reference model/counters/RNG, weights and pool state.

The first ad hoc replay comparison used ordinary scalar equality and incorrectly
reported a difference because NaN is not equal to itself. The qualified existing
comparator already handles byte-identical NaNs. Independent byte-aware comparison
confirmed28816 identical NaN scalar fields, including optional showdown-EV target
slot12 (see the frozen trainer's transition construction), with no restored-state
change. Preserve this observer-comparison correction; it was not a trainer failure
and did not justify interrupting the run.

Stage1's65536 physical evaluation executions represent49152 distinct
policy/deck/seat instances: the original parent has16384 excess intentionally
repeated executions across arms. The stage analysis's32768 parent-execution field
includes both occurrences, not32768 additional independent or excess hands. Paired
contrast uncertainty is computed from8192 deck means, not the execution total.
