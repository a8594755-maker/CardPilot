# Fresh-zero physical-v6 ELO K-best smoke

Registered before the full regression gate and before any environment training
hands.  This is the first local test found that removes the inherited
Standard10 actor, source KL/margin objectives, head-only scope, and low learning
rate together while retaining the repaired 200bb physical rules and exact
legacy-v4 observation/action bridge used by the strongest external reference.
It is not a rerun of `elo-kbest-league-pilot-20260830`: that experiment resumed
an inherited actor and constrained only policy/value heads.

## Hypothesis and implementation gate

An exact physical-v6 ELO tournament plus an immutable initial-policy pool seed
will make a genuine AlphaHoldem-style fresh-zero, full-network historical league
possible without evaluating survivors under the obsolete float-v55 rules.
Before training, the exact-v6 evaluator must pass mirrored self-cancellation
under native and legacy observations, deterministic ordering/accounting tests,
mode restoration, environment bridge regression, py_compile, and the complete
AlphaHoldem pytest suite.  Any failure blocks training.

The initial random actor is inserted as snapshot id0 at hands0 before rollout.
This is not an external teacher: it only bootstraps a comparative first
tournament and gives the learner a frozen historical version.  The checkpoint,
candidate history, assignments and tournament JSONL must preserve that identity.

## Fixed smoke

Train from random initialization: no `--resume`, no imported optimizer/counter,
no source policy regularization, no action priors, and every model parameter
trainable.  Contract `v6legacyv4obs`, 200bb, BN, critic_v1, LR3e-4, four PPO
epochs, 4096 transition-bearing collection target per update, 32,768 actual
environment-hand target, twelve single-env GPU workers, minibatch1024, default
Trinal-Clip settings (delta1=3, entropy coefficient .05/floor .3), fixed deal
stream, learner seed20261201, worker base2026120100.  Historical league K=3,
25% contemporaneous self-play, balanced eight groups, snapshot every two
updates, deterministic exact-v6 greedy ELO with64 mirrored pairs per match,
save every update, archive every two.  Runtime guard1800seconds; never overwrite
or restart based on outcomes.

Exact trainer command:

`python -u scripts/alpha_holdem/train_v5.py --device cuda --workers 12 --hands-per-iter 4096 --total-hands 99999999 --total-environment-hands 32768 --starting-stack 200 --env-version v6legacyv4obs --norm-layer bn --lr .0003 --ppo-epochs 4 --mini-batch-size 1024 --pool-strategy elo-kbest --k-best 3 --elo-seed-initial-policy --elo-tournament-pairs 64 --elo-k-factor 32 --elo-tournament-seed 2026120101 --elo-tournament-provenance-file research/experiments/v6-legacy-fresh-zero-elo-smoke-20260901/training/elo_tournaments.jsonl --hero-policy-mode sample --self-play-fraction .25 --opponent-assignment per-group --opponent-groups 8 --opponent-assignment-provenance-file research/experiments/v6-legacy-fresh-zero-elo-smoke-20260901/training/opponent_assignments.jsonl --rollout-mode single --rollout-envs-per-worker 1 --inference-min-batch-slots 0 --inference-batch-deadline-us 700 --worker-seed-base 2026120100 --fixed-training-deal-stream --critic-contract critic_v1 --value-coef .5 --snapshot-every 2 --save-interval 1 --archive-checkpoint-every 2 --run-id v6_legacy_fresh_zero_elo_smoke_20260901 --run-dir research/experiments/v6-legacy-fresh-zero-elo-smoke-20260901/training --out research/experiments/v6-legacy-fresh-zero-elo-smoke-20260901/training/latest.pt --seed 20261201 --max-runtime-seconds 1800 --validate-stream`

## Evidence and decision

Require terminal manifest, monotonic physical and transition counts, contiguous
metrics/assignments, initial pool size1, final pool size3, exact tournament
contract label, zero OOD, archive/model/optimizer finiteness, and independent ELO
session audit.  Tournament hands are evaluation hands, never training hands.

After the terminal audit, freeze `init.pt`, first archive, and final checkpoint
by counter only.  Evaluate these fixed policies on new mirrored exact physical-v6
legacy-observation deals against the same immutable initial actor and exact
Standard10 tensors, without Slumbot feedback.  A continuation to about262k in
the same run is admitted only if all audits pass, the actor changes finitely,
the final policy beats the initial policy with a positive 95% lower bound, and
the final-minus-initial paired change against Standard10 is positive in point
estimate.  The latter CI may cross zero at smoke scale.  Otherwise stop this
fresh-zero regimen or revise its optimization mechanism.  No external Slumbot
allocation follows from this smoke alone.
