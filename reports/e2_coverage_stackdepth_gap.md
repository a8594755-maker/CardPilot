# E2 Coverage — 50bb CFR vs 200bb Teacher Stack-Depth Gap (2026-06-07)

Supervisor cycle (idle, E gated). Zero-compute data scan to size E2 (distill CFR policy vnet-v10
into the agent) BEFORE the user funds the gated build. Source: first 200k rows of
`data/phase2/teacher_v3_5M.jsonl` via `head` (no full 22GB read, no model, no Slumbot API).

## Scan (200k teacher decisions, heuristic_v3 teacher)
- street: pre 33% / flop 23% / turn 22% / river 22% (postflop-heavy).
- facing a bet (to_call>0): **4.9%** (mostly check/first-to-act lines — small SRP pots).
- **pot type:** SRP (pot_before ≤8bb) = **97.5%**; 3bet+ (>14bb) = **1.8%**. CFR action tree (SRP) MATCHES.
- **stack depth (the blocker):** normalized min-stack = 1.0 for **98.3%** of rows; >0.30 ("deep",
  >~60bb behind) = **98.9%**. Small SRP pots barely dent the 200bb stacks → decisions stay ~200bb deep
  across all four streets.
- teacher_action: F 29% / CC 47% / R-small 8% / R-mid 14% / jam 1.3% (matches the anchor manifest).

## Implication — E2 (CFR distill) is depth-capped, not pot-capped
- The pot-type abstraction is fine (97.5% SRP), so vnet-v10's tree fits. **But vnet-v10 is solved at
  50bb**, while **~99% of teacher decisions occur at ~200bb effective depth.** A 50bb CFR strategy is
  not valid at 200bb: stack-to-pot ratios, stack-off/all-in thresholds, and bet sizing all differ.
  Distilling it would inject 50bb-appropriate (too-eager-to-commit) choices into deep spots — i.e.
  HURT exactly the deep-stack regime where heuristic_v3 is already weakest vs Slumbot.
- **Every CFR asset we own is ≤100bb** (vnet-v10=50bb-SRP, vnet-v5=50bb-3bet, vnet-v3=100bb-SRP,
  vnet-v4=100bb-3bet). The target (Slumbot/teacher) is **200bb**. CFR can validly relabel only the
  shallow tail — **~2% of teacher decisions** (eff<1.0). That cannot move the -45 ceiling.

## Campaign bottom line — the cheap axis is EXHAUSTED; the gap is an ASSET-REGIME gap
Two cycles of zero-compute audits have now downgraded BOTH cheap E options:
- **E3 (re-BC, same teacher): DEAD** — BC already saturates heuristic_v3 (98.6% / L1-TV 0.0091).
- **E2 (distill any owned CFR net): ~2% coverage** — all CFR assets ≤100bb (50bb-native policy),
  teacher is 200bb. Wholesale relabel impossible; at best a narrow shallow-stack patch.

The root cause of the -45 ceiling is now precisely characterized: **target regime = 200bb deep-stack;
all strong (CFR) assets = ≤100bb.** Breaking -45 requires producing a strong **200bb-native** signal —
and every way to do that crosses a gate:
| path | what it needs | gate |
|---|---|---|
| **200bb CFR solve** (+EV export) → E1 critic and/or E2 distill at the right depth | fresh multi-day CFR solve at 200bb (we have none; raw solves ≤100bb, no EV) | >8h / expensive / direction |
| **Stronger 200bb teacher** (heuristic v4, or learned) → re-BC | real new teacher engineering; heuristics frozen by doctrine | direction change |
| **New RL idea** targeting per-decision discipline at depth (not PPO-from-BC, which is dead) | new algorithm + likely >5M run | >5M / direction |

There is **no remaining cheap/local path** that can move -45. The supervisor cannot proceed without
the user funding one gated investment.

## Budget / gates
- This cycle: **zero compute / zero API**, read-only `head` scan + report. No gate crossed; new
  artifact only. The three paths above are all user-gated (>8h / >5M / direction / artifact).

## ASK (sharpened, decisive)
The cheap axis is exhausted by data. To break -45 you must fund ONE of:
1. **200bb CFR solve** (most principled; enables both E1 critic-EV and a depth-correct E2). Expensive.
2. **Stronger 200bb teacher → re-BC** (build heuristic v4 or a learned 200bb teacher).
3. **New RL direction** at depth (fresh idea; PPO-from-BC is dead).
Recommend (1) if you want the highest-ceiling principled fix and can fund the solve; (2) for the
fastest plausible lift on the existing BC track. Holding until you pick.
