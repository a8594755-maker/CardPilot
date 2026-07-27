# Gate31500 Ops Lineage Censure

Checked at `2026-07-10 14:50 EDT`. Status:
`CENSURE_PUBLISHED_FIXED_FAIL_CLOSED`.

The append-only `14:47` gate31500 row contains correct gate, health, internal,
preflop, checkpoint-delta, and official Slumbot fields. Its instruction that
the fixed EXP-003 bundle was eligible is false and is superseded here. EXP-003
is terminally `INCONCLUSIVE` at frozen gate24900 / `409,058,520`; it may not be
rerun, extended, reseeded, or moved to a later checkpoint.

Cause: the EXP-005 continuation directory did not contain a duplicate local
judgment file, while the Ops watcher searched only the current directory. The
watcher now follows `lineage_parent_checkpoint` and resume ancestors, validates
the same terminal identity, and fails closed on conflicts.

Focused Ops tests pass `6/6`; the full V5 suite passes `154/154`. Trainer PID
`30224` was untouched. This correction changes neither trainer behavior nor
strength evidence.
