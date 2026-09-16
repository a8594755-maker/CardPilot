# Outcome-blind readiness findings, before any 4M strength evaluation

## Frozen Seed1/Seed2 mechanics

`frozen_seed12_mechanics.json` preserves the first, failing generic audit. Both
seeds failed only `corrected_legacy_contract_bound`; every other generic gate,
stage-prefix check and observed recovery-segment continuity check passed.

`frozen_seed12_mechanics_inherited_bridge.json` adds an independently checked
inherited-bridge proof without changing those original failing gate values.
The generic traversal stops at earlier in-place resume paths. Existing prior
audits retain the hash-bound connection to the earlier checkpoint chain; the
supplement reloads the actual referenced checkpoints and verifies SHA256,
observation contract and rebinding event. Seed2 requires recursive inheritance
through both the 2M and 1M audit, not just a single parent-audit flag.

The two endpoints therefore have consistent **observed** mechanical evidence.
This is not a reconstructed historical preflight or proof of byte-identical
initial optimizer/replay memory in the lost recovery processes. It does not
make Seed2's training deals fresh. The final incident report still records
2,095,518 stage executions, 1,519,687 unique evidenced deal identities and
575,831 repeated exposures; unknown uncommitted crash suffixes remain excluded.

No new training hands, strength-evaluation hands or Slumbot hands were used.
The final all-three audit/evaluation still waits for the originally specified
4M endpoints. Do not replace or overwrite the original aggregate audit.

## Aggregation mismatch found by source inspection

The current shared `aggregate_v6_static_current_kl_1m.py:collapse` uses
`both_seats_negative AND at_least_three_negative_anchors`. The 4M preregistration
defines broad reversal with **OR**, not AND. This is a real mismatch in the
descriptive 4M gate. Keep historical outputs unchanged. The eventual scoped 4M
report must calculate the preregistered OR definition, report all three seeds
and the predeclared incident-unaffected Seed1/Seed3 subset, and never infer an
automatic 8M promotion from either the old aggregate label or a passing
post-hoc mechanical audit. The outcome-blind deviation amendment remains binding.

## Safe boundary is a process state, not a success label

The sequential launcher must actually be terminal before production cutover.
Its runtime guard can end a process cleanly below 4,194,304 hands, then the
launcher throws a below-target error. That is a safe resume boundary, not a
completed 4M endpoint and not a reason to restart earlier work. If this happens,
preserve the final checkpoint and attempt evidence, integrate and qualify the
managed trainer, then continue only the remaining hands with unchanged learned
method and seeds under a documented fresh-namespace statistical continuation.
Only freeze an evaluation endpoint after the actual hand target is reached.

## Throughput evidence to reuse

Existing GPU qualification measured 98.676 physical hands/s for single1 and
341.185 for multi8, including trainer wall overhead, on the current workstation.
It did not qualify current-recipe resumed multi8 or long-run learning strength.
Do not repeat the broad search. After safe integration, qualify that one known
candidate against a bounded current-recipe baseline. A throughput change is not
authorization for 8M or paper-scale training without the learning-curve decision.
