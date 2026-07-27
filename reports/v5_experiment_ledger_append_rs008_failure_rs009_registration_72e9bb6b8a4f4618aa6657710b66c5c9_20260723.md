# Append-only ledger shard: RS008 structural failure and RS009 registration

Timestamp: 2026-07-23T07:54:00Z  
Boundary: RS009 preregistration and independent audit complete  
Classification: `PASS / RS009_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_IMPLEMENTATION_READY_ONLY`

Before materialization, RS008 was proven structurally unsatisfiable. Its registered
files are 17,815 and 6,844 bytes, while immutable RS007 `verify_frozen_inputs()`
contains function-local literals 21,218 and 9,251. RS008 permitted only top-level
assignment changes and required all functions bit-exact. Therefore an unchanged
runner must reject the new files, while changing the literals violates the registered
AST contract.

RS008 failure/audit SHAs:
`6af981b4b1ff439fe8862aa618d6102a9679a5999e2d532f27f7f784782cd147` /
`8705cbee2e304f890f8bdc690c9e67d4a813a2caa6a6617ddebf211ebbbf31f8`.
No implementation file, probe, qualification row, rollout, GPU model load, quick5k
or official hand existed. RS008 is terminal and not correction-eligible.

WS009 result/audit selected `RS009_DIRECT_MATERIALIZED_CONTROL_SIZE_CONSTANTS`.
RS009 identity is
`72e9bb6b8a4f4618aa6657710b66c5c91918b64faadbbf63e0655554688c80c4`
(token `72e9bb6b8a4f4618aa6657710b66c5c9`). Preregistration/audit SHAs:
`54b081b37171449d782b6b64ffaf84e9c553eea2c0bae426a00533790d229aea` /
`4d22631cdb6d58d8a4a3d543daf4fe30f0aa9ea474214af4336e7796963465c6`,
PASS95/95.

RS009 adds only top-level `PREREG_BYTES` and `PREREG_AUDIT_BYTES`, replacing exactly
the two parent size literals in `verify_frozen_inputs`. A no-write in-memory
satisfiability simulation observed exactly those two replacements and proved the
complete normalized runner AST and result-auditor AST equal to RS007. Every science
function/class remains bit-exact; runtime import bridges remain forbidden.

The implementation auditor will own one final-launcher zero-file probe with nonce
`RS009_FINAL_IMPORT_PROBE_2034972301`; only its PASS may authorize one qualification
nonce `RS009_QUALIFICATION_2036972301`. Full qualification/result-audit PASS requires
the next quick5k screen under the unchanged -126.1726 bb/100 directional threshold.

Snapshot:
`reports/v5_rs009_registration_pre_refresh_snapshot_72e9bb6b8a4f4618aa6657710b66c5c9_20260723.json`.
No RS009 code or execution exists. Strength L0; route exhaustion false; goal active.
Next only is RS009 materialization, full normalized-AST implementation audit, one
final-launcher probe, and stop qualification-ready.
