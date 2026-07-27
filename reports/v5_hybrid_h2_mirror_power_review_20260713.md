# H2 Internal Mirror Power Review

- Status: `PASS_AMEND_BEFORE_REGISTRATION`
- Scope: prospective planning only; H2 has not launched and no H2 result was observed.
- Draft design: 20,000 common-deal pairs, non-inferiority lower bound `>= -20 bb/100`.
- Primary precision reference: valid EXP-003 native-axis row, 25,000 pairs, 95% half-width `15.7614 bb/100`.

Square-root scaling projects a `17.6218 bb/100` half-width at 20,000 pairs. Under a
true treatment-control difference of zero, the approximate probability that the lower
bound clears `-20` is only `60.4%`. At 40,000 pairs the projected half-width is
`12.4605 bb/100`, with an approximate pass probability of `88.2%`.

The final immutable H2 preregistration therefore fixes exactly `40,000` common-deal
pairs with seed `2026071403`. There is no adaptive extension, second seed, later
checkpoint substitution, Slumbot authority, or strength claim. Historical OOD or
quarantined rows are retained only as secondary precision context and never as effect
evidence. EXP-003 remains terminal `INCONCLUSIVE`.
