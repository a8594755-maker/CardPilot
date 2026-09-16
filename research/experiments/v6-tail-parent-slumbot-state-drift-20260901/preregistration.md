# Tail-parent Slumbot-state greedy drift diagnostic

The low-LR tail improved significantly over its parent on its five training
opponents but collapsed from the parent's separate greedy fresh5k point of
-9.4188 bb/100 to -91.0228 bb/100, with both tail confidence intervals below
zero.  Replay every decision state from the tail's complete audited fresh5k
through frozen tail SHA256 `6f3bf54433d72fdc4ebb9de33c52947c6da4fd0af2259d8b9561f7956821db5b`
and parent SHA256 `9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4`.

This is offline and outcome-free: zero network calls, new Slumbot hands,
training hands, weight changes, or endpoint selection.  Verify all hand and
checkpoint identities.  Compute tail/parent entropy, bidirectional KL, total
variation, greedy-action disagreement, and probability/greedy action-slot mixes
overall and by street/seat.  The corpus is tail-policy on-policy support, not an
unbiased parent value evaluation.

Call drift concentrated if a street/seat partition with at least 100 states has
greedy disagreement above 25% or mean TV above 0.10.  Regardless of that binary
label, use only well-supported outcome-free shifts to design a generic policy-
preservation or held-out-league hypothesis; do not derive Slumbot-specific
rules or use hand outcomes as supervision.

