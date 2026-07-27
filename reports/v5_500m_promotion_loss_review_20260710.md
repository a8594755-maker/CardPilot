# V5 500M Promotion Loss Review

Checked at `2026-07-10 14:10 EDT`.

## Verdict

The gate30700 official greedy-direct promotion is a complete, audited
`promotion20k` result, but it is decisively non-strong:

- frozen checkpoint: `30700 / 504,474,081`
- hands: `20,400`
- score: `-153.300 bb/100`
- 95% CI: `[-187.695, -118.905]`
- fresh V4 current-harness baseline: `-71.383 bb/100`, CI
  `[-92.222, -50.543]`
- delta versus V4: `-81.917 bb/100`
- `promotion_20k_candidate=false`, `promotion_20k_strong=false`, L0

Formal100k is blocked. No stronger-than-V4, L5, or L6 claim is allowed.

## Artifact completeness

The CI summary, promotion gate, selector replay, loss report, artifact audit,
and hand review all exist. Artifact audit and hand review are `PASS`; selector
replay is clean. The result is valid promotion-scale evidence and is not a
formal strength claim.

## Required loss cuts

- Position: BB `-167.341 bb/100`, SB `-139.259 bb/100` over 10,200 hands each.
  BB is the larger positional leak.
- Terminal: hero-fold `-3,683,652` chips (`-496.315 bb/100` within bucket),
  showdown `-1,292,401` chips (`-159.536`), all-in runout `-800,000`, offset by
  opponent-fold `+2,648,736`.
- Street: hero folds lose `-1,210,740` on turn, `-1,148,212` on flop,
  `-704,950` preflop, and `-619,750` on river. Runout loss is only 113 hands and
  is not a standalone tuning basis.
- First preflop decision: BB versus sub-2.5bb open, raise to 4-8bb loses
  `-1,544,000` chips over 7,020 hands (`-219.943 bb/100`). SB sub-2.5bb open
  raise loses `-1,252,993` over 8,427 hands (`-148.688`).
- Rates: SB fold/call/raise/all-in = `1.6% / 15.8% / 82.6% / 0%`; BB versus
  open call/raise = `6.6% / 76.3%`.
- Top line: `O:b200 H:b400 O:c` loses `-1,033,527` chips over 4,611 hands.
  Larger raise-war lines add concentrated losses.
- Hole families: other offsuit is worst at `-2,392,215` chips
  (`-215.360 bb/100` over 11,108); broadway offsuit `-164.528`, suited
  connector `-147.939`, other suited `-119.093`. Pairs and ace offsuit are
  positive, so this is not uniform card-strength failure.

## Stable mechanism across official checkpoints

The repeated signal is distribution instability, not a single fixed action
direction:

- 250M promotion: SB call/raise `49.6% / 37.8%`; BB call/raise
  `21.0% / 20.5%`; score `-140.151 bb/100`.
- 500M promotion: SB call/raise `15.8% / 82.6%`; BB call/raise
  `6.6% / 76.3%`; score `-153.300 bb/100`.
- BB moved from `-125.160` to `-167.341 bb/100`; the top first-decision loss
  moved from SB small-open to BB small-open 3bet.
- Exact-gate preflop PASS/WARN states and internal deltas repeatedly switch
  sign. The fixed pre-500M diagnostic already passed every EXP-005 structural
  support check.

This agrees with audit problem M3: `per-iteration` assigns every worker to one
opponent distribution for a full PPO update, then changes it discontinuously.
It explains passive-to-aggressive lurching better than a static handcrafted
prior leak.

## Why EXP-006A is not selected

The frozen 1,000-row direct PPO gate did not pass its full support rule:
KL>0.10 fraction was `0.049 < 0.10` and mean clip fraction was
`0.244539 < 0.25`. EXP-006A therefore remains unsupported. It must not be
bundled with EXP-005.

## Decision

Register and implement exactly one next behavior experiment: EXP-005 group
opponent assignment. Preserve EXP-002, EXP-003 configuration, EXP-004 prior
floor `0.01/0.02`, architecture, PPO math, pool strategy, and official greedy
policy. Do not add a handcrafted action prior.

