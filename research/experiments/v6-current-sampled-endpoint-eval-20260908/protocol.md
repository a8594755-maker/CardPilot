# Frozen current-lineage sampled endpoint evaluation

No learned updates. Compare original fixed2M Seed1/Seed3 parents to the completed
independent-critic trial's CONTROL stage2 endpoints, not the treatment. Keep its
eight named anchors in order. All models execute legal temperature-1 categorical
actions with physical-v6 200bb and legacy-v4 observations. Deck seeds are
202609087101 (Seed1), 202609087301 (Seed3), anchor stride1000003. Separate action
seeds are 202609088101/202609088301 with the same anchor stride. Action keys include
pair index, physical player and player-local decision count, not model identity;
paired policies share uniforms deliberately. All future input hashes are frozen
in contract.json before the first evaluation hand.

1024 decks per anchor,8 anchors,2 seeds,4 executions per deck:65536 hands on16384
distinct decks. Check new decks against retained prior evaluation corpus, latest
critic trial and sampled qualification fixtures before launch. This is an internal
development comparison, not a Slumbot blind cohort or unseen-opponent test.

Run all fixed pairs without outcome-based stopping. Exclusive outputs, no automatic
retry after failure. On interruption preserve raw evidence and account for any
unrecorded in-flight suffix before further work. Each completed hand is journaled;
the paired summary is secondary. Runner owns experiment accounting while live.

Review raw rows, exact prescribed decks, action keys, four distinct policy/seat
cells per deck, finite bounded rewards, counts and immutable inputs. Compute
endpoint-minus-parent seat-averaged paired mean and conditional unadjusted normal
95% CI per seed, seat, anchor and first4 preservation/last4 transfer panels.
Positive pooled and both panels in both seeds with no replicated negative seat
direction constitute directional support, not proof of general superiority.
Use existing greedy results only as context, not a paired cross-mode estimate.
No automatic training scale or Slumbot allocation. A positive signal requires
fresh external/cross-mode calibration; absent support redirect substantive learning
work while retaining uncertainty rather than declaring all long-run learning futile.
