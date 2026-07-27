# Gate 27600 Reporting-Race Censure

Checked at `2026-07-10 02:51 EDT`.

## Verdict

`CENSURE_PUBLISHED_FIXED_FAIL_CLOSED`.

The append-only Ops row written at `02:48` correctly recorded gate 27600,
checkpoint identity, health, preflop status, internal verdict, and the absence
of a strength claim. Its internal delta mean/lower values were stale: it copied
gate 27500's `+283.043 / +108.467 bb/100` while the exact 27600 target probe had
completed but the L6 aggregate had not yet refreshed.

The authoritative gate 27600 internal aggregate is:

- checkpoint: `27600 / 453,475,071`
- identity: `MATCH`
- verdict: `MIXED_INTERNAL`
- delta mean/lower: `-345.678 / -94.704 bb/100`
- target rows: call-station `+33.885`, aggressive `+167.75 bb/100`
- evidence class: internal-only; no strength claim

## Fix

`v5_post_gate_review.py` now keeps a completed exact target probe in
`PENDING_L6_AGGREGATE_IDENTITY` until the aggregate iteration exactly matches
the gate target. While stale, verdict/delta fields are null and the review
cannot reach the completed post-gate state.

Verification:

- focused post-gate tests: `5/5 PASS`
- complete V5 unittest suite: `152/152 PASS`
- watcher rearm contract: `14/14 PASS`
- canonical rearm: survival `PASS`, seven watchers, range `27700..28800`
- trainer PID `48476`: untouched

The historical Ops row is not edited. The appended CENSURE supersedes only its
internal delta mean/lower fields. No trainer behavior, weights, Slumbot run,
EXP-003 state, or strength conclusion changed.
