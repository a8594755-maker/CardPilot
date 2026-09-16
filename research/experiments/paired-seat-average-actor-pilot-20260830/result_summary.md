# Paired seat-average actor-return pilot

## Outcome

Decision: `REJECT_PAIRED_ACTOR_NO_ROBUST_GENERAL_GAIN`.

Pair-averaging actor terminal rewards consistently reduced their variance, but a production run ending at legacy marker counter 263,479 did not improve the frozen learned policy robustly over the untouched adaptive-league all-heads control. Its emitted paired evidence covers at least 316,700 physical environment hands; the exact historical worker-tail count is unavailable. No scaling or Slumbot evaluation is justified for this treatment unchanged.

## Contract and smoke recovery

- Every fixed-stream deal was mirrored against the same opponent with source player p mapped to mirror player 1-p.
- Raw realized transition rewards remained untouched for critic learning and league accounting. Only actor terminal rewards used the mean of the two seat-swapped returns.
- The first smoke failed before any accounted PPO update because some trainable seats have no policy decision. The initialized 0-hand evidence was preserved; pairing was repaired to use full per-player terminal rewards.
- Smoke2 completed 536 hands, but variance metrics were not persisted. Its evidence was preserved. Smoke3 completed 530 hands after persistence was repaired and passed the variance/session gate (variance ratio 0.644932).
- Relevant regression suite: 25 passed. Production used the same frozen-trunk all-policy-head configuration as the untouched fresh-only control, with the paired actor contract as the treatment.

## Production and integrity

- 263,479 legacy transition-bearing hand markers, 64 updates, no interruption or resume boundary. Historical physical work is at least 316,700 completed emitted paired hands, not exactly the marker counter.
- Fixed-pool/session audit PASS: 64 assignment records, pending=null, immutable three-opponent pool, optimizer state count 10 with step 1818, and all four archive hashes verified.
- Paired-session audit PASS: all 64 source/mirror counts balanced, 158,350 collected matched pairs, and 321,784 actor override rows all terminal-only.
- Actor/raw terminal variance ratio was below one in every batch: mean 0.557981, minimum 0.480354, maximum 0.639704.
- Zero KL early stops; maximum reference-policy KL 0.000760777; maximum clip fraction 0.00009765625.
- Archives: iter16=65,912 hands, iter32=131,818, iter48=197,655, iter64=263,479.
- Total legacy markers including completed smokes: 264,545. Evidence-backed physical lower bound including both completed smokes: 317,800 (316,700 + 550 + 550); unsaved tails and the failed pre-update smoke cannot be reconstructed exactly. Evaluation: 24,576 internal hands. Slumbot: 0.

## Frozen matched curve

Every checkpoint used seed 20260853, 1,024 mirrored pairs per anchor, 200bb stacks, and greedy argmax on both sides. The untouched control files were not modified. All OOD/mirror validity checks passed. Values below are treatment minus the matching `adaptive-league-all-heads-pilot-20260830` checkpoint, in bb/100 with paired 95% half-widths. Training checkpoints were matched by the historical marker-counter/update budget, not by exactly known physical-environment work.

| Iteration | Standard10 | slumbot_free | corrected CFR96 |
|---:|---:|---:|---:|
| 16 | +0.415 +/- 0.878 | -0.895 +/- 1.224 | +0.548 +/- 2.922 |
| 32 | -0.146 +/- 0.818 | -0.457 +/- 0.948 | -11.881 +/- 18.514 |
| 48 | -0.146 +/- 0.449 | -0.188 +/- 0.975 | -0.008 +/- 1.521 |
| 64 | +0.635 +/- 0.553 | -0.090 +/- 0.956 | -0.220 +/- 1.738 |

Only 3/12 point estimates were positive. Mean delta was -1.036051 bb/100 and median -0.146484. One interval (iter64 versus Standard10) had a positive lower bound, but the other anchors did not improve and the curve was not consistently positive. This is not evidence of general policy-strength improvement.

## Next information target

The treatment demonstrates a usable actor-only reward channel but does not justify more hands unchanged. Before another training variant, audit the mismatch between stochastic training (`hero-policy-mode sample`) and the exclusively greedy-argmax internal evaluation. A frozen sampled-policy diagnostic can determine whether learned distributional changes are being missed by the current evaluator, without creating more training hands or adding benchmark-specific rules.

The formal 100,000-fresh-hand Slumbot benchmark remains unmet.
