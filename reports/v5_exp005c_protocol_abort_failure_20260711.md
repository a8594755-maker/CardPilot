# EXP005-C Protocol Abort Failure

- Classification: `EXP005C_FAIL_PROTOCOL_ABORT`
- Design lock SHA256: `2d64d3b82700d5bea2250121a09567e78f46b6bcc486a55d593acb33bcb86007`
- Locked abort gate: treatment/control effective h/s `< 0.85` after 60 rows
- Control first60 effective h/s: `2658.731142`
- Treatment first60 effective h/s: `1101.197545`
- Ratio: `0.4141816098`
- Control log SHA256: `de97a7b4879793a9d52a5bf40fe725e95c6f3df162162e90aecb5fe0c45c92f3`
- Treatment log SHA256: `6cbc27a639f8f941ce7aa2808c3c91a42b425498e60c9e4452dc1b0e2b488755`

The registered throughput abort fired at row 60. All later treatment data are `POST_PROTOCOL_EXPLORATORY_ONLY`. Primary100k, MEAS-001, promotion20k, and formal100k are forbidden. Tier-2 from-zero adjustments are frozen; route-pivot review is required.

Latest official strength remains L0: 20,400 greedy-direct hands, -153.3 bb/100, CI [-187.695, -118.905].
