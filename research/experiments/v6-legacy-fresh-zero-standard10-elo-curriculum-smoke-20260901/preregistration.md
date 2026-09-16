# Fresh-zero Standard10-anchored ELO curriculum smoke

Registered after closing all three pure fresh-zero historical-league smokes and
before this run generates hands.  Pure self-history rapidly learned to dominate
its initial actor but transfer to untouched Standard10 ranged from uncertain to
decisively negative.  Optimizer stabilization alone did not prevent
non-transitive opponent overfitting.  Standard10 is the strongest mature
external reference under the historical greedy execution contract and has not
yet been tested as an opponent-only curriculum for a random-initialized,
full-network actor under the exact physical-v6 legacy bridge.

## Hypothesis and fixed intervention

Keep the main actor fresh random and fully trainable.  Add exact frozen
Standard10 tensors to the initial dynamic ELO pool alongside the exact frozen
random initial actor.  This is opponent experience only: no actor initialization,
source KL/margin, imitation target, heuristic action rule or Slumbot feedback.
K=5 ensures both initial strategies remain available through the first three
snapshot insertions; the terminal fourth tournament may prune one of six
competitors by exact mirrored ELO.

Use the best-transfer pure regimen as control basis: LR3e-4, target-KL.01,
maximum4 epochs, exact `v6legacyv4obs`, BN fresh hero/critic_v1, 12 workers,
4096 collection target, minibatch1024,25% contemporaneous self-play, balanced8
groups, fixed learner/worker/deal/tournament seeds, snapshot/archive every2,
32768 actual physical-hand target.  Only initial pool membership and K change.
Initial hero state SHA must remain
`afcf8f7406cf4159e76f6c21ca5e83d7d59665559e7eb2a0a3937750e3cb1665`;
Standard10 file SHA must remain
`91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428`.

Exact command:

`python -u scripts/alpha_holdem/train_v5.py --device cuda --workers 12 --hands-per-iter 4096 --total-hands 99999999 --total-environment-hands 32768 --starting-stack 200 --env-version v6legacyv4obs --norm-layer bn --lr .0003 --ppo-epochs 4 --ppo-target-kl .01 --mini-batch-size 1024 --pool-strategy elo-kbest --k-best 5 --initial-opponent-checkpoints models/baseline/standard10/latest.pt --elo-seed-initial-policy --elo-tournament-pairs 64 --elo-k-factor 32 --elo-tournament-seed 2026120101 --elo-tournament-provenance-file research/experiments/v6-legacy-fresh-zero-standard10-elo-curriculum-smoke-20260901/training/elo_tournaments.jsonl --hero-policy-mode sample --self-play-fraction .25 --opponent-assignment per-group --opponent-groups 8 --opponent-assignment-provenance-file research/experiments/v6-legacy-fresh-zero-standard10-elo-curriculum-smoke-20260901/training/opponent_assignments.jsonl --rollout-mode single --rollout-envs-per-worker 1 --inference-min-batch-slots 0 --inference-batch-deadline-us 700 --worker-seed-base 2026120100 --fixed-training-deal-stream --critic-contract critic_v1 --value-coef .5 --snapshot-every 2 --save-interval 1 --archive-checkpoint-every 2 --run-id v6_legacy_fresh_zero_standard10_elo_curriculum_smoke_20260901 --run-dir research/experiments/v6-legacy-fresh-zero-standard10-elo-curriculum-smoke-20260901/training --out research/experiments/v6-legacy-fresh-zero-standard10-elo-curriculum-smoke-20260901/training/latest.pt --seed 20261201 --max-runtime-seconds 1800 --validate-stream`

## Audits and breadth gate

Before launch require the mixed-seed implementation tests and full AlphaHoldem
suite.  Terminal evidence must show initial pool ids0(Standard10),1(initial
hero), final K5, four exact physical-v6 tournaments, zero OOD, monotonic
assignment/accounting, finite changed actor/optimizer and frozen hashes.  The
run is invalid for continuation if Standard10 id0 is absent from the terminal
pool, because the intended curriculum would disappear on resume.  KL must stay
<=1.5 and clip fraction<=.90.

Freeze final before any endpoint evaluation.  Evaluate exact greedy physical-v6
legacy-observation cross-play on4096 mirrored pairs each against:

1. Standard10 (training anchor; descriptive transfer),
2. no-stop pure fresh-zero final (untouched),
3. LR3e-4 KL-stop pure fresh-zero final (untouched),
4. LR1e-4 KL-stop pure fresh-zero final (untouched).

Use fixed seed20261210 plus anchor index*1000003, raw deck/seat evidence and
checkpoint hashes.  Admit a same-run continuation toward262144 physical hands
only if Standard10 id0 survives, all four candidate points are positive, at
least two 95% lower bounds are positive including at least one held-out pure
policy, and every health/evidence audit passes.  Otherwise close the regimen.
This internal breadth gate is not Slumbot qualification.
