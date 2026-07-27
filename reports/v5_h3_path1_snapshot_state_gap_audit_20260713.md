# H3 Path-1 snapshot-state gap audit

The v2 smoke failure is not safely repairable by redirecting slot 7 to another slot.
At the failing row, exact Path-1 replay and Python `HUNLGameState.apply()` reconstruct
different pot and stack states. The exact values and source identities are frozen in the
matching JSON artifact.

A successor adapter must therefore consume a source-tree snapshot produced by the same
Path-1 replay implementation that determines the solved node. It may then construct an
explicit synthetic v5.5 state, query the actual legal action table, and map sized teacher
actions by closest legal non-all-in action amount. No mass may be dropped, renormalized,
or sent to all-in merely because a nominal sizing slot is absent. Projection frequency
and error remain domain-transfer evidence, not hidden preprocessing.

This audit grants no dataset, H3 behavior, or official-hand authority.
