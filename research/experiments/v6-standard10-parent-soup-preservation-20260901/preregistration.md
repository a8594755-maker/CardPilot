# Conservative Standard10-parent actor model soup

Materialize exactly one candidate.  Its four actor tensors are
`0.75 * raw_parent + 0.25 * Standard10`; every other model tensor and all v6
contract metadata are copied bitwise from the raw parent.  The fixed alpha is
not selected by returns or by a sweep.  This is weight interpolation, not
imitation, a teacher, a rule, or an execution override.

Replay candidate and parent probabilities on every actual decision in the
already audited raw-parent generic-greedy fresh5k Slumbot corpus.  Admit a
separately logged fresh5k generic-greedy Slumbot test only if exact identity and
evidence audits pass, mean total variation is at most 0.02, and greedy action
disagreement is at most 0.02.  No outcome from the preserved corpus is used.
Failure stops the soup; passing preservation is not a strength claim.
