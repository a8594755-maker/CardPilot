# ELO K-best league pilot result

## Accounting and integrity

- Smoke plus live resume probe: 1,097 actual environment hands and 736 tournament evaluation hands.
- Production: 263,463 actual environment hands (64 updates; target 262,144).
- Production ELO competition: 8 deterministic mirrored round robins, 27,136 evaluation hands, zero OOD decisions.
- Frozen multi-anchor curve: four checkpoints × three anchors × 2,048 hands = 24,576 fresh evaluation hands.
- Total experiment accounting: 264,560 new training hands and 52,448 evaluation hands.
- Terminal audit: PASS for 64 contiguous metric/assignment rows, checkpoint-backed ELO JSONL hash chain, optimizer state, final pool identity, and all four archive SHA256/boundaries.

## Matched treatment minus untouched all-heads control (bb/100)

| Iteration | Standard10 | slumbot_free | corrected_cfr96 |
|---:|---:|---:|---:|
| 16 | -0.146 ± 1.109 | -0.690 ± 0.965 | +2.250 ± 2.853 |
| 32 | -0.195 ± 1.087 | -0.188 ± 1.400 | -10.062 ± 18.511 |
| 48 | -0.439 ± 0.870 | -0.536 ± 1.614 | +10.230 ± 18.485 |
| 64 | +0.513 ± 0.668 | +0.347 ± 0.637 | -1.390 ± 2.153 |

Only 4/12 point estimates were positive. The mean delta was -0.026 bb/100,
the median was -0.191 bb/100, no checkpoint improved all three anchors, and
every paired confidence interval crossed zero.

## Decision

`REJECT_ELO_KBEST_NO_ROBUST_GENERAL_GAIN`

The implementation and resume/evidence semantics passed, and the survivor pool
made nontrivial accept/reject decisions. However, replacing loss-proxy selection
with paper-mechanism ELO competition did not improve the preregistered robust
fresh-only curve over the matched control. No Slumbot gate is authorized.
