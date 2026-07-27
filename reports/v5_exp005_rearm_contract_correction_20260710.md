# EXP-005 Rearm Contract Correction

Checked at `2026-07-10 14:44 EDT`. Verdict: `CORRECTED_VALIDATED`.

The first canonical rearm after the EXP-005 cutover failed closed because the
gate watcher still expected `opponent_assignment=per-iteration`; the new run
manifest correctly declared the registered `per-group` behavior. The temporary
gate31500 failure was an identity-check mismatch only. Trainer PID `30224`
continued normally and was not restarted or modified.

The same audit found two stale control paths: the rearm script would reopen
terminal EXP-003 watchers on the continuation run, and would expose generic
promotion/formal watchers before EXP-005's fixed endpoint and MEAS-001 method
judgment. The canonical script now derives expected assignment from the run
manifest, explicitly skips EXP-003 for an EXP-005 evidence run, blocks
promotion20k until the frozen 20M endpoint plus MEAS-001, and keeps formal100k
blocked until a strong same-checkpoint promotion.

Final canonical coverage is `31500..32700`; seven required watchers survived.
Validation passed PowerShell parsing, `14/14` rearm contract checks, `5/5`
EXP-005 focused tests, and `153/153` full V5 unittests. This was a reporting and
control-plane correction only; it did not alter trainer behavior or strength
evidence.
