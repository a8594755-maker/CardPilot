# V5 experiment ledger append — RS005 / RS006 / WS007

Timestamp: 2026-07-23 00:45 EDT  
Goal status: ACTIVE  
Strength: L0  
Official hands: 0  
Route exhausted: false

## RS005 terminal

RS005 implementation audit completed 29/31 and failed closed before qualification.
Both launcher-bound probes passed with zero files and torch absent. The deep self-test
used `b600` after prefix `b200`, while the exact H11 policy table exposed `b400` and
all-in. No model was loaded and no scientific or behavior result was produced.

- Implementation audit SHA:
  `99bd9c01c41a67e142f5fa7ab561bf639b27a1c52f5f99ec38d5d800fd52bc71`
- Terminal judgment SHA:
  `5efbab547651b060834d384642d6bf307314ca388e62ede9a23f53531f91aa6a`
- Terminal audit SHA:
  `5cf2af78e766d675dcfd4009c530fec9aeed6b9eae8597277cceef5585343c93`
- Exact classification:
  `RS005_FAIL_CLOSED_PREQUALIFICATION_INVALID_DEEP_SELFTEST_FIXTURE_NO_RERUN`

## RS006 single fresh correction

The one governance-permitted fresh correction changed only the self-test fixture from
`b600` to the exact table action `b400`. Registration audit passed 43/43.
Implementation audit then passed 25/25, including deep self-test and two new zero-file
probes.

The sole qualification attempt failed during source-scoped adjacent-transition replay.
The immutable Slumbot ledger itself contains `b200 -> b600`. `b600` is a poker-legal
raise target, but it is not represented by the hero H11 nine-slot table at that prefix.
The implementation incorrectly used the policy table as the public action-legality
oracle. Only `invocation.json` existed before the failure. The one result-audit attempt
then failed as registered because `result.json` was absent. No terminal cohort,
resolver row, quick5k hand, checkpoint, or strength evidence was produced.

- Implementation audit SHA:
  `e79c64f7707fbea2c498aa301074eaf4960e58a47d8b742c838f8c9c9257a039`
- Qualification failure SHA:
  `7c781d2bbcc62dbb71b0e8c34a847f5e6a7331e13cb2ada178bdd70f143b127e`
- Failure audit SHA:
  `ab32b727442707f5a7cd857b2867c346c95bb89b67a3c4847cca6feb2f1cdf99`
- Exact classification:
  `RS006_FAIL_CLOSED_PREOUTPUT_PUBLIC_LEGAL_ACTION_VERSUS_POLICY_SLOT_CONFLATION`

RS005 and RS006 are immutable. Do not repair, rerun, reclassify, reconstruct, or launch
their qualification, audit, quick5k, or official evaluation.

## WS007 route review

WS007 preregistration/audit and result/audit passed. The review did not treat RS006 as
resolver-route exhaustion. It selected a materially revised RS007 design:

`SELECT_RS007_PUBLIC_LEGALITY_POLICY_SLOT_SEPARATION_DESIGN`

RS007 must define two domains:

1. `apply_public_increment` accepts every exact-cent poker-legal observed/opponent
   action, including targets not present in H11's abstraction.
2. `apply_policy_slot` permits H11 to choose only a non-null exact executable slot,
   then delegates that increment to the public transition.

It must independently replay all 29,878 rows and 24,878 source-scoped adjacent
transitions, cover minimum/full/short-all-in raise and reopen semantics, preserve the
fully-live terminal/refund/payout design, and forbid projection, dropping, collisions,
or renormalization.

- WS007 identity:
  `dfe4579762d435f924f11ae97a5bc59424ff063e2303446e65645ff50228ad44`
- Preregistration/audit SHAs:
  `0861aefb5c94deafa6f78a6f1b85b8cbe48ff3ae0c6d313a65bd9464d9f7c268` /
  `e5e53f632816591bf0c27867385e4be38a35440afce96fa6601bf9b986e30c53`
- Result/audit SHAs:
  `e4e601388623742f941084a48903501384de9dd085f447f0f60d4487493abb34` /
  `9046bf3bc4e56114e27588baa6dca5dfa7f1e7f3a974bef4313b2b205b616a1f`

Stop boundary: no RS007 registration or implementation exists, and there is no
quick5k, GPU, evaluator, Slumbot, checkpoint, or official-hand authority. Next is one
separately registered RS007 design preregistration plus independent preimplementation
audit only.
