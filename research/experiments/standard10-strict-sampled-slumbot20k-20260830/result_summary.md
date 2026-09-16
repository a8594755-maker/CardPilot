# Frozen native-sampled Standard10 Slumbot baseline

Decision: `SAMPLED_BASELINE_NONPOSITIVE`.

Exactly20,000 fresh external hands: **-48.9778bb/100**, raw95% CI **[-71.6649, -26.2907]**.

Session-mean t95 sensitivity interval(df7): [-76.2496, -21.7060]. This is additional sensitivity evidence,not a replacement selected for favorability.

| Session | Fresh hands | bb/100 |
|---|---:|---:|
| part01 | 2500 | -20.0608 |
| part02 | 2500 | -43.4504 |
| part03 | 2500 | -73.1584 |
| part04 | 2500 | -64.1064 |
| part05 | 2500 | -66.0032 |
| part06 | 2500 | -66.5112 |
| part07 | 2500 | +17.6072 |
| part08 | 2500 | -76.1392 |

Policy: unchanged Standard10, native sample/temp1, SHA256 `91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428`.
All8original clients exited0. Strict hand/session/model/mode/seed/reward/CI/fallback/replay checks passed; the independent review recomputed aggregate CIs directly in chip units, checked all hashes and found no extra raw files.

The original greedy20k baseline is a different policy; its hands are not pooled here and any historical comparison is not a matched causal effect. Observable deal checks cannot prove hidden-deck independence; raw normal CIs assume sufficiently independent outcomes.

## Next action

Do not extend this nonpositive pilot. Select the next general learned-weight experiment from the completed evidence; preserve this external baseline.

**Goal remains unachieved:**20k is below the required100k, regardless of point estimate or interval.
