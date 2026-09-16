# Low-LR actor tail generic-greedy fresh5k Slumbot pilot

Freeze the low-LR tail checkpoint SHA256
`6f3bf54433d72fdc4ebb9de33c52947c6da4fd0af2259d8b9561f7956821db5b`.
Its parent achieved -9.4188 bb/100 on a separate generic-greedy fresh5k, and
the tail passed its preregistered internal convergence gate at +46.3739 bb/100
over the parent with paired 95% CI lower bound +7.4970.  The internal opponents
were training members, so this live pilot is the first generalization evidence
for the tail.

Use the already tested generic greedy execution contract: legal argmax over
learned logits, one-hot behavior probabilities, no heuristic or opponent-specific
action rule.  Capture a fresh runtime before contact.  Run exactly eight new
sessions of 625 hands using seeds 2026110201..2026110208 and unique session IDs.
No retry, replacement, continuation, score stopping, endpoint change, or automatic
extension is allowed.  Require 5,000 durable raw hand JSONL records, complete
terminal/server-counter/model-decision replay, session independence, and token
disjointness from all discoverable prior passing audits.

Independently calculate raw-hand and session-t7 95% intervals.  Admit a separate
fresh20k confirmation only if aggregate bb/100 is positive and at least 4/8
session means are positive.  The pilot hands cannot be pooled into the fresh20k
or any later 100k qualification allocation.  A fresh5k result cannot complete
the Goal.

