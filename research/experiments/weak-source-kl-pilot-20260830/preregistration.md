# Matched source-KL weakening pilot

Registered before any training in this experiment. Parent sampled Standard10
external baseline completed20,000fresh hands at-48.9778bb/100,95%CI
[-71.66494934,-26.29065066],with passing strict evidence and independent review.
Its hands are not reused for optimization or validation. No new Slumbot test is
planned here. The transport change alters no learned weights or action rules.

## Why this hypothesis

The earlier component-gradient study did not find persistent instantaneous PPO
gradient cancellation. That result does not measure accumulated anchoring to the
starting policy. The one-million-hand all-heads curve with source-KL1 failed its
independent multi-anchor replication; the source itself now has a clearly negative
native-sampled external baseline. Test weaker anchoring as a single learning
variable, not a claim that constraints are necessarily the bottleneck. Prior
full-network pilot also changed scope/LR/KL jointly and is not this intervention.

## Fixed training design

Control coefficient1; treatment coefficient0.01 (100x weaker, not zero). Both use
the same reference-model loading and diagnostic path, avoiding a different RNG
initialization path from omitting the reference model. Both keep native sampling,
all policy heads plus value heads trainable and76representation tensors frozen,
source/checkpoint SHA91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428,
fresh Adam and explicitly reset experiment-local physical counters. Historical
source/checkpoint/counters remain untouched; its physical lineage is not claimed.

Each arm:262144new **physical completed environment hands**, allowed endpoint
overshoot at PPO boundaries, not a legacy transition-marker budget. Same seed
20260907,worker seed base2026090700;12workers,cuda,200bb,v55preflopv2v4obs,GN,
collection4096transition-bearing markers,minibatch1024,LR3e-5,PPO2epochs,target
KL0.01,advantage clip3,entropy0.005/floor0.05,critic_v2/divisor200/valuecoef1.
Use existing identical adaptive three-anchor league plus25%self-play,per-group8,
single-rollout,fixed training-deal stream. Save every update,archive every4;
max runtime7200seconds per arm. Final endpoint selection only; archives are not
candidates for rescue. Same seeds/physical budget do not imply identical realized
trajectories, worker tails or number of updates after policies diverge.

Anchors are original Standard10, preserved slumbot_free_anchor_position10m and
corrected_cfr96_anchor10; their exact paths/hashes are fixed in run_pilot.py.
The latter two and control/source tests are diagnostics,not proof of general Nash
strength or a wholly unseen opponent population.

Both runs are new experiments from original source, not resumes of any completed
pilot. Counters update from physical evidence while running. Keep full execution
source copies/patch/hashes, commands, manifests, assignment chains, metrics,
optimizer state and final frozen copies. On terminal failure preserve state;
never automatically restart/reset or substitute another checkpoint. No source
edits while this wrapper is live. Use only owned processes and do not interrupt
unrelated work. Existing validated1024-minibatch memory feasibility is reused.

## Frozen evaluation and decision

After both audited physical endpoints, evaluate original source, matched control,
and weak-KL treatment on all3anchors using untouched deal/action seed20260908,
4096mirrored pairs per anchor per candidate (73728internal physical hands), native
sampled_both_sides,temp1 and existing physical-seat keyed common random actions.
Save all pair/seat outcomes and source/model/command hashes; verify physical-seat
arithmetic, streams and counts; independently recompute paired deltas and CIs.

Primary: weak-minus-control per anchor. Admission to a **separate independent
confirmation only** requires all3positive point estimates, at least1positive
Bonferroni98.333%lower bound across these3primary contrasts, no negative
weak-minus-original-source point estimate, and all integrity/OOD-valid checks.
Report nominal95% and adjusted intervals; do not substitute the more favorable
one for this registered gate. Control-minus-source is descriptive; no alternate
control endpoint selection or pooled historical data. This pilot and its selected
gate do not establish a formal external result.

Before finishing, inspect finite model/Adam updates, exact frozen-trunk scope,
per-update KL/clip health and both session audits, then close this same record.
If gate fails, do not extend or promote these checkpoints; select another
mechanism/general-learning direction. If it passes, only a new independent
multi-anchor confirmation is admitted,not Slumbot promotion or paper-scale work.
