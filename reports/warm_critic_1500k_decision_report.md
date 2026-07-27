# Warm-Critic 1.5M Scale Test — Decision Report

Autopilot autonomous run, generated 2026-05-31. Halted at `ask_user_for_rl2_after_scale`.

## Decision rule outcome: **MIXED** (per user 2026-05-30 rule)

> If 2M improves or ties BC vs Slumbot within CI and keeps internal gains, then ask for full 5M.
> If 2M loses Slumbot badly or collapses action mix, do not continue; diagnose.
> If 2M is mixed, report position/street breakdown before asking for more compute.

Result: **Slumbot regression matches RL-1 5M, internal gains did NOT persist (some opponents better, some worse than BC). Reporting position/street breakdown below. NOT recommending full 5M with current setup.**

## Headline numbers

| metric | BC anchor | RL-1 5M | Warm 500k | Warm 1.5M |
|:--|---:|---:|---:|---:|
| Slumbot bb/100 (±21.9 CI) | **−42.84** | −57.13 | (not benched) | **−57.39** |
| Δ vs BC | — | −14.3 | — | **−14.6** |
| Mean Δ vs BC (7 realistic opp, excl random) | — | +3.3 | **+4.2** | **−3.2** |
| scripted_aggro (the 500k highlight) | +26.86 | +17.97 | **+47.10** | **−2.84** |

**Conclusion**: warm-critic 1.5M is statistically indistinguishable from RL-1 5M against Slumbot. The +4.2 bb/100 internal-suite gain from the 500k snapshot evaporated. The 1.5M policy is in a different basin from the 500k — passive, not aggressive.

## Per-iter trajectory: the basin transition

The 500k smoke captured a snapshot mid-evolution. 1.5M revealed what happens next:

| iter | hands | vloss | akl | mix (F/CC/R) | basin |
|---:|---:|---:|---:|:--|:--|
| 1 | 50k | 1117 | 1.60 | 40/46/14 | (warm start) |
| 5 | 250k | 322 | 3.04 | 57/06/37 | **aggressive** |
| 10 | 500k | 171 | 2.87 | **58/06/36** | aggressive (= 500k smoke endpoint) |
| 15 | 750k | 134 | 2.46 | 55/11/34 | aggressive |
| 17 | 850k | 158 | 1.93 | 52/29/19 | **TRANSITION** |
| 20 | 1.0M | 356 | 1.21 | 53/38/08 | passive |
| 25 | 1.25M | 279 | 1.22 | 55/33/12 | passive |
| 30 | 1.5M | 313 | 1.40 | **62/28/10** | passive (final) |

**The aggressive raise basin was transient.** Around iter 17 the anchor-KL pull dominated and yanked the policy back toward BC anchor's distribution. The final mix is closer to BC than to the 500k snapshot, but it didn't pick up BC's strategic discipline — just BC's shape.

`anchor_kl` dropped from 3.0+ to 1.2-1.4 — better than the warm 500k (2.6) but still 40× the PPO target (0.03).

## Slumbot bench (the decisive metric)

| candidate | bb/100 | CI |
|:--|---:|---:|
| BC anchor (re-bench) | −42.84 | ±21.9 |
| RL-1 5M | −57.13 | ±21.9 |
| **Warm-critic 1.5M** | **−57.39** | **±21.9** |
| Δ Warm-1.5M − BC | −14.55 | (consistent direction, within CI) |
| Δ Warm-1.5M − RL-1 | −0.26 | (essentially identical) |

The warm-critic 1.5M and RL-1 5M end up at the same Slumbot performance despite very different training trajectories. This suggests Slumbot exposes a deficiency that neither setup fixed: the cold-start critic mitigation alone is not the only blocker.

## Internal suite (per-opponent + position split)

| opp | BC | RL-1 5M | Warm 1.5M | Δ 1.5M−BC | SB Δ 1.5M−BC |
|:--|---:|---:|---:|---:|---:|
| fold | +8.99 | +4.71 | +3.42 | **−5.57** | −11.18 |
| call | +2.50 | +4.17 | +5.58 | +3.08 | −13.97 |
| random | +185.30 | +224.69 | +79.50 | −105.80 | (random is noise) |
| heuristic_v3 | +5.24 | +1.93 | +1.77 | −3.47 | −7.06 |
| scripted_aggro | +26.86 | +17.97 | **−2.84** | **−29.70** | −3.24 |
| scripted_station | +2.50 | +3.97 | +5.58 | +3.08 | −13.97 |
| scripted_jammer | +19.31 | +39.32 | +27.90 | +8.59 | +7.79 |
| pathb10m | +4.94 | +4.44 | +5.85 | +0.91 | +9.29 |

**Mean Δ vs BC (7 realistic opponents, excl random): −3.15 bb/100.** 
**Mean SB Δ vs BC: −4.6 bb/100** — the SB role regressed again, just like RL-1.

Specifically painful:
- vs scripted_aggro: dropped from +47.10 (warm 500k) → −2.84 (warm 1.5M). The aggressive-exploit win was a feature of the transient aggressive basin, not durable.
- vs fold: SB −43.50 vs BC −32.32 → 11 bb/100 worse. The bot is folding too much SB.

