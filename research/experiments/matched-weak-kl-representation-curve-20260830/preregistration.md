# Matched weak-KL representation-scope learning curve

Registered before tests, synthetic profiling or any new poker hands. Parent
weak-kl-strict-sampled-slumbot20k-20260830 finished exactly20000fresh hands,
-55.869bb/100,95%CI[-93.60892586,-18.12907414],with intact strict evidence.
Do not extend that pilot, reinterpret it as positive or reuse its hands to train.

## Evidence and intervention

Weak-source-KL training produced meaningful head-weight movement and independently
replicated improvement concentrated against CFR96. It did not demonstrate general
external strength. Its sampled Standard10 comparison was not significantly
different from the previous unpaired external baseline. The older full-network
pilot changed parameter scope,LR and KL together; it cannot isolate representation.

Test parameter scope ONLY between newly matched arms: heads trains native preflop,
postflop and value heads,freezing76representation tensors; full trains all existing
parameters. Both use source-KL0.01,legacy KL(reference||current),fixed original
Standard10 reference. This is not NashPG. Retain the current architecture and all
deployment semantics; do not add benchmark-specific action rules or overrides.

Both start from original Standard10 SHA256
91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428,
fresh Adam,explicit NEW-experiment counter reset,seed20260911,worker seed2026091100.
These are not resumes of any completed experiment. Historical source lineage is
unknown in physical-hand units and is not counted as new work.

Per arm fixed524288physical completed environment hands,checked at PPO boundaries
with overshoot reported. This is2x the previous stable weak-KL budget,not a blind
paper-scale launch.12workers,cuda,collection4096legacy transition-bearing markers,
minibatch1024,LR3e-5,PPO2epochs,targetKL0.01,advantageclip3,entropy0.005/floor0.05,
critic_v2,valuecoef1,stackdivisor200,200bb,v55preflopv2v4obs,GN,separatepreflophead.
Same adaptive3-anchor league(Standard10,slumbot_free,corrected_cfr96),25%self-play,
per-group8,single rollout,fixed deal stream. Shared seeds do not imply identical
trajectories,worker tails or optimizer-step counts after policies diverge.
Save latest each update,archive each4updates. Each arm max operational runtime
10800seconds. Run heads then full; no concurrent GPU learner/evaluator.

## Feasibility,source and stopping

First synthetic full-network forward/backward/Adam profiling at1024batch while
retaining32768rollout input rows must pass finite loss/gradients/weights,all76
representation tensors changed and GPU peak allocated<80%device capacity.
Scratch weights are discarded and count as zero environment hands. Source hash
must remain unchanged. Match command-contract,raw-statistics and gate unit tests.
Capture all execution source,preregistration,tests,exact commands and dirty patch
before either trainer. Do not edit captured sources while wrapper is live.

No outcome-dependent early stopping,extension or checkpoint replacement. On
terminal errors preserve all optimizer/checkpoint/counters/evidence; no automatic
restart. Absence of output/time-limited tool wait is not failure. Update record
physical accounting from persisted manifests during training. No Slumbot hands.

## Frozen curve and untouched evaluation

For each arm retain the FIRST scheduled archival checkpoint whose measured
physical count>=262144,plus its final completed524288target checkpoint. The curve
point can overshoot by up to the next4-update archive; report actual counts.
Choose by counters only after each arm finishes. Never substitute an earlier
checkpoint based on its score. Compare5candidates:source,heads_mid,heads_final,
full_mid,full_final. Both final points are the only primary treatment endpoints.

All5candidates evaluated AFTER both training arms finish on untouched seed20260912,
4096mirrored pairs per opponent,4opponents,total163840internal physical hands.
Native sampled_both_sides,temp1,physical-seat-keyed common action RNG. The first3
opponents are the fixed league anchors. Fourth is the frozen previous weak-KL
checkpoint SHA256 a68ac47aad7fa943f0e784e1c14be3d742fac7390a2cd853ba6cb971b429019b,
excluded from this experiment's training pool/reference. It is held OUT of this
training run,not a never-observed opponent family; it shares earlier league/source
lineage and failed its own external pilot. Do not claim fully unseen-population
generalization. Its Slumbot histories are not loaded for optimization/evaluation.

Record full pair/seat arrays,model/source hashes,seed/temperature/stack/anchor
identity,clean process exits,OOD counts and independent arithmetic. Recompute
paired full_final-minus-heads_final per opponent,95%normal and Bonferroni98.75%
intervals over the4primary contrasts. Intermediate curves are descriptive only.

Admission to a SEPARATE independent confirmation requires all4primary points>0,
at least2Bonferroni lower bounds>0,including Standard10 or heldout weak opponent,
and all4full_final-minus-source points>=0,with all integrity/OOD gates valid.
Thus another CFR96-only gain is insufficient. Do not change this gate after seeing
results. Source/head changes and mid/final curves remain descriptive; there is no
alternate candidate admission route. This internal gate does not establish Nash
strength,external win rate or the100000fresh-hand Goal.

After both arms and fixed matrix,independently audit finite model/Adam state,
training scope,physical accounting,assignment/session chains,raw cell statistics
and all paired contrasts;then finish the same experiment. If failed,do not extend
or select archives for rescue. Select a distinct next mechanism from the evidence.
