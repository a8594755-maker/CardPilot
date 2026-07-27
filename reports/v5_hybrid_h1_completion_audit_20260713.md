# HYBRID H1 Completion Audit

- Audit: **PASS_COMPLETE_H1_TERMINAL_FAIL**
- Experiment verdict: **FAIL**
- critic_v2 adoption: **REJECTED**; rollback/select critic_v1 from exact gate31400.
- Held-out normalized MSE: control 0.0091851773, treatment 0.0093871153.
- Relative reduction: -2.1985%; bootstrap 95% CI [-6.4167%, +1.7948%].
- Throughput ratio: first60 1.0540 PASS; full window 0.82665 FAIL.
- Entropy medians: control 1.30920, treatment 1.26550; floor/non-inferiority PASS.
- Both endpoint identities, checkpoint hashes, provenance, stderr and fixed budgets audited.
- Delayed canonical rearm is CENSUREd. It did not alter the registered first60 decision because the reconstructed ratio passed; full-window/value gates independently fail.
- Official Slumbot hands: 0. No V4/L5/L6 inference.

The JSON companion contains the requirement-by-requirement checks and SHA256 inventory.