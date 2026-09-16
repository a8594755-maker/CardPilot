# Fixed four-policy recent-pool external calibration

Independent terminal review passed after 33 reviewer tests. All 41 execution
jobs exited zero. All 80,000 raw hands, 244,387 audited decision replays, exact
session commands, and 672 frozen input hashes were verified. Controller wall
time was 3,374.11 seconds. Review added zero poker hands.

| Frozen endpoint | Hands | bb/100 | Raw-hand 95% CI |
|---|---:|---:|---|
| Seed1 control | 20,000 | -27.7469 | [-47.4064, -8.0874] |
| Seed1 recent | 20,000 | -16.3391 | [-37.2480, 4.5698] |
| Seed3 control | 20,000 | -31.9000 | [-52.8601, -10.9399] |
| Seed3 recent | 20,000 | -32.6017 | [-55.0748, -10.1286] |

Recent minus control is +11.4078 for Seed1 and -0.7017 for Seed3. Both
ordinary and family-adjusted raw/session contrast intervals include zero;
wave-block comparisons also include zero. No replicated benefit is established.
The paired internal final contrasts were -6.3751 and +2.6215, also inconclusive.
Neither internal nor external evidence supports a reproducible positive slope.
This is insufficient strength evidence, not proof that league learning cannot
succeed at larger scale, and not a causal attribution to individual actions.

All 32 session token chains are disjoint from each other and covered prior
evidence. This is an evidence-integrity check, not proof of server RNG independence.
Full session, seat, wave, and multiplicity sensitivity results remain in the
unaltered completed_analysis.json and independently checked review report.

Decision: close the fixed development experiment without selecting a winner,
starting a final benchmark, or automatically scaling this unchanged recipe.
The final-qualification count is zero; four policies cannot be pooled for the
100k frozen-policy goal. Next allocation work should consolidate existing
matched learning curves, own-parent comparisons and measured costs to choose
one justified training continuation or one major algorithmic control. Do not
commission another external cohort merely to resolve a lucky endpoint ranking.

The terminal reviewer was adapted from the qualified prior four-policy reviewer;
only experiment-local location, schema label and test arm labels changed. Runtime,
models, sessions, raw evidence and frozen launch files were not modified.
