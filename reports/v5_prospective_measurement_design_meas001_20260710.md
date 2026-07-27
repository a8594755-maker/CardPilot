# MEAS-001 Prospective Common-Deal Causal Measurement Design

- status: `IMPLEMENTED_VALIDATED_NOT_LAUNCHED`
- registered: `2026-07-10 EDT`
- owner: Codex
- scope: measurement protocol for a future, separately registered V5 behavior
  experiment. This registration does not authorize or schedule a trainer change.

## Why this is needed

The fixed EXP-003 bundle is terminally `INCONCLUSIVE`. Its
`post_vs_native` role had a 95% CI half-width of `22.199 bb/100`, above the
pre-registered `20.0 bb/100` limit. EXP-003 must not be reopened by adding
pairs, selecting a later checkpoint, or substituting a new seed.

MEAS-001 is prospective. It applies only to the next behavior experiment after
that experiment has its own ledger registration, exact cutover checkpoint, hand
window, abort rules, and rollback. It cannot change the EXP-003 judgment.

## Frozen design

1. Before the future behavior cutover, freeze and hash:
   - the exact pre-change checkpoint;
   - the native v55 anchor;
   - the evaluator code and configuration.
2. Before any candidate result is observed, pre-register the first eligible
   candidate checkpoint as the first exact `PASS` gate at or above the future
   experiment's fixed hand window. No later-checkpoint substitution is allowed.
3. Evaluate exactly `100,000` mirrored deal pairs with a single common deal-ID
   stream for all roles:
   - pre-change versus native anchor;
   - post-change versus native anchor;
   - post-change directly versus pre-change.
4. Policy is greedy argmax on both seats, stack is `200 bb`, execution is CPU
   `BelowNormal`, and official Slumbot work has priority. The role seeds and
   deal-ID manifest must be written before launch and hash-bound into every
   artifact.
5. No adaptive sample extension, optional stopping, second seed, or checkpoint
   reselection is allowed. A failed precision gate is `INCONCLUSIVE`.

## Estimands and gates

The evaluator must retain aligned per-pair returns and prove that the same
deal IDs were used across roles.

- Primary native-axis causal effect: per-deal
  `(post versus native) - (pre versus native)`. Compute its paired 95% CI
  directly from aligned deal returns; do not subtract two point estimates and
  then compare against separately rounded intervals.
- Primary direct causal check: post-change versus pre-change on the same common
  deal stream.
- Precision: each primary 95% CI half-width must be `<=20 bb/100`.
- Improvement: both primary CI lower bounds must be `>0` for an `ADOPT` method
  signal. A future experiment may pre-register non-inferiority instead, but its
  margin must be fixed before launch.
- Validity: every role must pass checkpoint/hash/protocol identity, native-anchor
  OOD rate `<=0.15`, legal-action, seat-swap, and complete-pair checks.
- Guards: health `PASS`, empty trainer stderr, no action/entropy collapse,
  experiment-specific counters valid, and throughput within that experiment's
  registered band.
- Official strength: no mirror result supports a V4/L5/L6 claim. The normal
  greedy-direct Slumbot cadence and complete hand-level bundle remain required.

## Power rationale

The worst EXP-003 role measured `22.199 bb/100` half-width at `25,000` pairs.
Under square-root scaling, `100,000` pairs projects about `11.10 bb/100` for
that role. Even the conservative independent-axis combination of the observed
`15.761` and `22.199` half-widths projects about `13.61 bb/100` at `100,000`
pairs; the common-deal paired estimator should usually be tighter because it
uses covariance rather than discarding it. These are planning calculations,
not a promise or a result.

## Implementation gate before use

Before MEAS-001 can judge a future method experiment, the measurement harness
must pass tests that verify:

- identical deal IDs and seat swaps across all three roles;
- per-pair return alignment and deterministic replay;
- checkpoint, evaluator, seed-manifest, and result hashes;
- rejection of duplicate, partial, mismatched, or late-checkpoint artifacts;
- one-shot terminal behavior after PASS, FAIL, or INCONCLUSIVE.

If any implementation gate fails, no result may be ingested and no audit verdict
may be forced. Fix the harness, revalidate it before launching the registered
future measurement, and preserve all failed artifacts for audit.

## Implementation result

Completed `2026-07-10 EDT` without touching the live trainer or launching a
measurement:

- Evaluator: `scripts/alpha_holdem/v5_meas001_common_deal_eval.py`, SHA256
  `03d8441f1caeb77e96c8f3bafc195574e3969fc5d5468acef99f40772bd4ec84`.
- Independent audit CLI: `scripts/alpha_holdem/v5_meas001_bundle_audit.py`,
  SHA256
  `1578556a1b46e77d4f6676c62a71e86e74234ff5363d8d09480f925687f91e8d`.
- Focused tests: `scripts/alpha_holdem/test_v5_meas001_common_deal_eval.py`,
  SHA256
  `3549fa49b4a66b9bdbfa3c7fd1d20c0c8b99de23e87a9bd3c9443c6ed937b297`;
  `10/10` passed.
- Full V5 regression: all `14` test scripts passed, comprising `142`
  unittest cases plus the canonical rearm script's `14` checks.
- The implementation writes a frozen UTF-8 source bundle and hash-bound deal
  manifest before evaluation; uses one deterministic deal stream across all
  three roles; streams aligned per-pair returns to JSONL; recomputes the paired
  native-axis CI; refuses non-100k samples, checkpoint identity mismatches,
  artifact collisions, partial bundles, duplicate deal IDs, hash mismatches,
  and incomplete seat swaps; and terminates only as `PASS`, `FAIL`, or
  `INCONCLUSIVE`.
- No 100k-pair MEAS-001 evaluation has been scheduled or run. The tool is
  prospective and may be used only by a future separately registered behavior
  experiment with frozen pre/post/native inputs.
- Machine-readable implementation audit:
  `reports/v5_meas001_implementation_validation_20260710.json` (`PASS_NOT_LAUNCHED`).

## Current consequence

MEAS-001 now satisfies both the prospective-registration requirement and its
implementation gate. It does not select EXP-005, EXP-006, or any other method
change. The live trainer remains unchanged with EXP-002 retained, EXP-003 flags
still active but judgment inconclusive, and EXP-004 at the stable `0.01/0.02`
prior floor.
