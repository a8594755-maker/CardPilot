# Frozen sampled-policy diagnostic

## Outcome

Decision: `NO_CONFIRMABLE_SAMPLED_GENERAL_GAIN`.

The trainer samples categorical actions for hero and opponents, whereas the previous internal evaluator always used greedy argmax. This experiment added a tested, opt-in sampled-both-sides evaluator and tested existing frozen weights without changing them. Neither learned candidate met the preregistered cross-anchor confirmation condition. The wider sampled confidence intervals do not exclude small improvements; they provide no confirmable general gain to scale or send to Slumbot.

## Evaluation contract

- Greedy argmax remains the default and old greedy artifacts are unchanged.
- Sampled actions use masked categorical probabilities and counter-based uniforms indexed by seed, pair, physical seat, and per-seat decision count. The action stream is separate from deck generation and shared across mirrored seats and compared checkpoints.
- Six new tests and five existing paired-return tests passed, including inverse-CDF legality/probabilities, RNG reproducibility, exact identical-policy mirror cancellation, greedy compatibility, and rejection of mismatched action streams.
- A real Standard10 self-match smoke completed 64 pairs with exactly 0 bb/100 and 0 CI half-width.
- The preregistered matrix used seed 20260881, 4,096 mirrored pairs per anchor, 200bb stacks, and the unchanged Standard10, slumbot_free, and corrected CFR96 anchors.
- Frozen policies: Standard10 source; untouched all-heads iter64 at legacy counter 263,602; paired-actor iter64 at legacy counter 263,479.
- All three matrix executions completed, every OOD gate passed, and checkpoint hashes matched before/after evaluation. No checkpoint or training evidence was modified.
- Accounting: 73,856 internal evaluation hands including smoke; zero new training hands and zero Slumbot hands.

## Matched results

Values are treatment minus control in bb/100 with paired 95% half-widths from 4,096 aligned pair outcomes per cell.

| Comparison | Standard10 anchor | slumbot_free | corrected CFR96 |
|---|---:|---:|---:|
| All-heads iter64 minus source | -0.642 +/- 8.382 | +0.288 +/- 5.995 | +1.684 +/- 15.928 |
| Paired actor iter64 minus source | -4.036 +/- 6.615 | +0.996 +/- 6.005 | +0.024 +/- 13.646 |
| Paired actor minus all-heads iter64 | -3.393 +/- 5.202 | +0.708 +/- 0.569 | -1.660 +/- 8.188 |

The primary candidate-versus-source comparisons each had two positive point estimates and one negative, with all primary intervals crossing zero. The secondary paired-actor-versus-control comparison had one positive lower bound only on slumbot_free and negative points on the other two anchors. No comparison was point-positive across all three anchors, so no independent-seed confirmation was triggered.

## Next prerequisite

Read-only inspection during this evaluation found that train_v5 total_hands counts transition-bearing hand markers and omits hands where the trainable seat never acts. In the paired pilot, emitted source/mirror counters cover at least 316,700 physical environment hands despite the legacy counter of 263,479. Future scaling must separate physical environment hands from decision-bearing training hands and preserve old checkpoint/resume semantics. No further training should start until that accounting contract is made explicit and audited.

The formal 100,000-fresh-hand Slumbot benchmark remains unmet.
