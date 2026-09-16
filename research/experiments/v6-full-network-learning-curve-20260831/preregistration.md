# Corrected-v6 full-network physical-budget learning curve

Registered before tests or new training/evaluation on2026-08-31. Parent
v6-physical-training-smoke-20260831 completed11261physical hands,2updates and768
tiny diagnostic hands with intact weights/accounting. Those tiny intervals did
not establish improvement. Contract repair passed88tests and4096independent
oracle trajectories. All legacy and smoke outcomes remain excluded here.

## Hypothesis and fixed training

Full-network PPO can learn broader strength when its actual game rules and policy
execution agree. Test one corrected-contract learning curve before attempting
paper-scale training. There is no matched legacy-contract arm and no claim that
this experiment isolates which historical bug caused external losses.

Start original Standard10 weights SHA256
91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428.
This is a NEW run with explicit v6 binding,fresh Adam,fresh counters,new seeds;
it does not resume or reset any completed experiment. No old replay,optimizer,
pool outcomes or Slumbot hand data are consumed. Old weights' physical lineage
is not inferred or added to new training counts.

Fixed target262144actual completed environment hands,stop at first PPO boundary
reaching target; report overshoot. Learnerseed20260918,workerbase2026091800.
12workers,cuda,4096legacy collection markers,1024minibatch,LR3e-5,PPO2epochs,
targetKL.01,sourceKL.01 from the fixed v6-rebound Standard10 actor,advantageclip3,
entropy.005/floor.05,GN,critic_v2,valuecoef1,stackdivisor200,separatepreflophead,
all86tensors trainable. Adaptive3-anchor league,25%self-play,per-group8,single
rollout,fixeddeals. Same production regimen as smoke except budget,seeds,identity
and archive cadence. Save latest everyupdate,archive every4updates. Operational
runtime cap6000seconds; no automatic restart or output overwrite.

Training anchors are exact v6-rebound copies from the smoke's frozen artifacts:
anchor0(Standard10)944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2,
anchor1(slumbot_free)d942236f1272664576daed3eb624cc2ee3647ad952a47eeb0f4a5185b5679e90,
anchor2(corrected_cfr96)c2c8171a3c06e6b2fca2012b4e693246881586c1e2a1831c0d66935713bca577.
Rebinding changes executed policy semantics but leaves learned tensors unchanged.

First exact command:
python research/experiments/v6-full-network-learning-curve-20260831/run_curve.py

## Counter-only frozen curve and held-out evidence

Retain source and FIRST scheduled4-update archives crossing65536and131072
physical hands,then final checkpoint. Freeze all four only by physical counters,
before any performance results. Never choose a different archive to rescue scores.

Two additional anchors are explicitly rebound to the same v6 contract before
training but NEVER included in this run's training pool/reference:
heldout_weak: original SHAa68ac47aad7fa943f0e784e1c14be3d742fac7390a2cd853ba6cb971b429019b;
heldout_full: original SHAff2b9e6fe188ac89aa3ff4b632b70a195a46e8e6a73f1b94a75fcfbbf543c17e.
They share source/family/historical training with other models. They are held out
from THIS training run,not wholly unseen strategy families. Their old external
outcomes are not used as new-contract performance evidence.

After all training ends, evaluate all4candidates against all5anchors,2048mirrored
pairs per cell,new seed20260919,sampled both sides,temp1,CPUfloat32 network and
float64legal softmax,physical-seat/decision keyed action RNG. Total81920new
internal physical hands. At most2CPU evaluation processes,1torch thread each;
no concurrent GPU trainer/evaluator. Raw paired decks,seat rewards,policy hashes,
exact commands and process outcomes must be retained. Live accounting follows
completed raw-pair evidence,not just the declared evaluation target.

Primary contrasts: final-minus-source on each of5anchors,matched by deck/seat RNG.
Report95%normal and Bonferroni99%intervals (z=2.5758293035489004),familyof5.
Admission to a SEPARATE independent confirmation requires all5points>0,at least3
Bonferroni lower bounds>0,including Standard10 and at least one held-out anchor,
and every accounting/weight/session/evidence check valid. Midpoint and sequential
curve differences are descriptive only. No alternative selection or promotion
route if the final fails. This gate is NOT100k Slumbot qualification or Nash proof.

## Provenance, failure and next decision

Capture full source copies/hashes/dirty patch before launch;test command contract,
counter selection,hash-path typing and statistics/gate before training. No captured
source edits while this wrapper or children run. Preserve terminal interruptions;
never restart based on a polling timeout. Require complete physical prefix,
monotonic checkpoint/manifest/metric counts,finite86changed weight tensors and
Adam states,and fixed-pool assignment/session audit. Then independently recompute
raw paired statistics and verify all source/frozen identities before finish.

If learning curve is weak or negative,analyze optimization health and breadth to
select the next mechanism. If gate passes,run separate independent confirmation
before external admission. Do not extend budget based on observed cell outcomes,
pool prior evidence or launch2.7B/100k merely because this run completes.
