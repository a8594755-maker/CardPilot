# Initial implementation failure

The first launch stopped during the second counterfactual row before a complete
dataset or summary existed. State collection and the first raw row used the frozen
inputs and preregistered seeds, but the branch runner mistakenly indexed the native
v6 action table with legal slots returned by the legacy observation bridge. A legal
legacy slot can intentionally be empty in the differently indexed native table, so
`apply_incr` rejected `None` as a malformed physical action.

No model weights, optimizer, checkpoint, network service, or frozen input changed.
The partial `data/rows.jsonl` is retained as failure evidence and may not be combined
with recovery results. Recovery uses the same configuration and seeds in a new
`data_recovery` directory after a regression test verifies that every legal bridge
slot carries its exact bridge-returned physical action.
