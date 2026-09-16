# Actual PPO graph route: source/config inspection, not a new update experiment

Inspected during the first detached control cell on2026-09-06. Controller and
trainer identities remain live; no source, optimizer, checkpoint, run command or
logger was changed. Attach this note after sole-owner exit. No new poker hands or
offline optimizer/model queries were requested by this inspection.

Frozen candidate sources:

- train_v5.py SHA bcce947477fdcf6593b7a88ce6845bf5638ce6698b9462deeecf4133b05472e6
- network_hybrid_h1.py SHA07350adfc79db5e81d5d978751492aad443aa72d493ff4f9c3cec5774c2840f8
- train_mp3_hybrid_h1.py SHA7b2ddf2e013782d4e439492ce1832467eb8ca9c89f26e117f0caac11eace8b33
- preflop_gradient_contract.py SHAff5d15ad75bcfbee411fcacf35d5341e198f6a625eac54f4fc1971bbcd70458f

## Observed actual control configuration

The active manifest has separate_preflop_head=true, preflop_trunk_gradient=false,
critic_contract=critic_v2, critic_head_only_gradient=false, policy_postflop_only=false,
preflop_teacher_coef=0, action_q_advantage=false, opponent_seat_mgda=false,
source_policy_kl_coef=1 and direction=current_to_reference. Context/action priors,
greedy margin coefficients and gradient diagnostic switches inspected here are0.
Connected jobs have not been launched at the time of this inspection; their
prospective sole command difference and later initial-state flag audit remain
the authority for admitting that treatment.

## Trace through the production update function

train_v5.py passes the same model object and these configuration values into
trinal_clip_ppo_update. In train_mp3_hybrid_h1.py:

- The ordinary action_q_advantage=false branch calls model(...) for logits/value
  inside the autocast context, not torch.no_grad, around lines1908-1921.
- policy_postflop_only=false selects all minibatch rows for actor/entropy at
  lines1928-1932, and all rows for the reference KL around lines1962-1968.
- Only the fixed reference-policy forward is evaluated under no_grad. The
  current model logits feed categorical_policy_kl and the actor loss.
- PPO surrogate, entropy and reference KL enter actor_loss, then
  loss=actor_loss+value_coef*vloss around lines2245-2273.
- With the observed action-Q, critic-head-only and MGDA switches false, the
  ordinary branch executes loss.backward(), global model-parameter norm clipping
  and optimizer.step() around lines2452-2459. It does not overwrite the actor
  gradient with an MGDA projection or recompute an independently detached actor.

Thus the network's opt-in preflop feature route is connected to the actual PPO
actor graph, not just the earlier logit/cross-entropy probes. This establishes a
reachable gradient path given the inspected configuration and frozen sources;
it does not measure the realized useful gradient on every minibatch, rule out
clipping/cancellation, prove successful learning, or substitute for the later
actual connected initial-state and endpoint audits.

## Important interpretation limit: clipping still couples parameter groups

critic_v2 blocks the value loss's DIRECT gradient to shared features. However,
critic_head_only_gradient=false means the unchanged PPO update clips all model
parameter gradients by one global norm. A new preflop body gradient can change
that norm and therefore can also change clipped head/critic update magnitudes.
This occurs only when the clipping/dynamics make it relevant; no magnitude or
causal contribution has been estimated here.

The qualification's paired diagnostic CE/zero-value-target Adam fixtures differed
only in body parameters because they did not execute this full PPO clipping
procedure. Their stated narrow result must not be generalized to claim that only
body weights differ in the live learned-weight experiment. The actual treatment is
the overall preflop actor-graph connection under the retained optimizer/clipping
regimen, including PPO, entropy and KL, as preregistered. Separating critic/actor
clipping would be a second intervention and is NOT introduced mid-run.

Both control and treatment retain identical clipping rules. Report realized
optimizer steps, KL stops, learning curves and breadth after complete endpoints;
do not label the global clipping rule a newly established failure or infer that
unclipped gradients would improve poker. The existing fixed allocation is intact.
