# Fixed 1M additional-dose milestone

All eight training and eight internal evaluation jobs exited normally. The
terminal-only independent review passed; original checkpoints and raw evidence
are preserved. This trial is complete, but the poker benchmark goal is not.

## Accounting

- 4,204,843 new physical training executions across four branches, not one policy.
- 3,730,572 transition-bearing hands; 472,198 no-trainable-decision hands;
  2,073 residual worker-tail executions. These sum to the physical count.
- 6,575,421 replay rows, separately counted and not new environment hands.
- 262,144 internal evaluation executions, 32,768 unique evaluation decks.
  No overlap with 780,290 rows in the 103-file preregistered historical corpus.
- Eight distinct managed attempt namespaces. Initial model/Adam/replay/adaptive
  state and raw prefixes verified preserved. This establishes statistical
  continuation, not bitwise worker/in-flight RNG restoration or measured unique
  training-deck coverage.
- Training subprocess wall time: 13,195.01 seconds; controller: 17,641.48 seconds.
  Resource contention was observed during early jobs (see the retained resource
  observation); these aggregate times are not uncontended throughput estimates.
- Zero new Slumbot hands and zero final qualification hands in this record.

## Strength evidence

Recent-pool minus loss-ranked control, paired internal bb/100 (conditional 95% CI):

| Additional dose | Seed1 | Seed3 |
|---|---|---|
| 262k | +2.2175 [-8.4269, 12.8620] | +0.1089 [-15.0410, 15.2587] |
| 1M | -6.3751 [-18.6471, 5.8969] | +2.6215 [-11.5602, 16.8032] |

At 1M, recent endpoints versus their own original parents are -6.8934 and
+1.0668 bb/100, respectively; both intervals cross zero. There is no replicated
positive own-parent slope or cross-seed advantage. Seed1 recent regresses on
legacy_iter16 versus its parent (-33.1177, CI [-57.4767,-8.7587]); its seat1
contrast versus control is also negative (-16.8152, CI [-33.4670,-0.1634]). These
are marginal bucket intervals, not multiplicity-adjusted discoveries. Seed3
does not replicate broad collapse. Neither stage triggers the preregistered
broad-collapse stop gate.

## Decision

The pool-turnover mechanism operates, but improved poker strength is unproven.
Do not promote a winner, automatically expand beyond the fixed dose, or treat
recency itself as opponent quality. Execute the preregistered four-endpoint
external development calibration in a separate record: 20,000 fresh Slumbot
hands per frozen policy, eight 2,500-hand sessions each. Do not select only a
lucky internal endpoint or pool these policies toward the final 100k criterion.
Use the external results with both-seed breadth and own curves to decide the
next compute allocation. Insufficient evidence here is not proof that all
opponent-league learning fails at larger scales.

## Review provenance

An initial read-only terminal audit was run inline and succeeded (tool trace).
The reusable `post_analysis/terminal_review.py` then repeated those checks and
added raw PPO health, attempt receipt, full-scope and recorded hash checks,
writing `post_terminal_review.json` exclusively. No poker hands were rerun.
The inherited statistics helper's historical arm names were explicitly mapped
to control/recent. Both-stage means and intervals match the controller output.
