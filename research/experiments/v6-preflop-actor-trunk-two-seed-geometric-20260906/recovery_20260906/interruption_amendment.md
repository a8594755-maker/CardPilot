# Unobserved-exit recovery review, 2026-09-06

The exact original controller PID57824/create_time1788676494.1425543 and
connected trainer PID10048/create_time1788680807.206966 were absent at the
2026-09-06T07:51Z read-only inspection. No Python training processes were observed.
Windows had not rebooted. No connected termination receipt or controller error
exists. Cause and exit codes are unknown; absence of an exception log is not
evidence of a clean exit. Do not blame a particular app or algorithm.

The completed detached Seed1 stage1 remains immutable:266415 new physical hands,
230891 transition-bearing hands, exit0, final iteration2271 and physical10764649.
The connected attempt's last logged/saved boundary appears to be iteration2217,
physical10507221 and transition9140101, adding8987/8253 since its original parent.
These are to be independently checked against the serialized state before reuse.
Unknown in-flight worker hands are NOT assumed to be zero or counted as retained
training. Preserve the original status, process metadata, checkpoint, logs,
receipt and all completed work under their current paths.

This is a review of the same RUNNING experiment, not a new algorithm family or a
failure of the connected gradient hypothesis. No automatic retry is admitted.
The audit adds no environment/evaluation/Slumbot hands and performs no policy
inference. A later qualified continuation must use the exact retained model,
all86 Adam states and actual1e-4 LR, replay entries/RNG/counter, pool, reference,
main RNG, gradient flag/origin, training seeds and original cumulative target.
It must allocate a fresh exclusive managed deal-attempt namespace, preserve the
full pending assignment evidence, and document statistical rather than bitwise
worker continuation. Any uncheckpointed evidence must remain immutable and be
accounted separately. A new output directory and explicit attempt-chain mapping
are required; never rerun the completed detached cell or replay the original
connected prefix. Recovery scheduling/evidence adaptations must be qualified
before launch. No training recipe, learning dose, evaluator, evaluation seed,
gate, stopping rule or external acceptance criterion changes in this amendment.
