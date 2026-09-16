# Matched fresh-zero PPO KL-stop smoke

Registered after `v6-legacy-fresh-zero-elo-smoke-20260901` was closed and before
this treatment generates any hands.  The control completed34,238 physical hands
and learned decisively against its initial random actor, but its first update
had approx-KL1.0745/clip fraction0.6756 and paired transfer against untouched
Standard10 worsened -161.2130bb/100, CI95[-283.3524,-39.0736].  Scaling that
regimen was rejected.

## Single change and fixed execution

Change only `--ppo-target-kl` from0 to.01.  The implementation completes an
epoch, computes its mean approximate KL, and skips remaining epochs when the
mean is strictly above.01.  LR remains3e-4 and maximum PPO epochs remains4.
Every other trainer option, model architecture, environment/observation
contract, initial-policy ELO seed, worker/deal/learner/tournament seed, physical
budget and archive cadence is identical to the completed control.  No resume,
source weights, source loss, Slumbot feedback or control optimizer is used.

The exact initial model-state SHA must reproduce
`afcf8f7406cf4159e76f6c21ca5e83d7d59665559e7eb2a0a3937750e3cb1665`.
The full init checkpoint hash may differ because config metadata records the KL
target.  Training target32768 actual physical hands, checked at PPO boundaries.

Exact trainer command:

`python -u scripts/alpha_holdem/train_v5.py --device cuda --workers 12 --hands-per-iter 4096 --total-hands 99999999 --total-environment-hands 32768 --starting-stack 200 --env-version v6legacyv4obs --norm-layer bn --lr .0003 --ppo-epochs 4 --ppo-target-kl .01 --mini-batch-size 1024 --pool-strategy elo-kbest --k-best 3 --elo-seed-initial-policy --elo-tournament-pairs 64 --elo-k-factor 32 --elo-tournament-seed 2026120101 --elo-tournament-provenance-file research/experiments/v6-legacy-fresh-zero-kl-stop-smoke-20260901/training/elo_tournaments.jsonl --hero-policy-mode sample --self-play-fraction .25 --opponent-assignment per-group --opponent-groups 8 --opponent-assignment-provenance-file research/experiments/v6-legacy-fresh-zero-kl-stop-smoke-20260901/training/opponent_assignments.jsonl --rollout-mode single --rollout-envs-per-worker 1 --inference-min-batch-slots 0 --inference-batch-deadline-us 700 --worker-seed-base 2026120100 --fixed-training-deal-stream --critic-contract critic_v1 --value-coef .5 --snapshot-every 2 --save-interval 1 --archive-checkpoint-every 2 --run-id v6_legacy_fresh_zero_kl_stop_smoke_20260901 --run-dir research/experiments/v6-legacy-fresh-zero-kl-stop-smoke-20260901/training --out research/experiments/v6-legacy-fresh-zero-kl-stop-smoke-20260901/training/latest.pt --seed 20261201 --max-runtime-seconds 1800 --validate-stream`

## Evidence and gate

Require the same fail-closed ELO session audit: 8 expected updates unless the
physical boundary differs, initial pool id0, final K3, exact physical-v6 legacy
tournament contract, zero OOD, monotonic assignments/accounting, finite model
and optimizer, terminal manifest, and frozen init/final hashes.  Record actual
epochs and KL-stop activation every update.

Reuse the control's init-vs-Standard10 raw4096-pair evidence only after proving
the treatment init model state is bit-exact.  Evaluate treatment final-vs-init
and final-vs-Standard10 on the same fixed evaluation seeds/decks and greedy
exact legacy bridge,4096 mirrored pairs each.  Independent analysis must verify
raw hashes and compute paired treatment-final minus shared-init transfer.

Admit a same-run continuation toward262k only if all audits pass, the treatment
reduces maximum approx-KL and maximum clip fraction by at least50% versus the
control, final-vs-init 95% lower bound remains positive, and paired final-minus-
init against Standard10 is nonnegative in point estimate.  A negative paired
point stops this mechanism even if its interval crosses zero.  No Slumbot gate
is authorized by this smoke.
