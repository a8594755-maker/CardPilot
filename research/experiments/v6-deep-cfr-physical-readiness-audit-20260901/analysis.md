# Deep CFR physical-v6 readiness audit

Decision: `REJECT_EXISTING_DEEP_CFR_HUNL_AS_PHYSICAL_V6_TRAINER`.

No HUNL environment training hands were generated. The exact tabular Leduc
control converged from 1287.7111 mbb/game at iteration 1 to 26.1112 at iteration
1000, so the small-game regret machinery is functional. The rejection is about
the HUNL integration, not CFR as an algorithm.

Five physical-contract gates failed:

1. `train_sdcfr` does not register `full_200bb`; an unknown value silently falls
   back to `srp_50bb`.
2. The CLI does not accept `full_200bb`.
3. Deep CFR's initial preflop action set contains only three fractional raises
   in slots 2--4, while physical-v6 exposes its fixed six-fraction grid with
   duplicate removal (live slots 2, 4, 5, 6, 7) plus slot 8 all-in.
4. With `raise_cap_per_street=1`, the opening flop bet increments the counter and
   leaves only fold/call; physical-v6 still permits a legal re-raise.
5. HUNL training uses nine output actions, while every HUNL export path
   reconstructs a six-action network. Loading a nine-action state dict into that
   exporter is shape-incompatible.

The 200-iteration preregistered Leduc control was underpowered and nonmonotone
(165.3158 mbb/game at iteration 200), so a recorded no-HUNL-hand extension to
1000 iterations was used before interpreting core correctness.

Artifacts:

- `readiness.json`: SHA256
  `e388a57366ed759dc7a8cf046a7e9ff1033f23c4d344377e3b1ec5987d776af8`
- `readiness_1000.json`: SHA256
  `c8b3e470bc361fe2335eefc4b5bdaebf48ebee29e1913ddec1ab55bd1a2d0721`

Highest-information next step: build a minimal CFR traversal adapter directly
over `ChipState` and the shared physical-v6 action table, then require deterministic
transition/action/payoff parity and a tiny traversal smoke before spending a HUNL
training budget. Do not repair only the legacy `GameConfig`, because doing so would
create a second rules implementation whose parity would remain unproven.
