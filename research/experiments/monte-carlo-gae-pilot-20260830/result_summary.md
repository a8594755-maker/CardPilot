# Monte-Carlo hand-return GAE pilot

## Outcome

Decision: `REJECT_MONTE_CARLO_GAE_NO_ROBUST_GAIN`.

Changing only GAE lambda from 0.95 to 1.0 produced a valid 263,581-hand treatment run, but weakened the matched multi-anchor curve overall and did not justify confirmation or Slumbot evaluation.

## Training and integrity

- A synthetic two-hand terminal-block check verified that lambda 1.0 returns equal exact discounted full-hand returns without crossing hand boundaries.
- Smoke: 4,136 actual environment hands; manifest lambda 1.0; fixed-pool terminal audit passed.
- Production: 263,581 actual environment hands over 64 updates; manifest lambda 1.0; fixed-pool terminal audit passed.
- The immutable three-anchor pool, assignment RNG/hash chain, global advantage normalization, optimizer state, architecture, and four archive boundaries/hashes were verified.
- Maximum source-policy KL was 0.00120513, maximum PPO clip fraction was zero, and there were zero KL early stops.
- No replay, mirrored deals, all-in EV, CFR targets, architecture change, or opponent-pool change was bundled into the treatment.

## Frozen matched evaluation

Each archived checkpoint was evaluated on the untouched seed-20260853 stream for 1,024 mirrored pairs against Standard10, slumbot_free, and corrected CFR96. Values below are lambda-1 treatment minus the untouched lambda-0.95 `adaptive-league-all-heads-pilot-20260830` control in bb/100 with paired 95% half-widths.

| Iteration | Standard10 | slumbot_free | corrected CFR96 |
|---:|---:|---:|---:|
| 16 | -0.122 +/- 0.519 | -0.391 +/- 0.579 | +0.305 +/- 2.239 |
| 32 | -0.928 +/- 1.101 | -1.949 +/- 2.244 | -10.237 +/- 18.490 |
| 48 | -0.171 +/- 0.620 | -0.708 +/- 0.875 | -0.760 +/- 2.202 |
| 64 | +0.342 +/- 0.826 | +0.348 +/- 0.642 | -0.597 +/- 1.454 |

Only 3 of 12 point estimates were positive and 9 were negative. The mean delta was -1.239 bb/100 and the median was -0.494 bb/100. Every paired 95% interval crossed zero, and no checkpoint improved all three anchors. The terminal checkpoint was mildly positive against the two lower-variance anchors but negative against CFR96; none of those terminal effects was significant.

## Interpretation

Full-hand Monte-Carlo actor credit is mechanically correct and numerically stable, but eliminating lambda-0.95 critic bootstrapping did not improve general learned-policy strength at this budget. The result argues against actor bootstrap bias being the main bottleneck in the current head-only PPO lineage.

No Slumbot hands were used. The formal benchmark remains unmet. Do not scale this treatment unchanged; the next direction should change the optimization target or policy-learning data more substantially.
