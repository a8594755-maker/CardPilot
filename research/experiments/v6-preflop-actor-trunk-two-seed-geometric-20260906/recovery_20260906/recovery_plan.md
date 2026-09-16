# Same-experiment continuation after reviewed missing-process interruption

The interruption audit passed with checkpoint SHA
9bc206c103b925ce7e77b62eadd0cc92575e1f35d6d7bfe59cee2fa9c274478b,
iteration2217, physical10507221 and transition9140101. All2217 metric rows and
2218 assignment rows are complete; pending2218 must be retained. There are zero
logged completed-but-uncheckpointed hands, but the in-flight tail is unknown.
No consumed-log trimming or model/metadata migration is necessary.

Use the original interrupted latest.pt directly as immutable resume input. Copy
its complete raw metric/assignment prefixes into a new output directory
recovery_20260906/seed1_connected_stage1_remainder. Retain all original seed,
optimizer, replay, reference, actor-route, pool, batch, worker and target settings.
The cumulative stage1 target stays10760378, leaving253157 checkpointed physical
hands plus complete-update overshoot. Keep the unchanged7200-second process
safety guard for this reviewed attempt; report earlier attempt runtime separately
as incompletely observed, never as zero or as part of a fake uninterrupted run.

The logical Seed1-connected-stage1 endpoint resolves to the remainder directory;
the old interrupted directory remains immutable evidence. Stage2 resumes that
endpoint, not the old interrupted checkpoint or the original unstepped copy.
The completed Seed1-detached-stage1 cell is loaded as a completed result and is
never launched again. Then run Seed3-connected-stage1 and Seed3-detached-stage1,
the unchanged stage1 internal evaluation/gate, and only if admitted the original
stage2 order. All other paths, anchors, evaluation seeds, cumulative targets and
gate logic remain the preregistered ones.

One new controller owns the same experiment logger, with its own ownership,
status, command, source contract and terminal reports under this directory.
Original controller ownership/status/logs are preserved. Include the interrupted
retained8987physical/8253transition hands exactly once in accounting; report any
observed unsaved suffix separately and leave the unknown worker tail null.
Every new attempt uses the existing durable registry and a new exclusive namespace.
Actual resumed GPU state must pass the existing full-state/gradient-origin checks,
plus an explicit fresh-namespace gate. No automatic retry after further failure.

The original prepared terminal reviewer is not recovery-aware and must not be run
as though the interruption did not occur. A recovery-aware terminal review must
verify the two-attempt connected chain, full original-parent contrasts, original
and new process receipts, accounting and runtime uncertainty before this same
experiment is finished. Its implementation can proceed separately while the
qualified remaining training runs. No new algorithm, strength claim, external
cohort, model selection or expanded hand budget is admitted by this plan.
