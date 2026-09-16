# Frozen weak-KL native-sampled Slumbot pilot

Decision: `SAMPLED_CANDIDATE_NONPOSITIVE`.

Exactly20,000 fresh external hands: **-55.8690bb/100**, raw95% CI **[-93.6089, -18.1291]**.

Session-mean t95 sensitivity interval(df7): [-110.2068, -1.5312]. This is additional sensitivity evidence,not a replacement selected for favorability.

| Session | Fresh hands | bb/100 |
|---|---:|---:|
| part01 | 2500 | -112.9956 |
| part02 | 2500 | -27.5768 |
| part03 | 2500 | -132.7904 |
| part04 | 2500 | +59.0472 |
| part05 | 2500 | -102.8456 |
| part06 | 2500 | -74.7856 |
| part07 | 2500 | +5.7436 |
| part08 | 2500 | -60.7488 |

Policy: unchanged weak-KL final checkpoint, native sample/temp1, SHA256 `a68ac47aad7fa943f0e784e1c14be3d742fac7390a2cd853ba6cb971b429019b`.
All8original clients exited0. Strict hand/session/model/mode/seed/reward/CI/fallback/replay checks passed; the independent review recomputed aggregate CIs directly in chip units, checked all hashes and found no extra raw files.

The original greedy20k baseline is a different policy; its hands are not pooled here and any historical comparison is not a matched causal effect. Observable deal checks cannot prove hidden-deck independence; raw normal CIs assume sufficiently independent outcomes.

Context: native-sampled Standard10 previously scored-48.9778bb/100 on a separate20k. This is unpaired historical context, not a matched treatment effect or pooled evidence.

## Next action

Do not extend this nonpositive pilot. Select the next general learned-weight experiment from the completed evidence; preserve this candidate evidence.

**Goal remains unachieved:**20k is below the required100k, regardless of point estimate or interval.
