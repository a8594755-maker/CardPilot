# Matched fresh-zero LR1e-4 trust-region smoke

Registered after closing `v6-legacy-fresh-zero-kl-stop-smoke-20260901` and
before this run generates hands.  The LR3e-4 target-KL treatment significantly
improved Standard10 transfer relative to the no-stop control, but one PPO epoch
still reached KL1.3378 and clip fraction.8519.  Epoch-boundary stopping cannot
undo an oversized first epoch.

## Single change

Change only learner LR from3e-4 to1e-4.  Keep target-KL.01, maximum four epochs,
all environment/model/ELO/rollout/batch options, deterministic random
initialization, worker/deal/tournament/evaluation seeds and32768 physical-hand
budget identical to the completed KL-stop treatment.  No inherited weights,
resume, source constraint, Slumbot feedback or benchmark action rule.

The initial model-state must again equal
`afcf8f7406cf4159e76f6c21ca5e83d7d59665559e7eb2a0a3937750e3cb1665`.
The run uses the exact physical-v6 legacy-observation ELO evaluator and seeds
its historical pool with that immutable initial actor.

Exact command:

`python -u scripts/alpha_holdem/train_v5.py --device cuda --workers 12 --hands-per-iter 4096 --total-hands 99999999 --total-environment-hands 32768 --starting-stack 200 --env-version v6legacyv4obs --norm-layer bn --lr .0001 --ppo-epochs 4 --ppo-target-kl .01 --mini-batch-size 1024 --pool-strategy elo-kbest --k-best 3 --elo-seed-initial-policy --elo-tournament-pairs 64 --elo-k-factor 32 --elo-tournament-seed 2026120101 --elo-tournament-provenance-file research/experiments/v6-legacy-fresh-zero-lr1e4-smoke-20260901/training/elo_tournaments.jsonl --hero-policy-mode sample --self-play-fraction .25 --opponent-assignment per-group --opponent-groups 8 --opponent-assignment-provenance-file research/experiments/v6-legacy-fresh-zero-lr1e4-smoke-20260901/training/opponent_assignments.jsonl --rollout-mode single --rollout-envs-per-worker 1 --inference-min-batch-slots 0 --inference-batch-deadline-us 700 --worker-seed-base 2026120100 --fixed-training-deal-stream --critic-contract critic_v1 --value-coef .5 --snapshot-every 2 --save-interval 1 --archive-checkpoint-every 2 --run-id v6_legacy_fresh_zero_lr1e4_smoke_20260901 --run-dir research/experiments/v6-legacy-fresh-zero-lr1e4-smoke-20260901/training --out research/experiments/v6-legacy-fresh-zero-lr1e4-smoke-20260901/training/latest.pt --seed 20261201 --max-runtime-seconds 1800 --validate-stream`

## Gate

Require terminal exact ELO/session/accounting/hash/tensor/optimizer audits, zero
OOD, bit-exact shared init and complete epoch-stop evidence.  Freeze final before
evaluation.  Reuse the already-audited shared init-vs-Standard10 cell only after
state equality; run final-vs-init and final-vs-Standard10 at4096 mirrored pairs
with the same seeds/decks and compute paired deltas, including LR1e-4 versus the
LR3e-4 KL-stop final.

Admit an exact same-run continuation toward262144 physical hands only if maximum
approx-KL <=0.668909 and maximum clip fraction <=0.425929 (at least50% reductions
from the LR3e-4 treatment), final-vs-init 95% lower bound >0, paired final-minus-
shared-init Standard10 point >=0, and every audit passes.  Otherwise stop this
regimen.  No Slumbot allocation follows from the smoke alone.
