# Stage1 boundary interpretation

The controller completed four fixed endpoint evaluations (131072 physical
evaluation executions, conditional paired-deck intervals). Its raw joining,
hash and freshness checks passed and broad_collapse=false. Full independent
terminal review remains pending; this is not final qualification.

Expanded minus control pooled bb/100:
- Seed1 -1.455688, CI95 [-14.156667,11.245290].
- Seed3 -2.520630, CI95 [-14.326569,9.285310].

Own-parent changes: Seed1 control -2.474365, expanded -3.930054;
Seed3 control +1.556519, expanded -0.964111. All pooled intervals include zero.
Each treatment/control contrast has two positive anchors; seat breadth is
mixed (Seed1) or both negative point estimates (Seed3). Standard10-relative
treatment/control points are negative for both seeds but both intervals include
zero. Monitor this at the fixed next dose; it is not a causal failure finding.

Classification: insufficient strength evidence at the quarter-million dose,
not demonstrated improvement, broad collapse, or proof of algorithm failure.
Continue the already preregistered fixed1M dose without changing configuration,
seeds, checkpoints, opponent distribution, evaluation size or stopping rule.
No new external/Slumbot cohort or additional research branch is launched.

The last evaluator exited0 with no observer errors in787.621seconds. Its
longer duration did not require interruption or retry. Raw output is batched
after each complete anchor comparison; absence of intermediate writes was
not treated as terminal failure.

Prepared outside frozen runtime dependencies while the controller exclusively
owns the logger. Attach this note to the same record at terminal review.
