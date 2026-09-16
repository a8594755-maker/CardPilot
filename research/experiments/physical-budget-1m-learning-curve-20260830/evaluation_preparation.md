# Frozen evaluation preparation

Prepared while the original uninterrupted training wrapper PID10740 and trainer PID10056 are live. The evaluator waits for the original wrapper identity to terminate, then requires completed physical accounting and a PASS production audit. It never restarts training. While waiting it does not write the experiment record, preventing concurrent logger writers.

The original preregistration is unchanged: select first archive at or above262144 physical hands, first at or above524288, and final endpoint at or above1048576. Selection does not inspect rewards. Use seed20260893, anchors Standard10, Slumbot-free10M, correctedCFR96 in fixed order. Greedy2048 pairs and sampled4096 pairs for each of source/early/mid/final: total147456 internal environment evaluation hands. These are not Slumbot hands. Frozen copied checkpoint hashes, source snapshots, exact commands and raw pair evidence are retained.

Implementation validation completed before launch:

- `python -m pytest research/experiments/physical-budget-1m-learning-curve-20260830/test_evaluation_runner.py scripts/alpha_holdem/test_sampled_mirror_eval.py -q`:22passed.
- `python -m py_compile research/experiments/physical-budget-1m-learning-curve-20260830/run_evaluation.py`:passed.
- Read-only validation of the prior `sampled-policy-frozen-diagnostic-20260830/matrix/standard10.json` and corresponding execution document:24576 existing hands validated for raw completeness, sampled random-stream identity, finite bounded outcomes, seat-pair arithmetic and reported score. No hands were replayed or added to accounting.

The evaluation execution snapshot includes full source copies and SHA256 for the alpha_holdem modules and their deep_cfr game_state/hand_eval dependencies. These supplemental dependency bytes are captured before evaluation, not falsely represented as part of the earlier pre-training snapshot. No live trainer module is changed.

Internal admission is exploratory only: all three matched anchor point deltas positive and at least one nominal95% lower bound positive, with valid OOD evidence. This can only admit independent confirmation. Multiple checkpoints/modes do not establish general strength or satisfy the formal100k fresh Slumbot criterion.
