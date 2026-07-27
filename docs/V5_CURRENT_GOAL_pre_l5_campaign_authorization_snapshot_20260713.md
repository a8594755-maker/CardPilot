# V5 Current Goal

Checked: 2026-07-13T04:06:15.0277867+00:00

## Immutable objective

- Build a general strong 200bb HUNL agent. Official strength evidence remains greedy-direct Slumbot only.
- L5 requires 100k+ official hands, bb/100 > 0 and 95% CI lower > 0; L6 additionally targets about +11.1 bb/100.
- Ledger is append-only; fail-closed identity, complete evidence bundles and one behavior change per window remain mandatory.
- EXP-002 is retained. EXP-003 is terminal INCONCLUSIVE. EXP-004 priors remain 0.01/0.02. EXP005-C and EXP-W1 are terminal and must not reopen.
- The from-zero constraint was lifted by explicit user escalation. 2.7B is only a resource cap, never continuation authority.

## Authoritative current state

### H1 — terminal FAIL

- Preregistration: reports/v5_hybrid_h1_preregistration_20260711.json, SHA256 bb998b84adb2cee4fa6c8f88861b612c556356c8b91fdae9d9c883b1c7b733ab.
- Watcher-only design lock v3: reports/v5_hybrid_h1_design_lock_v3_20260712.json, SHA256 dd99f3ecb09ffeae589b14d69d9040ab5a640272add6c3408b730592f9bccadb.
- Corrected holdout reports/h1_cal_001_attempt2_20260712 is PASS_IMMUTABLE_HOLDOUT: 10,000 common-deal pairs, 20,000 hands, 48,533 decisions, OOD0, FORBIDDEN_HOLDOUT_ONLY. Failed attempt1 remains terminal and preserved.
- Control endpoint: iter32617 / 536,004,082 hands, frozen SHA256 f3bc22de78caa4cc10493fdf6d8c4b09a4c3f6ec67c2e20ceba276ff76bba6b8.
- Treatment endpoint: iter32617 / 535,996,488 hands, frozen SHA256 4c021cbf9f25aeefa81b29c823bd7ec0b94bd87668cc7a4e1320d3c662588274.
- Normalized MSE control0.0091851773 versus treatment0.0093871153. Relative reduction -2.1985%, bootstrap95 CI [-6.4167%, +1.7948%]: point and lower-bound gates FAIL.
- Throughput first60 ratio1.054011 PASS; full-window ratio0.826652 FAIL. Entropy medians control1.30920/treatment1.26550: floor and non-inferiority PASS.
- Registered verdict: FAIL. critic_v2 is REJECTED. Do not extend, add a seed, use a later endpoint or reclassify.
- Completion audit: reports/v5_hybrid_h1_completion_audit_v2_20260713.json, SHA256 d00c482b63817e251707a20947d44901754b90b3831e8e8c9584119278560f8b, overall PASS_COMPLETE_H1_TERMINAL_FAIL.
- Delayed canonical rearm is CENSUREd. Reconstructed first60 passed, so no mandatory abort was missed; the unchanged endpoint watcher later froze exact identity/provenance evidence. It does not weaken or change the FAIL verdict.

### H2 — draft complete, no launch

- Draft: reports/v5_hybrid_h2_preregistration_draft_20260713.json, SHA256 b450ccb93de36c08fa064cc938693ef7c499942e6a7bfa080144997fe2ef5ca2.
- Draft audit: reports/v5_hybrid_h2_preregistration_draft_audit_20260713.json, SHA256 77938afd0eee7c94cc05e019815ce04387645d1ec45af08b659a4d66cd7069ef, PASS_DRAFT_COMPLETE_NO_LAUNCH.
- H1 FAIL branch selects exact gate31400 critic_v1 source checkpoint SHA256 bcbb46bd01d62fcdea602269b7047323315d4e9bbcf447ea0323e289fde11a8e.
- Proposed fixed design: 20M actual hands per same-start arm; treatment adds deterministic K=200 all-showdown critic targets only. Primary variance gates are point>=30% and bootstrap95 lower>=20%; mean-bias, endpoint-MSE, 20k-pair internal mirror non-inferiority, h/s>=0.85, entropy, health and identity are mandatory guards.
- Status is DRAFT_NO_LAUNCH. Implementation, H2-VAR-001, immutable preregistration/audit, design lock, preflight, watcher rearm and launch remain unauthorized.
- H1 is one terminal FAIL/no-progress window. A terminal H2 FAIL/no-progress would be the second consecutive and force route-pivot review.

### H3 Path-1 asset preparation

- CPU-only solver PID51176 is alive and RUNNING; 156/600 board meta artifacts currently complete.
- Config pipeline_srp_v3_200bb, 80K iterations, six RAM-safe workers, selection seed20260712, samples-per-bucket1.
- Output remains data/cfr/pipeline_v3_hu_srp_200bb/. Existing assets are preserved; streaming QA/retry rules remain active. Do not touch the GPU or convert these assets into H3 behavior authority without a separate preregistration.

## Immediate next direction

1. Preserve H1 as terminal FAIL and critic_v1/gate31400 as the H2 source branch.
2. Review and close the H2 draft open prerequisites; only then may a separate immutable preregistration be published. Do not launch H2 automatically.
3. Keep Path-1 solving CPU-only toward 600 boards with streaming QA.
4. Run zero official Slumbot hands until a later registered milestone explicitly authorizes them.

## Official strength

Latest official strength remains L0: 20,400 greedy-direct hands, -153.2999 bb/100, 95% CI [-187.6945, -118.9052]. H1/H2/H3 grant no V4/L5/L6 claim.