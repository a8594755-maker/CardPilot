# Current execution alignment allocation

The latest independent-critic trial is complete, not a running recovery. No
additional training or Slumbot cohort is allocated by this review.

The current PPO recipe samples both sides at temperature 1, while
v6_public_opponent_matched_eval calls v6_elo_eval.summarize_models, whose action
route uses legal-logit argmax. A flat greedy curve does not measure the sampled
objective. This logical distinction does NOT demonstrate that execution mismatch
caused the current plateau or that sampled deployment will be stronger.

Historical constraints, retained rather than rerun:

- The 20260830 sampled-policy diagnostic already completed 73,856 internal
  executions without confirmed cross-anchor gains. Different legacy lineage and
  earlier contracts prevent treating it as the current two-seed result.
- Greedy advantage-margin smoke: 21,494 training hands, contrast -0.266 with
  CI [-45.252,44.720]. Inconclusive small-dose evidence, not a general impossibility.
- Source-KL-temperature's selected external 5k result was -142.7232 with
  CI [-200.6425,-84.8039]. Its positive internal proxy failed to transfer.
- Recent two-seed opponent execution mixture did not demonstrate replicated
  improvement at 1M. Opponent execution mixing is not hero sampled evaluation.
- Latest critic treatment costs about 30.4% extra training time with mixed pooled
  and negative transfer-panel contrast points. Do not promote that architecture.

## Selected next work

Qualify an isolated physical-v6, legacy-observation sampled evaluator using the
same network/legal mapping as the current greedy evaluator. Use explicit keyed
action randomness independent of deck generation, player-local decision counters,
temperature 1, both seats and durable per-deck outcomes. Tests must cover finite
legal categorical selection, fixed-key reproducibility, distinct action streams,
same-policy matched cancellation and greedy-route parity. Do not use the legacy
v5 environment merely because it already supports sampling.

Then preregister one frozen endpoint comparison, without new learned updates:
two seeds, original fixed2M parents versus the completed critic trial's CONTROL
1M endpoints, eight fixed anchors, 1024 mirrored decks per anchor per seed,
sampled both sides. Four executions per paired row give 65,536 evaluation hands
and 16,384 distinct decks. Freeze actual new deck/action seeds and input hashes
before execution and check against existing evaluation evidence. Do not choose
independent-critic endpoints based on isolated favorable anchors.

Assess own-parent change across seeds, seats and preservation/transfer panels.
The earlier greedy results are context, not a paired cross-mode causal contrast
because their decks differ. If sampled breadth is positive across both seeds,
predeclare a fresh cross-mode/external calibration before major scale. If sampled
results are also flat, reject the hidden-sampled-gain explanation at measured
precision and change a substantive learning component, not another architecture
micro-variant. If uncertain, quantify detectable gains and allocation cost rather
than claiming either success or algorithm failure. No automatic large scale.

This is a bounded allocation decision, zero new poker hands and no stronger model.
Next action is evaluator implementation and qualification, not another survey.
