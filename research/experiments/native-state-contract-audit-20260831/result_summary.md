# Native state contract audit

Decision: `CONTRACT_DIVERGENCE_FOUND`.

| Fixed probe | Discrepancy observed |
|---|---|
| posted_blinds_action_binding | True |
| sb_completion_bb_option | True |
| flop_minimum_opening_bet | True |
| full_raise_increment_after_three_bb_bet | True |
| opening_allin_v4_action_type | True |

Zero completed environment hands, training hands, external hands or network attempts.

- Deterministic counterexamples, not representative policy strength or causal loss attribution.
- Constructed flop fixture isolates the public-state legal table from the separate SB-limp transition discrepancy.
- No historical hand, checkpoint, source or result is modified; further repair requires its own recorded experiment.
