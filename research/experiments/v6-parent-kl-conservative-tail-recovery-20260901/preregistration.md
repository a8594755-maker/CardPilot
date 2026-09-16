# Parent-KL conservative actor tail — zero-hand recovery

This is the unchanged recovery of `v6-parent-kl-conservative-tail-20260901`,
which failed during code-provenance capture before frozen inputs, trainer launch,
or any hands.  The only infrastructure change is naming the entry point
`run_tail.py`, as required by the reviewed shared runner.

Resume parent SHA256
`9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4`
with exact Adam, inherited 1e-5 LR, counters, EMA, adaptive league, assignment
RNG, and disjoint fixed deals from index 132,553.  Continue to at least 196,608
physical lineage hands.  The sole learning intervention remains replacing the
Standard10 KL reference/0.01 with the exact parent actor/0.1.

Require all continuity and fixed-pool audits.  Evaluate source, parent, and
treatment under generic greedy execution against the five training opponents,
1,024 common mirrored pairs per cell, seed 20261101.  Treat this only as a
mechanism gate.  Pass only if treatment-minus-parent average and its raw paired
95% CI lower bound are positive, treatment-minus-source is positive, and at
least 3/5 per-anchor treatment-minus-parent points are positive.  No Slumbot
hands are allocated here.