Where it's better than BC:
- vs scripted_jammer: +27.90 vs +19.31 (+8.6 bb/100). Passive cc beats jammer.
- vs pathb10m: SB −24.30 vs BC −33.59 (+9.3 bb/100 SB).

## Per-street action mix (final 1.5M)

| opp | PRE | FLOP | TURN | RIV |
|:--|:--|:--|:--|:--|
| fold | F94 C5 R1 | F0 C75 R25 | F0 C86 R14 | F0 C82 R18 |
| heuristic_v3 | F93 C5 R1 | F22 C66 R11 | F15 C68 R17 | F11 C66 R23 |
| **scripted_aggro** | F92 C6 R2 | F43 C43 R13 | F7 C54 R39 | F0 **C8** **R92** |
| pathb10m | F94 C5 R1 | F61 C35 R4 | F11 C86 R3 | F3 C94 R3 |

Versus the BC anchor's typical postflop "F~16 / CC~26 / R~50", the 1.5M warm-critic is **postflop call-heavy**, not raise-heavy. Only against scripted_aggro on the river does it become aggressive (because aggro has bet everything by then and the bot is forced to call/raise huge stakes).

This is essentially the **RL-1 failure mode** reasserting itself, just from a different starting point.

## Trainer-side hard stops
All passed (none tripped):
- fold > 92%: max was 0.62 (after iter 28)
- preflop allin > 15%: max was 0.00
- anchor_kl > 5: max was 3.65 (iter 2)
- vloss > 1000 sustained 3 iters after 500k: never (max sustained = 0 iters)
- cc < 3% sustained 3 iters: never (warm 1.5M kept cc >= 5% throughout)

## Diagnosis: why the basin transition?

The chain of events:
1. **Iter 1-2**: warmup-loaded policy starts at F=40/CC=46/R=14, then PPO pushes toward heuristic mix (F=47/CC=16/R=37) — the trainer "discovers" raises are profitable.
2. **Iter 3-15**: stable aggressive basin. Critic is noisy (vloss 100-400), but the policy is consistent.
3. **Iter 16-17**: anchor_kl pull starts dominating. Why now? At this point the data-driven anchor_kl_coef hasn't decayed yet (still 0.05), and the policy KL grew large enough (3.0+) that the 0.05 × KL penalty became significant relative to policy gradient.
4. **Iter 17-30**: policy drifts back toward BC anchor's softer mix. By iter 30, cc has recovered to BC-like levels (28%) but at the cost of raise mass (10% vs BC's 18%).

The warmup gave the critic a head-start, but it did NOT change the anchor-KL pull's long-run influence. Eventually the policy is dragged back to BC's neighborhood, and there it shows BC's Slumbot weaknesses without the discipline that made BC competitive in the first place.

## Recommendation (NOT promoting, NOT proposing 5M)

Per the user's decision rule, the mixed-Slumbot-bad result means **do not run 5M with this setup**. Two paths forward:

**Path A: Diagnose deeper before any more compute.**
- Run a value-loss-only smoke at the 1.5M checkpoint: did the critic ever learn the realistic-opponent return distribution, or is it still memorizing self-play returns?
- Run a per-opponent eval at iter 15 (the aggressive-basin peak): was the +47 vs aggro real, or just one good roll?
- Compare iter 15 policy_kl vs BC against iter 30 policy_kl vs BC to confirm the "anchor pull dominates after KL ~3" hypothesis.

**Path B: Try a structural change before any more 5M.**
- Disable anchor_kl after some warmup window (e.g. decay coef to 0 over 2M hands), letting the aggressive basin solidify.
- OR: warm the critic against the actual opponent mix, not self-play.
- OR: per-action anchor KL (only penalize raise-class drift, allow CC drift).

Both paths are diagnostic / smoke-level work that fits in the autonomy budget. Neither involves a 5M run.

## Runway state
- Experiments used: **3/3** (warmup + warm 500k + warm 1.5M)
- Runway active until 2026-05-31 02:16 — **already expired** at time of writing (2026-05-31 04:24)
- The chain completed before expiration; the ask_user_for_rl2_after_scale is the natural pause point.

## Autopilot state
- current_stage_id: `ask_user_for_rl2_after_scale`
- decisions: 12
- last decision: CONTINUE on warm_critic_1500k_slumbot_bench (passed gate)
- per-stage reports in `scripts/alpha_holdem/phase2/autopilot_runs/`

## Asking you

Per your decision rule the answer is "mixed → report position/street breakdown" (this report).

Three options for next:

1. **Stop and diagnose** (recommended). Run cheap diagnostics — value-loss-only training on existing checkpoint, mid-training eval at iter 15, per-action KL analysis. Under 1h compute total. No new runway needed.
2. **Try a structural change** (anchor-KL decay, opponent-mix warmup, per-action KL). Each is a small code change + new smoke. ~1-2h per smoke.
3. **Reject the warmup approach** and try a different RL setup (e.g. critic-only pretraining on existing CFR data, or different opponent mix).

I'm halted. No more autonomous runs until you direct.
