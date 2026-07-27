# RL-1 follow-up: autonomous diagnostic chain

Generated under the Autonomy Contract (see `CLAUDE.md`). All work below is
diagnostic / smoke-scale and does NOT promote any checkpoint.

## TL;DR
1. RL-1 5M postflop collapsed to ~75% check/call (vs BC anchor's ~50% raise/value-bet).
2. Slumbot regression confirmed: RL-1 5M −57.13 bb/100 vs BC anchor −42.84 (Δ −14.29, |Δ| < CI ±21.9 but consistent direction).
3. Root cause: critic cold-start. value_loss U-shape 703 → 1.2 → 1372 across the 100 iterations.
4. Value-head warmup is implementable and smoke-validated: 5.8× value_loss reduction with policy KL drift held to 0.116 nats (vs RL-1 iter-1 cold-start KL 1.75 — 15× lower).
5. **Need approval to run full RL-2 5M.**

## Artifacts
| Path | Purpose |
|:--|:--|
| `reports/rl1_5M_history_analysis.md` | Iteration-by-iteration value_loss / KL / mix evolution |
| `reports/rl1_vs_bc_diff.md` | Per-opponent, per-position, per-street action-mix shift |
| `scripts/alpha_holdem/phase2/analyze_rl1_history.py` | History parser |
| `scripts/alpha_holdem/phase2/compare_rl1_vs_bc.py` | BC ↔ RL-1 diff |
| `scripts/alpha_holdem/phase2/train_value_warmup.py` | Warmup implementation |
| `models/ppo/warm_critic_kl30_60ep_smoke/warmup.pt` | Smoke-warmed checkpoint |

## Diagnostic findings

### 1. Postflop action-mix collapse (averaged across 8 opponents)
| street | shift RL-1 − BC |
|:--|:--|
| FLOP | cc **+45.3 pp**, rS **−35.2 pp**, rM −7.1 |
| TURN | cc **+49.1 pp**, rS **−33.9 pp**, rM −11.6 |
| RIV | cc **+50.1 pp**, rS **−33.7 pp**, rM −9.8 |

RL-1 5M is a passive check/call bot postflop. It survives vs random/aggro/jammer/station because they fold less and inflate pots we win, but it loses 3–13 bb/100 at SB against realistic opponents (Slumbot, heuristic_v3, pathb10m, fold).

### 2. Value-loss trajectory (from `models/ppo/rl1_5M_run1/history.json`)
| iter | hands | value_loss | anchor_kl |
|---:|---:|---:|---:|
| 1 | 50k | **703.40** | **1.746** |
| 2 | 100k | 34.68 | 4.436 |
| 5 | 250k | 4.50 | 4.478 |
| 30 | 1.5M | 1.62 | 1.637 |
| 50 | 2.5M | 9.09 | 1.222 |
| 100 | 5M | **1372.40** | 1.440 |

The U-shape (703 → 1.2 → 1372) shows two failure modes:
- **Cold-start (iters 1–2)**: random critic → garbage advantages → CC collapsed to 0.08% within ONE iteration, never restored its raise mass.
- **Late-stage divergence (iters 50–100)**: critic re-explodes; advantage std climbs to 37.6 at iter 100 (worse than cold start).

### 3. CC collapse / recovery
- CC < 1% first seen at iter 2 (after 100k hands)
- CC > 5% recovered at iter 22 (after 1.1M hands)
- CC at iter 100: 29.3% (vs BC 22%) — recovered to anchor, but raise mass never came back.

## Value-head warmup smoke (implementation: `train_value_warmup.py`)

Approach: freeze `policy_head`, train `trunk + value_head` on bootstrapped GAE returns from 20k self-play hands, with `α · KL(current_policy || anchor_policy)` penalty in the loss to preserve the policy distribution while the trunk shifts to encode value information.

### Smoke matrix
| run | mode | policy_kl_coef | epochs | initial vloss | final vloss | reduction | policy KL drift |
|:--|:--|:--:|---:|---:|---:|:--:|---:|
| value_only | freeze trunk too | n/a | 30 | 157.1 | 147.7 | 1.06× | 0.000 (locked) |
| value_plus_trunk no KL | unfreeze trunk | 0 | 30 | 150.5 | 29.1 | 5.2× | **12.32** (catastrophic) |
| value_plus_trunk KL 1 | + KL pen | 1 | 30 | 148.6 | 28.1 | 5.3× | 1.012 |
| value_plus_trunk KL 10 | + KL pen | 10 | 30 | 156.3 | 30.1 | 5.2× | 0.296 |
| **value_plus_trunk KL 30 ×60ep** | + KL pen | 30 | **60** | 157.9 | **27.4** | **5.8×** | **0.116** |

Wall-clock: 69 s on RTX 4070 for the final 60-epoch run (3.5 s rollout + ~65 s training).

### Comparison to RL-1 cold start
| metric | RL-1 iter 1 | Warmed start (smoke) | improvement |
|:--|---:|---:|:--:|
| value_loss | 703 | 27 | **26× lower** |
| Implied adv.std (=√vloss) | 26.5 | 5.2 | **5× lower** |
| anchor_kl | 1.75 | 0.116 | **15× lower** |
| Implied explained variance | ≈ −3.5 | ≈ **0.82** | n/a |

### Sanity checks
- `policy_head.weight` max delta = 0.0 (frozen, verified)
- 99.97% of parameters trainable (only the 257 policy_head parameters frozen)
- Rollout returns: mean −1.07 BB, std 12.5, range ±128 (sane)

## Pass / fail gates

| gate | target | result | status |
|:--|:--|:--|:--:|
| value_loss reduction ≥ 5× | 5× | 5.8× | PASS |
| policy_head bit-exact unchanged | delta = 0 | delta = 0 | PASS |
| policy_kl_drift ≤ 0.5 nats | ≤ 0.5 | 0.116 | PASS |
| wall-clock ≤ 60 min | ≤ 60 m | 1.2 m | PASS |
| no destructive side-effect | n/a | new dirs only | PASS |

## Next autonomous step (no approval needed)
- None. All cheap diagnostic work is complete. The autonomy contract requires approval for the next stage.

## Approval requested

I want to run **RL-2 5M with warmed critic**, modifying the existing population-PPO trainer to optionally load a warmup checkpoint via `--warmup-ckpt`. Specifically:

1. Run `train_value_warmup.py` for the production-scale warmup: 100k hands, 60 epochs, kl_coef=30, lr=5e-4 (~5 min on the 4070).
2. Modify `train_population_ppo.py` to accept `--warmup-ckpt` which replaces the initial value_head + trunk weights while keeping policy_head from the BC anchor.
3. Start RL-2 5M training (same hyperparams as RL-1 5M run1 EXCEPT initial weights — opponent_mix unchanged at 5% proxy, lr 3e-5 unchanged, anchor_kl_coef 0.05 unchanged).
4. Stop and report at the 1M-hand checkpoint regardless of outcome.

Reasoning the contract requires approval:
- Total runtime is 5M hands at ~70 hands/s with eval = ~20 hours (exceeds 8h training and 5M-hand thresholds).
- Even though no hyperparameters change beyond initial-weights swap, the spirit of the contract is "ask before any multi-hour training".

If approved I will (a) generate the production warmup checkpoint, (b) wire `--warmup-ckpt` in PPO trainer, (c) launch background, (d) report at 1M-hand checkpoint and not promote anything until you say so.

If not approved I can instead:
- Try Option D adapter (separate value MLP between trunk and value_head) which would let policy_kl_drift go to 0 exactly.
- Try a different fix entirely (e.g. anchor regularization on raise slots specifically).
- Do nothing and wait for your direction.
