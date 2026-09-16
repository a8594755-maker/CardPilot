# Matched optimizer-regimen pilot

Registered after source/mature whole-hand probes both met the prior noise criterion. This pilot tests a joint batch/LR regimen, not a pure causal batch ablation and not a paper-scale replication.

## Fixed arms

| Setting | Control | Large-batch treatment |
|---|---:|---:|
| Optimizer minibatch transitions |1024|16384|
| Initial LR |0.00003|0.0003|
| Marker hands collected per PPO update |8192|8192|
| Physical terminal-hand budget |131072|131072|
| PPO epochs |2|2|
| Training seed / worker seed base |20260898 /2026089800|20260898 /2026089800|

Both start from original Standard10 with fresh Adam and a new local counter; do not reuse either diagnostic cohort's output. All-policy-heads/value-only updates,sourceKL1,advantage clip3,entropy.005/floor.05,critic_v2,12workers,25%selfplay,three unchanged fixed anchors with the same adaptive league, and single rollouts remain common. The common collection size is increased relative to the earlier1M run so full16384-row minibatches can occur; it is **not different between these arms**. Partial final minibatches and physical-target overshoot remain possible and must be reported. Archive every4 updates plus final. Each arm has a7200-second guard.

Tenfold LR partly compensates for roughly16-fold fewer optimizer steps per data pass; it is not claimed optimal. Actual Adam step counts,partial batch sizes,KL stops and numerical health are essential for interpretation. Shared seeds do not make trajectories bitwise identical after policies diverge or worker timing differs.

## Hardware gate

Before any production hand, a scratch synthetic profile held32768 input rows resident and ran finite forward/backward/Adam steps at1024 and16384 batch. The16384 peak allocated823134720bytes (6.39% device capacity), below the predeclared80% limit. Scratch weights were discarded, original source SHA unchanged,zero environment hands. This is capacity evidence,not poker training evidence. No silent batch reduction or automatic OOM retry is allowed.

## Frozen assessment

Train control then treatment, freeze each final endpoint by physical budget only. Evaluate original source,control,large in that order with sampled_both_sides,temperature1,stack200,seed20260899,4096 mirrored pairs per each of Standard10/slumbot_free/CFR96:73728 total independent internal hands. Keep the same three anchor SHA256 identities in run_pilot.py. Common per-anchor deck/action random streams permit paired deltas; do not reuse old discovery hands.

Primary contrast: large minus matched control. Also report large minus original source and control minus original source. Admission requires valid raw/OOD/hash evidence,positive primary point estimates on all3 anchors,at least one positive nominal95% primary lower bound,and nonnegative large-minus-source points on all3 anchors. Report Bonferroni98.333% secondary intervals; do not interpret the one-of-three nominal gate as familywise significance. Any admitted result requires a separately preregistered independent confirmation. No optional extra hands,seeds,checkpoint selection,temperature adjustment,Slumbot games or paper-scale expansion occurs here.

## Integrity and completion

14 preflight tests cover arm differences,raw evidence counts/identity/streams,rejected malformed evidence,zero self cancellation,and admission logic. The complete Python execution source is snapshotted before both arms; source and input-model hashes are checked around each phase. The single wrapper updates physical accounting after persisted iterations and evaluation accounting after complete cells. It never overwrites existing arm or matrix output and never automatically restarts a failed process.

Run `python research/experiments/large-batch-optimizer-regimen-pilot-20260830/run_pilot.py` once. This trains both arms,audits sessions,freezes final checkpoints,and performs the prespecified matrix. It leaves the same record RUNNING for result analysis/finish. On an actual terminal interruption, inspect preserved checkpoint/optimizer/counters and partial evidence before deciding a specific recovery; an observation timeout is not a failure or restart trigger. The long-term frozen100k Slumbot criterion remains unchanged and unachieved.
