# Mirrored self-play deal variance pilot

## Outcome

Decision: `REJECT_MIRRORED_DEALS_NO_ROBUST_GENERAL_GAIN`.

Enabling only `--mirror-self-play-deals` produced a valid 263,437-hand treatment run, but did not improve the untouched all-policy-heads control consistently enough to justify Slumbot evaluation or larger-scale training.

## Training and evidence integrity

- Smoke: 4,112 actual environment hands; 550 mirror sources and 550 replays; both audits passed.
- Production: 263,437 actual environment hands over 64 updates; 35,782 mirror sources and 35,781 replays (71,563 combined, 27.165% of hands).
- The one-hand source/replay difference is an expected terminal carry: each of 12 workers can hold at most one pending mirror. Cumulative pending stayed in `[0, 12]` at every update boundary and ended at 1.
- Fixed opponent pool, assignment RNG/hash chain, global advantage normalization, optimizer state, checkpoint schedule, and artifact hashes passed the terminal audit.
- There were zero PPO KL early stops; maximum source-policy KL was 0.001400875 and maximum clip fraction was 0.0000348772.
- All-in runout EV remained disabled throughout, isolating mirrored self-play deals as the only material treatment.

## Frozen matched evaluation

Each archived checkpoint was evaluated on the untouched seed-20260853 stream for 1,024 mirrored pairs against each of Standard10, slumbot_free, and corrected CFR96. The table reports treatment minus the untouched `adaptive-league-all-heads-pilot-20260830` control in bb/100, with paired 95% half-widths computed from aligned pair outcomes.

| Iteration | Standard10 | slumbot_free | corrected CFR96 |
|---:|---:|---:|---:|
| 16 | -0.195 +/- 0.590 | -0.424 +/- 0.964 | +1.603 +/- 2.007 |
| 32 | +0.098 +/- 1.135 | +0.151 +/- 1.544 | -10.752 +/- 18.518 |
| 48 | -0.757 +/- 0.859 | -0.293 +/- 0.474 | +0.745 +/- 2.191 |
| 64 | +0.293 +/- 0.425 | -0.700 +/- 1.091 | +9.959 +/- 18.445 |

Across the 12 matched rows, 6 point estimates were positive and 6 negative. The mean delta was -0.0225 bb/100 and the median was -0.0488 bb/100. Every paired 95% interval crossed zero. The terminal checkpoint was mixed: +0.293 versus Standard10, -0.700 versus slumbot_free, and +9.959 versus CFR96, with the CFR estimate too noisy to support promotion.

## Interpretation

The implementation and evidence chain are sound, but mirrored replay did not yield a robust general-strength gain at this budget. It also consumes about 27% of the environment-hand budget on replayed self-play deals, so scaling this treatment would displace substantial fresh experience without positive matched evidence.

No Slumbot hands were used. The benchmark claim remains unmet. The next experiment should change the learning signal or data distribution rather than spend more compute on this treatment unchanged.
