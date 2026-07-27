# EXP-W1 Control v3 Launch — 2026-07-11

Checked: 2026-07-11T11:59:59Z

- Overall: `CONTROL_ARM_RUNNING`.
- Run: `v5_zero_l6_expw1_control_same31400_20m_r2_20260711`; trainer PID `39316`.
- Immutable lock v3 SHA256: `ed38a7d1465cc22afb1fe69fa7fddb9a5daeb7c0272c437b5f19bb01c1e32984`.
- Exact source: gate31400 / 515,989,661 hands / SHA256 `bcbb46bd01d62fcdea602269b7047323315d4e9bbcf447ea0323e289fde11a8e`.
- Sole variable remains treatment warmup epochs; this control uses `exp_w1_value_warmup_epochs=0`.
- Runtime at check: iter31411 / 516,170,559 hands / latest 7,480 h/s / health PASS / entropy 1.4012 / stderr 0 bytes.
- First provenance record binds iteration31401; record SHA256 `8e1755d3aca366a268cd7af611a4b590322b657b9e48b934908b0e0948f50b0e`.
- Pre-copy and post-copy immutable verifiers PASS. Canonical rearm reports `survival_pass=true`, no failed watchers; endpoint watcher is `ARM_RUNNING`.
- Generic eval cadence, promotion20k, formal100k, EXP-003 reopen, and every Slumbot launch remain blocked.
- The preserved v2 r1 attempt is `INVALID_PREWINDOW_CONTROL_ATTEMPT_WATCHER_CONTRACT_FAILURE` with no method or strength authority.
- Next action: allow the control arm to reach the first exact endpoint checkpoint at or above 535,989,661 hands; do not start treatment early.

Latest official strength remains L0: 20,400 greedy-direct hands, -153.3 bb/100, 95% CI [-187.695, -118.905].
