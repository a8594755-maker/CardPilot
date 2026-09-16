# Seed3 failed-save recovery amendment

This is a recovery substep of the SAME RUNNING Seed3 experiment, not another
algorithm or experiment. A proposed standalone infrastructure record was denied
twice by the execution tool and was not created. Its draft remains a provenance
artifact only. That record's proposed separate-record lifecycle is superseded by
this amendment. No permission settings or execution-policy rules were changed.

Original controller47988 and trainer58456 plus every observed descendant are
terminal. Original static_stage1 and original controller/status files remain
immutable. Interruption audit establishes latest iteration1117/physical5314037/
transition4602125, SHA d5e9ca2e96f3cba6bcda6c64a58b6759b9d6f38872d52ec30de01cbb75482f59.
Metric/manifest1118 are ahead:4292 physical hands/4123 transition hands were
executed but their optimizer update was not retained. Other worker tails remain
unknown. Do not credit those4292 as retained learning, erase them, or reuse their
deal namespace. Remaining first-stage retained target is978023 physical hands.

The original source code, including train_v5.py and managed_checkpoint_io.py,
stays unchanged. A hash-bound trainer wrapper substitutes only atomic_torch_save
in the main trainer's imported module using an experiment-scoped candidate.
The candidate serializes once, flushes/fsyncs once, and retries ONLY Windows
native error5/32/33 for at most five seconds/64attempts. No optimizer step, poker
action, or new payload is computed between retries. Permanent replacement
failure retains both old destination and fully serialized pending candidate.
Partial serialization cleans only its own incomplete temporary file.

Qualification precedes any resumed hands: ordinary/failed I/O unit tests,
actual Windows sharing-lock transient and persistent tests, wrapper hash binding,
and production --help through the wrapper. Commands/output/SHA and wall time are
recorded by qualify_io.py and attached to the same experiment record.

Recovery will restore the1117 checkpoint, optimizer/LR, replay/RNG, league,
reference and saved main RNG. All1118 assignment rows (including pending1118)
stay intact. Create a separate explicitly derived consumed-metric prefix ending
1117 for a new attempt, while preserving the original metric1118 and full failed
attempt. The pending assignment may be reused but new durable namespace means
fresh deals, not replay of discarded1118 hands. This is statistical, not bitwise
worker continuation. Resume only remaining dose, then unchanged preregistered
static/moving stages and evaluation seeds. Preserve overshoot and crash accounting.

The previously prepared post_analysis normal-completion reporter is insufficient
after this interruption. An interruption-aware analysis must account for the
original retained prefix, observed uncheckpointed4292 hands, unknown tails and
new remainder before finishing. Do not use a normal four-run zero-crash report.
