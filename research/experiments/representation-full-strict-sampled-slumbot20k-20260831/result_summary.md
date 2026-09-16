# Frozen full-network native-sampled Slumbot pilot

Decision: `SAMPLED_CANDIDATE_NONPOSITIVE`.

Exactly20,000 fresh external hands: **-81.2510bb/100**, raw95% CI **[-123.1600, -39.3420]**.

Session-mean t95 sensitivity interval(df7): [-112.1622, -50.3398]. This is additional sensitivity evidence,not a replacement selected for favorability.

| Session | Fresh hands | bb/100 |
|---|---:|---:|
| part01 | 2500 | -73.7944 |
| part02 | 2500 | -107.2288 |
| part03 | 2500 | -73.1320 |
| part04 | 2500 | -109.2680 |
| part05 | 2500 | -29.7204 |
| part06 | 2500 | -41.3756 |
| part07 | 2500 | -73.5460 |
| part08 | 2500 | -141.9428 |

Policy: unchanged full-network final checkpoint, native sample/temp1, SHA256 `ff2b9e6fe188ac89aa3ff4b632b70a195a46e8e6a73f1b94a75fcfbbf543c17e`.
All8original clients exited0. Strict hand/session/model/mode/seed/reward/CI/fallback/replay checks passed; the independent review recomputed aggregate CIs directly in chip units, checked all hashes and found no extra raw files.

The original greedy20k baseline is a different policy; its hands are not pooled here and any historical comparison is not a matched causal effect. Observable deal checks cannot prove hidden-deck independence; raw normal CIs assume sufficiently independent outcomes.

Context: native-sampled Standard10 previously scored-48.9778bb/100 on a separate20k. This is unpaired historical context, not a matched treatment effect or pooled evidence.

## Next action

Do not extend this nonpositive pilot. Select the next general learned-weight experiment from the completed evidence; preserve this candidate evidence.

**Goal remains unachieved:**20k is below the required100k, regardless of point estimate or interval.
