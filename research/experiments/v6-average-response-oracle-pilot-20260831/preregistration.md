# Frozen-average approximate-response oracle pilot

Motivation: historical-average epoch12 completed20,000fresh Slumbot hands at
-70.40755bb/100, raw95%CI[-107.6049453916329,-33.21015460836711], session-t7
95%CI[-122.11631135789295,-18.69878864210704]. The complete evidence passed.
No extension, older-epoch rescue or100k confirmation is admitted.

The missing learning component is a response to an average opponent, not more
supervised epochs. NFSP distinguishes reinforcement-learned approximate responses
from supervised average-policy fitting (Heinrich and Silver,2016,sections2.3/3:
https://arxiv.org/html/1603.01121v2). This experiment qualifies ONE on-policy PPO
response oracle against ONE frozen average. It is NOT full NFSP, an exact best
response, a Nash-equilibrium computation, or proof of general poker strength.
There is no off-policy Q-learning, dynamic opponent substitution or average update.

Initialize all86network tensors from the exact completed epoch12 checkpoint:
cd7ce2b27cf3a86e96141432c92c6f92a3eb923dce519d1f1128af5acbb2364b.
The identical frozen checkpoint is the sole opponent for the entire experiment.
This is an explicitly NEW PPO experiment with fresh Adam and counters, NOT a
continuation/resume of supervised distillation. Its80-tensor SL optimizer, dataset,
reservoir and262144historical training-data hands remain preserved and are never
loaded, reset, overwritten or counted as new PPO hands. No legacy-v6 rebinding.

Use the qualified GPU multi8 native-v6 trainer:12workers,8slots/worker,fp32,
200bb,9legal actions,learned sampled policies only. All worker groups face the
same immutable average; self_play_fraction=0. Fixed-pool membership never changes,
so historical model-index pinning is not required. Adaptive weights over one
opponent are identically1 and only retain the qualified evidence machinery.
Train full network with Adam3e-5,PPO2epochs,targetKL.01,advantageclip3,global
advantage normalization,minibatch1024,entropy.005/floor.05,valuecoef1. Remove
the source-policy KL penalty (coefficient0) to test reward-driven response learning;
PPO's own trust-region control remains. No replay, teacher losses or action rules.

Target1048576NEW ACTUAL physical terminal hands, stopping at the first completed
update reaching it. Report overshoot and any shutdown tail separately. Seed20261013,
worker-seed-base2026101300,validate-stream,4096legacy rollout marker budget/update,
save every update,archive every4updates,maximum7200seconds as infrastructure cap.
No automatic restarts. Failed/incomplete attempts retain counters, manifests,
checkpoints, optimizer, assignment evidence and logs; they cannot silently rerun.

Before any evaluation choose exactly4checkpoints outcome-blind: initial average,
first archived checkpoint at or above262144actualhands, first at or above524288,
and the completed final. Only actual counters select archives, never filenames
or returns. Freeze them and all6opponents: the average plus existingv6anchors0..4.
Those anchor families are known, not novel unseen adversaries, but no anchor other
than the average is used for THIS training. No Slumbot data enter any training.

Then run all24fixed cells on4096NEW common full52-card deals, mirrored seats,
seed20261014,CPUfloat32sampletemperature1,maximum6evaluation children. Exactly
196608new internal hands. No internal partial-result peeking or cell selection.
Require all normal exits, unchanged checkpoint/runtime hashes,4096independently
regenerated unique decks matching every cell, full raw row accounting, exact
initial-average self-match zero and independent terminal arithmetic review.

Primary endpoint: final-minus-initial paired bb/100 versus the training average.
Its ordinary two-sided95%CI lower bound >0 admits a separate average-update /
multi-phase fictitious-self-play experiment, NOT a Slumbot qualification. Other
18candidate-minus-initial contrasts (3times x6opponents, including primary) are
reported with ordinary and family18Bonferroni intervals as diagnostics. Report
the known-anchor breadth separately; no endpoint/model is selected by these scores.
Failure of the primary gate means investigate response optimization before scaling.
No automatic external tests in this wrapper. Every valid result finishes the same
record, whether the primary gate passes or not.

Capture exact expanded commands, all executed code/patches, input SHA256s,
wall times, live actual-hand accounting and terminal session audit. Preserve all
prior experiment evidence. Root training/runtime sources are unchanged.

Exact launch after preparation tests:
python research/experiments/v6-average-response-oracle-pilot-20260831/run_pilot.py

Exact independent terminal review:
python research/experiments/v6-average-response-oracle-pilot-20260831/review_finish.py
