# EXP005-C Immutable Design Lock

Status: `LOCKED` at `2026-07-10 15:50 EDT`.

The machine-readable JSON companion is authoritative and will be made
read-only. Both arms start from the unique frozen gate31400 checkpoint
(`515,989,661` hands; SHA256
`bcbb46bd01d62fcdea602269b7047323315d4e9bbcf447ea0323e289fde11a8e`).
Control uses `per-iteration`; treatment uses `per-group/5`. Both load the same
optimizer and pool bytes, use the same explicit global and worker seeds, the
same deterministic worker/env/deal stream, identical non-assignment flags, a
20M actual-hand target, save every iteration, and hash-chain every executed
worker assignment to resolved pool snapshot identities.

Primary evidence is exactly 100,000 common-deal pairs between the control and
treatment endpoints, not gate30700 versus an endpoint. PASS requires complete
identity/provenance/health/budget/throughput/validity/precision gates and both
the paired native-axis effect and direct treatment-versus-control CI lower
bounds above zero. CI overlap or insufficient precision is INCONCLUSIVE; a
valid precision-passing non-positive result or protocol/abort failure is FAIL.
The 200-hand probe is smoke-only.

FAIL or INCONCLUSIVE freezes Tier-2 from-zero tuning. PASS only authorizes an
exact-treatment-endpoint promotion20k. Promotion must include a relative-to-V4
difference CI; a point estimate above `-71.4` is not a gate. Strong promotion
allows exact same-checkpoint formal100k; non-strong freezes Tier-2 and enters a
route-pivot review.

The continuation script refuses `-Execute` without this pre-existing lock,
its exact SHA256, an arm identity, a matching source checkpoint/config/trainer
toolchain, passing locked tests, and the ledger prefix/event binding.
