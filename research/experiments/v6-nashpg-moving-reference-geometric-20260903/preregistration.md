# Moving-reference geometric pilot preregistration

This is a NashPG-inspired local mechanism test, not a faithful reproduction of
the upstream repository or paper. It retains CardPilot's corrected physical-v6
legacy-v4 bridge, 25% current self-play, adaptive three-anchor learned league,
two-iteration complete-hand replay, Trinal-Clip PPO, and all-policy-head scope.

## Single intervention

All six runs start from the exact Standard10 checkpoint, use matched seeds and
fixed deal streams within seed, and use `KL(current || reference)` with
coefficient 1. The static arm keeps the initial reference. The moving arm copies
the post-update current policy into the reference after every complete trainer
PPO call. No other training setting changes between arms.

Three independent seeds each run to at least 65,536 actual environment hands.
Iteration-4 (about 16k) and final endpoints form the geometric curve. Dynamic
league consequences are part of the intervention, but all assignment evidence
must remain hash chained and independently replayable.

## Evidence and interpretation

Before strength analysis, every run must pass physical/transition accounting,
finite metric, optimizer synchronization, replay serialization, checkpoint
state/cadence, assignment independence, and changed-parameter-scope gates.

Frozen endpoints are evaluated on untouched common deals against Standard10,
CFR4, legacy iter16, and legacy mixed65k in both seats. We measure within-arm
16k-to-65k slopes and matched moving-minus-static deltas at both anchors. Final
policies also receive balanced outcome-blind Standard10 drift audits.

Promotion to roughly 262k is justified if the moving arm is mechanically sound,
has positive 16k-to-65k pooled slopes in at least two seeds with positive median,
does not show a reproducible both-seat/anchor collapse, and is directionally no
worse than the static-current-KL control in at least two seeds. Statistical
significance at 65k and positive absolute Slumbot bb/100 are not required.

Clear rejection requires a replicated mechanism failure, numerical instability,
catastrophic Standard10 drift (mean TV above 0.08 or greedy disagreement above
0.12), or reproducible proxy reversal across at least two seeds and both seats.
Mixed/noisy evidence with intact mechanics is labeled insufficient scale, not a
method rejection. No Slumbot calls are authorized by this preregistration.

