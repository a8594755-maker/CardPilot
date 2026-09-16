# Stochastic Slumbot evidence readiness

Validation: PASS; 59 tests passed.

Added action-independent aligned/shifted deal replay checks, duplicate-input rejection, strict raw/session/model/seed/reward/CI reconciliation, and client fallback telemetry. An optional explicit post-load RNG seed and per-row policy identity preserve reproducibility without changing native action probabilities.

Tests include100000 synthetic independent initial deals and deliberately duplicated streams with different sampled actions/winnings. The saved end-to-end fixture contains200 SYNTHETIC records and a dummy fixture checkpoint; none are actual poker evaluation hands. The real unchanged Standard10 sample/temp1 seed2026090400 zero-hand loader passed.

**Actual new training/evaluation/Slumbot hands:0.** All final source hashes matched the frozen final_code snapshot.

Limitations:

- Observable replay diagnostics cannot prove hidden-deck statistical independence.
- Normal raw-hand CI assumes sufficiently independent hand outcomes; no strength claim arises from fixtures.
- The strict new-run contract rejects old files missing execution metadata without retroactively relabeling old experiments.
- Native-policy behavior/observation strength is not established by evidence-format tests or a zero-hand loader.

Next: separately preregister a fixed20000 fresh native-sampled Standard10 external baseline with immutable output directories, distinct explicit session seeds, staggered first-hand readiness, exact counters and strict terminal evidence audit. A later qualifying100k remains independent and is not satisfied by this readiness work.
